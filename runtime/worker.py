"""Fail-closed worker wrapper: never import/load the model before guardian ACK."""
import json
import os
import signal
import subprocess
import time
from pathlib import Path

control=Path('/control')
child=None

def heartbeat_ok():
    guard=json.loads((control/'guard-status.json').read_text())
    runner=json.loads((control/'runner-heartbeat.json').read_text())
    now=time.monotonic()
    return (0<=now-guard['at']<=2 and 0<=now-runner['at']<=2 and not guard.get('reason'))

def terminate(signum=None,frame=None):
    if child is not None and child.poll() is None:
        os.killpg(child.pid,signal.SIGTERM)
        try: child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.wait()
    raise SystemExit(143)

signal.signal(signal.SIGTERM,terminate)
spec=json.loads(Path('/job/spec.json').read_text())
start=time.monotonic()
while True:
    try:
        go=json.loads((control/'go.json').read_text())
        if go.get('job_id')==spec['job_id']:break
    except (OSError,ValueError):pass
    if time.monotonic()-start>30: raise SystemExit('GUARD_START_TIMEOUT')
    time.sleep(.1)
if not heartbeat_ok():raise SystemExit('GUARD_UNAVAILABLE')
assert spec['preset'] in ('smoke','trial')
assert isinstance(spec['prompt'],str) and 1<=len(spec['prompt'])<=4000
assert isinstance(spec['seed'],int) and 0<=spec['seed']<=2147483647
spatial_tokens=spec.get('spatial_tokens',220)
assert type(spatial_tokens) is int and spatial_tokens in (220,440,880)
args=['python','inference.py','--model_name','/weights/wan2.2_ti2v_5b',
      '--transformer_path','/weights/creator','--audio_vae_path','/weights/audio_vae',
      '--image','/input.png','--prompt',spec['prompt'],'--output','/job/output.mp4',
      '--duration','1' if spec['preset']=='smoke' else '3','--fps','24',
      '--num_inference_steps','4' if spec['preset']=='smoke' else '50',
      '--target_spatial_tokens',str(spatial_tokens),'--weight_dtype','bfloat16',
      '--text_encoder_cpu_offload','--vae_cpu_offload','--seed',str(spec['seed'])]
child=subprocess.Popen(args,start_new_session=True)
while child.poll() is None:
    try: healthy=heartbeat_ok()
    except Exception: healthy=False
    if not healthy: terminate()
    time.sleep(.25)
raise SystemExit(child.returncode)
