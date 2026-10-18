import {useEffect,useId,useRef,useState,type ReactNode} from 'react';
import {createPortal} from 'react-dom';

export function CursorHelp({children,title,description}:{children:ReactNode;title:string;description:string}){
 const id=useId();
 const label=useRef<HTMLSpanElement>(null);
 const [visible,setVisible]=useState(false);
 const [position,setPosition]=useState({x:0,y:0});
 const timer=useRef<ReturnType<typeof setTimeout>|undefined>(undefined);
 const place=(x:number,y:number)=>setPosition({x:Math.max(12,Math.min(x-100,window.innerWidth-272)),y:Math.max(12,Math.min(y+22,window.innerHeight-140))});
 const dismiss=()=>{clearTimeout(timer.current);setVisible(false)};
 const begin=()=>{clearTimeout(timer.current);timer.current=setTimeout(()=>setVisible(true),2000)};
 useEffect(()=>{const close=()=>dismiss();const key=(event:KeyboardEvent)=>{if(event.key==='Escape')dismiss()};window.addEventListener('scroll',close,true);window.addEventListener('resize',close);window.addEventListener('keydown',key);return()=>{clearTimeout(timer.current);window.removeEventListener('scroll',close,true);window.removeEventListener('resize',close);window.removeEventListener('keydown',key)}},[]);
 useEffect(()=>{
  const button=label.current?.closest('button');if(!button)return;
  const enter=(event:PointerEvent)=>{if(event.pointerType==='touch')return;place(event.clientX,event.clientY);begin()};
  const move=(event:PointerEvent)=>{if(event.pointerType!=='touch')place(event.clientX,event.clientY)};
  const focus=()=>{if(!button.matches(':focus-visible'))return;const rect=button.getBoundingClientRect();place(rect.right,rect.bottom);begin()};
  button.addEventListener('pointerenter',enter);button.addEventListener('pointermove',move);button.addEventListener('pointerleave',dismiss);button.addEventListener('pointerdown',dismiss);button.addEventListener('focus',focus);button.addEventListener('blur',dismiss);
  return()=>{button.removeEventListener('pointerenter',enter);button.removeEventListener('pointermove',move);button.removeEventListener('pointerleave',dismiss);button.removeEventListener('pointerdown',dismiss);button.removeEventListener('focus',focus);button.removeEventListener('blur',dismiss)};
 },[]);
 useEffect(()=>{const button=label.current?.closest('button');if(visible)button?.setAttribute('aria-describedby',id);else button?.removeAttribute('aria-describedby');return()=>button?.removeAttribute('aria-describedby')},[visible,id]);
 return <><span ref={label} className="cursor-help-label" aria-describedby={visible?id:undefined}
 >{children}</span>{visible&&createPortal(<div id={id} role="tooltip" className="cursor-help-card" style={{left:position.x,top:position.y}}><span className="cursor-help-mark" aria-hidden="true">{title==='Experiments'?'01':title==='Incident'?'02':title==='Repair comparison'?'03':'04'} / SKYLARK</span><strong>{title}</strong><p>{description}</p></div>,document.body)}</>;
}
