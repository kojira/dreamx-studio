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
        r=self.client.post('/api/session',json={'secret':'x'*32},headers=self.origin)
        self.assertEqual(r.status_code,200)
        return {**self.origin,'x-csrf-token':r.json()['csrf']}
    def test_auth_closed(self):
        self.assertEqual(self.client.get('/api/status').status_code,401)
        self.assertEqual(self.client.post('/api/session',json={'secret':'x'*32}).status_code,401)
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
    def test_invalid_upload(self):
        headers=self.login()
        r=self.client.post('/api/inputs',files={'image':('bad.png',b'not an image','image/png')},headers=headers)
        self.assertEqual(r.status_code,422)
    def test_no_cross_site_and_no_csrf(self):
        self.login()
        self.assertEqual(self.client.post('/api/inputs',headers=self.origin).status_code,401)
        self.assertEqual(self.client.get('/api/status',headers={'host':'attacker.test'}).status_code,401)
    def test_login_limit_and_size(self):
        self.assertEqual(self.client.post('/api/session',content=b'x'*4097,headers=self.origin).status_code,413)
        for _ in range(5):
            self.assertEqual(self.client.post('/api/session',json={'secret':'bad'},headers=self.origin).status_code,401)
        self.assertEqual(self.client.post('/api/session',json={'secret':'x'*32},headers=self.origin).status_code,429)
