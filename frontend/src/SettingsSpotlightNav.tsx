import {useState} from 'react';
import {Activity,FlaskConical,Palette,Search,Server} from 'lucide-react';

export function SettingsSpotlightNav({items,active,onSelect}:{items:readonly string[];active:string;onSelect:(item:string)=>void}){
 const [query,setQuery]=useState('');
 const visibleItems=items.filter(item=>item.toLowerCase().includes(query.trim().toLowerCase()));
 const icons=[Server,Activity,FlaskConical,Palette];
 return <div className="settings-nav-wrap"><label className="settings-search"><Search size={16} aria-hidden="true"/><input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search settings" aria-label="Search settings"/></label><div className="settings-nav-caption">SKYLARK SETTINGS</div><div className="settings-spotlight-nav" role="group" aria-label="Settings sections">
  {visibleItems.map(item=>{const Icon=icons[items.indexOf(item)];return <button key={item} aria-pressed={active===item} onClick={()=>onSelect(item)}><Icon size={17} aria-hidden="true"/><span>{item}</span></button>})}
  {!visibleItems.length&&<p className="settings-search-empty">No matching settings</p>}
 </div></div>;
}
