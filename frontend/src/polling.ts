import {useEffect,useRef,type DependencyList} from 'react';

/** Schedule after completion, pause hidden pages, and stop terminal work. */
export function usePolling(poll:(signal:AbortSignal)=>Promise<number|false>, dependencies:DependencyList=[]){
 const latest=useRef(poll);latest.current=poll;
 useEffect(()=>{
  const controller=new AbortController();
  let timer:ReturnType<typeof setTimeout>|undefined,pending=false,finished=false;
  const update=async()=>{
   if(controller.signal.aborted||pending||finished||document.hidden)return;
   clearTimeout(timer);pending=true;
   let delay:number|false=5000;
   try{delay=await latest.current(controller.signal)}finally{
    pending=false;finished=delay===false;
    if(!controller.signal.aborted&&!finished)timer=setTimeout(()=>{void update()},delay as number);
   }
  };
  const visible=()=>{if(!document.hidden)void update()};
  void update();document.addEventListener('visibilitychange',visible);
  return()=>{controller.abort();clearTimeout(timer);document.removeEventListener('visibilitychange',visible)};
 },dependencies);
}
