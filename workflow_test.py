"""Stable labels, multi-source conflicts and real on-disk rough archives."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
import storyboard as sb
import studio_link as studio
import media_catalog as catalog
from studio_link_test import shared
from integration_test import drawings,reference
import export_core as core
class WorkflowTests(unittest.TestCase):
 def test_lettered_frames_do_not_fall_back_to_normal_numbers(self):
  ref=reference();ch=ref['chapters'][0];base=ch['cards'][0];base.update(frameLabel='1',globalFrameLabel='1',displayLabel='1',exportNumber=1,slightModifyIndex='')
  mod={**base,'id':'variation','sourceCardId':'variation','number':2,'globalNumber':100,'displayNumber':2,'frameLabel':'1A','globalFrameLabel':'1A','displayLabel':'1A','exportNumber':1,'slightModifyIndex':'A'};ch['cards'].append(mod)
  from dataclasses import replace
  ds=drawings();d=ds[0];node=replace(d.frame or d.node,name='Frame 1A');d=replace(d,frame=node)
  # Name the source chapter to the reference chapter explicitly.
  overrides={'chapters':{sb.chapter_key(sb.source_chapter(d)):ch['id']},'lettered':True}
  self.assertEqual(sb.resolve_links([d],ref,overrides)[1][sb.frame_key(d)]['card']['id'],'variation')
  overrides['lettered']=False;self.assertIsNone(sb.resolve_links([d],ref,overrides)[1][sb.frame_key(d)]['card'])
  self.assertIsNone(sb.frame_number('3B',False));self.assertEqual(sb.frame_number('Frame 3B',True),'3B')
 def test_saved_frame_identity_survives_normal_card_renumbering(self):
  ref=reference();ds=drawings();d=ds[0];ch=ref['chapters'][0];card=ch['cards'][0];overrides={'chapters':{sb.chapter_key(sb.source_chapter(d)):ch['id']},'frames':{sb.frame_match_key(d):card['id']}}
  card.update(number=7,displayNumber=7,frameLabel='7',displayLabel='7');self.assertEqual(sb.resolve_links([d],ref,overrides)[1][sb.frame_key(d)]['card']['id'],card['id'])
 def test_letter_matching_is_opt_in_so_existing_numeric_folders_keep_their_meaning(self):
  from dataclasses import replace
  ref=reference();ch=ref['chapters'][0];template=ch['cards'][0]
  base={**template,'id':'base','sourceCardId':'base','number':3,'globalNumber':3,'displayNumber':3,'frameLabel':'3','displayLabel':'3'}
  mod={**template,'id':'mod','sourceCardId':'mod','number':4,'globalNumber':4,'displayNumber':4,'frameLabel':'3A','displayLabel':'3A'}
  normal={**template,'id':'regular','sourceCardId':'regular','number':5,'globalNumber':5,'displayNumber':5,'frameLabel':'4','displayLabel':'4'}
  ch['cards']=[base,mod,normal];d=drawings()[0];d=replace(d,frame=replace(d.frame or d.node,name='Frame 4'));opts={'chapters':{sb.chapter_key(sb.source_chapter(d)):ch['id']}}
  self.assertEqual(sb.resolve_links([d],ref,opts)[1][sb.frame_key(d)]['card']['id'],'mod')
  opts['lettered']=True;self.assertEqual(sb.resolve_links([d],ref,opts)[1][sb.frame_key(d)]['card']['id'],'regular')
 def test_archive_uses_configured_names_and_updates_registry(self):
  with TemporaryDirectory() as tmp:
   project=shared(tmp);card=project.reference['chapters'][0]['cards'][0];ch=project.reference['chapters'][0];old='1 - Opening/Rough.png';path=project.root/old;path.parent.mkdir();path.write_bytes(b'rough');manifest=studio.read_json(project.root/'Studio Link/project.json');manifest['storyboards']={'saved':{'relativePath':old,'sourceCardId':card.get('sourceCardId',card['id']),'cardId':card['id']}}
   catalog.atomic_json(project.root/'Studio Link/project.json',manifest);catalog.atomic_json(project.root/'Studio Link/storyboard-outputs.json',{'format':'storyboard-outputs-v1','files':{old:{'project':project.project_id,'key':'drawing:'+card['id']+':0'}}})
   catalog.archive_storyboards(project,{'frame':{'sourceCardId':card.get('sourceCardId',card['id']),'card':card,'chapter':ch}})
   after=project.root/'1 - Opening_storyboard/1_storyboard.png';self.assertEqual(after.read_bytes(),b'rough');self.assertFalse(path.exists());self.assertEqual(studio.read_json(project.root/'Studio Link/project.json')['storyboards']['saved']['relativePath'],after.relative_to(project.root).as_posix())
 def test_empty_suffix_for_normal_card_and_separate_letter_field(self):
  profile={**studio.DEFAULT_NAMING,'card':'{card_number}{slight_modify_index}_{chapter_number}.{project}'};context={'card_number':3,'chapter_number':1,'project':'Film','slight_modify_index':'A'};self.assertEqual(studio.render_name(profile,'card',context),'3A_1.Film');context['slight_modify_index']='';self.assertEqual(studio.render_name(profile,'card',context),'3_1.Film')
if __name__=='__main__':unittest.main()
