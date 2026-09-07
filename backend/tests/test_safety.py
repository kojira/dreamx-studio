import unittest
from dataclasses import replace
from dreamx.safety import GIB, Sample, admission, emergency, exact_container_id, memory_available

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.sample = Sample(100*GIB, 200*GIB, 10*GIB, 0.1)

    def test_admission(self):
        self.assertIsNone(admission(self.sample, runtime_ready=True, active=False))
        for sample, ready, active, expected in [
            (self.sample, True, True, 'BUSY'),
            (self.sample, False, False, 'RUNTIME_NOT_READY'),
            (replace(self.sample, available=96*GIB-1), True, False, 'INSUFFICIENT_MEMORY'),
            (replace(self.sample, disk_free=150*GIB-1), True, False, 'INSUFFICIENT_DISK'),
            (replace(self.sample, guardian_age=2), True, False, 'GUARDIAN_UNAVAILABLE'),
            (replace(self.sample, guardian_age=float('nan')), True, False, 'GUARDIAN_UNAVAILABLE'),
        ]:
            with self.subTest(expected=expected):
                self.assertEqual(admission(sample, runtime_ready=ready, active=active), expected)

    def test_emergency_boundaries(self):
        self.assertIsNone(emergency(replace(self.sample, available=24*GIB, worker_memory=72*GIB-1)))
        self.assertEqual(emergency(replace(self.sample, available=24*GIB-1)), 'HOST_MEMORY_GUARD')
        self.assertEqual(emergency(replace(self.sample, worker_memory=72*GIB)), 'WORKER_MEMORY_GUARD')
        self.assertEqual(emergency(replace(self.sample, worker_memory=None)), 'WORKER_TELEMETRY_LOST')
        self.assertEqual(emergency(replace(self.sample, guardian_age=2.01)), 'GUARDIAN_LOST')

    def test_kill_target_is_exact(self):
        self.assertEqual(exact_container_id('a'*64), 'a'*64)
        for invalid in ['', 'db', 'a'*12, '--all', '$(rm -rf /)', 'a'*64+';true']:
            with self.assertRaises(ValueError):
                exact_container_id(invalid)

    def test_meminfo(self):
        self.assertEqual(memory_available('MemTotal: 200 kB\nMemAvailable: 100 kB\n'), 102400)
        for invalid in ['', 'MemAvailable: -1 kB', 'MemAvailable: 1 GB']:
            with self.assertRaises(ValueError):
                memory_available(invalid)

if __name__ == '__main__':
    unittest.main()
