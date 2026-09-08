"""Shared validation/inference lease contract, without Docker or private media."""
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dreamx.jobs import Busy, Conflict, Jobs, job_kind


class OperationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.jobs = Jobs(Path(directory.name) / 'jobs.sqlite')

    def upload(self):
        identity = str(uuid.uuid4())
        self.jobs.reserve_upload(identity)
        return identity

    def test_validation_blocks_inference_without_creating_job(self):
        identity = self.upload()
        self.jobs.reserve_validation(identity)
        for kind in ('generate', 'refine'):
            with self.assertRaises(Busy):
                self.jobs.create(kind, {'kind': kind})
        with self.jobs.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)
        self.assertEqual(self.jobs.operation()['owner_id'], identity)

    def test_inference_blocks_validation_without_changing_input(self):
        identity = self.upload()
        job, _ = self.jobs.create('first', {})
        with self.assertRaises(Busy):
            self.jobs.reserve_validation(identity)
        self.assertEqual(self.jobs.video(identity)['state'], 'uploading')
        self.assertEqual(self.jobs.operation()['owner_id'], job['id'])

    def test_parallel_validation_and_inference_have_one_winner(self):
        identity = self.upload()

        def attempt(index):
            try:
                if index == 0:
                    self.jobs.reserve_validation(identity)
                else:
                    self.jobs.create(str(index), {'kind': 'refine'})
                return True
            except Busy:
                return False

        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_duplicate_request_returns_original_while_busy(self):
        payload = {'kind': 'refine', 'input_id': self.upload()}
        first, created = self.jobs.create('same', payload)
        second, duplicate = self.jobs.create('same', payload)
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(first['id'], second['id'])
        with self.assertRaises(Conflict):
            self.jobs.create('same', {'kind': 'generate'})

    def test_bound_container_keeps_lease_until_stop_confirmation(self):
        job, _ = self.jobs.create('first', {})
        self.jobs.bind_container(job['id'], 'a' * 64)
        self.jobs.transition(job['id'], 'failed', 'STOP_UNCONFIRMED')
        with self.assertRaises(Busy):
            self.jobs.create('next', {})
        self.jobs.release_stopped('different-owner')
        self.assertIsNotNone(self.jobs.operation())
        self.jobs.release_stopped(job['id'])
        self.jobs.create('next', {})

    def test_wrong_owner_cannot_bind_or_rebind(self):
        identity = self.upload()
        self.jobs.reserve_validation(identity)
        with self.assertRaises(Conflict):
            self.jobs.bind_container('wrong', 'a' * 64)
        self.jobs.bind_container(identity, 'a' * 64)
        with self.assertRaises(Conflict):
            self.jobs.bind_container(identity, 'b' * 64)
        self.assertEqual(self.jobs.operation()['container_id'], 'a' * 64)

    def test_validation_failure_does_not_release_running_container(self):
        identity = self.upload()
        self.jobs.reserve_validation(identity)
        self.jobs.bind_container(identity, 'a' * 64)
        self.jobs.fail_video(identity)
        self.assertEqual(self.jobs.video(identity)['state'], 'failed')
        self.assertIsNotNone(self.jobs.operation())

    def test_restart_keeps_validation_until_explicit_reconciliation(self):
        identity = self.upload()
        self.jobs.reserve_validation(identity)
        self.jobs.bind_container(identity, 'a' * 64)
        reopened = Jobs(self.jobs.path)
        self.assertIsNotNone(reopened.operation())
        with self.assertRaises(Busy):
            reopened.create('next', {})
        reopened.recover_after_worker_reconciliation()
        self.assertIsNone(reopened.operation())
        self.assertEqual(reopened.video(identity)['state'], 'failed')

    def test_missing_input_cannot_reserve_validation(self):
        with self.assertRaises(Conflict):
            self.jobs.reserve_validation(str(uuid.uuid4()))
        self.assertIsNone(self.jobs.operation())

    def test_legacy_kind_detection(self):
        self.assertEqual(job_kind({}), 'generate')
        self.assertEqual(job_kind({'kind': 'refine'}), 'refine')
        self.assertEqual(job_kind({'operator_test': True}), 'operator_test')
        self.assertEqual(job_kind({'operator_test': True, 'kind': 'generate'}), 'operator_test')
