"""Operator-side additional SSH liveness evidence; independent host guard remains primary."""
import argparse
import json
import shlex
import subprocess
import time
import uuid
import re

p=argparse.ArgumentParser();p.add_argument('--target',required=True);p.add_argument('--container',required=True);p.add_argument('--job',required=True);a=p.parse_args()
assert re.fullmatch('[0-9a-f]{64}',a.container)
assert str(uuid.UUID(a.job))==a.job
base=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=2',a.target]
read="python3 -c "+shlex.quote('from pathlib import Path;print((Path.home()/"dreamx-studio-runtime/control/guard-status.json").read_text())')
kill="PYTHONPATH=$HOME/dreamx-studio-runtime/build python3 -c "+shlex.quote(f'from dreamx.docker_control import kill_job;kill_job({a.container!r},{a.job!r})')
failures=0;deadline=time.monotonic()+10800
while time.monotonic()<deadline:
    started=time.monotonic()
    try:
        r=subprocess.run(base+[read],capture_output=True,text=True,timeout=2,check=True)
        s=json.loads(r.stdout);failures=0
        print(json.dumps({'at':time.time(),'ssh_seconds':time.monotonic()-started,'available':s['available'],'worker_memory':s.get('worker_memory'),'reason':s.get('reason')}),flush=True)
        if s.get('container_id')!=a.container:break
    except Exception:
        failures+=1;print(json.dumps({'at':time.time(),'ssh_failure':failures}),flush=True)
        if failures>=2:
            try:subprocess.run(base+[kill],timeout=5,check=True,capture_output=True)
            except Exception:print('SSH abort request could not be delivered; independent host guard remains primary',flush=True)
            break
    time.sleep(2)
