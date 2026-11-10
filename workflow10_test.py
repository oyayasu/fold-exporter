import unittest
from dataclasses import replace
import storyboard as sb
from integration_test import drawings,reference
class Workflow10(unittest.TestCase):
 def test_bounded_labels_and_organizers(self):
  self.assertEqual(sb.frame_number('work #3a',True),'3A');self.assertEqual(sb.frame_number('work #3',False),3)
  self.assertIsNone(sb.frame_number('take 2 frame 3',True));self.assertEqual(sb.frame_number('3Chapter',True),'3CHAPTER');self.assertEqual(sb.chapter_number('3Chapter'),'3')
 def test_loose_cards_can_map_to_different_chapters_without_using_stack_index(self):
  ref=reference();ds=drawings();d=replace(ds[0],source_chapter=());ch=ref['chapters'][-1];card=ch['cards'][0];over={'frameChapters':{sb.frame_match_key(d):ch['id']},'frames':{sb.frame_match_key(d):card['id']}}
  result=sb.resolve_links([d],ref,over)[1][sb.frame_key(d)];self.assertEqual(result['chapter']['id'],ch['id']);self.assertEqual(result['card']['id'],card['id'])
if __name__=='__main__':unittest.main()
