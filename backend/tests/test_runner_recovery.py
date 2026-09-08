import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from dreamx.host_runner import Supervisor
from dreamx.jobs import Jobs


class RunnerRecoveryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / 'app').mkdir()
        (self.root / 'config.json').write_text(json.dumps({'validated': False}))
        self.jobs = Jobs(self.root / 'app' / 'jobs.sqlite')
        self.identity = str(uuid.uuid4())
        self.jobs.reserve_upload(self.identity)
        self.jobs.reserve_validation(self.identity)
        self.jobs.bind_container(self.identity, 'a' * 64)

    def test_live_cpu_validator_blocks_restart_even_without_gpu_active_file(self):
        with patch('dreamx.host_runner.inspect_job', return_value={'State': {'Running': True}}):
            with self.assertRaises(RuntimeError):
                Supervisor(self.root)
        self.assertIsNotNone(self.jobs.operation())
        self.assertEqual(self.jobs.video(self.identity)['state'], 'validating')

    def test_unreachable_cpu_validator_keeps_lease(self):
        with patch('dreamx.host_runner.inspect_job', side_effect=RuntimeError('Docker unavailable')):
            with self.assertRaises(RuntimeError):
                Supervisor(self.root)
        self.assertIsNotNone(self.jobs.operation())

    def test_verified_stopped_cpu_validator_can_be_reconciled(self):
        with patch('dreamx.host_runner.inspect_job', return_value={'State': {'Running': False}}) as inspect, \
             patch('dreamx.host_runner.threading.Thread.start'):
            Supervisor(self.root)
        inspect.assert_called_once_with('a' * 64, self.identity)
        self.assertIsNone(self.jobs.operation())
        self.assertEqual(self.jobs.video(self.identity)['state'], 'failed')
