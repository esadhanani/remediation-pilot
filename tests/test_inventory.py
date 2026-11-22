import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import inventory


class AdvisoryResponseTests(unittest.TestCase):
    def test_confirmed_empty_result_and_match_stay_aligned(self):
        packages = [('PyPI', 'example-a', '1'), ('PyPI', 'example-b', '1')]
        response = {'results': [{}, {'vulns': [{'id': 'example-advisory'}]}]}
        with patch.object(inventory, 'http', return_value=response):
            self.assertEqual(inventory.osv_batch(packages), [[], ['example-advisory']])

    def test_failed_batch_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = [folder / name for name in ('repos.jsonl', 'findings.jsonl')]
            for path in paths:
                path.write_text('previous snapshot')
            with patch.object(inventory, 'DATA', folder), patch.object(inventory, 'ORGS', [{'org': 'fixture'}]), \
                 patch.object(inventory, 'list_repos', return_value=[{'repo': 'fixture/sample'}]), \
                 patch.object(inventory, 'sbom_packages', return_value={('PyPI', 'example', '1'): True}):
                for response in (None, {}, {'results': []}, {'results': [{'error': 'unavailable'}]}):
                    with self.subTest(response=response), patch.object(inventory, 'http', return_value=response):
                        with self.assertRaisesRegex(RuntimeError, 'snapshot was not written'):
                            inventory.main()
                        self.assertEqual([p.read_text() for p in paths], ['previous snapshot'] * 2)
