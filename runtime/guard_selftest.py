"""Harmless real Docker test: dead runner heartbeat must stop only test job."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from dreamx.host_guard import atomic_json
from dreamx.docker_control import inspect_job,kill_job

root=Path(sys.argv[1]).resolve();root.mkdir(mode=0o700,parents=True,exist_ok=False)
job='heartbeat-selftest';cid=None;guardian=None
try:
    cid=subprocess.check_output(['docker','run','-d','--name','dreamx-'+root.name,
        '--label','org.dreamx.studio.job='+job,'--restart','no','--memory','128m','--memory-swap','128m',
        '--cpus','0.25','--pids-limit','32','--network','none','--cap-drop','ALL',
        '--security-opt','no-new-privileges','alpine:latest','sleep','300'],text=True).strip()
    c=inspect_job(cid,job);pid=c['State']['Pid']
    cg=next(x.split('::',1)[1] for x in Path(f'/proc/{pid}/cgroup').read_text().splitlines() if x.startswith('0::'))
    atomic_json(root/'runner-heartbeat.json',{'at':time.monotonic()})
    atomic_json(root/'active.json',{'container_id':cid,'job_id':job,'cgroup':'/sys/fs/cgroup'+cg,'started_at':time.monotonic()})
    guardian=subprocess.Popen([sys.executable,'-m','dreamx.host_guard','--root',str(root)])
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        if not inspect_job(cid,job)['State']['Running']:break
        time.sleep(.25)
    assert not inspect_job(cid,job)['State']['Running'],'Guardian failed to stop harmless test'
    status=json.loads((root/'guard-status.json').read_text())
    assert status['reason']=='RUNNER_HEARTBEAT_LOST',status
    print(json.dumps({'test':'independent guardian detects dead runner heartbeat','result':'PASS','model_loaded':False,'status':status}))
finally:
    if cid:kill_job(cid,job)
    if guardian:
        guardian.terminate();guardian.wait(timeout=5)
