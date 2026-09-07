import unittest
from unittest.mock import Mock, patch
from dreamx.guardian import guard_job, kill_container
from dreamx.safety import GIB, Sample

class GuardianTests(unittest.TestCase):
    def test_low_memory_kills_only_admitted_id(self):
        kill = Mock(); event = Mock()
        reason = guard_job('b'*64, lambda: Sample(31*GIB, 200*GIB, 1, 0), lambda: True, kill, event)
        self.assertEqual(reason, 'HOST_MEMORY_GUARD')
        kill.assert_called_once_with('b'*64)
        event.assert_called_once_with(reason)

    def test_sensor_failure_fails_closed(self):
        observe = Mock(side_effect=OSError('unavailable')); kill = Mock()
        self.assertEqual(guard_job('b'*64, observe, lambda: True, kill), 'TELEMETRY_ERROR')
        kill.assert_called_once()

    def test_no_kill_after_exit(self):
        kill = Mock()
        self.assertEqual(guard_job('b'*64, Mock(), lambda: False, kill), 'EXITED')
        kill.assert_not_called()

    def test_kill_failure_is_not_success(self):
        kill = Mock(side_effect=RuntimeError('docker unavailable')); event = Mock()
        with self.assertRaises(RuntimeError):
            guard_job('b'*64, lambda: Sample(1, 1, 1, 0), lambda: True, kill, event)
        event.assert_not_called()

    def test_timeout(self):
        clock = Mock(side_effect=[0, 3600]); kill = Mock()
        self.assertEqual(guard_job('b'*64, lambda: Sample(100*GIB,200*GIB,1,0),lambda:True,kill,clock=clock), 'TIME_LIMIT')

    @patch('dreamx.guardian.subprocess.run')
    def test_kill_argv(self, run):
        kill_container('c'*64)
        self.assertEqual(run.call_args.args[0], ['docker','kill','--signal','KILL','c'*64])
        self.assertNotIn('shell', run.call_args.kwargs)
        with self.assertRaises(ValueError): kill_container('--all')
        self.assertEqual(run.call_count,1)
