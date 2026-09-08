"""CPU unit tests; never demux user media on the host."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from dreamx.video_contract import InvalidVideo

location = Path(__file__).resolve().parents[2] / 'runtime' / 'video_validator.py'
# backend/tests -> repository root is parents[2].
spec = importlib.util.spec_from_file_location('video_validator', location)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def atom(kind, body):
    return struct.pack('>I4s', len(body) + 8, kind) + body


def movie(flags=1, brand=b'isom'):
    entry = atom(b'url ', struct.pack('>I', flags))
    data = atom(b'dref', struct.pack('>II', 0, 1) + entry)
    for kind in (b'dinf', b'minf', b'mdia', b'trak', b'moov'):
        data = atom(kind, data)
    return atom(b'ftyp', brand + b'\x00' * 4 + brand) + data + atom(b'mdat', b'dummy')


class VideoValidatorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.source = Path(directory.name) / 'source.mp4'

    def test_structural_self_contained_mp4(self):
        self.source.write_bytes(movie())
        validator.self_contained_mp4(self.source)

    def test_external_reference_rejected(self):
        self.source.write_bytes(movie(flags=0))
        with self.assertRaisesRegex(InvalidVideo, 'UNSUPPORTED_VIDEO'):
            validator.self_contained_mp4(self.source)

    def test_quicktime_only_rejected(self):
        self.source.write_bytes(movie(brand=b'qt  '))
        with self.assertRaises(InvalidVideo):
            validator.self_contained_mp4(self.source)

    def test_malformed_boxes_rejected(self):
        for payload in (b'', b'1234', movie()[:-2], struct.pack('>I4s', 7, b'moov'),
                        struct.pack('>I4s', 1, b'moov') + b'1234'):
            self.source.write_bytes(payload)
            with self.subTest(payload=payload[:16]), self.assertRaises(InvalidVideo):
                validator.self_contained_mp4(self.source)

    def test_missing_reference_rejected(self):
        self.source.write_bytes(atom(b'ftyp', b'isom' + b'\x00' * 4))
        with self.assertRaises(InvalidVideo):
            validator.self_contained_mp4(self.source)

    def test_mdat_is_not_parsed_as_container(self):
        self.source.write_bytes(movie() + atom(b'mdat', b'url \x00external payload'))
        validator.self_contained_mp4(self.source)

    def test_frame_timestamp_gap_rejected_even_when_average_fps_matches(self):
        stream = {'avg_frame_rate': '24/1', 'time_base': '1/12288',
                  'duration': '0.25', 'width': 1280, 'height': 720}
        frames = [{'best_effort_timestamp_time': str(i / 24), 'width': 1280,
                   'height': 720, 'pix_fmt': 'yuv420p'} for i in range(6)]
        frames[3]['best_effort_timestamp_time'] = str(3.5 / 24)
        with patch.object(validator, 'run', return_value=json.dumps({'frames': frames}).encode()):
            with self.assertRaisesRegex(InvalidVideo, 'UNSUPPORTED_VIDEO'):
                validator.decoded_frames(self.source, stream)

    def test_cfr_decode_also_requires_strict_ffmpeg_decode(self):
        stream = {'avg_frame_rate': '24/1', 'time_base': '1/12288',
                  'duration': '0.25', 'width': 1280, 'height': 720}
        frames = [{'best_effort_timestamp_time': str(i / 24), 'width': 1280,
                   'height': 720, 'pix_fmt': 'yuv420p'} for i in range(6)]
        with patch.object(validator, 'run', side_effect=[json.dumps({'frames': frames}).encode(), b'']) as run:
            self.assertEqual(validator.decoded_frames(self.source, stream), 6)
            self.assertIn('-xerror', run.call_args.args[0])
            self.assertIn('explode', run.call_args.args[0])

    def test_nonzero_decoder_exit_is_not_success(self):
        with patch.object(validator.subprocess, 'run') as run:
            run.return_value.returncode = 1
            with self.assertRaises(InvalidVideo):
                validator.run(['ffmpeg'])
            self.assertEqual(run.call_args.kwargs['timeout'], 50)
