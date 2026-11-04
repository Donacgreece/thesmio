"""Offline verification of legalize-gr fallback."""
import io, json, unittest
from unittest.mock import patch
import sync_data

class Reply:
    def __init__(self,obj): self.data=json.dumps(obj).encode()
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def read(self,*a): return self.data

class GazetteTests(unittest.TestCase):
    @patch.object(sync_data,'urlopen')
    def test_fek_is_never_mislabeled_as_a_law(self,request):
        request.return_value=Reply({'tree':[
           {'type':'blob','path':'gr/FEK-A-0046-2020.md'},
           {'type':'blob','path':'gr/FEK-A-0182-2026.md'},
           {'type':'blob','path':'codes/AK/AK-0001.md'}]})
        rows=sync_data.collect_gazette_index()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['title'],'ΦΕΚ Α΄ 182/2026')
        self.assertEqual(rows[0]['lawnum'],'')
        self.assertIn('legalize-gr',rows[0]['source'])

    @patch.object(sync_data,'collect_gazette_index',return_value=[{'id':'fek-a-2026-1'}])
    @patch.object(sync_data,'collect_law_archive',side_effect=RuntimeError('empty archive'))
    def test_second_fallback_runs_after_failure(self,first,second):
        self.assertEqual(sync_data.backup_legislation()[0]['id'],'fek-a-2026-1')
        self.assertTrue(second.called)

if __name__=='__main__': unittest.main()
