import unittest
import json
import time
from pathlib import Path
from unittest.mock import patch
from dreamx.host_guard import guarded_path,sample_guard
from dreamx.safety import GIB

class HostGuardTests(unittest.TestCase):
    def test_actual_memory_only(self):
        available=[100*GIB]
        def read(path,*args,**kwargs):
            if str(path)=='/proc/meminfo':return f'MemAvailable: {available[0]//1024} kB'
            if path.name=='active.json':return json.dumps({'container_id':'a'*64,'job_id':'test','cgroup':'/sys/fs/cgroup/test','started_at':time.monotonic()})
            if path.name=='runner-heartbeat.json':return json.dumps({'at':time.monotonic()})
            if path.name=='memory.current':return str(20*GIB)
            raise FileNotFoundError()
        with patch.object(Path,'read_text',autospec=True,side_effect=read),patch.object(Path,'exists',return_value=True),patch('time.monotonic',return_value=100.0):
            for value in (100*GIB,68*GIB,30*GIB,24*GIB):
                available[0]=value
                self.assertIsNone(sample_guard(Path('/virtual'))[0]['reason'])
            available[0]=24*GIB-1024
            self.assertEqual(sample_guard(Path('/virtual'))[0]['reason'],'HOST_MEMORY_GUARD')
    def test_exited_worker_is_not_telemetry_failure(self):
        def read(path,*args,**kwargs):
            if str(path)=='/proc/meminfo':return 'MemAvailable: 100000000 kB'
            if path.name=='active.json':return json.dumps({'container_id':'a'*64,'job_id':'test','cgroup':'/sys/fs/cgroup/gone','started_at':time.monotonic()})
            if path.name=='runner-heartbeat.json':return json.dumps({'at':time.monotonic()})
            raise FileNotFoundError()
        with patch.object(Path,'read_text',autospec=True,side_effect=read),patch.object(Path,'exists',return_value=True),patch('dreamx.host_guard.inspect_job',return_value={'State':{'Running':False}}):
            result,active=sample_guard(Path('/virtual'))
        self.assertIsNone(result['reason']);self.assertTrue(result['worker_exited']);self.assertIsNone(active)

    def test_extended_time_budget(self):
        age=[3600]
        def read(path,*args,**kwargs):
            if str(path)=='/proc/meminfo':return 'MemAvailable: 100000000 kB'
            if path.name=='active.json':return json.dumps({'container_id':'a'*64,'job_id':'test','cgroup':'/sys/fs/cgroup/test','started_at':20000-age[0]})
            if path.name=='runner-heartbeat.json':return json.dumps({'at':20000})
            if path.name=='memory.current':return str(20*GIB)
            raise FileNotFoundError()
        with patch.object(Path,'read_text',autospec=True,side_effect=read),patch.object(Path,'exists',return_value=True),patch('time.monotonic',return_value=20000):
            for elapsed in (3600,6000,10799):
                age[0]=elapsed;self.assertIsNone(sample_guard(Path('/virtual'))[0]['reason'])
            age[0]=10800;self.assertEqual(sample_guard(Path('/virtual'))[0]['reason'],'TIME_LIMIT')

    def test_no_path_escape(self):
        for value in ['/tmp','/sys/fs/cgroup/../../etc','relative']:
            with self.assertRaises(ValueError):guarded_path(value)
