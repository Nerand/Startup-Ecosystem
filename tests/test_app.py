import sys, unittest, tempfile, datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import profile, evaluate, CATALOG, initialize, route_create, toggle, routes

class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.db=str(Path(self.temp.name)/'test.db'); initialize(self.db)
        self.p=profile(dict(title='Исследование растений',grade=9,age=15,team=2,topics=['ai'],has_project=True))
    def tearDown(self): self.temp.cleanup()
    def test_age_and_team_block_research_competition(self):
        e=CATALOG[0]
        self.assertTrue(evaluate(self.p,e)['eligible'])
        self.assertFalse(evaluate({**self.p,'age':12},e)['eligible'])
        self.assertFalse(evaluate({**self.p,'team':4},e)['eligible'])
        self.assertFalse(evaluate({**self.p,'has_project':False},e)['eligible'])
    def test_grade_changes_nto_track(self):
        self.assertTrue(evaluate(self.p,CATALOG[1])['eligible'])
        self.assertFalse(evaluate(self.p,CATALOG[2])['eligible'])
        younger={**self.p,'grade':6,'age':12}
        self.assertFalse(evaluate(younger,CATALOG[1])['eligible'])
        self.assertTrue(evaluate(younger,CATALOG[2])['eligible'])
    def test_route_survives_reopen_and_status_reversal(self):
        deadline=(datetime.date.today()+datetime.timedelta(days=30)).isoformat()
        r=route_create(self.db,self.p,'baltic',deadline)
        toggle(self.db,r['id'],'0',True); initialize(self.db)
        self.assertTrue(routes(self.db)[0]['tasks'][0]['done'])
        toggle(self.db,r['id'],'0',False)
        self.assertFalse(routes(self.db)[0]['tasks'][0]['done'])
    def test_invalid_creation_and_status_do_not_corrupt_data(self):
        with self.assertRaises(ValueError): route_create(self.db,{**self.p,'team':5},'baltic','2030-01-01')
        self.assertEqual(routes(self.db),[])
        r=route_create(self.db,self.p,'baltic','2030-01-01')
        with self.assertRaises(ValueError): toggle(self.db,r['id'],'0','true')
        self.assertFalse(routes(self.db)[0]['tasks'][0]['done'])
    def test_profile_rejects_unknown_directions_and_boolean_age(self):
        with self.assertRaises(ValueError): profile({**self.p,'topics':['unknown']})
        with self.assertRaises(ValueError): profile({**self.p,'age':True})

if __name__=='__main__': unittest.main()
