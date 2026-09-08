import copy
import json
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from dreamx.jobs import Jobs, Busy
from dreamx.safety import GIB
from dreamx.video_container import validation_command, verify_validator, video_paths
from dreamx.video_validation import VideoValidation, ValidationFailure

IMAGE = 'sha256:' + 'b' * 64
CID = 'a' * 64


class VideoValidationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = Path(directory.name)
        self.jobs = Jobs(self.app / 'jobs.sqlite')
        self.identity = str(uuid.uuid4())
        parent = self.app / 'video-inputs' / self.identity
        parent.mkdir(parents=True)
        self.raw, self.work = video_paths(self.app, self.identity)
        self.raw.write_bytes(b'synthetic source')
        self.work.mkdir()
        self.jobs.reserve_upload(self.identity)
        self.args, self.mounts = validation_command(self.app, self.identity, IMAGE, '1001:1001')
        self.container = {
            'Image': IMAGE,
            'Config': {'User': '1001:1001', 'Labels': {'org.dreamx.studio.job': self.identity,
                       'org.dreamx.studio.operation': 'validate_video'}},
            'State': {'Running': False, 'ExitCode': 0, 'OOMKilled': False},
            'HostConfig': {'Memory': 2 * GIB, 'MemorySwap': 2 * GIB, 'NanoCpus': 2_000_000_000,
                           'PidsLimit': 128, 'NetworkMode': 'none', 'ReadonlyRootfs': True,
                           'RestartPolicy': {'Name': 'no'}, 'CapDrop': ['ALL'],
                           'SecurityOpt': ['no-new-privileges']},
            'Mounts': [dict(zip(('Type', 'Source', 'Destination', 'RW'), mount)) for mount in self.mounts],
        }
        self.service = VideoValidation(self.app, self.jobs, threading.Lock(), IMAGE,
                                       lambda: {'runtime_ready': True})

    def verify(self, container):
        verify_validator(container, input_id=self.identity, expected_image_id=IMAGE,
                         expected_user='1001:1001', expected_mounts=self.mounts)

    def test_exact_cpu_policy(self):
        self.verify(self.container)
        self.assertNotIn('--gpus', self.args)
        self.assertEqual(self.mounts[0][3], False)
        self.assertNotEqual(Path(self.mounts[0][1]).parent, Path(self.mounts[1][1]))
        for key, value in [('Memory', 0), ('MemorySwap', -1), ('NanoCpus', 0),
                           ('PidsLimit', -1), ('NetworkMode', 'bridge'), ('ReadonlyRootfs', False),
                           ('Privileged', True), ('DeviceRequests', [{'Count': -1}]),
                           ('CapAdd', ['SYS_ADMIN']), ('PidMode', 'host')]:
            changed = copy.deepcopy(self.container)
            changed['HostConfig'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(changed)

    def test_extra_mount_or_different_owner_rejected(self):
        changed = copy.deepcopy(self.container)
        changed['Mounts'].append({'Type': 'bind', 'Source': '/secret', 'Destination': '/secret', 'RW': False})
        with self.assertRaises(ValueError):
            self.verify(changed)
        changed = copy.deepcopy(self.container)
        changed['Config']['Labels']['org.dreamx.studio.job'] = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            self.verify(changed)

    def test_mutable_image_root_user_and_symlink_rejected(self):
        for image, user in [('image:latest', '1001:1001'), (IMAGE, '0:0')]:
            with self.assertRaises(ValueError):
                validation_command(self.app, self.identity, image, user)
        self.raw.rename(self.raw.with_suffix('.saved'))
        self.raw.symlink_to(self.raw.with_suffix('.saved'))
        with self.assertRaises(ValueError):
            video_paths(self.app, self.identity)

    def test_success_releases_only_after_container_has_stopped(self):
        metadata = dict(width=1280, height=720, duration_seconds=3, source_fps=30,
                        normalized_frames=72, normalized_fps=24, has_audio=True,
                        raw_sha256='c' * 64, normalized_sha256='d' * 64)
        (self.work / 'normalized.mp4').write_bytes(b'synthetic normalized')
        (self.work / 'result.json').write_text(json.dumps({'metadata': metadata}))
        with patch('dreamx.video_validation.os.getuid', return_value=1001), \
             patch('dreamx.video_validation.os.getgid', return_value=1001), \
             patch('dreamx.video_validation.execute', return_value=CID), \
             patch('dreamx.video_validation.inspect_job', return_value=self.container):
            result = self.service.validate(self.identity)
        self.assertEqual(result['normalized_frames'], 72)
        self.assertNotIn('raw_sha256', result)
        self.assertEqual(self.jobs.video(self.identity)['state'], 'validated')
        self.assertIsNone(self.jobs.operation())

    def test_inference_lease_blocks_validation(self):
        self.jobs.create('generation', {})
        with self.assertRaises(Busy):
            self.service.validate(self.identity)
        self.assertEqual(self.jobs.video(self.identity)['state'], 'uploading')

    def test_unconfirmed_stop_retains_lease(self):
        def execute(args):
            if args[0] == 'start':
                raise RuntimeError('start response lost')
            return CID
        with patch('dreamx.video_validation.os.getuid', return_value=1001), \
             patch('dreamx.video_validation.os.getgid', return_value=1001), \
             patch('dreamx.video_validation.execute', side_effect=execute), \
             patch('dreamx.video_validation.inspect_job', return_value=self.container), \
             patch('dreamx.video_validation.kill_job', side_effect=RuntimeError('unreachable')):
            with self.assertRaisesRegex(ValidationFailure, 'STOP_UNCONFIRMED'):
                self.service.validate(self.identity)
        self.assertEqual(self.jobs.operation()['container_id'], CID)
        with self.assertRaises(Busy):
            self.jobs.create('next', {})

    def test_cancel_stops_exact_container_before_release(self):
        live = copy.deepcopy(self.container)
        live['State']['Running'] = True
        def execute(args):
            if args[0] == 'start':
                self.service.cancel(self.identity)
            return CID
        def kill(cid, owner):
            self.assertEqual((cid, owner), (CID, self.identity))
            self.assertIsNotNone(self.jobs.operation())
        with patch('dreamx.video_validation.os.getuid', return_value=1001), \
             patch('dreamx.video_validation.os.getgid', return_value=1001), \
             patch('dreamx.video_validation.execute', side_effect=execute), \
             patch('dreamx.video_validation.inspect_job', side_effect=[self.container, live, self.container]), \
             patch('dreamx.video_validation.kill_job', side_effect=kill):
            with self.assertRaisesRegex(ValidationFailure, 'VALIDATION_CANCELLED'):
                self.service.validate(self.identity)
        self.assertIsNone(self.jobs.operation())
        self.assertEqual(self.jobs.video(self.identity)['state'], 'failed')
