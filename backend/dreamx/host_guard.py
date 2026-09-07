"""Independent host process. Never deploy inside the GPU worker cgroup."""
import argparse
import json
import os
import time
from pathlib import Path
from collections import deque
from .safety import GIB, memory_available, exact_container_id
from .docker_control import kill_job


def atomic_json(path:Path,data:dict):
    temp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    with temp.open('w') as f: json.dump(data,f)
    os.replace(temp,path)


def load(path):
    return json.loads(path.read_text())


def guarded_path(value):
    path=Path(value)
    base=Path('/sys/fs/cgroup')
    if not path.is_absolute() or not path.resolve().is_relative_to(base):
        raise ValueError('Invalid cgroup path')
    return path


def sample_guard(root:Path):
    """One sample; returning an abort request does not claim kill succeeded."""
    now=time.monotonic(); available=memory_available(Path('/proc/meminfo').read_text())
    result={'at':now,'available':available,'container_id':None,'reason':None}
    active_path=root/'active.json'
    if not active_path.exists(): return result,None
    active=load(active_path)
    if not active.get('container_id'): return result,None
    target=exact_container_id(active['container_id']); result['container_id']=target
    try:
        runner=load(root/'runner-heartbeat.json')
        age=now-float(runner['at'])
        if not 0<=age<=2: result['reason']='RUNNER_HEARTBEAT_LOST'
        cgroup=guarded_path(active['cgroup'])
        used=int((cgroup/'memory.current').read_text())
        result['worker_memory']=used
        if available<48*GIB: result['reason']='HOST_MEMORY_GUARD'
        if used>=72*GIB: result['reason']='WORKER_MEMORY_GUARD'
        if now-float(active['started_at'])>=3600: result['reason']='TIME_LIMIT'
    except Exception:
        result['reason']='TELEMETRY_ERROR'
    return result,active


def projected_low(history, now, available):
    if not history:return False
    elapsed=now-history[0][0]
    rate=max(0,(history[0][1]-available)/elapsed) if elapsed>0 else 0
    return available-2*rate<48*GIB


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True); args=parser.parse_args()
    root=args.root.resolve(); os.umask(0o077)
    history=deque()
    while True:
        try:
            result,active=sample_guard(root)
            if active:
                history.append((result['at'],result['available']))
                while len(history)>1 and result['at']-history[0][0]>1: history.popleft()
                if len(history)>1:
                    if projected_low(history,result['at'],result['available']): result['reason']='PROJECTED_MEMORY_GUARD'
            else: history.clear()
            if result['reason'] and active:
                # Publish the reason before potentially blocking on the Docker API.
                atomic_json(root/'guard-status.json',result)
                atomic_json(root/'last-abort.json',{**result,'job_id':active['job_id']})
                kill_job(active['container_id'],active['job_id'])
                result['kill_requested']=True
            atomic_json(root/'guard-status.json',result)
        except Exception:
            # Do not overwrite a recent failure with a false healthy heartbeat.
            # The separate runner detects a stale guardian and kills its exact worker.
            pass
        time.sleep(.1)

if __name__=='__main__':main()
