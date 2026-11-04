"""Offline contract test for backup public legislative archive."""
import json
import unittest
from unittest.mock import patch
import sync_data

class FakeHTTP:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self):
        return json.dumps({'tree':[
            {'type':'blob','path':'2026/law_5310.txt'},
            {'type':'blob','path':'2025/N_5201.txt'},
            {'type':'blob','path':'2026/README.md'},
            {'type':'blob','path':'2026/unrelated.txt'}
        ]}).encode()

class ArchiveTests(unittest.TestCase):
    @patch.object(sync_data,'urlopen',return_value=FakeHTTP())
    def test_archive_preserves_source_and_law_number(self, fake):
        laws=sync_data.collect_law_archive()
        self.assertEqual({x['lawnum'] for x in laws},{'5310','5201'})
        self.assertTrue(all('kafidas/just-text' in x['source'] for x in laws))
        self.assertTrue(all(x['title'].startswith('Νόμος ') for x in laws))

if __name__=='__main__': unittest.main()
