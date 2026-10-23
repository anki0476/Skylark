import {AnnotatedText} from './AnnotatedText';
import {WorkflowExplainer} from './WorkflowExplainer';
import React, {useEffect, useLayoutEffect, useState, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {ArrowUpRight, ArrowLeft, ArrowRight, Play, Check, X, FlaskConical, Activity, GitCompareArrows, ChartNoAxesCombined, Settings, Download, RefreshCw, ShieldCheck, ChevronRight, CircleDot, Square, Wind, Info, Cloud, Cable} from 'lucide-react';
import experimentsFlask from './assets/experiments-flask.png';
import incidentPulse from './assets/incident-pulse.png';
import repairComparison from './assets/repair-comparison.png';
import resultsChart from './assets/results-chart.png';
import connectAgentIcon from './assets/connect-agent.png';
import aboutInfo from './assets/about-info.png';
import './style.css';
import {Landing} from './Landing';
import {CursorHelp} from './CursorHelp';
import {AboutWordmark} from './AboutWordmark';
import {SettingsSpotlightNav} from './SettingsSpotlightNav';
import {applyTheme,readTheme,type ThemePreference} from './theme';
import {api} from './api';
import {usePolling} from './polling';

type Verdict = {verdict:string; assertions:{name:string;passed:boolean;detail:string}[]; final?:{status:string;reservation_id?:string;explanation:string}; fault_triggered?:boolean; tool_calls?:number; elapsed_seconds?:number; evidence?:string};
type Run = {id:string;status:string;created:number;error?:string;result?:Verdict;state?:{reservations:Record<string,unknown>[]};snapshot:{verifier_version:string;spec:{mode:string;scenario:{name:string;fault:{kind:string}};policy:Record<string,unknown>}}};
type BenchmarkSummary = {id:string;created:number;mode:string;split:string;run_count:number;protocol_hash?:string};
type Event = {id:string;sequence:number;kind:string;payload:Record<string,any>};
type Repair = {id:string;approved:number;payload:{kind:string;before:Record<string,unknown>;after:Record<string,unknown>;explanation:string;provenance:string;limitation:string}};
type Status = {verifier_version?:string;queue:{queued:number;running:number};live:{enabled:boolean;reason?:string;model?:string;allowance_usd?:number};budget:{accounted_usd:number;uncertain_usd:number};scenarios:{kind:string;title:string;description:string;suggested_task_message?:string}[]};
const STALE_READ_FOLLOWUP='After creating the reservation, check availability again before reporting the booking outcome.';
const CURRENT_VERIFIER_VERSION='reservation/5';
const navHelp:Record<string,string>={Experiments:'Try a booking failure with the included sample agent.',Incident:'See what the agent observed, what actually happened, and which checks passed.', 'Repair comparison':'Review a targeted repair and compare original and repaired runs.',Results:'Find recent attempts and review evidence across experiments.','Connect agent':'Learn how to test a trusted local Python agent.'};
const settingsSections=['Connection & budget','Model Context Protocol','Experiment defaults','Appearance'] as const;
const saved={
 get:(key:string)=>{try{return localStorage.getItem(key)}catch{return null}},
 set:(key:string,value:string)=>{try{localStorage.setItem(key,value);return true}catch{return false}},
 remove:(key:string)=>{try{localStorage.removeItem(key);return true}catch{return false}},
};
const pretty = (text:string) => text.replaceAll('_',' ');
function Badge({text}:{text:string}){return <span className={'badge '+text}>{pretty(text)}</span>}
function NavIcon({src,fallback}:{src:string;fallback:React.ReactNode}){
 const [loaded,setLoaded]=useState(false);
 const [failed,setFailed]=useState(false);
 return <div className="nav-icon-slot" aria-hidden="true">
  {!loaded&&fallback}
  {!failed&&<img src={src} alt="" className={`nav-art-icon${loaded?' is-loaded':''}`} onLoad={()=>setLoaded(true)} onError={()=>{setLoaded(false);setFailed(true)}}/>}
 </div>;
}
function WorkspaceSwitcher(){
 const [open,setOpen]=useState(false);
 const root=useRef<HTMLDivElement>(null);
 const trigger=useRef<HTMLButtonElement>(null);
 useEffect(()=>{
  if(!open)return;
  const dismissOutside=(event:PointerEvent)=>{if(!root.current?.contains(event.target as Node))setOpen(false)};
  const dismissWithEscape=(event:KeyboardEvent)=>{if(event.key==='Escape'){setOpen(false);trigger.current?.focus()}};
  document.addEventListener('pointerdown',dismissOutside);
  document.addEventListener('keydown',dismissWithEscape);
  return()=>{document.removeEventListener('pointerdown',dismissOutside);document.removeEventListener('keydown',dismissWithEscape)};
 },[open]);
 return <div className="workspace-switcher" ref={root}>
  <button type="button" className="workspace" ref={trigger} aria-label="Switch workspace. Current: Local workspace" aria-expanded={open} aria-controls="workspace-options" onClick={()=>setOpen(value=>!value)}>
   <span className="workspace-avatar">S</span><span className="workspace-label">Local workspace</span><ChevronRight className={`workspace-chevron${open?' is-open':''}`} size={15}/>
  </button>
  {open&&<div id="workspace-options" className="workspace-menu" role="group" aria-label="Workspaces">
   <span className="workspace-menu-heading">WORKSPACES</span>
   <button type="button" className="workspace-option is-current" aria-current="true" onClick={()=>{setOpen(false);trigger.current?.focus()}}><span className="workspace-avatar">S</span><span>Local workspace</span><Check size={15} aria-hidden="true"/></button>
   <button type="button" className="workspace-option" disabled><Cloud size={17} aria-hidden="true"/><span>Cloud workspace</span><span className="workspace-coming-soon">Coming soon</span></button>
  </div>}
 </div>;
}
function App({theme,onThemeChange}:{theme:ThemePreference;onThemeChange:(value:ThemePreference)=>void}){
 const [status,setStatus]=useState<Status>(),[runs,setRuns]=useState<Run[]>([]),[events,setEvents]=useState<Event[]>([]),[repair,setRepair]=useState<Repair>(),[comparison,setComparison]=useState<{pairs:{before:string;after:string;trial:number}[]}>(),[report,setReport]=useState<any>();
 const [benchmarks,setBenchmarks]=useState<BenchmarkSummary[]>([]),[benchmarksUnavailable,setBenchmarksUnavailable]=useState(false),[resultScope,setResultScope]=useState(saved.get('skylark.resultScope')||''),[scopedRuns,setScopedRuns]=useState<Run[]>([]);
 const [navigation,setNavigation]=useState(()=>({entries:[{page:'Experiments',selected:saved.get('skylark.run')||''}],index:0}));
 const {page,selected}=navigation.entries[navigation.index];
 const setPage=(nextPage:string,incidentId?:string)=>setNavigation(current=>{
  const previous=current.entries[current.index];
  const next={page:nextPage,selected:incidentId??previous.selected};
  if(next.page===previous.page&&next.selected===previous.selected)return current;
  const entries=[...current.entries.slice(0,current.index+1),next];
  return {entries,index:entries.length-1};
 });
 const travel=(direction:number)=>setNavigation(current=>({...current,index:Math.max(0,Math.min(current.entries.length-1,current.index+direction))}));
 useLayoutEffect(()=>{
  window.scrollTo({top:0,behavior:'instant'});
 },[navigation.index,page,selected]);
 const [fault,setFault]=useState('timeout_after_commit'),[mode,setMode]=useState('fixture'),[resource,setResource]=useState(saved.get('skylark.defaultResource')||'studio-a'),[customer,setCustomer]=useState(saved.get('skylark.defaultCustomer')||'Alex'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[setup,setSetup]=useState(false),[repairKind,setRepairKind]=useState('runtime');
 const [settingsSection,setSettingsSection]=useState('Connection & budget');
 const [taskMessage,setTaskMessage]=useState('');
 const [defaultResource,setDefaultResource]=useState(saved.get('skylark.defaultResource')||'studio-a');
 const [defaultCustomer,setDefaultCustomer]=useState(saved.get('skylark.defaultCustomer')||'Alex');
 const [shine,setShine]=useState(saved.get('skylark.shine')!=='off');
 const [compact,setCompact]=useState(saved.get('skylark.compact')==='on');
 const [refreshSpin,setRefreshSpin]=useState(0);
 const [resultOrder,setResultOrder]=useState<'newest'|'oldest'>('newest');
 const savePreference=(key:string,value:string)=>{if(!saved.set('skylark.'+key,value))setError('Could not save preferences in this browser.')};
 const [inspected,setInspected]=useState<Run>();
 const [comparisonRuns,setComparisonRuns]=useState<Run[]>([]);
 const [comparisonTrials,setComparisonTrials]=useState(1);
 const startRequest=useRef<{fingerprint:string;key:string;body:string}|undefined>(undefined);
 const run=inspected?.id===selected?inspected:runs.find(r=>r.id===selected), active=Boolean(status?.queue?.queued||status?.queue?.running);
 const resultRuns=resultScope?scopedRuns:runs;
 const latestResult=[...resultRuns].sort((a,b)=>b.created-a.created||b.id.localeCompare(a.id))[0];
 const refresh=async(signal?:AbortSignal)=>{
  try{const [s,r]=await Promise.all([api('/status',{signal}),api('/runs',{signal})]);if(!signal?.aborted){setStatus(s);setRuns(r)}return s.queue.queued||s.queue.running?2000:10000}
  catch(e){if(!signal?.aborted)setError((e as Error).message);return 5000}
 };
 usePolling(refresh);
 useEffect(()=>{if(page!=='Results')return;const controller=new AbortController();api('/benchmarks',{signal:controller.signal}).then(items=>{if(!controller.signal.aborted){setBenchmarks(items);setBenchmarksUnavailable(false);setResultScope(current=>{if(current&&!items.some((item:BenchmarkSummary)=>item.id===current)){saved.remove('skylark.resultScope');return ''}return current})}}).catch(()=>{if(!controller.signal.aborted)setBenchmarksUnavailable(true)});return()=>controller.abort()},[page]);
 usePolling(async signal=>{
  if(page!=='Results')return false;
  try{const query=resultScope?`?comparison_id=${encodeURIComponent(resultScope)}`:'';const [summary,selectedRuns]=await Promise.all([api('/results'+query,{signal}),resultScope?api('/runs'+query,{signal}):Promise.resolve([])]);if(!signal.aborted){setReport(summary);setScopedRuns(selectedRuns)}}catch(e){if(!signal.aborted)setError((e as Error).message)}
  return active?2000:10000;
 },[page,resultScope]);
 useEffect(()=>{
  if(!selected||page!=='Incident')return;
  const controller=new AbortController();
  let cursor=0,pending=false,finished=false,timer:ReturnType<typeof setTimeout>|undefined;
  setEvents([]);setInspected(undefined);saved.set('skylark.run',selected);
  const merge=(items:Event[])=>{if(controller.signal.aborted)return;for(const item of items)cursor=Math.max(cursor,item.sequence);setEvents(old=>Array.from(new Map([...old,...items].map(item=>[item.id,item])).values()).sort((a,b)=>a.sequence-b.sequence))};
  const stream=new EventSource(`/api/v1/runs/${selected}/events?stream=true`);
  const poll=async()=>{
   if(controller.signal.aborted||pending||finished||document.hidden)return;
   clearTimeout(timer);pending=true;
   try{
    const [items,current]=await Promise.all([api(`/runs/${selected}/events?after=${cursor}`,{signal:controller.signal}),api(`/runs/${selected}`,{signal:controller.signal})]);
    if(!controller.signal.aborted){
     merge(items);setInspected(current);
     if(!['queued','running'].includes(current.status)){
      // Read once more after terminal status: completion may have raced the first read.
      merge(await api(`/runs/${selected}/events?after=${cursor}`,{signal:controller.signal}));
      finished=true;stream.close();void refresh();
     }
    }
   }catch(e){if(!controller.signal.aborted)setError((e as Error).message)}
   finally{pending=false;if(!controller.signal.aborted&&!finished)timer=setTimeout(()=>{void poll()},2000)}
  };
  void poll();
  stream.onmessage=e=>{try{merge([JSON.parse(e.data)])}catch{void poll()}};
  stream.onerror=()=>{void poll()};
  stream.addEventListener('done',()=>{stream.close();void poll()});
  const visible=()=>{if(!document.hidden)void poll()};
  document.addEventListener('visibilitychange',visible);
  return()=>{controller.abort();clearTimeout(timer);stream.close();document.removeEventListener('visibilitychange',visible)};
 },[selected,page]);
 useEffect(()=>{
  if(!setup)return;
  const previousBodyOverflow=document.body.style.overflow;
  const previousRootOverflow=document.documentElement.style.overflow;
  document.body.style.overflow='hidden';
  document.documentElement.style.overflow='hidden';
  const previous=document.activeElement as HTMLElement|null;
  const dialog=document.querySelector<HTMLElement>('[role="dialog"]');
  dialog?.querySelector<HTMLButtonElement>('button')?.focus();
  const keydown=(event:KeyboardEvent)=>{
   if(event.key==='Escape'){event.preventDefault();setSetup(false)}
   if(event.key==='Tab'&&dialog){const nodes=Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input,select,[tabindex="0"]'));const first=nodes[0],last=nodes[nodes.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}
  };
  document.addEventListener('keydown',keydown);return()=>{document.removeEventListener('keydown',keydown);document.body.style.overflow=previousBodyOverflow;document.documentElement.style.overflow=previousRootOverflow;previous?.focus()}
 },[setup]);
 useEffect(()=>{const repairId=saved.get('skylark.repair');if(repairId)api('/repairs/'+repairId).then(setRepair).catch(()=>{});const comparisonId=saved.get('skylark.comparison');if(comparisonId)api('/comparisons/'+comparisonId).then(x=>{setComparison(x.payload);setComparisonTrials(x.payload.pairs.length)}).catch(()=>{})},[]);
 usePolling(async signal=>{
  if(!comparison||page!=='Repair comparison')return false;
  try{
   const rows=await Promise.all(comparison.pairs.flatMap(pair=>[pair.before,pair.after]).map(id=>api('/runs/'+id,{signal})));
   if(!signal.aborted)setComparisonRuns(rows);
   return rows.some(row=>['queued','running'].includes(row.status))?2000:false;
  }catch(e){if(!signal.aborted)setError((e as Error).message);return 5000}
 },[comparison,page]);
 const action=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');try{await fn();await refresh()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const suggestedTask=(kind:string)=>status?.scenarios.find(s=>s.kind===kind)?.suggested_task_message||(kind==='stale_read'?STALE_READ_FOLLOWUP:'');
 const changeFault=(next:string)=>{const previous=suggestedTask(fault),suggested=suggestedTask(next);setTaskMessage(current=>current===previous&&previous?'':mode==='live'&&!current.trim()?suggested:current);setFault(next)};
 const changeMode=(next:string)=>{const suggested=suggestedTask(fault);setTaskMessage(current=>next==='fixture'&&current===suggested?'':next==='live'&&!current.trim()?suggested:current);setMode(next)};
 const start=()=>action(async()=>{
  const customTask=mode==='live'?taskMessage.trim():'';
  const presetTask=customTask&&customTask===suggestedTask(fault);
  const fingerprint=JSON.stringify({mode,fault,resource,customer,customTask});
  if(startRequest.current?.fingerprint!==fingerprint){
   const scenario=status?.scenarios.find(s=>s.kind===fault);
   startRequest.current={fingerprint,key:crypto.randomUUID(),body:JSON.stringify({mode,scenario:{name:customTask&&!presetTask?`Custom booking request · ${scenario?.title}`:scenario?.title,task_message:customTask,resource,customer,intent_id:'intent-'+crypto.randomUUID(),fault:{kind:fault}}})};
  }
  const pending=startRequest.current!;
  const result=await api('/runs',{method:'POST',headers:{'Idempotency-Key':pending.key},body:pending.body});
  startRequest.current=undefined;setPage('Incident',result.id);
 });
 const diagnose=()=>action(async()=>{const result=await api(`/runs/${selected}/repairs`,{method:'POST',body:JSON.stringify({kind:run?.snapshot.spec.mode==='live'?repairKind:'runtime'})});setRepair(result);setComparison(undefined);saved.remove('skylark.comparison');saved.set('skylark.repair',result.id);setPage('Repair comparison')});
 const compare=()=>action(async()=>{if(!repair)return;const approved=await api(`/repairs/${repair.id}/approve`,{method:'POST'});setRepair(approved);const result=await api('/comparisons',{method:'POST',body:JSON.stringify({repair_id:repair.id,trials:comparisonTrials})});setComparison(result);saved.set('skylark.comparison',result.id)});
 const nav=[{name:'Experiments',image:experimentsFlask,fallback:<FlaskConical size={18}/>},{name:'Incident',image:incidentPulse,fallback:<Activity size={18}/>},{name:'Repair comparison',image:repairComparison,fallback:<GitCompareArrows size={18}/>},{name:'Results',image:resultsChart,fallback:<ChartNoAxesCombined size={18}/>},{name:'Connect agent',image:connectAgentIcon,fallback:<Cable size={18}/>},{name:'About',image:aboutInfo,fallback:<Info size={18}/>}];
 return <div className={`shell${shine?'':' no-shine'}${compact?' compact-tables':''}`}><aside className="sidebar" inert={setup}><a className="brand" href="#"><span className="brand-wordmark">skylark</span><span className="beta">LABS</span></a><nav>{nav.map(({name,image,fallback})=><button key={name} aria-label={name} title={navHelp[name]?undefined:name} className={page===name?'nav active':'nav'} onClick={()=>setPage(name)}>{image?<NavIcon src={image} fallback={fallback}/>:<div className="nav-icon-slot" aria-hidden="true">{fallback}</div>}{navHelp[name]?<CursorHelp title={name} description={navHelp[name]}>{name}</CursorHelp>:<span>{name}</span>}</button>)}</nav><div className="sidebar-bottom"><WorkspaceSwitcher/><button aria-label="Settings" title="Settings" className="nav" onClick={()=>setSetup(true)}><Settings size={17}/>Settings<ArrowUpRight size={15}/></button></div></aside>
 <main inert={setup}><header>{navigation.entries.length>1&&<div className="history-controls" role="group" aria-label="Page history">{navigation.index>0&&<button aria-label="Go back" title="Back" onClick={()=>travel(-1)}><ArrowLeft size={17}/></button>}{navigation.index<navigation.entries.length-1&&<button aria-label="Go forward" title="Forward" onClick={()=>travel(1)}><ArrowRight size={17}/></button>}</div>}<nav className="breadcrumb" aria-label="Location"><ol><li><button onClick={()=>setPage('Experiments')}>Workspace</button></li><li aria-hidden="true"><ChevronRight size={14}/></li>{page==='Incident'&&<><li><button onClick={()=>setPage('Experiments')}>Experiments</button></li><li aria-hidden="true"><ChevronRight size={14}/></li></>}<li aria-current="page"><strong title={page==='Incident'&&run?`${run.snapshot.spec.scenario.name} · ${run.id}`:page}>{page==='Incident'&&run?`Incident · ${run.snapshot.spec.scenario.name} · ${run.id.slice(0,8)}`:page}</strong></li></ol></nav></header><div className="content">
 {error&&<div className="error" role="alert"><Info size={18}/>{error}<button aria-label="Dismiss error" onClick={()=>setError('')}><X size={16}/></button></div>}
 {page==='Experiments'&&<><div className="experiments-heading"><PageTitle title="Experiments"/><button className="primary pop-button compact-connect" onClick={()=>setPage('Connect agent')}>Connect my agent<ArrowRight size={15}/></button></div>
 <div className="metric-strip"><div><small>ENVIRONMENT</small><strong><ShieldCheck size={17}/>Local sandbox</strong></div><div><small>SAMPLE AGENT MODEL</small><strong>{status?.live.enabled?status.live.model:'Scripted · no model needed'}<button aria-label="Connection and budget" onClick={()=>{setSettingsSection('Connection & budget');setSetup(true)}}><ArrowUpRight size={15}/></button></strong></div><div><small>API USAGE</small><strong>${status?.budget.accounted_usd.toFixed(4)||'0.0000'}<span>USD</span></strong></div></div>
 <section id="sample-experiment" className="sample-experiment"><div className="section-title"><div><h2>Try the sample booking failure</h2><p>Choose a failure. Skylark checks what the sample agent actually does.</p></div></div>
 <div className="configure sample-configure"><div className="configure-fields"><label>How to run<select value={mode} onChange={e=>changeMode(e.target.value)}><option value="fixture">Scripted evaluation · $0 API cost</option><option value="live" disabled={!status?.live.enabled}>Model evaluation · API cost applies{!status?.live.enabled?' · connect Nebius first':''}</option></select></label><label>Failure to test<select value={fault} onChange={e=>changeFault(e.target.value)}>{status?.scenarios.map(s=><option key={s.kind} value={s.kind}>{s.title}</option>)}</select></label></div>
 <div className="sample-task-summary"><p><strong>Practice booking:</strong> The sample agent will try to book {resource==='studio-a'?'Studio A':resource||'a place'} for {customer||'a customer'}. No real booking is made.</p><details className="sample-details"><summary>Change the booking details</summary><div className="sample-detail-fields"><label>Place to book<input aria-label="Place to book" aria-describedby="resource-hint" value={resource} onChange={e=>setResource(e.target.value)} maxLength={40}/><small id="resource-hint" className="field-hint">Name of the practice place.</small></label><label>Name for the booking<input aria-label="Name for the booking" aria-describedby="customer-hint" value={customer} onChange={e=>setCustomer(e.target.value)} maxLength={80}/><small id="customer-hint" className="field-hint">Use your name or any name you like.{mode==='live'?' Model tests send it to Nebius.':''}</small></label></div></details></div>
 {mode==='live'&&<section className="task-prompt-panel"><div className="section-title"><h2>Optional guidance for the sample agent</h2><span className="pill">MODEL EVALUATION ONLY</span></div><p className="task-prompt-note">The failure is selected above. Add instructions for the built-in booking agent here; this box does not connect your own agent.</p><textarea id="task-message" aria-label="Optional guidance for the sample agent" value={taskMessage} onChange={e=>setTaskMessage(e.target.value)} maxLength={1000} rows={4} placeholder="For this booking, check what happened if the confirmation does not arrive before trying again."/></section>}
 <div className="launch sample-launch"><div className="sample-fault-preview"><strong>What goes wrong</strong><p>{status?.scenarios.find(s=>s.kind===fault)?.description}</p></div><button className="primary pop-button" disabled={busy||active||(mode==='live'&&!status?.live.enabled)} onClick={start}><Play size={15}/>{busy?'Starting…':mode==='fixture'?'Run sample test':'Run fresh evaluation'}<ArrowRight size={16}/></button></div></div></section>
 <div className="section-title"><div><h2>Recent experiments <span className="count">{runs.length}</span></h2></div><button className="text-button" onClick={()=>{setRefreshSpin(value=>value+1);void refresh()}}><RefreshCw key={refreshSpin} size={14} className={refreshSpin?'refresh-spin-once':undefined}/>Refresh</button></div><RunTable runs={runs} open={id=>{setPage('Incident',id)}}/>
 </>}
 {page==='Incident'&&<><PageTitle title="Incident"/>{!run?<Empty text="Run an experiment to inspect its timeline."/>:<><div className="run-heading"><div><h2>{run.snapshot.spec.scenario.name}</h2><code>{run.id.slice(0,12)}</code><Badge text={run.snapshot.spec.mode}/></div><div className="actions"><Badge text={run.result?.verdict||run.status}/><span className="run-verifier">verifier {run.snapshot.verifier_version}</span>{['queued','running'].includes(run.status)?<button className="secondary" onClick={()=>action(async()=>{await api(`/runs/${selected}/cancel`,{method:'POST'})})}><Square size={14}/>Cancel</button>:<a className="secondary" href={`/api/v1/runs/${selected}/bundle`}><Download size={15}/>Export incident</a>}</div></div>{run.error&&<div className="notice">{run.error}</div>}{run.snapshot.verifier_version!==(status?.verifier_version||CURRENT_VERIFIER_VERSION)&&<div className="notice">This recorded verdict uses verifier {run.snapshot.verifier_version}. {status?.verifier_version?`The running server uses ${status.verifier_version} and may score this claim differently.`:`Local code has ${CURRENT_VERIFIER_VERSION}; restart the server before treating its checks as active.`} The original evidence is preserved.</div>}<div className="assertions">{run.result?.assertions.map(a=><div key={a.name} className={'assertion '+(a.passed?'pass':'fail')}><div>{a.passed?<Check size={17}/>:<X size={17}/>}<strong>{pretty(a.name)}</strong></div><details className="check-detail"><summary>Details</summary><p>{a.detail}</p></details></div>)}</div><div className="incident-grid"><section className="panel"><div className="panel-heading"><h2>Execution timeline</h2><span className="pill">{events.length} EVENTS</span></div><div className="timeline">{events.map(e=><article key={e.id} className={'event '+(e.payload.fault?'fault':'')}><div className="event-dot"><CircleDot size={14}/></div><div className="event-heading"><span>{String(e.sequence).padStart(2,'0')}</span><strong>{e.payload.fault?'Fault delivered':pretty(e.kind)}</strong>{e.payload.name&&<code>{e.payload.name}</code>}</div>{['tool_observed','agent_observed'].includes(e.kind)?<><div className="observation"><small>{e.kind==='agent_observed'?'DELIVERED TO AGENT':'TOOL RESPONSE · BEFORE SAFEGUARDS'}</small><details open={Boolean(e.payload.fault)}><summary>Response</summary><pre>{JSON.stringify(e.payload.result,null,2)}</pre></details></div>{e.payload.fault&&<div className="truth"><small>AUTHORITATIVE OUTCOME · NOT SHOWN TO AGENT</small><pre>{JSON.stringify(e.payload.authoritative_result,null,2)}</pre></div>}</>:<details><summary>Inspect event</summary><pre>{JSON.stringify(e.payload,null,2)}</pre></details>}</article>)}</div></section><aside className="incident-aside"><section className="panel"><h3>Actual reservations</h3>{run.state?.reservations?.length?run.state.reservations.map((r,i)=><div className="reservation" key={i}><strong>{String(r.id)}</strong><span>{String(r.customer)} → {String(r.resource)}</span></div>):<p className="muted">No reservations recorded.</p>}<hr/><h3>Agent's final claim</h3><p className="claim-status">{pretty(run.result?.final?.status||'awaiting completion')}</p>{run.result?.final?.reservation_id&&<code>{run.result.final.reservation_id}</code>}<details><summary>Full claim</summary><pre>{JSON.stringify(run.result?.final||{status:'awaiting completion'},null,2)}</pre></details></section><section className="repair-callout"><h3>Let Skylark test a fix</h3>{run.result?.fault_triggered&&run.snapshot.spec.mode!=='local_adapter'?<><p>Skylark can prepare a change for this test agent and check whether it helps. Your original run stays unchanged.</p>{run.snapshot.spec.mode==='live'&&<><label className="sr-only" htmlFor="repair-kind">Repair type</label><select id="repair-kind" value={repairKind} onChange={e=>setRepairKind(e.target.value)}><option value="runtime">Runtime safeguards</option><option value="prompt">Prompt guidance</option></select></>}<button className="primary pop-button" disabled={busy||!['completed','failed'].includes(run.status)} onClick={diagnose}>{busy?'Preparing…':'Find a fix'}<ArrowRight size={15}/></button></>:<p>{['queued','running'].includes(run.status)?'Waiting for the test result before looking for a fix.':run.snapshot.spec.mode==='local_adapter'?'This run used a local adapter. Use the adapter repair comparison command from Connect agent to test a reservation safeguard. It will not change your live agent.':run.snapshot.spec.scenario.fault.kind==='none'?'This was a control run with no failure to fix. Choose a failure in Experiments to test a repair.':'The selected failure was not reached in this run, so there is no verified fix to test yet.'}</p>}</section></aside></div></> }</>}
 {page==='Repair comparison'&&<><PageTitle title="Repair comparison"/>{!repair?<Empty text="Open a completed incident and propose a repair."/>:<><p className="repair-summary">{repair.payload.explanation}</p><details className="repair-technical"><summary>See technical changes</summary><div className="diff-grid"><section className="panel"><small>ORIGINAL CONFIGURATION</small><Configuration values={repair.payload.before}/></section><section className="panel green-panel"><small>PROPOSED {repair.payload.kind.toUpperCase()} REPAIR</small><Configuration values={repair.payload.after}/></section></div></details><div className="launch"><p>Testing this fix creates a local comparison; it does not change your live agent. {repair.payload.limitation}<br/>Source: {pretty(repair.payload.provenance)}.</p><div className="comparison-launch-controls"><label>Trials per version<select aria-label="Trials per version" value={comparisonTrials} onChange={e=>setComparisonTrials(Number(e.target.value))}><option value={1}>1 trial</option><option value={2}>2 trials</option><option value={3}>3 trials</option></select></label><button className="primary pop-button" disabled={busy||active} onClick={compare}><Check size={16}/>{repair.approved?'Test this fix again':'Test this fix'}</button></div></div>{comparison&&<><div className="section-title"><h2>Comparison evidence</h2><span className="pill">{comparison.pairs.length} {comparison.pairs.length===1?'TRIAL':'TRIALS'} PER VERSION</span></div>{comparison.pairs.map(pair=><div className="diff-grid" key={pair.trial}>{(['before','after'] as const).map(side=>{const r=comparisonRuns.find(x=>x.id===pair[side])||runs.find(x=>x.id===pair[side]);const calls=r?.result?.tool_calls;return <section className="panel" key={side}><small>{side==='before'?'ORIGINAL':'REPAIRED'}</small><h2>{r?.result?.verdict?pretty(r.result.verdict):r?.status||'queued'}</h2><Badge text={r?.snapshot.spec.mode||'fixture'}/><p>{calls??'—'} {calls===1?'tool call':'tool calls'} · {r?.result?.elapsed_seconds?.toFixed(2)||'—'} seconds</p><button className="text-button" onClick={()=>{setPage('Incident',pair[side])}}>Inspect evidence<ArrowRight size={14}/></button></section>})}</div>)}</>}</>}</>}
 {page==='Results'&&<><PageTitle title="Results"/>{benchmarksUnavailable&&<div className="notice">Saved benchmark scopes are unavailable from this server. Restart Skylark to load the updated Results view.</div>}{benchmarks.length>0&&<div className="results-scope"><label htmlFor="results-scope-select">Result scope<select id="results-scope-select" value={resultScope} onChange={e=>{const value=e.target.value;setResultScope(value);if(value)saved.set('skylark.resultScope',value);else saved.remove('skylark.resultScope');setReport(undefined);setScopedRuns([])}}><option value="">All project results</option>{benchmarks.map(item=><option key={item.id} value={item.id}>{pretty(item.split)} · {item.mode} · {item.run_count} runs · {new Date(item.created*1000).toLocaleDateString()} · {item.id.slice(0,8)}</option>)}</select></label>{resultScope&&<p>Showing one saved benchmark protocol. Verdicts and unknowns remain in its original denominator.</p>}</div>}
 {latestResult&&<section className="panel latest-result"><div><small>LATEST ATTEMPT IN THIS VIEW</small><h2>{latestResult.snapshot.spec.scenario.name}</h2><p>{new Date(latestResult.created*1000).toLocaleString([],{dateStyle:'medium',timeStyle:'medium'})} · {pretty(latestResult.snapshot.spec.mode)} · {pretty(latestResult.result?.verdict||latestResult.status)}</p></div><button className="secondary" onClick={()=>setPage('Incident',latestResult.id)}>Open incident<ArrowRight size={15}/></button></section>}
 <div className="section-title results-attempts-title"><div><h2>{resultScope?'Protocol attempts':'Recent attempts'}</h2><p>Each row is one run. The outcome summary below combines runs by condition.</p></div><label>Sort attempts<select aria-label="Sort attempts" value={resultOrder} onChange={e=>setResultOrder(e.target.value as 'newest'|'oldest')}><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select></label></div>{resultScope&&!report?<p className="muted">Loading protocol attempts…</p>:<RunTable runs={resultRuns} order={resultOrder} open={id=>{setPage('Incident',id)}}/>}<ResultsView report={report} scope={resultScope}/></>}
 {page==='Connect agent'&&<ConnectAgent onTrySample={()=>{setPage('Experiments');requestAnimationFrame(()=>document.getElementById('sample-experiment')?.scrollIntoView({behavior:'smooth',block:'start'}))}}/>}
 {page==='About'&&<About/>}<footer><span><Wind size={15}/>SKYLARK · LOCAL BETA</span></footer></div></main>
 {setup&&<div className="modal-backdrop" onClick={()=>setSetup(false)}><section className="modal settings-modal" role="dialog" aria-modal="true" aria-label="Settings" onClick={e=>e.stopPropagation()}><button className="close" aria-label="Close settings" onClick={()=>setSetup(false)}><X/></button><div className="settings-layout"><aside className="settings-sidebar"><h2>Settings</h2><SettingsSpotlightNav items={settingsSections} active={settingsSection} onSelect={setSettingsSection}/></aside><div className="settings-main"><div className="settings-main-inner">{settingsSection==='Connection & budget'&&<section><h3>Connection & budget</h3><p>A Nebius connection runs Skylark's included sample model; it does not connect your own agent. Live calls use credits. Scripted tests work without it.</p><div className="notice">{status?.live.enabled?'Live execution enabled.':status?.live.reason}</div><h4>Where to enter these settings</h4><p>This browser cannot change server credentials. In the PowerShell window used to start Skylark, stop the server, set the variables below, and start it again. A different PowerShell window will not update an already-running server.</p><pre>Get-Content .env.example{ '\n' }$secret = Read-Host 'Nebius API key' -AsSecureString{ '\n' }$env:NEBIUS_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password{ '\n' }Remove-Variable secret</pre><p>Then set <code>NEBIUS_MODEL</code>, both model price variables, <code>SKYLARK_CONFIRMED_CREDITS_USD</code>, <code>SKYLARK_ALLOWANCE_USD</code>, and <code>SKYLARK_LIVE_ENABLED=1</code> in that same window. Use verified values from your account and <code>Get-Content .env.example</code> for the full list. Keep your API key out of chat, files, and screenshots.</p><p className="muted">Check credits and expiry; disable automatic top-ups. Set the allowance within 60% of confirmed credits.{status?.live.enabled&&status.live.allowance_usd!==undefined?` Current allowance: $${status.live.allowance_usd.toFixed(2)}.`:''}</p></section>}
{settingsSection==='Experiment defaults'&&<section className="settings-fields"><h3>Experiment defaults</h3><p>Saved in this browser. Applied when Skylark reloads.</p><label>Default resource<input value={defaultResource} maxLength={40} onChange={e=>{setDefaultResource(e.target.value);savePreference('defaultResource',e.target.value)}}/></label><label>Default customer<input value={defaultCustomer} maxLength={80} onChange={e=>{setDefaultCustomer(e.target.value);savePreference('defaultCustomer',e.target.value)}}/></label><p>Live execution always requires an explicit selection.</p></section>}
{settingsSection==='Model Context Protocol'&&<section className="settings-fields"><h3>Model Context Protocol</h3><p className="notice"><Info size={16}/>Not available in this build</p><dl className="configuration-list"><div><dt>Connected servers</dt><dd>None</dd></div><div><dt>Tool integration</dt><dd>Local Python adapter</dd></div></dl><p>MCP server connections are not implemented yet. Skylark currently instruments tools through its local Python adapter.</p></section>}
{settingsSection==='Appearance'&&<section className="settings-fields"><h3>Appearance</h3><label><span>Theme</span><select aria-label="Theme" value={theme} onChange={e=>onThemeChange(e.target.value as ThemePreference)}><option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option></select></label><label className="preference-toggle"><span>Animated wordmark</span><input type="checkbox" checked={shine} onChange={e=>{setShine(e.target.checked);savePreference('shine',e.target.checked?'on':'off')}}/></label><label className="preference-toggle"><span>Compact experiment tables</span><input type="checkbox" checked={compact} onChange={e=>{setCompact(e.target.checked);savePreference('compact',e.target.checked?'on':'off')}}/></label><p>Reduced-motion system preferences are always respected.</p></section>}
<button className="primary settings-done" onClick={()=>setSetup(false)}>Done<ArrowRight size={16}/></button></div></div></div></section></div>}
 </div>
}
function Configuration({values}:{values:Record<string,unknown>}){return <dl className="configuration-list">{Object.entries(values).map(([key,value])=><div key={key}><dt>{pretty(key)}</dt><dd>{typeof value==='boolean'?(value?'On':'Off'):typeof value==='string'?value:JSON.stringify(value)}</dd></div>)}</dl>}
function PageTitle({title}:{title:string}){return <div className="page-title"><h1><AnnotatedText variant={title==='About Skylark'?'doubleUnderline':'dottedUnderline'}>{title}</AnnotatedText></h1></div>}
function ConnectAgent({onTrySample}:{onTrySample:()=>void}){return <><PageTitle title="Connect agent"/>
 <section className="connect-intro panel"><span className="start-path-label">NO AGENT? START HERE</span><h2>See a fix in action</h2><p>Run a sample failure and test its fix. No real booking or API key.</p><button className="primary pop-button" onClick={onTrySample}>Try the sample<ArrowRight size={16}/></button></section>
 <section className="connect-guide panel"><h2>Have your own agent?</h2><p>Today Skylark connects trusted local Python code. n8n, Make, and hosted agents need connectors we have not built yet. Use a test copy and test credentials; Skylark does not deploy changes to your live agent.</p>
 <details className="connect-detail"><summary>Connect and test an agent: step by step</summary><ol className="adapter-steps">
  <li><strong>Check the connection</strong><p>From the Skylark folder, run the included local agent:</p><pre>.\.venv\Scripts\python.exe -m skylark adapter examples/cautious_adapter.py</pre><p>Look for <code>local_adapter_reported</code>, <code>fault_triggered: true</code>, and a verdict.</p></li>
  <li><strong>Connect your agent</strong><p>A developer wraps trusted Python code with <code>Adapter.run</code>, records relevant actions with <code>context.call</code>, and adds an independent outcome check. <a className="text-button" href="https://github.com/anki0476/Skylark#connect-a-local-agent" target="_blank" rel="noreferrer">Read the adapter guide<ArrowUpRight size={15}/></a></p></li>
  <li><strong>Test a repair</strong><p>Try the included training agent that retries a failed-looking booking:</p><pre>.\.venv\Scripts\python.exe -m skylark adapter examples/unsafe_retry_adapter.py --compare-repair</pre><p>Expect <code>failed</code> with two reservations before, then <code>passed</code> with one after. The same agent code runs twice; Skylark tests a reservation safeguard in the sandbox.</p></li>
 </ol><p>The CLI prints each result. Use the same <code>--data</code> directory as the server to see these runs in the browser. To test your own reservation agent, route its actions through <code>context.call</code>, then replace the file path. Direct calls outside that context are not sandboxed or verified. Other tasks need their own environment, verifier, and repair logic.</p></details>
 <details className="connect-detail"><summary>Why can't I just upload my agent?</summary><p>Skylark must see its actions and verify the real outcome. An upload alone cannot prove a fix worked, and running unknown code in the browser is unsafe. Today, use the trusted local Python adapter.</p></details></section></>}
function About(){return <><PageTitle title="About Skylark"/><div className="about-content">
<section><h2>Test agent recovery</h2><p>Run an experiment, inspect what the agent observed alongside the actual outcome, review a repair, and compare results. The supplied reservation application uses synthetic data; no real bookings are made.</p></section>
<WorkflowExplainer/>
<section><h2>Faults and controls</h2><dl><dt>Timeout after commit</dt><dd>The reservation succeeds, but the response times out. An unsafe retry can create a duplicate.</dd><dt>Stale read</dt><dd>A read returns an earlier snapshot instead of the current state.</dd><dt>Incomplete response</dt><dd>The operation completes, but its response is missing a required field.</dd><dt>Controls</dt><dd>Fault-free and timeout-before-commit runs distinguish normal behavior from ambiguous failures.</dd></dl></section>
<section><h2>Evidence modes</h2><dl><dt>Scripted fixture</dt><dd>A deterministic demo that tests Skylark itself. No inference credits are used. This is not evidence of model reliability.</dd><dt>Fresh model evaluation</dt><dd>New Nebius calls against a fresh sandbox. Repeated trials are needed to assess reliability.</dd><dt>Deterministic regression</dt><dd>Recorded decisions replayed against the sandbox to test the harness or a supported runtime change. This is not fresh model evidence.</dd><dt>Recorded playback</dt><dd>Inspection of existing traces only, with no new inference or evidence.</dd></dl></section>
<section><h2>Reading results</h2><p>Execution status and verdict are separate: an experiment can finish successfully while the agent fails its task.</p><dl><dt>Safety</dt><dd>No duplicates, wrong reservations, or capacity violations.</dd><dt>Completion</dt><dd>The intended reservation exists.</dd><dt>Accurate report</dt><dd>The agent’s structured final claim agrees with authoritative state.</dd><dt>Fault reached</dt><dd>The configured fault actually triggered. Untriggered faults do not establish recovery.</dd></dl><p>Safe but incomplete is not a full pass. Missing evidence is inconclusive. Infrastructure failures, unknown checks, latency, and usage are reported separately. Small trial counts do not establish universal reliability.</p></section>
<section><h2>Repairs and comparisons</h2><p>Review the proposed change and its limitations before approval. Approval creates a new version and preserves the original incident. Compare controls and held-out cases as well as the original failure.</p><p>Runtime safeguards and prompt repairs are different interventions. A safeguard preventing duplicates does not show that the model learned recovery. Fixture comparisons establish harness behavior only. The interface schedules one trial per version.</p></section>
<section><h2>Local execution and privacy</h2><p>Trusted adapter code runs locally. Only instrumented calls are covered. Process separation is not a security sandbox for hostile code. Authoritative state is available to the verifier, not the agent.</p><p>Live runs send task and tool messages to Nebius. Keep credentials in the local environment and out of traces, exports, and public repositories. Review evidence before sharing it.</p></section>
<section><h2>Connection and spending</h2><p>Connection & budget lists the required environment variables. Set them locally and restart Skylark. Scripted fixtures need no key.</p><p>Verify credited balance, expiry, model prices, and disabled automatic top-ups in your provider account. Keep the initial capability experiment within $2 of confirmed credits. Skylark does not provision GPU compute.</p><p>Usage figures are local estimates, not your provider balance. Accounted usage and reserved or unconfirmed charges are separate. Unknown charges remain reserved until reconciled. App limits are not a provider-enforced billing guarantee.</p></section>
<section><h2>Export and reproduce</h2><p>Export an incident for its evidence bundle and regression test, or download results JSON for analysis. Preserve model settings, scenario versions, and fault schedules when comparing runs. Redaction or missing evidence can prevent exact reproduction.</p><p>Skylark is a local controlled beta. Multi-user hosting and production capacity have not been validated.</p></section>
</div><AboutWordmark/></>}

function Empty({text}:{text:string}){return <div className="empty"><FlaskConical size={28}/><h3>No evidence yet</h3><p>{text}</p></div>}
function ResultsView({report,scope}:{report:any;scope:string}){
 const dimensions=[['safety','Safety'],['task_completion','Completion'],['reporting_accuracy','Accurate report'],['fault_coverage','Fault reached']];
 const scopedCost=report?.groups?.reduce((total:number,group:any)=>total+group.accounted_usd,0)??0;
 return <><div className="section-title"><h2>Outcome dimensions</h2><a className="secondary" href={'/api/v1/results/export'+(scope?`?comparison_id=${encodeURIComponent(scope)}`:'')}><Download size={15}/>Export results JSON</a></div>
 {!report?<p className="muted">Loading results…</p>:!report.groups.length?<Empty text="Run an experiment to collect measured results."/>:report.groups.map((g:any)=><section className="panel result-group" key={g.id}>
 <div className="result-heading"><div><h3>{g.condition==='none'?'Fault-free control':pretty(g.condition)} · {pretty(g.configuration)}</h3><p>{g.model.id} · {g.split} · verifier {g.verifier_version}</p></div><Badge text={g.mode}/></div>
 <div className="assertions">{dimensions.map(([key,label])=>{const metric=g.dimensions[key];return <div className="assertion" key={key}><strong>{label}</strong><p>{metric.not_applicable===g.total?'Fault-free control':<><b>{metric.passed}/{metric.observed}</b> checks passed</>}</p>{(metric.unknown>0||metric.failed>0)&&<p>{[metric.unknown>0&&`${metric.unknown} unknown`,metric.failed>0&&`${metric.failed} failed`].filter(Boolean).join(' · ')}</p>}</div>})}</div>
 <p className="result-counts">{g.total} attempts · {g.passed} passed{g.failed>0&&` · ${g.failed} failed`}{g.safe_incomplete>0&&` · ${g.safe_incomplete} incomplete`}{g.inconclusive>0&&` · ${g.inconclusive} inconclusive`}{g.pending>0&&` · ${g.pending} pending`}</p>
 <p>Median {g.latency_seconds.median?.toFixed(2)??'—'} s · {g.tool_calls.median??'—'} tool calls · ${g.accounted_usd.toFixed(4)} accounted · ${g.uncertain_usd.toFixed(4)} uncertain</p>
 <details><summary>Execution details</summary><pre>{JSON.stringify({unique_scenarios:g.unique_scenarios,execution:g.execution_statuses,dimensions:g.dimensions,input_tokens:g.input_tokens,output_tokens:g.output_tokens,provider_requests:g.provider_requests},null,2)}</pre></details>
 </section>)}<div className="panel budget-panel"><h2>Usage & uncertainty</h2>{scope&&<p><strong>${scopedCost.toFixed(4)}</strong> accounted in this protocol</p>}<p><strong>${report?.budget.accounted_usd.toFixed(4)||'0.0000'}</strong> accounted across the whole project · <strong>${report?.budget.uncertain_usd.toFixed(4)||'0.0000'}</strong> reserved or unconfirmed across the whole project</p><p className="muted">Local estimates · not provider balance.</p></div></>
}
function RunTable({runs,open,order='newest'}:{runs:Run[];open:(id:string)=>void;order?:'newest'|'oldest'}){const sorted=[...runs].sort((a,b)=>(order==='newest'?b.created-a.created:a.created-b.created)||a.id.localeCompare(b.id));return sorted.length?<div className="table-wrap"><table><thead><tr><th>Experiment</th><th>Started</th><th>Evidence</th><th>Execution</th><th>Verdict</th><th/></tr></thead><tbody>{sorted.map(r=><tr key={r.id}><td><button className="run-name" onClick={()=>open(r.id)}>{r.snapshot.spec.scenario.name}<small>{r.id.slice(0,8)}</small></button></td><td><time dateTime={new Date(r.created*1000).toISOString()}>{new Date(r.created*1000).toLocaleString([],{dateStyle:'medium',timeStyle:'medium'})}</time></td><td><Badge text={r.snapshot.spec.mode}/></td><td>{pretty(r.status)}</td><td><Badge text={r.result?.verdict||(['queued','running'].includes(r.status)?'pending':'inconclusive')}/></td><td><button aria-label={'Open incident '+r.id.slice(0,8)} className="icon-button" onClick={()=>open(r.id)}><ArrowUpRight size={17}/></button></td></tr>)}</tbody></table></div>:<Empty text="Choose a scenario above to create your first experiment."/>}
function Root(){
 const [theme,setTheme]=useState<ThemePreference>(readTheme);
 const [inApp,setInApp]=useState(location.hash.startsWith('#/app'));
 useEffect(()=>{const update=()=>setInApp(location.hash.startsWith('#/app'));window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update)},[]);
 useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const update=()=>applyTheme(theme);update();media.addEventListener('change',update);return()=>media.removeEventListener('change',update)},[theme]);
 useEffect(()=>{const sync=(event:StorageEvent)=>{if(event.key==='skylark.theme'||event.key===null)setTheme(readTheme())};window.addEventListener('storage',sync);return()=>window.removeEventListener('storage',sync)},[]);
 const changeTheme=(value:ThemePreference)=>{setTheme(value);applyTheme(value);try{localStorage.setItem('skylark.theme',value)}catch{/* Keep the chosen theme for this session if storage is unavailable. */}};
 return inApp?<App theme={theme} onThemeChange={changeTheme}/>:<Landing/>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><Root/></React.StrictMode>);
