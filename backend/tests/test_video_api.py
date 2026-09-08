import asyncio
import threading
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from dreamx.api import create_app
from dreamx.jobs import Jobs
from dreamx.video_container import video_paths


class VideoRunner:
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.error = None
        self.calls = []
        self.cancelled = []
        self.refiner = False
        self.submitted = []

    def status(self):
        return {'runtime_ready': not self.busy, 'video_validation_ready': not self.busy,
                'reason': 'BUSY' if self.busy else None, 'refiner_ready': self.refiner and not self.busy}

    def validate_video(self, identity, output_fps=24):
        self.calls.append(identity)
        if self.error:
            raise RuntimeError(self.error)
        jobs = Jobs(self.root / 'jobs.sqlite')
        jobs.reserve_validation(identity)
        raw, work = video_paths(self.root, identity)
        (work / 'normalized.mp4').write_bytes(raw.read_bytes())
        metadata = dict(width=1280, height=720, duration_seconds=3, source_fps=30,
                        normalized_frames=round(3 * output_fps), normalized_fps=output_fps, has_audio=False,
                        raw_sha256='a' * 64, normalized_sha256='b' * 64)
        jobs.finish_video(identity, metadata)
        jobs.release_stopped(identity)
        return {**metadata, 'input_id': identity, 'normalized_fps': output_fps}

    def submit(self, job):
        self.submitted.append(job['id'])
        self.busy = True
        Jobs(self.root / 'jobs.sqlite').transition(job['id'], 'preparing')

    def cancel_validation(self, identity):
        self.cancelled.append(identity)
        return {'state': 'failed'}


class VideoApiTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runner = VideoRunner(self.root)
        self.app = create_app(self.root, 'x' * 32, self.runner)
        self.client = TestClient(self.app, base_url='http://127.0.0.1:8780')
        self.origin = {'origin': 'http://127.0.0.1:8780'}
        session = self.client.post('/api/session', json={}, headers=self.origin)
        self.headers = {**self.origin, 'x-csrf-token': session.json()['csrf'],
                        'content-type': 'application/octet-stream'}

    def test_upload_validation_and_preview(self):
        response = self.client.post('/api/video-inputs', content=b'synthetic', headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result['normalized_frames'], 72)
        preview = self.client.get('/api/video-inputs/' + result['input_id'] + '/preview')
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.content, b'synthetic')
        self.assertEqual(self.runner.cancelled, [])

    def test_selected_fps_persisted_and_submitted(self):
        response = self.client.post('/api/video-inputs?output_fps=30', content=b'synthetic', headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        identity = response.json()['input_id']
        self.assertEqual(self.app.state.jobs.video(identity)['normalized_fps'], 30)
        self.runner.refiner = True
        headers = {**self.headers, 'content-type': 'application/json', 'idempotency-key': 'fps30'}
        result = self.client.post('/api/refiner-jobs', json={'input_id': identity}, headers=headers)
        self.assertEqual(result.status_code, 202, result.text)
        import json
        payload = json.loads(self.app.state.jobs.get(result.json()['job_id'])['payload'])
        self.assertEqual((payload['output_fps'], payload['frames']), (30, 90))

    def test_invalid_fps_rejected_before_upload(self):
        for fps in ('0', '-1', 'nan', 'inf', 'hello'):
            result = self.client.post('/api/video-inputs?output_fps=' + fps, content=b'x', headers=self.headers)
            self.assertEqual(result.status_code, 422)
        self.assertEqual(self.runner.calls, [])

    def test_auth_and_csrf_required(self):
        response = self.client.post('/api/video-inputs', content=b'x', headers=self.origin)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.runner.calls, [])

    def test_busy_rejected_without_input_reservation(self):
        self.runner.busy = True
        response = self.client.post('/api/video-inputs', content=b'x', headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertFalse((self.root / 'video-inputs').exists())

    def test_shared_database_lease_blocks_even_when_status_is_stale(self):
        self.app.state.jobs.create('generation', {})
        response = self.client.post('/api/video-inputs', content=b'x', headers=self.headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.runner.calls, [])

    def test_actual_stream_limit_and_unfinished_file_cleanup(self):
        with patch('dreamx.api.MAX_UPLOAD_BYTES', 4):
            response = self.client.post('/api/video-inputs', content=iter([b'123', b'456']), headers=self.headers)
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(list((self.root / 'video-inputs').glob('*/raw.mp4')), [])
        with self.app.state.jobs.connect() as db:
            rows = db.execute('SELECT state FROM video_inputs').fetchall()
        self.assertEqual([row['state'] for row in rows], ['failed'])

    def test_declared_oversize_rejected_before_reservation(self):
        response = self.client.post('/api/video-inputs', content=b'x',
                                    headers={**self.headers, 'content-length': str(101 * 1024 * 1024)})
        self.assertEqual(response.status_code, 413)
        self.assertFalse((self.root / 'video-inputs').exists())

    def test_runner_error_is_sanitized_and_input_fails(self):
        self.runner.error = '/private/unknown/trace'
        response = self.client.post('/api/video-inputs', content=b'x', headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['detail'], 'RUNNER_NOT_READY')
        identity = self.runner.calls[0]
        self.assertEqual(self.app.state.jobs.video(identity)['state'], 'failed')
        self.assertEqual(self.runner.cancelled, [identity])
        self.assertEqual(self.client.get('/api/video-inputs/' + identity + '/preview').status_code, 409)

    def test_disconnect_after_body_notifies_host_before_validation_finishes(self):
        started, cancelled = threading.Event(), threading.Event()
        def validate(identity):
            self.runner.calls.append(identity)
            started.set()
            cancelled.wait(5)
            raise RuntimeError('VALIDATION_CANCELLED')
        def cancel(identity):
            self.runner.cancelled.append(identity)
            cancelled.set()
            return {'state': 'failed'}
        self.runner.validate_video = validate
        self.runner.cancel_validation = cancel
        headers = {**self.headers, 'host': '127.0.0.1:8780',
                   'cookie': 'dreamx_session=' + self.client.cookies.get('dreamx_session')}
        scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                 'method': 'POST', 'scheme': 'http', 'path': '/api/video-inputs',
                 'raw_path': b'/api/video-inputs', 'query_string': b'',
                 'headers': [(k.encode(), v.encode()) for k, v in headers.items()],
                 'client': ('127.0.0.1', 10000), 'server': ('127.0.0.1', 8780)}
        async def exercise():
            sent = False
            async def receive():
                nonlocal sent
                if not sent:
                    sent = True
                    return {'type': 'http.request', 'body': b'synthetic', 'more_body': False}
                await asyncio.to_thread(started.wait, 4)
                return {'type': 'http.disconnect'}
            async def send(message):
                pass
            await asyncio.wait_for(self.app(scope, receive, send), timeout=4)
        try:
            asyncio.run(exercise())
            self.assertTrue(cancelled.is_set())
            self.assertEqual(self.runner.cancelled, self.runner.calls)
            self.assertEqual(self.app.state.jobs.video(self.runner.calls[0])['state'], 'failed')
        finally:
            cancelled.set()

    def test_refiner_admission_idempotency_and_kind(self):
        self.runner.refiner = True
        identity = self.client.post('/api/video-inputs', content=b'x', headers=self.headers).json()['input_id']
        headers = {**self.headers, 'content-type': 'application/json', 'idempotency-key': 'refine-once'}
        first = self.client.post('/api/refiner-jobs', json={'input_id': identity}, headers=headers)
        second = self.client.post('/api/refiner-jobs', json={'input_id': identity}, headers=headers)
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(len(self.runner.submitted), 1)
        detail = self.client.get('/api/jobs/' + first.json()['job_id']).json()
        self.assertEqual(detail['kind'], 'refine')
        self.assertEqual(detail['output_size'], [1920, 1080])
        self.assertEqual(detail['artifacts'], [])
        self.assertEqual(self.client.get('/api/jobs').json()[0]['kind'], 'refine')
        other = self.client.post('/api/refiner-jobs', json={'input_id': identity}, headers={**headers, 'idempotency-key': 'other'})
        self.assertEqual(other.status_code, 409)

    def test_refiner_not_enabled_or_unknown_options_rejected(self):
        identity = self.client.post('/api/video-inputs', content=b'x', headers=self.headers).json()['input_id']
        headers = {**self.headers, 'content-type': 'application/json', 'idempotency-key': 'request'}
        self.assertEqual(self.client.post('/api/refiner-jobs', json={'input_id': identity}, headers=headers).status_code, 503)
        self.runner.refiner = True
        response = self.client.post('/api/refiner-jobs', json={'input_id': identity, 'seed': 99}, headers=headers)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.runner.submitted, [])

    def test_preview_symlink_rejected(self):
        result = self.client.post('/api/video-inputs', content=b'x', headers=self.headers).json()
        _, work = video_paths(self.root, result['input_id'])
        output = work / 'normalized.mp4'
        output.rename(work / 'saved.mp4')
        output.symlink_to(work / 'saved.mp4')
        self.assertEqual(self.client.get('/api/video-inputs/' + result['input_id'] + '/preview').status_code, 404)
