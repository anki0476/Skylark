import {useEffect,useId,useRef,useState} from 'react';
import type {ReactNode} from 'react';

export type CircuitNode = {id:string;x:number;y:number;label:string;icon:ReactNode};
export type CircuitConnection = {from:string;to:string};

type Props = {nodes:CircuitNode[];connections:CircuitConnection[];width:number;height:number};

/** Adapted from Componentry's Circuit Board: orthogonal traces and travelling pulses. */
export function CircuitBoard({nodes,connections,width,height}:Props){
 const uid=useId().replace(/:/g,'');
 const scrollRef=useRef<HTMLDivElement>(null);
 const [visible,setVisible]=useState(false);
 const [mobile,setMobile]=useState(()=>matchMedia('(max-width: 700px)').matches);
 useEffect(()=>{
  const media=matchMedia('(max-width: 700px)');
  const update=()=>setMobile(media.matches);
  media.addEventListener('change',update);
  return()=>media.removeEventListener('change',update);
 },[]);
 useEffect(()=>{
  const element=scrollRef.current;
  if(!element)return;
  const observer=new IntersectionObserver(([entry])=>setVisible(entry.isIntersecting));
  observer.observe(element);
  return()=>observer.disconnect();
 },[]);
 const shownNodes=mobile?nodes.map((node,i)=>({...node,x:130,y:65+i*120})):nodes;
 const boardWidth=mobile?260:width,boardHeight=mobile?625:height;
 const byId=new Map(shownNodes.map(node=>[node.id,node]));
 return <div ref={scrollRef} className={`circuit-scroll${visible?' is-visible':''}`}>
  <svg className="circuit-board" viewBox={`0 0 ${boardWidth} ${boardHeight}`} width={boardWidth} height={boardHeight} role="img" aria-label="Choose fault, run agent, inspect incident, review repair, verify and export">
   <defs>
    <pattern id={`${uid}-grid`} width="20" height="20" patternUnits="userSpaceOnUse"><circle cx="10" cy="10" r="1" className="circuit-grid-dot"/></pattern>
    <filter id={`${uid}-glow`} x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2"/></filter>
   </defs>
   <rect width={boardWidth} height={boardHeight} fill={`url(#${uid}-grid)`}/>
   {connections.map(({from,to},i)=>{
    const a=byId.get(from), b=byId.get(to);
    if(!a||!b)return null;
    const path=mobile
     ?`M ${a.x} ${a.y+23} V ${(a.y+b.y)/2} H ${b.x} V ${b.y-23}`
     :`M ${a.x+23} ${a.y} H ${(a.x+b.x)/2} V ${b.y} H ${b.x-23}`;
    return <g key={`${from}-${to}`}>
     <path d={path} className="circuit-trace"/>
     <path d={path} className="circuit-pulse-glow" filter={`url(#${uid}-glow)`} pathLength="100" style={{animationDelay:`${i*.35}s`}}/>
     <path d={path} className="circuit-pulse" pathLength="100" style={{animationDelay:`${i*.35}s`}}/>
    </g>;
   })}
   {shownNodes.map((node,i)=><g key={node.id} className="circuit-node">
    <rect x={node.x-23} y={node.y-23} width="46" height="46" rx="11"/>
    <foreignObject x={node.x-12} y={node.y-12} width="24" height="24"><div className="circuit-icon">{node.icon}</div></foreignObject>
    <text x={node.x} y={node.y-35} textAnchor="middle" className="circuit-number">{String(i+1).padStart(2,'0')}</text>
    <text x={node.x} y={node.y+53} textAnchor="middle" className="circuit-label">{node.label}</text>
   </g>)}
  </svg>
 </div>;
}
