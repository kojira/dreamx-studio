"""Private UNIX socket supervisor; run on host, separate from GPU cgroup."""
import argparse
import json
import os
import secrets
import shutil
import socketserver
import subprocess
import threading
import time
from pathlib import Path
from .docker_control import inspect_job, kill_job, verify_limits, execute
from .host_guard import atomic_json, load
from .paths import id_path
from .jobs import Jobs
from .safety import GIB, Sample, admission, memory_available

class Supervisor:
    def __init__(self,root):
        self.root=root;self.control=root/'control';self.app=root/'app'
        self.control.mkdir(mode=0o700,exist_ok=True);self.app.mkdir(mode=0o700,exist_ok=True)
        self.jobs=Jobs(self.app/'jobs.sqlite');self.lock=threading.Lock();self.active=None;self.cancelled=threading.Event()
        self.config=load(root/'config.json')
        # Reconciliation is deliberately fail-closed, not an automatic broad stop.
        if (self.control/'active.json').exists() and load(self.control/'active.json').get('container_id'):
            raise RuntimeError('Previous worker requires exact-job reconciliation before startup')
        self.jobs.recover_after_worker_reconciliation()
        threading.Thread(target=self.heartbeat,daemon=True).start()

    def heartbeat(self):
        while True:
            atomic_json(self.control/'runner-heartbeat.json',{'at':time.monotonic()})
            time.sleep(.5)

    def status(self):
        available=memory_available(Path('/proc/meminfo').read_text()); disk=shutil.disk_usage(self.root).free
        try:
            guard=load(self.control/'guard-status.json'); age=time.monotonic()-guard['at']
            healthy=not guard.get('reason')
        except Exception:age=999;healthy=False
        ready=self.config.get('validated',False) and healthy
        reason=admission(Sample(available,disk,0,age),runtime_ready=ready,active=self.active is not None)
        return {'runtime_ready':reason is None,'reason':reason,'available_gib':available/GIB,'active_job_id':self.active}

    def submit(self,job_id):
        with self.lock:
            status=self.status()
            if not status['runtime_ready']:raise RuntimeError(status['reason'])
            job=self.jobs.get(job_id)
            if job['state']!='admitted':raise ValueError('Not admitted')
            id_path(self.app/'jobs',job_id)
            self.active=job_id;self.cancelled.clear()
            threading.Thread(target=self.run,args=(job,),daemon=True).start()
        return {'accepted':True}

    def cancel(self,job_id):
        with self.lock:
            if self.active!=job_id:raise ValueError('No matching active job')
            self.cancelled.set()
        return {'state':'cancelling'}

    def run(self,job):
        job_id=job['id'];cid=None;failure=None
        try:
            self.jobs.transition(job_id,'preparing')
            payload=json.loads(job['payload']);image=id_path(self.app/'inputs',payload['input_id'],'.png')
            if not image.is_file():raise ValueError('Input missing')
            output=id_path(self.app/'jobs',job_id);output.mkdir(mode=0o700,parents=True,exist_ok=False)
            seed=payload.get('seed');seed=secrets.randbelow(2147483648) if seed is None else seed
            spec={**payload,'seed':seed,'job_id':job_id}
            atomic_json(output/'spec.json',spec)
            image_id=self.config['image_id'];user=f'{os.getuid()}:{os.getgid()}'
            mounts=[('bind',str(self.root/'weights'),'/weights',False),('bind',str(image),'/input.png',False),
                    ('bind',str(output),'/job',True),('bind',str(self.control),'/control',False),
                    ('bind',str(self.root/'build/worker.py'),'/opt/worker.py',False)]
            args=['create','--name','dreamx-job-'+job_id,'--label','org.dreamx.studio.job='+job_id,
                  '--restart','no','--memory','80g','--memory-swap','80g','--cpus','8','--pids-limit','512',
                  '--network','none','--gpus','all','--user',user,'--cap-drop','ALL','--security-opt','no-new-privileges',
                  '--env','USER=dreamx','--env','HOME=/tmp','--env','TORCHINDUCTOR_CACHE_DIR=/tmp/dreamx-inductor',
                  '--env','HF_HUB_OFFLINE=1','--env','TRANSFORMERS_OFFLINE=1',
                  '--log-opt','max-size=10m','--log-opt','max-file=3']
            for typ,src,dst,rw in mounts:
                args+=['--mount',f'type={typ},src={src},dst={dst}'+('' if rw else ',readonly')]
            args += [image_id,'python','/opt/worker.py']
            cid=execute(args).strip()
            c=inspect_job(cid,job_id);verify_limits(c,expected_image_id=image_id,expected_mounts=mounts,expected_user=user)
            execute(['start',cid]);c=inspect_job(cid,job_id);pid=c['State']['Pid']
            if not c['State']['Running'] or pid<=0:raise RuntimeError('Worker failed to start')
            cgline=Path(f'/proc/{pid}/cgroup').read_text().strip().splitlines()
            cg=next(x.split('::',1)[1] for x in cgline if x.startswith('0::'))
            cgroup=Path('/sys/fs/cgroup')/cg.lstrip('/')
            assert int((cgroup/'memory.max').read_text())==80*GIB
            assert int((cgroup/'memory.swap.max').read_text())==0
            atomic_json(self.control/'active.json',{'container_id':cid,'job_id':job_id,'cgroup':str(cgroup),'started_at':time.monotonic()})
            # Guardian must observe this exact worker before granting model load.
            deadline=time.monotonic()+5
            while True:
                guard=load(self.control/'guard-status.json')
                if guard.get('container_id')==cid and not guard.get('reason') and 0<=time.monotonic()-guard['at']<2:break
                if time.monotonic()>deadline:raise RuntimeError('No guardian acknowledgement')
                time.sleep(.1)
            self.jobs.transition(job_id,'generating')
            atomic_json(self.control/'go.json',{'job_id':job_id})
            while True:
                c=inspect_job(cid,job_id)
                if not c['State']['Running']:break
                if self.cancelled.is_set():
                    self.jobs.transition(job_id,'cancelling')
                    execute(['kill','--signal','TERM',cid]);deadline=time.monotonic()+5
                    while inspect_job(cid,job_id)['State']['Running'] and time.monotonic()<deadline:time.sleep(.2)
                    kill_job(cid,job_id);self.jobs.transition(job_id,'cancelled');return
                guard=load(self.control/'guard-status.json')
                if not 0<=time.monotonic()-guard['at']<=2 or guard.get('reason'):
                    failure=guard.get('reason') or 'GUARDIAN_LOST';raise RuntimeError(failure)
                with (output/'resources.jsonl').open('a') as f:f.write(json.dumps(guard)+'\n')
                time.sleep(.5)
            if c['State']['OOMKilled']:failure='WORKER_OOM';raise RuntimeError(failure)
            if c['State']['ExitCode']!=0:
                failure='INFERENCE_FAILED'
                try:
                    aborted=load(self.control/'last-abort.json')
                    if aborted.get('container_id')==cid:failure=aborted['reason']
                except (OSError,ValueError):pass
                raise RuntimeError(failure)
            self.jobs.transition(job_id,'muxing')
            media=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output/'output.mp4')],text=True,timeout=15))
            types={s['codec_type'] for s in media['streams']}
            if not {'audio','video'}<=types:raise ValueError('Missing audio or video')
            expected=(21 if payload['preset']=='smoke' else 69)/24
            if abs(float(media['format']['duration'])-expected)>1/24:raise ValueError('Duration mismatch')
            if not (output/'output.wav').is_file():raise ValueError('Missing WAV')
            atomic_json(output/'evidence.json',{'seed':seed,'image_id':image_id,'media':media})
            self.jobs.transition(job_id,'succeeded')
        except Exception as exc:
            failure=failure or type(exc).__name__.upper()
            if cid:
                try:kill_job(cid,job_id)
                except Exception:
                    # Keep active slot locked when exact worker stop is unconfirmed.
                    atomic_json(self.control/'runner-error.json',{'job_id':job_id,'reason':'STOP_UNCONFIRMED'})
                    return
            current=self.jobs.get(job_id)['state']
            if current not in ('succeeded','failed','cancelled','interrupted'):
                self.jobs.transition(job_id,'failed',failure)
        finally:
            stopped=cid is None
            if cid:
                try:stopped=not inspect_job(cid,job_id)['State']['Running']
                except Exception:pass
            if stopped:
                # A concurrent guardian stop can make docker kill return an error.
                # Reconcile terminal DB state only after stop is independently confirmed.
                current=self.jobs.get(job_id)['state']
                if current not in ('succeeded','failed','cancelled','interrupted'):
                    self.jobs.transition(job_id,'failed',failure or 'WORKER_STOPPED')
                atomic_json(self.control/'active.json',{'container_id':None})
                with self.lock:self.active=None


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);args=p.parse_args()
    os.umask(0o077);root=args.root.resolve();supervisor=Supervisor(root)
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(5)
            try:
                data=self.rfile.readline(65537)
                if len(data)>65536:raise ValueError('Request too large')
                request=json.loads(data);op=request.get('op')
                if op=='status':result=supervisor.status()
                elif op=='submit':result=supervisor.submit(request['job_id'])
                elif op=='cancel':result=supervisor.cancel(request['job_id'])
                else:raise ValueError('Unknown operation')
            except Exception as exc:result={'error':type(exc).__name__}
            self.wfile.write(json.dumps(result).encode()+b'\n')
    socket_path=root/'control/runner.sock'
    # Never unlink an unknown/stale socket automatically; operator must reconcile.
    with socketserver.ThreadingUnixStreamServer(str(socket_path),Handler) as server:
        os.chmod(socket_path,0o600);server.serve_forever()

if __name__=='__main__':main()
