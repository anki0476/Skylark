export async function api(path:string, options:RequestInit={}) {
 const response=await fetch('/api/v1'+path,{...options,headers:{'Content-Type':'application/json',...options.headers}});
 const body=await response.text();
 let data:any;
 try {data=JSON.parse(body)} catch {
  throw new Error(`Server returned an unexpected response (${response.status}). Check that Skylark is running.`);
 }
 if(!response.ok){
  const detail=data.detail;
  const message=typeof detail==='string'?detail:Array.isArray(detail)?detail.map(item=>`${(item.loc||[]).filter((part:string)=>part!=='body').join('.')}: ${item.msg||'Invalid value'}`).join(';'):`Request failed (${response.status})`;
  throw new Error(message);
 }
 return data;
}
