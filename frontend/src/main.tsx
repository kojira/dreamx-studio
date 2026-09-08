import React, {useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

type Status={runtime_ready:boolean;reason?:string;available_gib?:number;active_job_id?:string|null;active_kind?:string;video_validation_ready?:boolean;refiner_ready?:boolean};
type VideoInput={input_id:string;width:number;height:number;duration_seconds:number;source_fps:number;normalized_fps:number;normalized_frames:number;has_audio:boolean};
type Job={id:string;state:string;kind?:string;input_id?:string;artifacts?:string[];error_code?:string;created_at:string;spatial_tokens?:number;elapsed_seconds?:number;progress?:{phase:string;step?:number;total_steps?:number;percent?:number;completed_chunks?:number;total_chunks?:number}};
const phases:Record<string,string>={refining:'高解像度化中',decoding:'動画デコード中',muxing:'音声結合・出力確認中',preparing:'モデル準備・前処理中',generating:'動画・音声を生成中',encoding_output:'動画を書き出し中',update_pending:'進捗の更新待ち',succeeded:'生成完了',failed:'生成失敗',cancelled:'キャンセル済み',interrupted:'中断',cancelling:'停止処理中'};
const terminal=new Set(['succeeded','failed','cancelled','interrupted']);
function App(){
 const [csrf,setCsrf]=useState(''),[error,setError]=useState('');
 const [status,setStatus]=useState<Status|null>(null),[job,setJob]=useState<Job|null>(null),[history,setHistory]=useState<Job[]>([]);
 const [file,setFile]=useState<File|null>(null),[preview,setPreview]=useState(''),[prompt,setPrompt]=useState(''),[busy,setBusy]=useState(false);
 const [seed,setSeed]=useState('');
 const [spatialTokens,setSpatialTokens]=useState(880);
 const [mode,setMode]=useState<'generate'|'refine'>('generate');
 const [videoFile,setVideoFile]=useState<File|null>(null),[videoPreview,setVideoPreview]=useState('');
 const [outputFps,setOutputFps]=useState('24');
 const [videoInput,setVideoInput]=useState<VideoInput|null>(null),[uploading,setUploading]=useState(false);
 const uploadAbort=useRef<AbortController|null>(null),refineKey=useRef('');
 useEffect(()=>{if(!videoFile){setVideoPreview('');return;}const url=URL.createObjectURL(videoFile);setVideoPreview(url);return()=>URL.revokeObjectURL(url);},[videoFile]);
 useEffect(()=>()=>uploadAbort.current?.abort(),[]);
 useEffect(()=>{if(job?.id)localStorage.setItem('dreamx-last-job',job.id);},[job?.id]);
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
   const saved=localStorage.getItem('dreamx-last-job');
   const id=job?.id||s.active_job_id||(saved&&/^[a-f0-9-]{36}$/.test(saved)?saved:null);if(id){const j=await api('/jobs/'+id);if(active)setJob(j);}
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
  const j=await api('/jobs',{method:'POST',headers:{'content-type':'application/json','idempotency-key':crypto.randomUUID()},body:JSON.stringify({input_id:input.input_id,prompt,seed:seed===''?null:Number(seed),preset:'trial',spatial_tokens:spatialTokens})});
  setJob(await api('/jobs/'+j.job_id));
 }catch(e){setError(String(e));}finally{setBusy(false);}}
 async function uploadVideo(selected:File|null){
  setVideoFile(selected);setVideoInput(null);setError('');refineKey.current='';
  if(!selected)return;
  if(!Number.isFinite(Number(outputFps))||Number(outputFps)<=0){setError('fpsは0より大きい数値を入力してください');return;}
  if(selected.size>100*1024*1024){setError('動画は100MiB以内にしてください（UPLOAD_TOO_LARGE）');return;}
  const controller=new AbortController();uploadAbort.current=controller;setUploading(true);
  try{const result=await api('/video-inputs?output_fps='+encodeURIComponent(outputFps),{method:'POST',headers:{'content-type':'application/octet-stream'},body:selected,signal:controller.signal});setVideoInput(result);refineKey.current=crypto.randomUUID();}
  catch(e){if(!controller.signal.aborted)setError(String(e));}
  finally{uploadAbort.current=null;setUploading(false);}
 }
 async function refine(e:React.FormEvent){e.preventDefault();if(!videoInput)return;setBusy(true);setError('');
  try{const result=await api('/refiner-jobs',{method:'POST',headers:{'content-type':'application/json','idempotency-key':refineKey.current},body:JSON.stringify({input_id:videoInput.input_id})});setJob(await api('/jobs/'+result.job_id));}
  catch(e){setError(String(e));}finally{setBusy(false);}
 }
 const running=!!job&&!terminal.has(job.state);
 const kindLabel=(kind?:string)=>kind==='refine'?'1080p高解像度化':kind==='operator_test'?'Refiner試験':'画像から生成';
 return <main><header><h1>DreamX Studio</h1><p>画像から、音のある動画へ。GB10 お試し版</p></header>
 {error&&<p role="alert" className="error">{error}</p>}
 {!csrf?<section><p>接続中…</p>{!busy&&<button onClick={()=>void connect()}>再接続</button>}</section>:<>
 <nav aria-label="処理種別"><button type="button" aria-pressed={mode==='generate'} disabled={busy||uploading} onClick={()=>setMode('generate')}>画像から生成</button> <button type="button" aria-pressed={mode==='refine'} disabled={busy||uploading} onClick={()=>setMode('refine')}>動画を1080p化</button></nav>
 <aside>{status?.active_kind==='validate_video'?'動画検証中':status?.runtime_ready?'処理受付可能':`準備中・受付停止：${status?.reason||'確認中'}`}{status?.available_gib!==undefined&&` ／ RAM空き ${status.available_gib.toFixed(1)} GiB`}</aside>
 {mode==='generate'?<form onSubmit={generate}><label>最初のフレーム（PNG / JPEG / WebP、10MiBまで）<input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>setFile(e.target.files?.[0]||null)} required/></label>
 {preview&&<img className="preview" src={preview} alt="入力画像"/>}
 <label>映像・音声のプロンプト<textarea value={prompt} onChange={e=>setPrompt(e.target.value)} maxLength={4000} rows={5} required placeholder="シーン、動き、聞こえる音を説明してください"/></label>
 <label>シード（空欄でランダム）<input type="number" min="0" max="2147483647" step="1" value={seed} onChange={e=>setSeed(e.target.value)}/></label>
 <label>解像度設定<select value={spatialTokens} onChange={e=>setSpatialTokens(Number(e.target.value))}><option value={220}>軽量 — 220トークン</option><option value={440}>中間 — 440トークン</option><option value={880}>公式 — 880トークン</option></select></label>
 <p>69フレーム（約2.88秒）・50ステップ。実際の縦横サイズは画像に合わせます。高解像度ほどRAMと時間を使います。2K化は未対応。</p>
 <button disabled={busy||running||!status?.runtime_ready||!file||!prompt.trim()}>音声付き動画を生成</button></form>:<form onSubmit={refine}>
 <p>動画の長さ制限はありません。横動画・720p以下・100MiB以内のMP4 / MOV（H264/AAC）。出力は1920×1080、fpsは下の数値で指定します。長尺はGPU未検証で、処理時間やメモリ使用量が増える場合があります。</p>
 <p>画質や顔の改善は保証しません。口を閉じる、発話を除く、本人性を補正する機能ではありません。</p>
 <label>出力fps<input type="number" step="any" required value={outputFps} disabled={busy||running||uploading} onChange={e=>{setOutputFps(e.target.value);setVideoInput(null);}}/></label>
 {videoFile&&!videoInput&&!uploading&&<button type="button" disabled={busy||running||!status?.video_validation_ready} onClick={()=>void uploadVideo(videoFile)}>このfpsで検証</button>}
 <label>入力動画<input type="file" accept="video/mp4,video/quicktime,.mp4,.mov" disabled={busy||running||uploading||!status?.video_validation_ready} onChange={e=>void uploadVideo(e.target.files?.[0]||null)}/></label>
 {videoInput?<><p>検証済み入力（{videoInput.normalized_fps}fpsのMP4）</p><video controls src={'/api/video-inputs/'+videoInput.input_id+'/preview'} aria-label="入力動画"/></>:videoPreview&&<><p>検証後、MP4形式に正規化した動画をプレビューします。</p>{videoFile?.type!=='video/quicktime'&&!videoFile?.name.toLowerCase().endsWith('.mov')&&<video controls src={videoPreview} aria-label="入力動画"/>}</>}
 {uploading&&<p role="status">アップロード・動画検証中… <button type="button" onClick={()=>uploadAbort.current?.abort()}>アップロード接続を中断</button>（検証開始後は停止確認まで受付を保持します）</p>}
 {videoInput&&<p>{videoInput.width}×{videoInput.height} ／ {videoInput.duration_seconds}秒 ／ 入力{videoInput.source_fps}fps → 出力{videoInput.normalized_fps}fps・{videoInput.normalized_frames}フレーム ／ {videoInput.has_audio?'音声あり':'無音'}</p>}
 <button disabled={busy||running||uploading||!videoInput||!status?.refiner_ready}>高解像度化</button>
 {!status?.refiner_ready&&<p>高解像度化は準備中、または他の処理が実行中です。</p>}
 </form>}
 {job&&<section><h2>{phases[job.state==='cancelling'?'cancelling':job.progress?.phase||job.state]||job.state}</h2>
 <p>{kindLabel(job.kind)}</p>
 {(!job.kind||job.kind==='generate')&&job.spatial_tokens!==undefined&&<p>この生成：{job.spatial_tokens}トークン</p>}
 {job.kind==='refine'&&job.input_id&&<><p>入力動画（MP4正規化済み）</p><video controls src={'/api/video-inputs/'+job.input_id+'/preview'}/></>}
 {job.progress?.completed_chunks!==undefined&&<p>{job.progress.completed_chunks} / {job.progress.total_chunks} チャンク完了（デコード・保存は別工程）</p>}
 {job.elapsed_seconds!==undefined&&<p>経過：{Math.floor(job.elapsed_seconds/60)}分{job.elapsed_seconds%60}秒</p>}
 {job.progress?.step!==undefined&&job.progress.total_steps!==undefined&&<><progress value={job.progress.step} max={job.progress.total_steps}/><p>{job.progress.step} / {job.progress.total_steps} ステップ（{job.progress.percent}%）</p></>}
 {running&&job.progress?.phase==='preparing'&&<p>読み込み・前処理には数分かかる場合があります。生成ステップが始まると進捗を表示します。</p>}
 {job.error_code&&<p className="error">{job.error_code}</p>}
 {running&&<button onClick={()=>{void api('/jobs/'+job.id+'/cancel',{method:'POST'}).catch(e=>setError(String(e)));}}>キャンセル</button>}
 {job.state==='succeeded'&&<><video controls src={'/api/jobs/'+job.id+'/artifacts/mp4'}/><p><a download href={'/api/jobs/'+job.id+'/artifacts/mp4'}>MP4を保存</a>{job.artifacts?.includes('wav')&&<> · <a download href={'/api/jobs/'+job.id+'/artifacts/wav'}>音声を保存</a></>}</p></>}</section>}
 <details><summary>最近の結果</summary>{history.map(j=><p key={j.id}><button onClick={()=>setJob(j)}>{j.created_at} — {kindLabel(j.kind)} — {j.state}</button></p>)}</details>
 <footer>動画検証・生成・高解像度化は同時に1件。ホストの実空きRAMが8GiB未満になった場合など、安全条件に従って処理を停止します。元データや結果は自動削除しません。</footer></>}
 </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
