import {lazy,Suspense,useEffect,useState} from 'react';
import source from './assets/skylark-particles.svg';
const Particles=lazy(()=>import('./InteractiveParticles'));
export function AboutWordmark(){
 const [reduced,setReduced]=useState(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);
 useEffect(()=>{const media=matchMedia('(prefers-reduced-motion: reduce)');const update=()=>setReduced(media.matches);media.addEventListener('change',update);return()=>media.removeEventListener('change',update)},[]);
 const fallback=<span className="particle-fallback">SKYLARK</span>;
 return <div className="about-wordmark" role="img" aria-label="SKYLARK — interactive particle wordmark"><div aria-hidden="true">{reduced?fallback:<Suspense fallback={fallback}><Particles src={source} allowUpload={false} background="transparent" color="#7297ee" maxDimension={520} size={1.5} randomness={.5} depth={1} touchRadius={.2}/></Suspense>}</div></div>;
}
