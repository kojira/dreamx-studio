import ast,json,time,unittest
from pathlib import Path
from unittest.mock import patch

class RefinerHandshakeTests(unittest.TestCase):
    def test_exact_identity_and_heartbeat(self):
        path=Path(__file__).resolve().parents[2]/'runtime/refiner_test_worker.py'
        tree=ast.parse(path.read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='healthy')
        env={'json':json,'time':time,'control':Path('/virtual'),'spec':{'job_id':'test'}}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),env)
        data={'active.json':{'job_id':'test','container_id':'a'*64},'guard-status.json':{'container_id':'a'*64,'at':99,'reason':None},'runner-heartbeat.json':{'at':99}}
        with patch.object(Path,'read_text',autospec=True,side_effect=lambda p:json.dumps(data[p.name])),patch('time.monotonic',return_value=100):
            self.assertTrue(env['healthy']())
            data['active.json']['job_id']='other';self.assertFalse(env['healthy']())
            data['active.json']['job_id']='test';data['guard-status.json']['container_id']='b'*64;self.assertFalse(env['healthy']())
            data['guard-status.json']['container_id']='a'*64;data['runner-heartbeat.json']['at']=97;self.assertFalse(env['healthy']())
            data['runner-heartbeat.json']['at']=99;data['guard-status.json']['reason']='HOST_MEMORY_GUARD';self.assertFalse(env['healthy']())
