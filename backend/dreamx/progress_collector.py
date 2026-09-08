"""Read-only Docker progress observer; does not start/stop any container."""
import argparse
import json
import time
from pathlib import Path
from .docker_control import execute,inspect_job
from .host_guard import atomic_json
from .paths import id_path
from .progress import parse_progress


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    while True:
        try:
            active=json.loads((root/'control/active.json').read_text())
            if active.get('container_id'):
                c=inspect_job(active['container_id'],active['job_id'])
                # subprocess stderr carries tqdm; execute() returns only stdout.
                import subprocess
                r=subprocess.run(['docker','logs','--tail','1000',c['Id']],capture_output=True,text=True,timeout=3)
                if r.returncode==0:
                    progress=parse_progress(r.stdout+'\n'+r.stderr)
                    output=id_path(root/'app/jobs',active['job_id'])
                    # A busy log tail must not erase an already observed step.
                    if progress.get('phase')=='preparing':
                        try:
                            previous=json.loads((output/'progress.json').read_text())
                            if previous.get('phase') in ('generating','encoding_output','refining','decoding','muxing'):
                                progress=previous
                        except (OSError,ValueError):pass
                    progress['at']=time.time()
                    atomic_json(output/'progress.json',progress)
        except Exception:
            # Missing/stale progress is visible as such; observer errors must never
            # stop a user's job or produce fabricated progress.
            pass
        time.sleep(2)

if __name__=='__main__':main()
