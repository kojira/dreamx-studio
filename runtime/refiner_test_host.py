"""One-shot operator test. Reuses the application's atomic single-job reservation.
Never restart the application runner during this test. No automatic retries.
"""
import argparse,hashlib,json,os,shutil,subprocess,threading,time
from pathlib import Path
from dreamx.jobs import Jobs
from dreamx.host_guard import atomic_json,load
from dreamx.docker_control import execute,inspect_job,kill_job,verify_limits,configure_no_swap
from dreamx.safety import GIB,WORKER_LIMIT,Sample,admission,memory_available
from dreamx.paths import id_path


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--source-job',required=True);p.add_argument('--attention-patch',type=Path);p.add_argument('--target1080',action='store_true');a=p.parse_args()
    if a.target1080:assert a.attention_patch,'1080 trial requires the verified attention patch'
    if a.attention_patch:
        a.attention_patch=a.attention_patch.resolve()
        assert hashlib.sha256(a.attention_patch.read_bytes()).hexdigest()=='9104decd2574690d397438e59eaf87e54e1bd6c2c695adfc0c45c01b06a14ab7','Unexpected attention patch'
    trial='v1.10-1080-sdpa' if a.target1080 else ('v1.11-sdpa' if a.attention_patch else 'v1.11')
    root=a.root.resolve();os.umask(0o077);jobs=Jobs(root/'app/jobs.sqlite')
    source_job=jobs.get(a.source_job);assert source_job['state']=='succeeded'
    source=id_path(root/'app/jobs',a.source_job)/'output.mp4'
    if a.target1080:
        srcmeta=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(source)],text=True,timeout=15))['streams'][0]
        assert (srcmeta['width'],srcmeta['height'],int(srcmeta['nb_frames']),srcmeta['avg_frame_rate'])==(1248,704,69,'24/1'),'Unsupported1080 test input'
    with source.open('rb') as f:original_sha=hashlib.file_digest(f,'sha256').hexdigest()
    assert not load(root/'control/active.json').get('container_id'),'User job active'
    guard=load(root/'control/guard-status.json')
    reason=admission(Sample(memory_available(Path('/proc/meminfo').read_text()),shutil.disk_usage(root).free,0,time.monotonic()-guard['at']),runtime_ready=not guard.get('reason'),active=False)
    assert reason is None,reason
    payload=json.loads(source_job['payload']);payload['operator_test']='refiner2x-'+trial
    job,created=jobs.create('operator-refiner2x-'+trial+'-'+a.source_job,payload)
    assert created,'Test already reserved or completed; do not duplicate'
    jid=job['id'];cid=None;guardian=None;heartbeat_stop=threading.Event();control=None;failure=None
    output=id_path(root/'app/jobs',jid)
    try:
        output.mkdir(mode=0o700,exist_ok=False);control=root/'evidence'/('refiner-control-'+jid);control.mkdir(mode=0o700,exist_ok=False)
        atomic_json(output/'spec.json',{'job_id':jid,'source_job':a.source_job,'kind':'operator-refiner1080' if a.target1080 else 'operator-refiner2x','source_sha256':original_sha})
        atomic_json(control/'active.json',{'container_id':None})
        def heartbeat():
            while not heartbeat_stop.is_set():
                atomic_json(control/'runner-heartbeat.json',{'at':time.monotonic()});heartbeat_stop.wait(.5)
        threading.Thread(target=heartbeat,daemon=True).start()
        glog=(output/'guardian.log').open('ab')
        guardian=subprocess.Popen(['python3','-m','dreamx.host_guard','--root',str(control)],env={**os.environ,'PYTHONPATH':str(root/'build')},stdin=subprocess.DEVNULL,stdout=glog,stderr=glog,start_new_session=True)
        image=load(root/'config.json')['image_id'];user=f'{os.getuid()}:{os.getgid()}'
        mounts=[('bind',str(root/'weights'),'/opt/dreamx/checkpoints',False),('bind',str(source),'/input.mp4',False),('bind',str(output),'/job',True),('bind',str(control),'/control',False),('bind',str(root/'build/refiner-site-v1'),'/deps',False),('bind',str(root/'build/refiner_test_worker.py'),'/opt/refiner_test_worker.py',False)]
        if a.attention_patch:
            mounts.append(('bind',str(a.attention_patch),'/opt/dreamx/video_refiner/wan/modules/sr_dit/attention.py',False))
            mounts.append(('bind',str(root/'build/check_refiner_attention.py'),'/opt/check_refiner_attention.py',False))
        args=['create','--name','dreamx-refiner-test-'+jid,'--label','org.dreamx.studio.job='+jid,'--restart','no','--memory',str(WORKER_LIMIT),'--memory-swap',str(WORKER_LIMIT),'--cpus','8','--pids-limit','512','--network','none','--gpus','all','--user',user,'--cap-drop','ALL','--security-opt','no-new-privileges','--log-opt','max-size=10m','--log-opt','max-file=3']
        for env in ['USER=dreamx','HOME=/tmp','PYTHONPATH=/deps','TORCHINDUCTOR_CACHE_DIR=/tmp/dreamx-inductor','HF_HUB_OFFLINE=1','TRANSFORMERS_OFFLINE=1']:
            args+=['--env',env]
        if a.attention_patch:args+=['--env','CHECK_REFINER_ATTENTION=1']
        if a.target1080:args+=['--env','REFINER_TARGET1080=1']
        for typ,src,dst,rw in mounts:args+=['--mount',f'type={typ},src={src},dst={dst}'+('' if rw else ',readonly')]
        args+=[image,'python','/opt/refiner_test_worker.py']
        atomic_json(output/'launch.json',{'image':image,'argv':args})
        jobs.transition(jid,'preparing');cid=execute(args).strip()
        verify_limits(inspect_job(cid,jid),expected_image_id=image,expected_mounts=mounts,expected_user=user)
        execute(['start',cid]);c=inspect_job(cid,jid);assert c['State']['Running'];pid=c['State']['Pid']
        cgroup=configure_no_swap(cid,jid)
        started=time.monotonic();atomic_json(control/'active.json',{'container_id':cid,'job_id':jid,'cgroup':str(cgroup),'started_at':started})
        deadline=started+5
        while True:
            try:
                g=load(control/'guard-status.json')
                if g.get('container_id')==cid and not g.get('reason') and 0<=time.monotonic()-g['at']<2:break
            except (OSError,ValueError):pass
            assert time.monotonic()<deadline,'Guardian ACK timeout';time.sleep(.1)
        jobs.transition(jid,'generating');atomic_json(control/'go.json',{'job_id':jid})
        print(json.dumps({'job_id':jid,'container_id':cid,'state':'refining'}),flush=True)
        with (output/'resources.jsonl').open('a') as samples:
            while True:
                c=inspect_job(cid,jid)
                if not c['State']['Running']:break
                g=load(control/'guard-status.json')
                assert 0<=time.monotonic()-g['at']<=2 and not g.get('reason'),g.get('reason') or 'GUARDIAN_LOST'
                samples.write(json.dumps(g)+'\n');samples.flush();time.sleep(.5)
        assert not c['State']['OOMKilled'] and c['State']['ExitCode']==0,'Refiner exited unsuccessfully'
        jobs.transition(jid,'muxing');results=list((output/'refined').glob('*.mp4'));assert len(results)==1,'Expected exactly one output'
        video=results[0]
        if a.target1080:
            raw=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(video)],text=True,timeout=15))['streams'][0]
            assert (raw['width'],raw['height'])==(1920,1088),'Unexpected internal target size'
            final=output/'final1080.mp4'
            subprocess.run(['ffmpeg','-nostdin','-n','-v','error','-i',str(video),'-map','0:v:0','-map','0:a:0','-vf','scale=1914:1080:flags=lanczos,pad=1920:1080:(ow-iw)/2:0,setsar=1','-c:v','libx264','-crf','18','-preset','fast','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(final)],check=True,capture_output=True,timeout=120)
            video=final
        media=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)],text=True,timeout=15))
        v=next(s for s in media['streams'] if s['codec_type']=='video')
        assert (v['width'],v['height'])==((1920,1080) if a.target1080 else (2496,1408)) and int(v['nb_frames'])==69
        assert v['avg_frame_rate']=='24/1' and abs(float(media['format']['duration'])-69/24)<=1/24
        assert any(s['codec_type']=='audio' for s in media['streams'])
        def audio_hash(path):return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-'],text=True,timeout=20).strip()
        assert audio_hash(source)==audio_hash(video),'Audio stream changed'
        with source.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==original_sha
        os.link(video,output/'output.mp4')
        atomic_json(output/'evidence.json',{'kind':'operator-refiner1080' if a.target1080 else 'operator-refiner2x','source_sha256':original_sha,'elapsed_seconds':time.monotonic()-started,'media':media,'image_id':image,'audio_stream_unchanged':True})
        jobs.transition(jid,'succeeded');print('REFINER_TEST_SUCCEEDED',flush=True)
    except Exception as e:
        failure=type(e).__name__+': '+str(e);print(failure,flush=True)
        raise
    finally:
        stopped=cid is None
        if cid:
            try:
                kill_job(cid,jid);stopped=not inspect_job(cid,jid)['State']['Running']
            except Exception:pass
        if stopped:
            if jobs.get(jid)['state'] not in ('succeeded','failed','cancelled','interrupted'):
                jobs.transition(jid,'failed','REFINER_TEST_FAILED')
            if control:atomic_json(control/'active.json',{'container_id':None})
            heartbeat_stop.set()
            if guardian:guardian.terminate();guardian.wait(timeout=5)
        else:
            heartbeat_stop.set()
            print('STOP_UNCONFIRMED: reservation retained; guardian remains active',flush=True)

if __name__=='__main__':main()
