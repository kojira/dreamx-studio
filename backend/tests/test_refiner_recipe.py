import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
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
