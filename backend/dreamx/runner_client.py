import json
import socket
from pathlib import Path

class SocketRunner:
    def __init__(self,path:Path): self.path=path
    def call(self,operation,**kwargs):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(5);s.connect(str(self.path))
            s.sendall(json.dumps({'op':operation,**kwargs}).encode()+b'\n')
            data=b''
            while b'\n' not in data:
                chunk=s.recv(4096)
                if not chunk: raise RuntimeError('Runner disconnected')
                data+=chunk
                if len(data)>65536: raise RuntimeError('Oversized response')
            result=json.loads(data.split(b'\n',1)[0])
            if result.get('error'): raise RuntimeError(result['error'])
            return result
    def status(self):
        try: return self.call('status')
        except (OSError,RuntimeError,ValueError): return {'runtime_ready':False,'reason':'RUNNER_UNAVAILABLE'}
    def submit(self,job):return self.call('submit',job_id=job['id'])
    def cancel(self,job_id):return self.call('cancel',job_id=job_id)
