import copy
import unittest
from dreamx.video_contract import InvalidVideo, normalized_contract, output_geometry, padded_frames, probe_contract


def sample():
    return {'streams': [
        {'codec_type': 'video', 'codec_name': 'h264', 'pix_fmt': 'yuv420p',
         'width': 1280, 'height': 720, 'avg_frame_rate': '30/1', 'r_frame_rate': '30/1',
         'sample_aspect_ratio': '1:1', 'duration': '3.000', 'start_time': '0.000'},
        {'codec_type': 'audio', 'codec_name': 'aac', 'channels': 1,
         'sample_rate': '48000', 'duration': '3.000', 'start_time': '0.000'}]}


class VideoContractTests(unittest.TestCase):
    def test_padding_retains_all_original_frames(self):
        for n, p in ((6, 9), (24, 25), (68, 69), (69, 69), (72, 73)):
            self.assertEqual(padded_frames(n), p)
        for n in (1, 5, 6, 69, 72, 73, 450, 900, 1800, 100000):
            p = padded_frames(n)
            self.assertEqual(p % 4, 1)
            self.assertTrue(0 <= p - n <= 3)
        for n in (0, -1, 6.0, True):
            with self.assertRaises(InvalidVideo):
                padded_frames(n)

    def test_duration_no_artificial_ceiling(self):
        for duration in (0.1, 3.01, 15, 20, 30, 600):
            probe = sample()
            for stream in probe['streams']:
                stream['duration'] = str(duration)
            self.assertEqual(probe_contract(probe)['duration_seconds'], duration)

    def test_selected_fps(self):
        for fps, frames in ((30, 90), (60, 180), (120, 360), (0.5, 2), (29.97, 90)):
            source = probe_contract(sample())
            normalized = sample()
            from fractions import Fraction
            for stream in normalized['streams']:
                stream['duration'] = str(frames / fps)
            normalized['streams'][0].update(avg_frame_rate=str(Fraction(str(fps))), r_frame_rate=str(Fraction(str(fps))), nb_read_frames=str(frames))
            self.assertEqual(normalized_contract(normalized, source, fps), frames)

    def test_geometry_matches_proven_source_and_centers_even_padding(self):
        self.assertEqual(output_geometry(1248, 704), (1914, 1080, 2, 0))
        self.assertEqual(output_geometry(1280, 720), (1920, 1080, 0, 0))
        for w, h in ((1276, 720), (1280, 718), (1248, 704)):
            W, H, x, y = output_geometry(w, h)
            self.assertTrue(W <= 1920 and H <= 1080)
            self.assertEqual((W % 2, H % 2, x % 2, y % 2), (0, 0, 0, 0))
            self.assertLessEqual(abs(x - (1920 - W - x)), 2)
            self.assertLessEqual(abs(y - (1080 - H - y)), 2)

    def test_supported_metadata(self):
        result = probe_contract(sample())
        self.assertEqual(result['source_fps'], 30)
        self.assertTrue(result['has_audio'])
        silent = sample()
        silent['streams'].pop()
        self.assertFalse(probe_contract(silent)['has_audio'])

    def test_short_audio_allowed_but_shifted_or_long_audio_rejected(self):
        probe = sample()
        probe['streams'][1]['duration'] = '2.8'
        self.assertTrue(probe_contract(probe)['has_audio'])
        for changes in ({'duration': '3.1'}, {'start_time': '0.05'}, {'start_time': '-0.05'}):
            probe = sample()
            probe['streams'][1].update(changes)
            with self.assertRaisesRegex(InvalidVideo, 'UNSUPPORTED_AUDIO_TIMING'):
                probe_contract(probe)

    def test_unsupported_video_metadata(self):
        cases = [{'codec_name': 'hevc'}, {'pix_fmt': 'yuv444p'}, {'width': 1920},
                 {'height': 721}, {'width': 720, 'height': 1280}, {'sample_aspect_ratio': '2:1'},
                 {'tags': {'rotate': '90'}}, {'side_data_list': [{'rotation': 180}]},
                 {'avg_frame_rate': '30/1', 'r_frame_rate': '60/1'},
                 {'avg_frame_rate': '61/1', 'r_frame_rate': '61/1'},
                 {'duration': '0'}, {'duration': '-1'}, {'duration': 'nan'},
                 {'avg_frame_rate': '0/0'}]
        for changes in cases:
            with self.subTest(changes=changes):
                probe = sample()
                probe['streams'][0].update(changes)
                with self.assertRaises(InvalidVideo):
                    probe_contract(probe)

    def test_extra_streams_rejected(self):
        for extra in ({'codec_type': 'subtitle'}, sample()['streams'][0], sample()['streams'][1]):
            probe = sample()
            probe['streams'].append(copy.deepcopy(extra))
            with self.assertRaises(InvalidVideo):
                probe_contract(probe)

    def test_normalized_frames_count_and_duration(self):
        source = probe_contract(sample())
        normalized = sample()
        normalized['streams'][0].update(avg_frame_rate='24/1', r_frame_rate='24/1', nb_read_frames='72')
        self.assertEqual(normalized_contract(normalized, source), 72)
        normalized['streams'][0]['nb_read_frames'] = '69'
        with self.assertRaisesRegex(InvalidVideo, 'INVALID_DURATION'):
            normalized_contract(normalized, source)
        normalized['streams'][0]['nb_read_frames'] = 'N/A'
        with self.assertRaises(InvalidVideo):
            normalized_contract(normalized, source)
