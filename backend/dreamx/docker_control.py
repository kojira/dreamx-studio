"""Narrow Docker boundary. IDs must be bound to a known DreamX job."""
import json
import subprocess
from .safety import GIB, exact_container_id

LABEL='org.dreamx.studio.job'

def execute(args):
    return subprocess.run(['docker',*args],text=True,capture_output=True,check=True,timeout=5).stdout

def inspect_job(container_id: str, job_id: str):
    target=exact_container_id(container_id)
    data=json.loads(execute(['inspect',target]))
    if len(data)!=1 or data[0]['Id']!=target:
        raise ValueError('Container identity mismatch')
    c=data[0]
    if c['Config'].get('Labels',{}).get(LABEL)!=job_id:
        raise ValueError('Job ownership mismatch')
    return c

def verify_limits(c, *, expected_image_id, expected_mounts, expected_user):
    h=c['HostConfig']
    if c['Image']!=expected_image_id: raise ValueError('Image mismatch')
    if h['Memory']!=80*GIB or h['MemorySwap']!=80*GIB: raise ValueError('Memory limits missing')
    if h.get('Privileged') or h.get('PidMode')=='host': raise ValueError('Unsafe privileges')
    if h['RestartPolicy']['Name']!='no': raise ValueError('Unexpected restart policy')
    if c['Config']['User']!=expected_user or not expected_user.split(':')[0].isdigit() or int(expected_user.split(':')[0])==0:
        raise ValueError('Expected explicit non-root UID')
    if h.get('NetworkMode')!='none': raise ValueError('Inference must have no network')
    if h.get('CapDrop')!=['ALL'] or 'no-new-privileges' not in h.get('SecurityOpt',[]):
        raise ValueError('Security constraints missing')
    actual=sorted([(v['Type'],v['Source'],v['Destination'],v['RW']) for v in c['Mounts']])
    if actual!=sorted(expected_mounts): raise ValueError('Mount mismatch')

def kill_job(container_id, job_id):
    c=inspect_job(container_id,job_id)
    if c['State']['Running']:
        try:
            execute(['kill','--signal','KILL',exact_container_id(container_id)])
        except subprocess.CalledProcessError:
            # The independent guardian may have stopped it between inspect/kill.
            # Treat only a freshly verified stopped exact job as success.
            if inspect_job(container_id,job_id)['State']['Running']:
                raise
