"""Regression checks for the approved exact-worker swap setup; no host writes."""
import unittest
from pathlib import Path
from unittest.mock import patch
from dreamx.docker_control import configure_no_swap

CID='a'*64
CG=Path('/sys/fs/cgroup/system.slice')/('docker-'+CID+'.scope')

class NoSwapSetupTests(unittest.TestCase):
    def run_setup(self, *, relative=None, ceiling='max', swap='0', after_pid=42, running=True):
        relative=relative if relative is not None else '/system.slice/docker-'+CID+'.scope'
        def read(path,*args,**kwargs):
            if str(path)=='/proc/42/cgroup':return '0::'+relative+'\n'
            if path.name=='memory.max':return ceiling+'\n'
            if path.name=='memory.swap.max':return swap+'\n'
            raise AssertionError('Unexpected read: '+str(path))
        self.writer=self.enterContext(patch('dreamx.docker_control.subprocess.run'))
        self.enterContext(patch('dreamx.docker_control.inspect_job',side_effect=[{'State':{'Running':running,'Pid':42}},{'State':{'Running':True,'Pid':after_pid}}]))
        self.enterContext(patch.object(Path,'resolve',autospec=True,side_effect=lambda path,*args,**kwargs:path))
        self.enterContext(patch.object(Path,'read_text',autospec=True,side_effect=read))
        return configure_no_swap(CID,'test-job')

    def test_only_exact_worker_swap_file_is_written(self):
        self.assertEqual(self.run_setup(),CG)
        self.writer.assert_called_once_with(['sudo','-n','tee',str(CG/'memory.swap.max')],input='0\n',text=True,capture_output=True,check=True,timeout=5)

    def test_foreign_cgroup_is_never_written(self):
        with self.assertRaises(ValueError):self.run_setup(relative='/system.slice/docker-'+('b'*64)+'.scope')
        self.writer.assert_not_called()

    def test_cgroup_root_is_never_written(self):
        with self.assertRaises(ValueError):self.run_setup(relative='/')
        self.writer.assert_not_called()

    def test_stopped_worker_is_never_written(self):
        with self.assertRaises(ValueError):self.run_setup(running=False)
        self.writer.assert_not_called()

    def test_ram_ceiling_is_rejected_before_write(self):
        with self.assertRaises(ValueError):self.run_setup(ceiling=str(112*1024**3))
        self.writer.assert_not_called()

    def test_pid_change_is_not_success(self):
        with self.assertRaises(ValueError):self.run_setup(after_pid=43)
        self.writer.assert_called_once()

    def test_swap_write_must_be_verified(self):
        with self.assertRaises(ValueError):self.run_setup(swap='max')
        self.writer.assert_called_once()
