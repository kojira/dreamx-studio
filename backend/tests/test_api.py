import io
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from dreamx.api import create_app

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.client=TestClient(create_app(Path(self.temp.name),'x'*32),base_url='http://127.0.0.1:8780')
        self.origin={'origin':'http://127.0.0.1:8780'}
    def login(self):
        r=self.client.post('/api/session',json={},headers=self.origin)
        self.assertEqual(r.status_code,200)
        return {**self.origin,'x-csrf-token':r.json()['csrf']}
    def test_auth_closed(self):
        self.assertEqual(self.client.get('/api/status').status_code,401)
        self.assertEqual(self.client.post('/api/session',json={}).status_code,401)
        headers=self.login()
        self.assertFalse(self.client.get('/api/status').json()['runtime_ready'])
        self.assertEqual(self.client.delete('/api/session',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/status').status_code,401)
    def test_image_and_no_runner(self):
        headers=self.login(); data=io.BytesIO(); Image.new('RGB',(16,16)).save(data,format='PNG')
        r=self.client.post('/api/inputs',files={'image':('unsafe../../name.png',data.getvalue(),'image/png')},headers=headers)
        self.assertEqual(r.status_code,201,r.text)
        item=r.json()
        self.assertEqual(item['width'],16)
        r=self.client.post('/api/jobs',json={'input_id':item['input_id'],'prompt':'test','preset':'trial'},headers={**headers,'idempotency-key':'test'})
        self.assertEqual(r.status_code,503)
    def test_idempotency_during_active_job(self):
        class FakeRunner:
            active=False
            def status(self):return {'runtime_ready':not self.active,'reason':'BUSY' if self.active else None}
            def submit(self,job):self.active=True
            def cancel(self,job_id):pass
        runner=FakeRunner()
        self.client=TestClient(create_app(Path(self.temp.name),'x'*32,runner),base_url='http://127.0.0.1:8780')
        headers=self.login();data=io.BytesIO();Image.new('RGB',(16,16)).save(data,format='PNG')
        item=self.client.post('/api/inputs',files={'image':('a.png',data.getvalue(),'image/png')},headers=headers).json()
        body={'input_id':item['input_id'],'prompt':'test','preset':'trial'}
        first=self.client.post('/api/jobs',json=body,headers={**headers,'idempotency-key':'same'})
        again=self.client.post('/api/jobs',json=body,headers={**headers,'idempotency-key':'same'})
        self.assertEqual(first.status_code,202);self.assertEqual(first.json(),again.json())
        other=self.client.post('/api/jobs',json=body,headers={**headers,'idempotency-key':'other'})
        self.assertEqual(other.status_code,409)

    def test_legacy_job_idempotency_defaults_to_220(self):
        headers=self.login();data=io.BytesIO();Image.new('RGB',(16,16)).save(data,format='PNG')
        item=self.client.post('/api/inputs',files={'image':('a.png',data.getvalue(),'image/png')},headers=headers).json()
        payload={'input_id':item['input_id'],'prompt':'test','seed':None,'preset':'trial'}
        old,_=self.client.app.state.jobs.create('legacy-resolution',payload)
        response=self.client.post('/api/jobs',json=payload,headers={**headers,'idempotency-key':'legacy-resolution'})
        self.assertEqual(response.status_code,202);self.assertEqual(response.json()['job_id'],old['id'])
        conflict=self.client.post('/api/jobs',json={**payload,'spatial_tokens':880},headers={**headers,'idempotency-key':'legacy-resolution'})
        self.assertEqual(conflict.status_code,409)
        self.assertEqual(self.client.get('/api/jobs/'+old['id']).json()['spatial_tokens'],220)

    def test_resolution_values_and_legacy(self):
        from dreamx.api import JobRequest
        from pydantic import ValidationError
        for value in (220,440,880):
            self.assertEqual(JobRequest(input_id='test',prompt='x',spatial_tokens=value).spatial_tokens,value)
        self.assertEqual(JobRequest(input_id='test',prompt='x').spatial_tokens,220)
        for value in ('880',880.0,True):
            with self.assertRaises(ValidationError):JobRequest(input_id='test',prompt='x',spatial_tokens=value)
        headers=self.login()
        response=self.client.post('/api/jobs',json={'input_id':'test','prompt':'x','spatial_tokens':999},headers={**headers,'idempotency-key':'invalid-token'})
        self.assertEqual(response.status_code,422)

    def test_invalid_upload(self):
        headers=self.login()
        r=self.client.post('/api/inputs',files={'image':('bad.png',b'not an image','image/png')},headers=headers)
        self.assertEqual(r.status_code,422)
    def test_no_cross_site_and_no_csrf(self):
        self.login()
        self.assertEqual(self.client.post('/api/inputs',headers=self.origin).status_code,401)
        self.assertEqual(self.client.get('/api/status',headers={'host':'attacker.test'}).status_code,401)
    def test_session_body_and_size(self):
        self.assertEqual(self.client.post('/api/session',content=b'x'*4097,headers=self.origin).status_code,413)
        self.assertEqual(self.client.post('/api/session',json={'secret':'not-needed'},headers=self.origin).status_code,422)
        self.assertEqual(self.client.post('/api/session',json={},headers=self.origin).status_code,200)
