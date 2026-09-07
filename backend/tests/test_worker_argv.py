"""Exercise the actual worker argv expression without importing its model launcher."""
import ast
from pathlib import Path
import unittest

class WorkerArgvTests(unittest.TestCase):
    def test_selected_resolution_is_forwarded(self):
        tree=ast.parse((Path(__file__).resolve().parents[2]/'runtime/worker.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='args' for t in n.targets))
        code=compile(ast.Expression(node.value),'<worker-argv>','eval')
        for tokens in (220,440,880):
            prompt='literal; $(never-run)'
            argv=eval(code,{'__builtins__':{'str':str}}, {'spatial_tokens':tokens,'spec':{'preset':'trial','prompt':prompt,'seed':123}})
            self.assertEqual(argv[argv.index('--target_spatial_tokens')+1],str(tokens))
            self.assertEqual(argv[argv.index('--num_inference_steps')+1],'50')
            self.assertEqual(argv[argv.index('--prompt')+1],prompt)
            self.assertEqual(argv.count('--target_spatial_tokens'),1)
