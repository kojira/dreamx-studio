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

    def test_self_contained_quicktime_alias(self):
        self.source.write_bytes(movie(brand=b'qt  ').replace(b'url ', b'alis'))
        validator.self_contained_mp4(self.source)
        self.source.write_bytes(movie(flags=0, brand=b'qt  ').replace(b'url ', b'alis'))
        with self.assertRaises(InvalidVideo):
            validator.self_contained_mp4(self.source)

    def test_external_reference_rejected(self):
        self.source.write_bytes(movie(flags=0))
        with self.assertRaisesRegex(InvalidVideo, 'UNSUPPORTED_VIDEO'):
            validator.self_contained_mp4(self.source)

    def test_quicktime_container_accepted(self):
        self.source.write_bytes(movie(brand=b'qt  '))
        validator.self_contained_mp4(self.source)

    def test_legacy_mov_requires_structural_movie_and_data(self):
        data = movie()
        ftyp_size = struct.unpack('>I', data[:4])[0]
        self.source.write_bytes(data[ftyp_size:])
        validator.self_contained_mp4(self.source)
        self.source.write_bytes(data[ftyp_size:-len(atom(b'mdat', b'dummy'))])
        with self.assertRaises(InvalidVideo):
            validator.self_contained_mp4(self.source)

    def test_mov_external_reference_and_unknown_brand_rejected(self):
        for data in (movie(flags=0, brand=b'qt  '), movie(brand=b'xxxx')):
            self.source.write_bytes(data)
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

    def test_variable_frame_timing_is_normalized_not_rejected(self):
        stream = {'avg_frame_rate': '24/1', 'time_base': '1/12288',
                  'duration': '0.25', 'width': 1280, 'height': 720}
        frames = [{'best_effort_timestamp_time': str(i / 24), 'width': 1280,
                   'height': 720, 'pix_fmt': 'yuv420p'} for i in range(6)]
        frames[3]['best_effort_timestamp_time'] = str(3.5 / 24)
        with patch.object(validator, 'run', side_effect=[json.dumps({'frames': frames}).encode(), b'']):
            self.assertEqual(validator.decoded_frames(self.source, stream), 6)

    def test_cfr_decode_also_requires_strict_ffmpeg_decode(self):
        stream = {'avg_frame_rate': '24/1', 'time_base': '1/12288',
                  'duration': '0.25', 'width': 1280, 'height': 720}
        frames = [{'best_effort_timestamp_time': str(i / 24), 'width': 1280,
                   'height': 720, 'pix_fmt': 'yuv420p'} for i in range(6)]
        with patch.object(validator, 'run', side_effect=[json.dumps({'frames': frames}).encode(), b'']) as run:
            self.assertEqual(validator.decoded_frames(self.source, stream), 6)
            self.assertIn('-xerror', run.call_args.args[0])
            self.assertIn('explode', run.call_args.args[0])

    def test_conversion_does_not_run_prevalidation_or_full_output_decode(self):
        self.source.write_bytes(b'input')
        output = self.source.parent / 'output.mp4'
        original = {'streams': [{'codec_type': 'video', 'avg_frame_rate': '25/1'}]}
        converted = {'streams': [{'codec_type': 'video', 'width': 896, 'height': 512, 'duration': '15.04', 'nb_frames': '376'}]}
        with patch.object(validator, 'probe', side_effect=[original, converted]) as probe, \
             patch.object(validator, 'run', side_effect=lambda args: output.write_bytes(b'output')) as run, \
             patch.object(validator, 'self_contained_mp4', side_effect=AssertionError('No structural gate')), \
             patch.object(validator, 'decoded_frames', side_effect=AssertionError('No predecode')), \
             patch.object(validator, 'normalized_contract', side_effect=AssertionError('No postdecode gate')), \
             patch.object(validator, 'audio_hash', side_effect=AssertionError('No audio prehash')):
            result = validator.validate(self.source, output, 25)
            self.assertEqual(result['normalized_frames'], 376)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(probe.call_args_list, [unittest.mock.call(self.source), unittest.mock.call(output)])

    def test_nonzero_decoder_exit_is_not_success(self):
        with patch.object(validator.subprocess, 'run') as run:
            run.return_value.returncode = 1
            with self.assertRaises(InvalidVideo):
                validator.run(['ffmpeg'])
            self.assertEqual(run.call_args.kwargs['timeout'], 50)
