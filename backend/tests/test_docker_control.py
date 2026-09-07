import unittest
import subprocess
from unittest.mock import patch
from dreamx.docker_control import verify_limits, kill_job
from dreamx.safety import GIB

class DockerControlTests(unittest.TestCase):
    def config(self):
        return {'Image':'sha256:expected','Config':{'User':'1001:1001'},'Mounts':[],
            'HostConfig':{'Memory':80*GIB,'MemorySwap':80*GIB,'Privileged':False,'PidMode':'',
            'RestartPolicy':{'Name':'no'},'NetworkMode':'none','CapDrop':['ALL'],'SecurityOpt':['no-new-privileges']}}

    def test_limits_fail_closed(self):
        def verify(c): verify_limits(c,expected_image_id='sha256:expected',expected_mounts=[],expected_user='1001:1001')
        verify(self.config())
        for key,value in [('Memory',0),('MemorySwap',-1),('Privileged',True),('NetworkMode','host'),('RestartPolicy',{'Name':'always'}),('CapDrop',[])]:
            c=self.config(); c['HostConfig'][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): verify(c)

    @patch('dreamx.docker_control.execute',side_effect=subprocess.CalledProcessError(1,['docker','kill']))
    @patch('dreamx.docker_control.inspect_job',side_effect=[{'State':{'Running':True}},{'State':{'Running':False}}])
    def test_concurrent_guardian_stop_is_idempotent(self,inspect,execute):
        kill_job('a'*64,'job')
        self.assertEqual(inspect.call_count,2)

    @patch('dreamx.docker_control.execute')
    @patch('dreamx.docker_control.inspect_job',side_effect=ValueError('ownership mismatch'))
    def test_never_kill_wrong_owner(self,inspect,execute):
        with self.assertRaises(ValueError): kill_job('a'*64,'job')
        execute.assert_not_called()
