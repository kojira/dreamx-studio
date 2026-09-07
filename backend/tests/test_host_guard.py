import unittest
from dreamx.host_guard import projected_low,guarded_path
from dreamx.safety import GIB

class HostGuardTests(unittest.TestCase):
    def test_projection(self):
        self.assertTrue(projected_low([(0,80*GIB)],1,60*GIB))
        self.assertFalse(projected_low([(0,80*GIB)],1,79*GIB))
        self.assertFalse(projected_low([(0,80*GIB)],1,90*GIB))
        self.assertFalse(projected_low([],1,60*GIB))
    def test_no_path_escape(self):
        for value in ['/tmp','/sys/fs/cgroup/../../etc','relative']:
            with self.assertRaises(ValueError):guarded_path(value)
