import ast
from pathlib import Path
import unittest
from patch_pi import patched

class PatchTests(unittest.TestCase):
    def test_current_production_patch(self):
        source=Path('/opt/ragtech-monitor/ragtech_nut.py').read_text()
        updated=patched(source);self.assertEqual(patched(updated),updated)
        before,after=ast.parse(source),ast.parse(updated)
        changed={'main','power_restored_sequence','clear_fsd'}
        for node in before.body:
            if isinstance(node,ast.FunctionDef) and node.name not in changed:
                other=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name==node.name)
                self.assertEqual(ast.dump(node),ast.dump(other),node.name)
        code=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name=='power_restored_sequence')
        self.assertNotIn('read_ups()',ast.unparse(code))
        main=next(n for n in after.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        self.assertIn('record_critical(data)',ast.unparse(main))

if __name__=='__main__':unittest.main(verbosity=2)
