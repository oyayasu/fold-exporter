from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import json,unittest
from types import SimpleNamespace
import media_catalog as catalog
class CatalogTests(unittest.TestCase):
 def project(self,tmp):
  root=Path(tmp).resolve();(root/'Studio Link').mkdir();return SimpleNamespace(root=root,project_id='project')
 def index(self,p,export='new',stamp='2026-11-06T10:00:00.000Z'):
  path=p.root/'Chapter'/'arbitrary.png';path.parent.mkdir(exist_ok=True);path.write_bytes(b'png')
  return {'exportId':export,'source':{'id':'source'},'frames':[{'sourceCardId':'card','variantIndex':0,'variantAssetId':'art','exportId':export,'exportedAt':stamp,'complete':True,'files':[{'kind':'whole-frame','path':'Chapter/arbitrary.png','filename':'arbitrary.png','width':2,'height':2}]}]}
 def test_publishes_arbitrary_names_and_stable_drawing_identity(self):
  with TemporaryDirectory()as tmp:
   p=self.project(tmp);catalog.publish(p,self.index(p));data=catalog.read(p);e=data['entries'][catalog.key('card',0)];self.assertEqual(e['files'][0]['name'],'arbitrary.png');self.assertEqual(e['files'][0]['stackOrder'],1);self.assertEqual(catalog.known_owners(p)['Chapter/arbitrary.png'],catalog.key('card',0))
 def test_old_partial_frames_do_not_reclaim_manual_cleanup(self):
  with TemporaryDirectory()as tmp:
   p=self.project(tmp);index=self.index(p);catalog.publish(p,index);data=catalog.read(p);e=data['entries'][catalog.key('card',0)];e['source']='manual';e['updatedAt']='2026-11-06T11:00:00.000Z';(p.root/'Studio Link/media-index.json').write_text(json.dumps(data));index['exportId']='another';catalog.publish(p,index);self.assertEqual(catalog.read(p)['entries'][catalog.key('card',0)]['source'],'manual')
 def test_fresh_explicit_export_replaces_manual_or_different_source(self):
  with TemporaryDirectory()as tmp:
   p=self.project(tmp);index=self.index(p);catalog.publish(p,index);new=self.index(p,'later','2026-11-06T12:00:00.000Z');new['source']['id']='moved-csp';catalog.publish(p,new);self.assertEqual(len(catalog.read(p)['entries']),1);self.assertEqual(catalog.read(p)['entries'][catalog.key('card',0)]['sourceId'],'moved-csp');self.assertFalse((p.root/'Studio Link/.media-index.lock').exists())
 def test_unrelated_project_is_rejected(self):
  with TemporaryDirectory()as tmp:
   p=self.project(tmp);index=self.index(p);catalog.publish(p,index);p.project_id='other'
   with self.assertRaises(ValueError):catalog.read(p)
if __name__=='__main__':unittest.main()
