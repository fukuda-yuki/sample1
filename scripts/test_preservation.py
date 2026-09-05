import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from preserve import pack, restore, verify, verify_receipt, read, digest, safe_name
from preservation_gate import check, reserve


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root / 'source'; self.source.mkdir()
        (self.source / 'a').write_text('original')
        self.archive = self.root / 'archive'

    def test_restore_without_source_and_reference_validation(self):
        common = pack(self.archive, 'common', {'files': self.source})
        run = pack(self.archive, 'run', {'submission': self.source}, references=[common])
        (self.source / 'a').unlink()
        receipt = restore(self.archive, run, self.root / 'restored')
        self.assertEqual((self.root / 'restored/submission/a').read_text(), 'original')
        self.assertEqual(verify_receipt(self.archive, receipt)['reference'], run)
        (self.archive / 'packages/common/payload/files/a').unlink()
        with self.assertRaises(ValueError): verify(self.archive, run['package_id'], run['sha256'])

    def test_extra_missing_modified_and_index_tampering(self):
        for mutation in ('extra', 'missing', 'modified', 'index'):
            with self.subTest(mutation=mutation):
                ref = pack(self.archive, mutation, {'a': self.source / 'a'})
                package = self.archive / 'packages' / mutation
                if mutation == 'extra': (package / 'payload/extra').write_text('x')
                if mutation == 'missing': (package / 'payload/a').unlink()
                if mutation == 'modified': (package / 'payload/a').write_text('x')
                if mutation == 'index': (package / 'package.json').write_text('{}')
                with self.assertRaises(ValueError): restore(self.archive, ref, self.root / mutation)

    def test_failed_copy_never_publishes_or_reuses_id(self):
        with patch('preserve.shutil.copy2', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):pack(self.archive, 'interrupted', {'a': self.source / 'a'})
        self.assertFalse((self.archive / 'packages/interrupted').exists())
        with self.assertRaises(FileExistsError):pack(self.archive, 'interrupted', {'a': self.source / 'a'})

    def test_paths_links_and_same_storage_rejected(self):
        for name in ('../x', '/x', 'a/../x', 'C:x', 'a\\x', 'a//x'):
            with self.assertRaises(ValueError):safe_name(name)
        with self.assertRaises(ValueError):pack(self.source / 'archive', 'nested', {'all': self.source})
        try: (self.source / 'link').symlink_to(self.source / 'a')
        except OSError: return
        with self.assertRaises(ValueError):pack(self.archive, 'link', {'all': self.source})

    def test_receipt_tampering(self):
        ref=pack(self.archive,'receipt',{'files':self.source})
        receipt=restore(self.archive,ref,self.root/'restore')
        (self.archive/receipt['path']).write_text('{}')
        with self.assertRaises(ValueError):verify_receipt(self.archive,receipt)

    def test_gate_version_and_single_use(self):
        common=pack(self.archive,'common',{'files':self.source})
        receipt=restore(self.archive,common,self.root/'restore')
        (self.root/'order.json').write_text(json.dumps({'order':[{'planned_run':'pilot-2-normal'}]}))
        keys=('hashes_match','usage_recomputed','normal_exit','timeout_exit','abnormal_exit',
              'normal_fixture','threshold_mutation','empty_daemon_restore','source_unavailable','evaluation_restored')
        proof={'checks':dict.fromkeys(keys,True),'model_called':False,'receipts':[receipt],
               'common':common,'source_hashes':{'source/a':digest(self.source/'a')}}
        (self.root/'proof.json').write_text(json.dumps(proof))
        gate=pack(self.archive,'gate',{'proof.json':self.root/'proof.json'},metadata={'kind':'restoration-proof'},references=[common])
        scope={'batch_id':'batch','planned_manifest':'order.json','preservation':{
            'archive':{'windows':str(self.archive),'linux':str(self.archive)},'gate':gate,'common':common}}
        config={'planned_run':'pilot-2-normal'}
        self.assertEqual(check(scope,config,self.root),self.archive)
        reserve(scope,config,self.root,'uuid')
        with self.assertRaises(ValueError):check(scope,config,self.root)
        with self.assertRaises(ValueError):reserve(scope,config,self.root,'other-uuid')
        check(scope,config,self.root,'uuid')
        (self.source/'a').write_text('changed')
        with self.assertRaises(ValueError):check(scope,config,self.root,'uuid')


if __name__ == '__main__':unittest.main()
