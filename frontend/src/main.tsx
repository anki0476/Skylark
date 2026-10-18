import React, {useEffect, useState, useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {ArrowUpRight, ArrowLeft, ArrowRight, Play, Check, X, FlaskConical, Activity, GitCompareArrows, ChartNoAxesCombined, Settings, Download, RefreshCw, ShieldCheck, ChevronRight, CircleDot, Square, Wind, Info} from 'lucide-react';
import './style.css';
import {Landing} from './Landing';
import {CursorHelp} from './CursorHelp';
import {AboutWordmark} from './AboutWordmark';
import {applyTheme,readTheme,type ThemePreference} from './theme';
import {api} from './api';
import {usePolling} from './polling';

type Verdict = {verdict:string; assertions:{name:string;passed:boolean;detail:string}[]; final?:{status:string;reservation_id?:string;explanation:string}; tool_calls?:number; elapsed_seconds?:number; evidence?:string};
type Run = {id:string;status:string;created:number;error?:string;result?:Verdict;state?:{reservations:Record<string,unknown>[]};snapshot:{spec:{mode:string;scenario:{name:string;fault:{kind:string}};policy:Record<string,unknown>}}};
type Event = {id:string;sequence:number;kind:string;payload:Record<string,any>};
type Repair = {id:string;approved:number;payload:{kind:string;before:Record<string,unknown>;after:Record<string,unknown>;explanation:string;provenance:string;limitation:string}};
type Status = {queue:{queued:number;running:number};live:{enabled:boolean;reason?:string;model?:string;allowance_usd?:number};budget:{accounted_usd:number;uncertain_usd:number};scenarios:{kind:string;title:string;description:string}[]};
const navHelp:Record<string,string>={Experiments:'Choose a scenario, inject a tool failure, and run your agent.',Incident:'See what the agent observed, what actually happened, and which checks passed.', 'Repair comparison':'Review a targeted repair and compare original and repaired runs.',Results:'Review safety, completion, reporting accuracy, and usage across experiments.'};
const pretty = (text:string) => text.replaceAll('_',' ');
function Badge({text}:{text:string}){return <span className={'badge '+text}>{pretty(text)}</span>}
function App({theme,onThemeChange}:{theme:ThemePreference;onThemeChange:(value:ThemePreference)=>void}){
 const [status,setStatus]=useState<Status>(),[runs,setRuns]=useState<Run[]>([]),[events,setEvents]=useState<Event[]>([]),[repair,setRepair]=useState<Repair>(),[comparison,setComparison]=useState<{pairs:{before:string;after:string;trial:number}[]}>(),[report,setReport]=useState<any>();
 const [navigation,setNavigation]=useState(()=>({entries:[{page:'Experiments',selected:localStorage.getItem('skylark.run')||''}],index:0}));
 const {page,selected}=navigation.entries[navigation.index];
 const setPage=(nextPage:string,incidentId?:string)=>setNavigation(current=>{
  const previous=current.entries[current.index];
  const next={page:nextPage,selected:incidentId??previous.selected};
  if(next.page===previous.page&&next.selected===previous.selected)return current;
  const entries=[...current.entries.slice(0,current.index+1),next];
  return {entries,index:entries.length-1};
 });
 const travel=(direction:number)=>setNavigation(current=>({...current,index:Math.max(0,Math.min(current.entries.length-1,current.index+direction))}));
 const [fault,setFault]=useState('timeout_after_commit'),[mode,setMode]=useState('fixture'),[resource,setResource]=useState(localStorage.getItem('skylark.defaultResource')||'studio-a'),[customer,setCustomer]=useState(localStorage.getItem('skylark.defaultCustomer')||'Alex'),[busy,setBusy]=useState(false),[error,setError]=useState(''),[setup,setSetup]=useState(false),[repairKind,setRepairKind]=useState('runtime');
 const [settingsSection,setSettingsSection]=useState('Connection & budget');
 const [defaultResource,setDefaultResource]=useState(localStorage.getItem('skylark.defaultResource')||'studio-a');
 const [defaultCustomer,setDefaultCustomer]=useState(localStorage.getItem('skylark.defaultCustomer')||'Alex');
 const [shine,setShine]=useState(localStorage.getItem('skylark.shine')!=='off');
 const [compact,setCompact]=useState(localStorage.getItem('skylark.compact')==='on');
 const savePreference=(key:string,value:string)=>{try{localStorage.setItem('skylark.'+key,value)}catch{setError('Could not save preferences in this browser.')}};
 const [inspected,setInspected]=useState<Run>();
 const [comparisonRuns,setComparisonRuns]=useState<Run[]>([]);
 const startRequest=useRef<{fingerprint:string;key:string;body:string}|undefined>(undefined);
 const run=inspected?.id===selected?inspected:runs.find(r=>r.id===selected), active=Boolean(status?.queue?.queued||status?.queue?.running);
 const refresh=async(signal?:AbortSignal)=>{
  try{const [s,r]=await Promise.all([api('/status',{signal}),api('/runs',{signal})]);if(!signal?.aborted){setStatus(s);setRuns(r)}return s.queue.queued||s.queue.running?2000:10000}
  catch(e){if(!signal?.aborted)setError((e as Error).message);return 5000}
 };
 usePolling(refresh);
 usePolling(async signal=>{
  if(page!=='Results')return false;
  try{const summary=await api('/results',{signal});if(!signal.aborted)setReport(summary)}catch(e){if(!signal.aborted)setError((e as Error).message)}
  return active?2000:10000;
 },[page]);
 useEffect(()=>{
  if(!selected||page!=='Incident')return;
  const controller=new AbortController();
  let cursor=0,pending=false,finished=false,timer:ReturnType<typeof setTimeout>|undefined;
  setEvents([]);setInspected(undefined);localStorage.setItem('skylark.run',selected);
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
  const previous=document.activeElement as HTMLElement|null;
  const dialog=document.querySelector<HTMLElement>('[role="dialog"]');
  dialog?.querySelector<HTMLButtonElement>('button')?.focus();
  const keydown=(event:KeyboardEvent)=>{
   if(event.key==='Escape'){event.preventDefault();setSetup(false)}
   if(event.key==='Tab'&&dialog){const nodes=Array.from(dialog.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],input,select,[tabindex="0"]'));const first=nodes[0],last=nodes[nodes.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}
  };
  document.addEventListener('keydown',keydown);return()=>{document.removeEventListener('keydown',keydown);previous?.focus()}
 },[setup]);
 useEffect(()=>{const saved=localStorage.getItem('skylark.repair');if(saved)api('/repairs/'+saved).then(setRepair).catch(()=>{});const c=localStorage.getItem('skylark.comparison');if(c)api('/comparisons/'+c).then(x=>setComparison(x.payload)).catch(()=>{})},[]);
 usePolling(async signal=>{
  if(!comparison||page!=='Repair comparison')return false;
  try{
   const rows=await Promise.all(comparison.pairs.flatMap(pair=>[pair.before,pair.after]).map(id=>api('/runs/'+id,{signal})));
   if(!signal.aborted)setComparisonRuns(rows);
   return rows.some(row=>['queued','running'].includes(row.status))?2000:false;
  }catch(e){if(!signal.aborted)setError((e as Error).message);return 5000}
 },[comparison,page]);
 const action=async(fn:()=>Promise<void>)=>{setBusy(true);setError('');try{await fn();await refresh()}catch(e){setError((e as Error).message)}finally{setBusy(false)}};
 const start=()=>action(async()=>{
  const fingerprint=JSON.stringify({mode,fault,resource,customer});
  if(startRequest.current?.fingerprint!==fingerprint){
   const scenario=status?.scenarios.find(s=>s.kind===fault);
   startRequest.current={fingerprint,key:crypto.randomUUID(),body:JSON.stringify({mode,scenario:{name:scenario?.title,resource,customer,intent_id:'intent-'+crypto.randomUUID(),fault:{kind:fault}}})};
  }
  const pending=startRequest.current!;
  const result=await api('/runs',{method:'POST',headers:{'Idempotency-Key':pending.key},body:pending.body});
  startRequest.current=undefined;setPage('Incident',result.id);
 });
 const diagnose=()=>action(async()=>{const result=await api(`/runs/${selected}/repairs`,{method:'POST',body:JSON.stringify({kind:repairKind})});setRepair(result);setComparison(undefined);localStorage.removeItem('skylark.comparison');localStorage.setItem('skylark.repair',result.id);setPage('Repair comparison')});
 const compare=()=>action(async()=>{if(!repair)return;const approved=await api(`/repairs/${repair.id}/approve`,{method:'POST'});setRepair(approved);const result=await api('/comparisons',{method:'POST',body:JSON.stringify({repair_id:repair.id,trials:1})});setComparison(result);localStorage.setItem('skylark.comparison',result.id)});
 const nav=[{name:'Experiments',icon:FlaskConical},{name:'Incident',icon:Activity},{name:'Repair comparison',icon:GitCompareArrows},{name:'Results',icon:ChartNoAxesCombined},{name:'About',icon:Info}];
 return <div className={`shell${shine?'':' no-shine'}${compact?' compact-tables':''}`}><aside className="sidebar" inert={setup}><a className="brand" href="#"><span className="brand-wordmark">skylark</span><span className="beta">LABS</span></a><nav>{nav.map(({name,icon:Icon})=><button key={name} aria-label={name} title={navHelp[name]?undefined:name} className={page===name?'nav active':'nav'} onClick={()=>setPage(name)}><Icon size={18}/>{navHelp[name]?<CursorHelp title={name} description={navHelp[name]}>{name}</CursorHelp>:<span>{name}</span>}</button>)}</nav><div className="sidebar-bottom"><div className="workspace"><span className="workspace-avatar">S</span><div>Local workspace</div><ChevronRight size={15}/></div><button aria-label="Settings" title="Settings" className="nav" onClick={()=>setSetup(true)}><Settings size={17}/>Settings<ArrowUpRight size={15}/></button></div></aside>
 <main inert={setup}><header>{navigation.entries.length>1&&<div className="history-controls" role="group" aria-label="Page history">{navigation.index>0&&<button aria-label="Go back" title="Back" onClick={()=>travel(-1)}><ArrowLeft size={17}/></button>}{navigation.index<navigation.entries.length-1&&<button aria-label="Go forward" title="Forward" onClick={()=>travel(1)}><ArrowRight size={17}/></button>}</div>}<nav className="breadcrumb" aria-label="Location"><ol><li><button onClick={()=>setPage('Experiments')}>Workspace</button></li><li aria-hidden="true"><ChevronRight size={14}/></li>{page==='Incident'&&<><li><button onClick={()=>setPage('Experiments')}>Experiments</button></li><li aria-hidden="true"><ChevronRight size={14}/></li></>}<li aria-current="page"><strong title={page==='Incident'&&run?`${run.snapshot.spec.scenario.name} · ${run.id}`:page}>{page==='Incident'&&run?`Incident · ${run.snapshot.spec.scenario.name} · ${run.id.slice(0,8)}`:page}</strong></li></ol></nav></header><div className="content">
 {error&&<div className="error" role="alert"><Info size={18}/>{error}<button aria-label="Dismiss error" onClick={()=>setError('')}><X size={16}/></button></div>}
 {page==='Experiments'&&<><PageTitle title="Experiments"/>
 <div className="metric-strip"><div><small>ENVIRONMENT</small><strong><ShieldCheck size={17}/>Local sandbox</strong></div><div><small>MODEL</small><strong>{status?.live.enabled?status.live.model:'Not connected'}<button aria-label="Connection and budget" onClick={()=>{setSettingsSection('Connection & budget');setSetup(true)}}><ArrowUpRight size={15}/></button></strong></div><div><small>API USAGE</small><strong>${status?.budget.accounted_usd.toFixed(4)||'0.0000'}<span>USD</span></strong></div></div>
 <div className="section-title"><div><h2>Choose a fault</h2></div></div>
 <div className="scenario-grid">{status?.scenarios.slice(0,3).map((s,i)=><button key={s.kind} className={'scenario '+(fault===s.kind?'selected':'')} onClick={()=>setFault(s.kind)}><div className="scenario-top"><span className="scenario-number">0{i+1}</span><span className="radio">{fault===s.kind&&<Check size={12}/>}</span></div><h3>{s.title}</h3><span className="scenario-link">{pretty(s.kind)}<ArrowUpRight size={15}/></span></button>)}</div>
 <div className="configure"><div className="configure-fields"><label>Execution mode<select value={mode} onChange={e=>setMode(e.target.value)}><option value="fixture">Scripted fixture · $0 API cost</option><option value="live" disabled={!status?.live.enabled}>Fresh model evaluation{!status?.live.enabled?' · connect Nebius first':''}</option></select></label><label>Scenario<select value={fault} onChange={e=>setFault(e.target.value)}>{status?.scenarios.map(s=><option key={s.kind} value={s.kind}>{s.title}</option>)}</select></label><label>Resource<input value={resource} onChange={e=>setResource(e.target.value)} maxLength={40}/></label><label>Customer<input value={customer} onChange={e=>setCustomer(e.target.value)} maxLength={80}/></label></div><div className="launch"><p><Info size={15}/>{mode==='fixture'?'Scripted demo · no live-model evidence.':`Uses Nebius credits · allowance $${status?.live.allowance_usd}.`}</p><button className="primary pop-button" disabled={busy||active||(mode==='live'&&!status?.live.enabled)} onClick={start}><Play size={15}/>{busy?'Starting…':mode==='fixture'?'Run fixture':'Run fresh evaluation'}<ArrowRight size={16}/></button></div></div>
 <div className="section-title"><div><h2>Recent experiments <span className="count">{runs.length}</span></h2></div><button className="text-button" onClick={()=>{void refresh()}}><RefreshCw size={14}/>Refresh</button></div><RunTable runs={runs} open={id=>{setPage('Incident',id)}}/>
 </>}
 {page==='Incident'&&<><PageTitle title="Incident"/>{!run?<Empty text="Run an experiment to inspect its timeline."/>:<><div className="run-heading"><div><h2>{run.snapshot.spec.scenario.name}</h2><code>{run.id.slice(0,12)}</code><Badge text={run.snapshot.spec.mode}/></div><div className="actions"><Badge text={run.result?.verdict||run.status}/>{['queued','running'].includes(run.status)?<button className="secondary" onClick={()=>action(async()=>{await api(`/runs/${selected}/cancel`,{method:'POST'})})}><Square size={14}/>Cancel</button>:<a className="secondary" href={`/api/v1/runs/${selected}/bundle`}><Download size={15}/>Export incident</a>}</div></div>{run.error&&<div className="notice">{run.error}</div>}<div className="assertions">{run.result?.assertions.map(a=><div key={a.name} className={'assertion '+(a.passed?'pass':'fail')}><div>{a.passed?<Check size={17}/>:<X size={17}/>}<strong>{pretty(a.name)}</strong></div><details className="check-detail"><summary>Details</summary><p>{a.detail}</p></details></div>)}</div><div className="incident-grid"><section className="panel"><div className="panel-heading"><h2>Execution timeline</h2><span className="pill">{events.length} EVENTS</span></div><div className="timeline">{events.map(e=><article key={e.id} className={'event '+(e.payload.fault?'fault':'')}><div className="event-dot"><CircleDot size={14}/></div><div className="event-heading"><span>{String(e.sequence).padStart(2,'0')}</span><strong>{e.payload.fault?'Fault delivered':pretty(e.kind)}</strong>{e.payload.name&&<code>{e.payload.name}</code>}</div>{['tool_observed','agent_observed'].includes(e.kind)?<><div className="observation"><small>{e.kind==='agent_observed'?'DELIVERED TO AGENT':'TOOL RESPONSE · BEFORE SAFEGUARDS'}</small><details open={Boolean(e.payload.fault)}><summary>Response</summary><pre>{JSON.stringify(e.payload.result,null,2)}</pre></details></div>{e.payload.fault&&<div className="truth"><small>AUTHORITATIVE OUTCOME · NOT SHOWN TO AGENT</small><pre>{JSON.stringify(e.payload.authoritative_result,null,2)}</pre></div>}</>:<details><summary>Inspect event</summary><pre>{JSON.stringify(e.payload,null,2)}</pre></details>}</article>)}</div></section><aside className="incident-aside"><section className="panel"><h3>Actual reservations</h3>{run.state?.reservations?.length?run.state.reservations.map((r,i)=><div className="reservation" key={i}><strong>{String(r.id)}</strong><span>{String(r.customer)} → {String(r.resource)}</span></div>):<p className="muted">No reservations recorded.</p>}<hr/><h3>Agent's final claim</h3><p className="claim-status">{pretty(run.result?.final?.status||'awaiting completion')}</p>{run.result?.final?.reservation_id&&<code>{run.result.final.reservation_id}</code>}<details><summary>Full claim</summary><pre>{JSON.stringify(run.result?.final||{status:'awaiting completion'},null,2)}</pre></details></section><section className="repair-callout"><h3>Repair</h3><label className="sr-only" htmlFor="repair-kind">Repair type</label><select id="repair-kind" value={repairKind} onChange={e=>setRepairKind(e.target.value)}><option value="runtime">Runtime safeguards</option><option value="prompt" disabled={run.snapshot.spec.mode!=='live'}>Prompt guidance · live only</option></select><button className="primary pop-button" disabled={busy||!['completed','failed'].includes(run.status)} onClick={diagnose}>{busy?'Preparing…':'Propose repair'}<ArrowRight size={15}/></button></section></aside></div></> }</>}
 {page==='Repair comparison'&&<><PageTitle title="Repair comparison"/>{!repair?<Empty text="Open a completed incident and propose a repair."/>:<><p className="repair-summary">{repair.payload.explanation}</p><div className="diff-grid"><section className="panel"><small>ORIGINAL CONFIGURATION</small><Configuration values={repair.payload.before}/></section><section className="panel green-panel"><small>PROPOSED {repair.payload.kind.toUpperCase()} REPAIR</small><Configuration values={repair.payload.after}/></section></div><div className="launch"><p>{repair.payload.limitation}<br/>Source: {pretty(repair.payload.provenance)}.</p><button className="primary" disabled={busy||active} onClick={compare}><Check size={16}/>{repair.approved?'Run comparison again':'Approve & compare'}</button></div>{comparison&&<><div className="section-title"><h2>Comparison evidence</h2><span className="pill">ONE TRIAL PER VERSION</span></div>{comparison.pairs.map(pair=><div className="diff-grid" key={pair.trial}>{(['before','after'] as const).map(side=>{const r=comparisonRuns.find(x=>x.id===pair[side])||runs.find(x=>x.id===pair[side]);return <section className="panel" key={side}><small>{side==='before'?'ORIGINAL':'REPAIRED'}</small><h2>{r?.result?.verdict?pretty(r.result.verdict):r?.status||'queued'}</h2><Badge text={r?.snapshot.spec.mode||'fixture'}/><p>{r?.result?.tool_calls??'—'} tool calls · {r?.result?.elapsed_seconds?.toFixed(2)||'—'} seconds</p><button className="text-button" onClick={()=>{setPage('Incident',pair[side])}}>Inspect evidence<ArrowRight size={14}/></button></section>})}</div>)}</>}</>}</>}
 {page==='Results'&&<><PageTitle title="Results"/><ResultsView report={report}/><div className="section-title"><h2>Experiments</h2></div><RunTable runs={runs} open={id=>{setPage('Incident',id)}}/></>}
 {page==='About'&&<About/>}<footer><span><Wind size={15}/>SKYLARK · LOCAL BETA</span></footer></div></main>
 {setup&&<div className="modal-backdrop" onClick={()=>setSetup(false)}><section className="modal settings-modal" role="dialog" aria-modal="true" aria-label="Settings" onClick={e=>e.stopPropagation()}><button className="close" aria-label="Close settings" onClick={()=>setSetup(false)}><X/></button><h2>Settings</h2><div className="settings-sections" role="group" aria-label="Settings sections">{['Connection & budget','Model Context Protocol','Experiment defaults','Appearance'].map(section=><button key={section} aria-pressed={settingsSection===section} onClick={()=>setSettingsSection(section)}>{section}</button>)}</div>{settingsSection==='Connection & budget'&&<section><h3>Connection & budget</h3><p>Live runs send task and tool messages to Nebius and use credits.</p><div className="notice">{status?.live.enabled?'Live execution enabled.':status?.live.reason}</div><p>Set these variables locally, then restart. Keep your API key private.</p><pre>NEBIUS_API_KEY<br/>NEBIUS_MODEL<br/>NEBIUS_INPUT_USD_PER_MILLION<br/>NEBIUS_OUTPUT_USD_PER_MILLION<br/>SKYLARK_CONFIRMED_CREDITS_USD<br/>SKYLARK_ALLOWANCE_USD=2<br/>SKYLARK_LIVE_ENABLED=1</pre><p className="muted">Check credits and expiry; disable automatic top-ups. Initial allowance: $2.</p></section>}
{settingsSection==='Experiment defaults'&&<section className="settings-fields"><h3>Experiment defaults</h3><p>Saved in this browser. Applied when Skylark reloads.</p><label>Default resource<input value={defaultResource} maxLength={40} onChange={e=>{setDefaultResource(e.target.value);savePreference('defaultResource',e.target.value)}}/></label><label>Default customer<input value={defaultCustomer} maxLength={80} onChange={e=>{setDefaultCustomer(e.target.value);savePreference('defaultCustomer',e.target.value)}}/></label><p>Live execution always requires an explicit selection.</p></section>}
{settingsSection==='Model Context Protocol'&&<section className="settings-fields"><h3>Model Context Protocol</h3><p className="notice"><Info size={16}/>Not available in this build</p><dl className="configuration-list"><div><dt>Connected servers</dt><dd>None</dd></div><div><dt>Tool integration</dt><dd>Local Python adapter</dd></div></dl><p>MCP server connections are not implemented yet. Skylark currently instruments tools through its local Python adapter.</p></section>}
{settingsSection==='Appearance'&&<section className="settings-fields"><h3>Appearance</h3><label><span>Theme</span><select aria-label="Theme" value={theme} onChange={e=>onThemeChange(e.target.value as ThemePreference)}><option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option></select></label><label className="preference-toggle"><span>Animated wordmark</span><input type="checkbox" checked={shine} onChange={e=>{setShine(e.target.checked);savePreference('shine',e.target.checked?'on':'off')}}/></label><label className="preference-toggle"><span>Compact experiment tables</span><input type="checkbox" checked={compact} onChange={e=>{setCompact(e.target.checked);savePreference('compact',e.target.checked?'on':'off')}}/></label><p>Reduced-motion system preferences are always respected.</p></section>}
<button className="primary settings-done" onClick={()=>setSetup(false)}>Done<ArrowRight size={16}/></button></section></div>}
 </div>
}
function Configuration({values}:{values:Record<string,unknown>}){return <dl className="configuration-list">{Object.entries(values).map(([key,value])=><div key={key}><dt>{pretty(key)}</dt><dd>{typeof value==='boolean'?(value?'On':'Off'):typeof value==='string'?value:JSON.stringify(value)}</dd></div>)}</dl>}
function PageTitle({title}:{title:string}){return <div className="page-title"><h1>{title}</h1></div>}
function About(){return <><PageTitle title="About Skylark"/><div className="about-content">
<section><h2>Test agent recovery</h2><p>Run an experiment, inspect what the agent observed alongside the actual outcome, review a repair, and compare results. The supplied reservation application uses synthetic data; no real bookings are made.</p></section>
<section><h2>Faults and controls</h2><dl><dt>Timeout after commit</dt><dd>The reservation succeeds, but the response times out. An unsafe retry can create a duplicate.</dd><dt>Stale read</dt><dd>A read returns an earlier snapshot instead of the current state.</dd><dt>Incomplete response</dt><dd>The operation completes, but its response is missing a required field.</dd><dt>Controls</dt><dd>Fault-free and timeout-before-commit runs distinguish normal behavior from ambiguous failures.</dd></dl></section>
<section><h2>Evidence modes</h2><dl><dt>Scripted fixture</dt><dd>A deterministic demo that tests Skylark itself. No inference credits are used. This is not evidence of model reliability.</dd><dt>Fresh model evaluation</dt><dd>New Nebius calls against a fresh sandbox. Repeated trials are needed to assess reliability.</dd><dt>Deterministic regression</dt><dd>Recorded decisions replayed against the sandbox to test the harness or a supported runtime change. This is not fresh model evidence.</dd><dt>Recorded playback</dt><dd>Inspection of existing traces only, with no new inference or evidence.</dd></dl></section>
<section><h2>Reading results</h2><p>Execution status and verdict are separate: an experiment can finish successfully while the agent fails its task.</p><dl><dt>Safety</dt><dd>No duplicates, wrong reservations, or capacity violations.</dd><dt>Completion</dt><dd>The intended reservation exists.</dd><dt>Accurate report</dt><dd>The agent’s structured final claim agrees with authoritative state.</dd><dt>Fault reached</dt><dd>The configured fault actually triggered. Untriggered faults do not establish recovery.</dd></dl><p>Safe but incomplete is not a full pass. Missing evidence is inconclusive. Infrastructure failures, unknown checks, latency, and usage are reported separately. Small trial counts do not establish universal reliability.</p></section>
<section><h2>Repairs and comparisons</h2><p>Review the proposed change and its limitations before approval. Approval creates a new version and preserves the original incident. Compare controls and held-out cases as well as the original failure.</p><p>Runtime safeguards and prompt repairs are different interventions. A safeguard preventing duplicates does not show that the model learned recovery. Fixture comparisons establish harness behavior only. The interface schedules one trial per version.</p></section>
<section><h2>Local execution and privacy</h2><p>Trusted adapter code runs locally. Only instrumented calls are covered. Process separation is not a security sandbox for hostile code. Authoritative state is available to the verifier, not the agent.</p><p>Live runs send task and tool messages to Nebius. Keep credentials in the local environment and out of traces, exports, and public repositories. Review evidence before sharing it.</p></section>
<section><h2>Connection and spending</h2><p>Connection & budget lists the required environment variables. Set them locally and restart Skylark. Scripted fixtures need no key.</p><p>Verify credited balance, expiry, model prices, and disabled automatic top-ups in your provider account. Keep the initial capability experiment within $2 of confirmed credits. Skylark does not provision GPU compute.</p><p>Usage figures are local estimates, not your provider balance. Accounted usage and reserved or unconfirmed charges are separate. Unknown charges remain reserved until reconciled. App limits are not a provider-enforced billing guarantee.</p></section>
<section><h2>Export and reproduce</h2><p>Export an incident for its evidence bundle and regression test, or download results JSON for analysis. Preserve model settings, scenario versions, and fault schedules when comparing runs. Redaction or missing evidence can prevent exact reproduction.</p><p>Skylark is a local controlled beta. Multi-user hosting and production capacity have not been validated.</p></section>
</div><AboutWordmark/></>}

function Empty({text}:{text:string}){return <div className="empty"><FlaskConical size={28}/><h3>No evidence yet</h3><p>{text}</p></div>}
function ResultsView({report}:{report:any}){
 const dimensions=[['safety','Safety'],['task_completion','Completion'],['reporting_accuracy','Accurate report'],['fault_coverage','Fault reached']];
 return <><div className="section-title"><h2>Outcome dimensions</h2><a className="secondary" href="/api/v1/results/export"><Download size={15}/>Export results JSON</a></div>
 {!report?.groups.length?<Empty text="Run an experiment to collect measured results."/>:report.groups.map((g:any)=><section className="panel result-group" key={g.id}>
 <div className="result-heading"><div><h3>{pretty(g.condition)} · {pretty(g.configuration)}</h3><p>{g.model.id} · {g.split} · verifier {g.verifier_version}</p></div><Badge text={g.mode}/></div>
 <div className="assertions">{dimensions.map(([key,label])=>{const metric=g.dimensions[key];return <div className="assertion" key={key}><strong>{label}</strong><p>{metric.not_applicable===g.total?'Fault-free control':<><b>{metric.passed}/{metric.observed}</b> checks passed</>}</p>{(metric.unknown>0||metric.failed>0)&&<p>{metric.unknown} unknown · {metric.failed} failed</p>}</div>})}</div>
 <p className="result-counts">{g.total} attempts · {g.passed} passed{g.failed>0&&` · ${g.failed} failed`}{g.safe_incomplete>0&&` · ${g.safe_incomplete} incomplete`}{g.inconclusive>0&&` · ${g.inconclusive} inconclusive`}{g.pending>0&&` · ${g.pending} pending`}</p>
 <p>Median {g.latency_seconds.median?.toFixed(2)??'—'} s · {g.tool_calls.median??'—'} tool calls · ${g.accounted_usd.toFixed(4)} accounted · ${g.uncertain_usd.toFixed(4)} uncertain</p>
 <details><summary>Execution details</summary><pre>{JSON.stringify({unique_scenarios:g.unique_scenarios,execution:g.execution_statuses,dimensions:g.dimensions,input_tokens:g.input_tokens,output_tokens:g.output_tokens,provider_requests:g.provider_requests},null,2)}</pre></details>
 </section>)}<div className="panel budget-panel"><h2>Usage & uncertainty</h2><p><strong>${report?.budget.accounted_usd.toFixed(4)||'0.0000'}</strong> accounted · <strong>${report?.budget.uncertain_usd.toFixed(4)||'0.0000'}</strong> reserved or unconfirmed</p><p className="muted">Local estimates · not provider balance.</p></div></>
}
function RunTable({runs,open}:{runs:Run[];open:(id:string)=>void}){return runs.length?<div className="table-wrap"><table><thead><tr><th>Experiment</th><th>Evidence</th><th>Execution</th><th>Verdict</th><th/></tr></thead><tbody>{runs.map(r=><tr key={r.id}><td><button className="run-name" onClick={()=>open(r.id)}>{r.snapshot.spec.scenario.name}<small>{r.id.slice(0,8)} · {new Date(r.created*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</small></button></td><td><Badge text={r.snapshot.spec.mode}/></td><td>{pretty(r.status)}</td><td><Badge text={r.result?.verdict||(['queued','running'].includes(r.status)?'pending':'inconclusive')}/></td><td><button aria-label={'Open incident '+r.id.slice(0,8)} className="icon-button" onClick={()=>open(r.id)}><ArrowUpRight size={17}/></button></td></tr>)}</tbody></table></div>:<Empty text="Choose a scenario above to create your first experiment."/>}
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
