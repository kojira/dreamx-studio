import unittest
import json
import time
from pathlib import Path
from unittest.mock import patch
from dreamx.host_guard import projected_low,guarded_path,sample_guard
from dreamx.safety import GIB

class HostGuardTests(unittest.TestCase):
    def test_projection(self):
        self.assertTrue(projected_low([(0,80*GIB)],1,60*GIB))
        self.assertFalse(projected_low([(0,80*GIB)],1,79*GIB))
        self.assertFalse(projected_low([(0,80*GIB)],1,90*GIB))
        self.assertFalse(projected_low([],1,60*GIB))
    def test_exited_worker_is_not_telemetry_failure(self):
        def read(path,*args,**kwargs):
            if str(path)=='/proc/meminfo':return 'MemAvailable: 100000000 kB'
            if path.name=='active.json':return json.dumps({'container_id':'a'*64,'job_id':'test','cgroup':'/sys/fs/cgroup/gone','started_at':time.monotonic()})
            if path.name=='runner-heartbeat.json':return json.dumps({'at':time.monotonic()})
            raise FileNotFoundError()
        with patch.object(Path,'read_text',autospec=True,side_effect=read),patch.object(Path,'exists',return_value=True),patch('dreamx.host_guard.inspect_job',return_value={'State':{'Running':False}}):
            result,active=sample_guard(Path('/virtual'))
        self.assertIsNone(result['reason']);self.assertTrue(result['worker_exited']);self.assertIsNone(active)

    def test_no_path_escape(self):
        for value in ['/tmp','/sys/fs/cgroup/../../etc','relative']:
            with self.assertRaises(ValueError):guarded_path(value)
