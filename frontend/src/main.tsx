import React, {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type Status={runtime_ready:boolean;reason?:string;available_gib?:number;active_job_id?:string|null};
type Job={id:string;state:string;error_code?:string;created_at:string;elapsed_seconds?:number;progress?:{phase:string;step?:number;total_steps?:number;percent?:number}};
const phases:Record<string,string>={preparing:'モデル準備・前処理中',generating:'動画・音声を生成中',encoding_output:'動画を書き出し中',update_pending:'進捗の更新待ち',succeeded:'生成完了',failed:'生成失敗',cancelled:'キャンセル済み',interrupted:'中断',cancelling:'停止処理中'};
const terminal=new Set(['succeeded','failed','cancelled','interrupted']);
function App(){
 const [csrf,setCsrf]=useState(''),[error,setError]=useState('');
 const [status,setStatus]=useState<Status|null>(null),[job,setJob]=useState<Job|null>(null),[history,setHistory]=useState<Job[]>([]);
 const [file,setFile]=useState<File|null>(null),[preview,setPreview]=useState(''),[prompt,setPrompt]=useState(''),[busy,setBusy]=useState(false);
 const [seed,setSeed]=useState('');
 async function api(path:string,init:RequestInit={}){
  const response=await fetch('/api'+path,{...init,headers:{...init.headers,'x-csrf-token':csrf}});
  const data=await response.json();
  if(!response.ok){if(response.status===401)setCsrf('');throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
  return data;
 }
 useEffect(()=>{if(!file){setPreview('');return;}const url=URL.createObjectURL(file);setPreview(url);return()=>URL.revokeObjectURL(url);},[file]);
 useEffect(()=>{
  if(!csrf)return;let active=true;
  async function refresh(){try{
   const s=await api('/status');if(!active)return;setStatus(s);
   const items=await api('/jobs');if(!active)return;setHistory(items);
   const id=job?.id||s.active_job_id;if(id){const j=await api('/jobs/'+id);if(active)setJob(j);}
  }catch(e){if(active)setError(String(e));}}
  void refresh();const timer=setInterval(()=>void refresh(),2000);return()=>{active=false;clearInterval(timer);};
 },[csrf,job?.id]);
 async function connect(){setBusy(true);setError('');try{
  const response=await fetch('/api/session',{method:'POST',headers:{'content-type':'application/json'},body:'{}'});
  const data=await response.json();if(!response.ok)throw new Error(data.detail);setCsrf(data.csrf);
 }catch(e){setError(String(e));}finally{setBusy(false);}}
 useEffect(()=>{void connect();},[]);
 async function generate(e:React.FormEvent){e.preventDefault();if(!file)return;setBusy(true);setError('');try{
  const body=new FormData();body.append('image',file);const input=await api('/inputs',{method:'POST',body});
  const j=await api('/jobs',{method:'POST',headers:{'content-type':'application/json','idempotency-key':crypto.randomUUID()},body:JSON.stringify({input_id:input.input_id,prompt,seed:seed===''?null:Number(seed),preset:'trial'})});
  setJob(await api('/jobs/'+j.job_id));
 }catch(e){setError(String(e));}finally{setBusy(false);}}
 const running=!!job&&!terminal.has(job.state);
 return <main><header><h1>DreamX Studio</h1><p>画像から、音のある動画へ。GB10 お試し版</p></header>
 {error&&<p role="alert" className="error">{error}</p>}
 {!csrf?<section><p>接続中…</p>{!busy&&<button onClick={()=>void connect()}>再接続</button>}</section>:<>
 <aside>{status?.runtime_ready?'生成可能':`準備中・受付停止：${status?.reason||'確認中'}`}{status?.available_gib!==undefined&&` ／ RAM空き ${status.available_gib.toFixed(1)} GiB`}</aside>
 <form onSubmit={generate}><label>最初のフレーム（PNG / JPEG / WebP、10MiBまで）<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>setFile(e.target.files?.[0]||null)} required/></label>
 {preview&&<img className="preview" src={preview} alt="入力画像"/>}
 <label>映像・音声のプロンプト<textarea value={prompt} onChange={e=>setPrompt(e.target.value)} maxLength={4000} rows={5} required placeholder="シーン、動き、聞こえる音を説明してください"/></label>
 <label>シード（空欄でランダム）<input type="number" min="0" max="2147483647" step="1" value={seed} onChange={e=>setSeed(e.target.value)}/></label>
 <p>低負荷プリセット：220空間トークン・69フレーム（約2.88秒）・50ステップ。2K化は未対応。</p>
 <button disabled={busy||running||!status?.runtime_ready||!file||!prompt.trim()}>音声付き動画を生成</button></form>
 {job&&<section><h2>{phases[job.state==='cancelling'?'cancelling':job.progress?.phase||job.state]||job.state}</h2>
 {job.elapsed_seconds!==undefined&&<p>経過：{Math.floor(job.elapsed_seconds/60)}分{job.elapsed_seconds%60}秒</p>}
 {job.progress?.step!==undefined&&job.progress.total_steps!==undefined&&<><progress value={job.progress.step} max={job.progress.total_steps}/><p>{job.progress.step} / {job.progress.total_steps} ステップ（{job.progress.percent}%）</p></>}
 {running&&job.progress?.phase==='preparing'&&<p>読み込み・前処理には数分かかる場合があります。生成ステップが始まると進捗を表示します。</p>}
 {job.error_code&&<p className="error">{job.error_code}</p>}
 {running&&<button onClick={()=>{void api('/jobs/'+job.id+'/cancel',{method:'POST'}).catch(e=>setError(String(e)));}}>キャンセル</button>}
 {job.state==='succeeded'&&<><video controls src={'/api/jobs/'+job.id+'/artifacts/mp4'}/><p><a download href={'/api/jobs/'+job.id+'/artifacts/mp4'}>MP4を保存</a> · <a download href={'/api/jobs/'+job.id+'/artifacts/wav'}>音声を保存</a></p></>}</section>}
 <details><summary>最近の結果</summary>{history.map(j=><p key={j.id}><button onClick={()=>setJob(j)}>{j.created_at} — {j.state}</button></p>)}</details>
 <footer>同時生成は1件。メモリ不足の予兆があれば生成を停止します。元画像や結果は自動削除しません。</footer></>}
 </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
