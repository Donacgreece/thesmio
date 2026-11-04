import unittest
import sync_data as app

class DiavgeiaTests(unittest.TestCase):
    def test_ada_normalization(self):
        row={'ada':'ABC-123','subject':'Υπουργική απόφαση','issueDate':1730710800000,'organizationId':'15','decisionTypeId':'Α.3'}
        x=app.normalize_diavgeia(row)
        self.assertEqual(x['id'],'ABC-123')
        self.assertEqual(x['title'],'Υπουργική απόφαση')
        self.assertTrue(x['url'].endswith('/ABC-123'))
        self.assertEqual(x['date'],'2024-11-04')
    def test_no_fabricated_ada(self):
        self.assertIsNone(app.normalize_diavgeia({'subject':'No ADA'}))
    def test_array_from_decisions(self):
        self.assertEqual(len(app.arr({'decisions':[{'ada':'A','subject':'B'}]})),1)

if __name__=='__main__':unittest.main()
