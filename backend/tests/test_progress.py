import unittest
from dreamx.progress import parse_progress

class ProgressTests(unittest.TestCase):
    def test_actual_steps(self):
        p=parse_progress('Denoising:  24%|██▍       | 12/50 [00:56<02:59, 4.72s/step]')
        self.assertEqual(p,{'phase':'generating','step':12,'total_steps':50,'percent':24})
    def test_latest_step_and_encoding(self):
        p=parse_progress('Denoising:  25%|xx| 1/4 [00:02]\rDenoising: 100%|xxxx| 4/4 [00:06]')
        self.assertEqual(p['phase'],'encoding_output');self.assertEqual(p['step'],4)
    def test_never_fabricate_percent(self):
        self.assertEqual(parse_progress('Loading model...'),{'phase':'preparing'})
        self.assertEqual(parse_progress('Denoising completed in 6.95s'),{'phase':'encoding_output'})
