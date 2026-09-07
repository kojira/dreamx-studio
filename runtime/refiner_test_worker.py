"""Operator-only Refiner test; model load follows exact guardian acknowledgement."""
import json,os,signal,subprocess,time
from pathlib import Path
control=Path('/control');spec=json.loads(Path('/job/spec.json').read_text());child=None

def healthy():
    g=json.loads((control/'guard-status.json').read_text())
    r=json.loads((control/'runner-heartbeat.json').read_text())
    a=json.loads((control/'active.json').read_text());now=time.monotonic()
    return (a.get('job_id')==spec['job_id'] and g.get('container_id')==a.get('container_id')
            and 0<=now-g['at']<=2 and 0<=now-r['at']<=2 and not g.get('reason'))

def stop(*unused):
    if child is not None and child.poll() is None:
        os.killpg(child.pid,signal.SIGTERM)
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
    raise SystemExit(143)

signal.signal(signal.SIGTERM,stop)
start=time.monotonic()
while True:
    try:
        if json.loads((control/'go.json').read_text()).get('job_id')==spec['job_id'] and healthy():break
    except (OSError,ValueError,KeyError):pass
    if time.monotonic()-start>30:raise SystemExit('GUARD_START_TIMEOUT')
    time.sleep(.1)
env={**os.environ,'INPUT':'/input.mp4','OUTPUT':'/job/refined','NUM_FRAMES':'-1','SR_SCALE':'2.0','SEED':'42','ENABLE_FP8':'0','ENABLE_NU_LIGHTVAE':'0'}
if os.environ.get('REFINER_TARGET1080')=='1':env['SR_SCALE']=str(1088/704)
command=['bash','run_inference.sh']
if os.environ.get('CHECK_REFINER_ATTENTION')=='1':
    command=['bash','-c','python /opt/check_refiner_attention.py /opt/dreamx/video_refiner/wan/modules/sr_dit/attention.py --cuda && exec bash run_inference.sh']
child=subprocess.Popen(command,cwd='/opt/dreamx/video_refiner',env=env,start_new_session=True)
while child.poll() is None:
    try:ok=healthy()
    except Exception:ok=False
    if not ok:stop()
    time.sleep(.25)
raise SystemExit(child.returncode)
