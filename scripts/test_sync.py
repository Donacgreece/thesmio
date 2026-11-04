"""Offline contract tests for the open-data adapters."""
import unittest
import sync_data as s
class Adapters(unittest.TestCase):
    def test_law(self):
        row={'Title':'Δοκιμή','LawNum':123,'DateVoted':'03/11/2026'}
        parsed=s.law(row)
        self.assertEqual(parsed['datevoted'],'2026-11-03')
        self.assertEqual(parsed['lawnum'],'123')
    def test_nested(self):
        self.assertEqual(s.arr({'data':{'items':[{'title':'A'}]}}),[{'title':'A'}])
    def test_member(self):
        self.assertEqual(s.generic({'first_name':'Μαρία','last_name':'Παπαδοπούλου'},'members')['title'],'Μαρία Παπαδοπούλου')
    def test_links(self):
        self.assertEqual(s.href('javascript:alert(1)'),'')
if __name__=='__main__':unittest.main()
