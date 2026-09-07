import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dreamx.jobs import Jobs, Busy, Conflict

class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.jobs = Jobs(Path(self.temp.name)/'jobs.sqlite')

    def test_idempotency(self):
        first, created = self.jobs.create('request-1', {'prompt':'test'})
        again, duplicate = self.jobs.create('request-1', {'prompt':'test'})
        self.assertTrue(created); self.assertFalse(duplicate)
        self.assertEqual(first['id'], again['id'])
        with self.assertRaises(Conflict):
            self.jobs.create('request-1', {'prompt':'different'})

    def test_parallel_admission(self):
        def attempt(i):
            try:
                self.jobs.create(str(i), {})
                return True
            except Busy:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(results), 1)

    def test_transitions(self):
        job, _ = self.jobs.create('r', {})
        with self.assertRaises(Conflict): self.jobs.transition(job['id'], 'succeeded')
        for state in ['preparing','generating','muxing','succeeded']:
            self.jobs.transition(job['id'], state)
        self.assertEqual(self.jobs.get(job['id'])['state'], 'succeeded')
        self.jobs.create('next', {})

    def test_cancel_holds_slot_until_worker_stopped(self):
        job, _ = self.jobs.create('r', {})
        self.jobs.transition(job['id'], 'cancelling')
        with self.assertRaises(Busy): self.jobs.create('second', {})
        self.jobs.transition(job['id'], 'cancelled')
        self.jobs.create('second', {})

    def test_restart_does_not_implicitly_release_slot(self):
        self.jobs.create('r', {})
        reopened = Jobs(self.jobs.path)
        with self.assertRaises(Busy): reopened.create('next', {})
        self.assertEqual(reopened.recover_after_worker_reconciliation(), 1)
        self.assertEqual(reopened.recover_after_worker_reconciliation(), 0)
        reopened.create('next', {})
