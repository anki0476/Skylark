import {BadgeCheck,FlaskConical,Play,Search,Wrench} from 'lucide-react';
import {CircuitBoard} from './CircuitBoard';

const nodes=[
 {id:'fault',x:80,y:110,label:'Choose a fault',icon:<FlaskConical size={22}/>},
 {id:'run',x:260,y:110,label:'Run the agent',icon:<Play size={22}/>},
 {id:'inspect',x:440,y:110,label:'Inspect evidence',icon:<Search size={22}/>},
 {id:'repair',x:620,y:110,label:'Review a repair',icon:<Wrench size={22}/>},
 {id:'verify',x:800,y:110,label:'Verify & export',icon:<BadgeCheck size={22}/>},
];
const connections=[
 {from:'fault',to:'run'},
 {from:'run',to:'inspect'},
 {from:'inspect',to:'repair'},
 {from:'repair',to:'verify'},
];

export function WorkflowExplainer(){return <section className="workflow-section" aria-labelledby="workflow-title">
 <h2 id="workflow-title">How Skylark works</h2>
 <p>Start with a known task and a fault. Skylark records what the agent sees, checks the actual outcome, and compares a reviewed repair against fresh runs.</p>
 <CircuitBoard nodes={nodes} connections={connections} width={880} height={215}/>
 <p className="workflow-note">A scripted fixture checks the harness. Fresh model evaluations provide new agent evidence.</p>
 </section>}
