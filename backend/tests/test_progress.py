import unittest
from dreamx.progress import parse_progress

class ProgressTests(unittest.TestCase):
    def test_actual_steps(self):
        p=parse_progress('Denoising:  24%|██▍       | 12/50 [00:56<02:59, 4.72s/step]')
        self.assertEqual(p,{'phase':'generating','step':12,'total_steps':50,'percent':24})
    def test_latest_step_and_encoding(self):
        p=parse_progress('Denoising:  25%|xx| 1/4 [00:02]\rDenoising: 100%|xxxx| 4/4 [00:06]')
        self.assertEqual(p['phase'],'encoding_output');self.assertEqual(p['step'],4)
    def test_refiner_chunks_do_not_mean_job_completion(self):
        prefix = 'REFINER_PHASE preparing\n'
        partial = parse_progress(prefix + ' 50%|██| 3/6 [00:18<00:18]\r')
        self.assertEqual(partial, {'phase':'refining', 'completed_chunks':3, 'total_chunks':6})
        complete = prefix + '100%|██| 6/6 [00:39<00:00]\nSR inference: 100%|██| 1/1 [01:57]\n'
        self.assertEqual(parse_progress(complete)['phase'], 'decoding')
        self.assertEqual(parse_progress(complete)['completed_chunks'], 6)
        self.assertEqual(parse_progress(complete + 'REFINER_PHASE muxing\n')['phase'], 'muxing')
        self.assertNotIn('percent', partial)

    def test_never_fabricate_percent(self):
        self.assertEqual(parse_progress('Loading model...'),{'phase':'preparing'})
        self.assertEqual(parse_progress('Denoising completed in 6.95s'),{'phase':'encoding_output'})
