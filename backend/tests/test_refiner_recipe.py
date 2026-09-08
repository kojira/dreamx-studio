import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from dreamx.video_contract import RECIPE, padded_frames
from dreamx.refiner_recipe import final_command, inference_command


class RefinerRecipeTests(unittest.TestCase):
    def test_fixed_recipe_and_processing_padding(self):
        for frames, processing in ((6, 9), (24, 25), (68, 69), (69, 69), (72, 73)):
            args = inference_command(frames)
            self.assertEqual(args[args.index('--num_frames') + 1], str(processing))
            self.assertEqual(args[args.index('--target_size') + 1:args.index('--target_size') + 3], ['1088', '1920'])
            self.assertEqual(args[args.index('--window_attn_impl') + 1], 'triton')
            for forbidden in ('--auto_target_size', '--fp8_linear', '--enable_nu_lightvae', '--pixel_upsample'):
                self.assertNotIn(forbidden, args)

    def test_final_mapping_keeps_source_audio_and_only_trims_padding(self):
        args = final_command('/job/refined/example.mp4', 69, 1248, 704, True)
        self.assertIn('1:a:0', args)
        self.assertIn('trim=end_frame=69', args[args.index('-vf') + 1])
        self.assertIn('scale=1914:1080:flags=lanczos,pad=1920:1080:2:0', args[args.index('-vf') + 1])
        self.assertNotIn('-shortest', args)
        self.assertNotIn('-frames:v', args)
        silent = final_command('/job/refined/example.mp4', 72, 1280, 720, False)
        self.assertNotIn('1:a:0', silent)

    def test_worker_accepts_original_frames_after_upstream_removes_padding(self):
        location = Path(__file__).resolve().parents[2] / 'runtime' / 'refiner_worker.py'
        spec = importlib.util.spec_from_file_location('refiner_padding_test', location)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for frames in (6, 24, 68, 69, 72):
            with self.subTest(frames=frames), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'refined').mkdir()
                (root / 'refined' / 'result.mp4').write_bytes(b'fixture')
                (root / 'go.json').write_text(json.dumps({'job_id': 'job'}))
                data = dict(kind='refine', recipe=RECIPE, seed=42, frames=frames,
                            width=1280, height=720, has_audio=False, normalized_sha256='hash', job_id='job')
                worker = module.Worker(data, control=root, job=root)
                intermediate = {'streams': [{'codec_type':'video', 'width':1920, 'height':1088,
                                              'nb_read_frames':str(frames)}]}
                final = {'streams': [{'codec_type':'video', 'width':1920, 'height':1080,
                                       'nb_read_frames':str(frames), 'avg_frame_rate':'24/1',
                                       'codec_name':'h264', 'pix_fmt':'yuv420p',
                                       'sample_aspect_ratio':'1:1', 'duration':str(frames / 24)}]}
                with patch.object(worker, 'healthy', return_value=True), \
                     patch.object(worker, 'run') as run, \
                     patch.object(worker, 'probe', side_effect=[intermediate, final]), \
                     patch.object(module, 'digest', return_value='hash'):
                    worker.main()
                inference = run.call_args_list[0].args[0]
                self.assertEqual(inference[inference.index('--num_frames') + 1], str(padded_frames(frames)))
                evidence = json.loads((root / 'refiner-evidence.json').read_text())
                self.assertEqual(evidence['frames'], frames)
                self.assertEqual(evidence['processing_frames'], padded_frames(frames))
                if padded_frames(frames) != frames:
                    intermediate['streams'][0]['nb_read_frames'] = str(padded_frames(frames))
                    with patch.object(worker, 'healthy', return_value=True), \
                         patch.object(worker, 'run'), \
                         patch.object(worker, 'probe', return_value=intermediate), \
                         patch.object(module, 'digest', return_value='hash'):
                        with self.assertRaisesRegex(ValueError, 'processing frame/size mismatch'):
                            worker.main()

    def test_worker_health_is_bound_to_exact_active_job_and_container(self):
        location = Path(__file__).resolve().parents[2] / 'runtime' / 'refiner_worker.py'
        spec = importlib.util.spec_from_file_location('product_refiner_worker', location)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def save(name, value):
                (root / name).write_text(json.dumps(value))
            now = time.monotonic()
            save('runner-heartbeat.json', {'at': now})
            save('guard-status.json', {'at': now, 'container_id': 'worker-a'})
            save('active.json', {'job_id': 'job-a', 'container_id': 'worker-a'})
            worker = module.Worker({'job_id': 'job-a'}, control=root, job=root)
            self.assertTrue(worker.healthy())
            save('active.json', {'job_id': 'job-b', 'container_id': 'worker-a'})
            self.assertFalse(worker.healthy())
            save('active.json', {'job_id': 'job-a', 'container_id': 'worker-b'})
            self.assertFalse(worker.healthy())
            save('active.json', {'job_id': 'job-a', 'container_id': 'worker-a'})
            save('runner-heartbeat.json', {'at': now - 3})
            self.assertFalse(worker.healthy())
