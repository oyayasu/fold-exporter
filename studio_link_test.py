"""Studio Link regressions with real source PSDs and actual image-index files."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import shutil
import unittest
from unittest.mock import patch
from PIL import Image
import export_core as core
import storyboard as sb
import studio_link as studio
from integration_test import reference,drawings,hidden_psd,frame_one_drawings


def shared(root,ref=None):
    root=Path(root);link=root/studio.LINK_FOLDER;link.mkdir(parents=True,exist_ok=True)
    ref=deepcopy(ref or reference())
    for ch in ref['chapters']:
        for card in ch['cards']:card.update(variantIndex=0,variantAssetId='art-'+card['id'])
    ref['naming']={**studio.DEFAULT_NAMING,'card':'Drawing_{card_number}'}
    ref['chapterDirectories']=[{'chapterId':ch['id'],'path':ch['number']+' - '+ch['title']} for ch in ref['chapters']]
    manifest={'format':'studio-link-project-v1','schemaVersion':1,'project':ref['project'],
              'naming':ref['naming'],'chapterDirectories':ref['chapterDirectories'],'files':{'reference':'storyboard.ssreference.json'}}
    (link/'project.json').write_text(json.dumps(manifest),encoding='utf-8')
    (link/'storyboard.ssreference.json').write_text(json.dumps(ref),encoding='utf-8')
    return studio.read_project(root)


class StudioLinkTests(unittest.TestCase):
    def test_linked_reexport_updates_owned_images_and_one_index_without_numbered_versions(self):
        with TemporaryDirectory() as tmp:
            p=shared(tmp);source=p.root/'clean.psd';doc=hidden_psd(source)
            ds=frame_one_drawings(doc,'Whole frame only');settings=core.Settings(component_mode='Whole frame only')
            def plan():return sb.make_plan(ds,{d.node.key for d in ds},p.root,settings,p.reference,workspace=p,chapter_style=studio.PROJECT_FOLDERS,naming_mode=studio.PROJECT_NAMES)
            first=plan();records=[]
            made,failed,cancelled=core.export(doc,False,first.tasks,settings,on_saved=lambda d,path,size:records.append((d,path,size)),output_root=p.root,output_writer=sb.linked_image_writer(first,source))
            self.assertEqual(failed,[]);old=made[0].read_bytes();index=sb.write_plan_index(first,sb.inventory(first,settings,source,(16,12),records,failed,cancelled))
            second=plan();self.assertEqual(first.tasks[0][1],second.tasks[0][1]);records=[]
            with patch('export_core.render',return_value=Image.new('RGBA',(16,12),(0,255,0,255))):
                updated,failed,cancelled=core.export(doc,False,second.tasks,settings,on_saved=lambda d,path,size:records.append((d,path,size)),output_root=p.root,output_writer=sb.linked_image_writer(second,source))
            self.assertEqual(failed,[]);self.assertEqual(made,updated);self.assertNotEqual(updated[0].read_bytes(),old)
            self.assertEqual(sb.write_plan_index(second,sb.inventory(second,settings,source,(16,12),records,failed,cancelled)),index)
            self.assertEqual(len(list(index.parent.glob('folderexporter-index*.json'))),1);self.assertEqual(len(list(updated[0].parent.glob('*.png'))),1)
            updated[0].write_bytes(b'An external edit to preserve')
            made,failed,_=core.export(doc,False,second.tasks,settings,output_root=p.root,output_writer=sb.linked_image_writer(second,source))
            self.assertEqual(failed,[]);self.assertEqual(made,updated);self.assertNotEqual(updated[0].read_bytes(),b'An external edit to preserve')

    def test_root_or_studio_link_selection_and_wrong_project_gate(self):
        with TemporaryDirectory() as tmp:
            p=shared(tmp);self.assertEqual(studio.read_project(Path(tmp)/studio.LINK_FOLDER).root,p.root)
            with self.assertRaisesRegex(ValueError,'another project'):studio.read_project(tmp,'wrong')
            with self.assertRaises(OSError):studio.read_project(Path(tmp)/'missing')

    def test_invalid_and_external_chapter_locations_are_rejected(self):
        with TemporaryDirectory() as tmp,TemporaryDirectory() as outside:
            p=shared(tmp);manifest=p.manifest
            for path in ('../outside','/outside','Chapter\\1','a//b','a/./b'):
                manifest['chapterDirectories'][0]['path']=path;(p.root/studio.LINK_FOLDER/'project.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):studio.read_project(tmp)
            (p.root/'escape').symlink_to(outside,target_is_directory=True);manifest['chapterDirectories'][0]['path']='escape'
            (p.root/studio.LINK_FOLDER/'project.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):studio.read_project(tmp)

    def test_project_profile_reuses_exact_flat_chapter_paths_and_shared_card_base(self):
        with TemporaryDirectory() as tmp:
            p=shared(tmp);ds=drawings();settings=core.Settings(component_stack_order=True,padding=1)
            plan=sb.make_plan(ds,{d.node.key for d in ds},tmp,settings,p.reference,chapter_style=studio.PROJECT_FOLDERS,workspace=p,naming_mode=studio.PROJECT_NAMES)
            names={d.node.name:path.relative_to(p.root).as_posix() for d,path in plan.tasks}
            self.assertEqual(names['Background'],'1 - Opening/Drawing_2_component-1.png')
            self.assertEqual(names['Character'],'1 - Opening/Drawing_2_component-3.png')
            self.assertEqual(names['Frame 1'],'1 - Opening/Drawing_1.png')
            self.assertEqual(sb.chapter_path(p.reference['chapters'][1],p.reference,studio.PROJECT_FOLDERS,()),('1.1 - Detail',))

    def test_custom_slots_remain_available_with_shared_folders(self):
        with TemporaryDirectory() as tmp:
            p=shared(tmp);ds=drawings();settings=core.Settings(slots=(core.NameSlot('Custom text','My files'),core.NameSlot('Card number'),core.NameSlot('Component'),core.NameSlot('Component index')),separators=('_','_','_'),padding=1,component_stack_order=True)
            plan=sb.make_plan(ds,{d.node.key for d in ds},tmp,settings,p.reference,chapter_style=studio.PROJECT_FOLDERS,workspace=p)
            self.assertIn('My files_2_Background_1.png',[path.name for d,path in plan.tasks]);self.assertTrue(all(path.parent==p.root/'1 - Opening' for d,path in plan.tasks))

    def test_existing_storyboards_are_kept_and_index_contains_actual_cleanup_locations(self):
        with TemporaryDirectory() as tmp:
            p=shared(tmp);source=p.root/'clean.psd';doc=hidden_psd(source);digest=hashlib.sha256(source.read_bytes()).hexdigest()
            out=p.root/'1 - Opening';out.mkdir();original=out/'Drawing_1.png';original.write_bytes(b'preserve this prior output')
            ds=frame_one_drawings(doc,'Whole frame only');settings=core.Settings(component_mode='Whole frame only');records=[]
            plan=sb.make_plan(ds,{d.node.key for d in ds},p.root,settings,p.reference,workspace=p,chapter_style=studio.PROJECT_FOLDERS,naming_mode=studio.PROJECT_NAMES)
            made,failed,cancelled=core.export(doc,False,plan.tasks,settings,on_saved=lambda d,path,size:records.append((d,path,size)),output_root=p.root)
            self.assertEqual(failed,[]);self.assertEqual(original.read_bytes(),b'preserve this prior output');self.assertEqual(len(made),1)
            data=sb.inventory(plan,settings,source,(16,12),records,failed,cancelled);index=sb.write_plan_index(plan,data)
            self.assertEqual(index.parent,p.root/'Studio Link');self.assertEqual(data['pathBase'],'media-root');self.assertEqual(data['mediaRoot'],'.')
            self.assertEqual(data['storyboardReference']['chapters'][0]['cards'][0]['variantIndex'],0)
            self.assertTrue(data['reuse']['variantAssignmentsIncluded']);self.assertTrue((p.root/data['frames'][0]['files'][0]['path']).is_file())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),digest)
            second=sb.write_plan_index(plan,data);self.assertEqual(index,second);self.assertTrue(index.is_file());self.assertEqual(len(list(index.parent.glob("folderexporter-index*.json"))),1)

    def test_project_move_rebases_paths_without_losing_identity(self):
        with TemporaryDirectory() as tmp:
            original=Path(tmp)/'Old';original.mkdir();p=shared(original);destination=Path(tmp)/'Moved';shutil.move(original,destination)
            moved=studio.read_project(destination,p.project_id);self.assertEqual(moved.project_id,p.project_id);self.assertEqual(moved.root,destination.resolve())
            with self.assertRaises(OSError):studio.validate_output_root(p)

    def test_foreign_reference_and_changed_project_snapshot_are_rejected(self):
        with TemporaryDirectory() as tmp:
            p=shared(tmp);path=p.root/'Studio Link/storyboard.ssreference.json';ref=deepcopy(p.reference);ref['project']['id']='other';path.write_text(json.dumps(ref))
            with self.assertRaisesRegex(ValueError,'different projects'):studio.read_project(tmp)
            ref['project']['id']=p.project_id;ref['structuralSignature']='new-version';path.write_text(json.dumps(ref))
            with self.assertRaisesRegex(ValueError,'changed while exporting'):studio.validate_output_root(p)

    def test_export_refuses_external_symlink_before_creating_any_subfolders(self):
        with TemporaryDirectory() as tmp,TemporaryDirectory() as outside:
            p=shared(tmp);escape=p.root/'escape';escape.symlink_to(outside,target_is_directory=True);node=core.Node((0,),'Frame 1',None)
            drawing=core.Drawing(node,());target=escape/'not-created'/'File.png'
            made,failed,cancelled=core.export(None,False,[(drawing,target)],core.Settings(),output_root=p.root)
            self.assertEqual(made,[]);self.assertEqual(len(failed),1);self.assertFalse((Path(outside)/'not-created').exists())

    def test_shared_sanitization_padding_and_unicode_match_documented_contract(self):
        profile={**studio.DEFAULT_NAMING,'card':'{project}_{global_number}_{variant}','padding':4}
        self.assertEqual(studio.render_name(profile,'card',{'project':'日本語 / Project','global_number':12,'variant':'B'}),'日本語 _ Project_0012_B')
        self.assertLessEqual(len(studio.file_leaf('猫'*100).encode('utf-8')),120)
        self.assertEqual(studio.file_leaf('CON'),'_CON')
        for invalid in ('../escape','{unknown}','{card_number'):
            with self.assertRaises(ValueError):studio.naming_profile({**profile,'card':invalid})

    def test_relative_source_identity_survives_project_move_and_partial_frames_are_marked(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'Before';root.mkdir();p=shared(root);source=root/'Art.psd';source.write_bytes(b'not rendered');identity=studio.source_id(source,p)
            moved=Path(tmp)/'After';shutil.move(root,moved);new=studio.read_project(moved,p.project_id)
            self.assertEqual(studio.source_id(moved/'Art.psd',new),identity)
            ds=drawings();settings=core.Settings();plan=sb.make_plan(ds,{d.node.key for d in ds},moved,settings,new.reference,workspace=new)
            part=next((d,path) for d,path in plan.tasks if d.is_component)
            data=sb.inventory(plan,settings,moved/'Art.psd',(16,12),[(part[0],part[1],(16,12))],[('Character','failed')],False)
            self.assertFalse(data['complete']);self.assertFalse(data['frames'][0]['complete']);self.assertEqual(data['frames'][0]['expectedFileCount'],3)

    def test_index_fallback_keeps_existing_files_and_cleans_temporary_output(self):
        with TemporaryDirectory() as tmp,patch('storyboard.os.link',side_effect=OSError('No hard links')):
            first=sb.write_index(tmp,{'first':True});second=sb.write_index(tmp,{'second':True})
            self.assertNotEqual(first,second);self.assertEqual(json.loads(first.read_text()),{'first':True})
            self.assertEqual(json.loads(second.read_text()),{'second':True});self.assertFalse(list(Path(tmp).glob('*.tmp')))

    def test_legacy_reference_does_not_claim_variant_snapshots(self):
        with TemporaryDirectory() as tmp:
            ds=drawings();settings=core.Settings();plan=sb.make_plan(ds,{d.node.key for d in ds},tmp,settings,reference());records=[(d,path,(16,12)) for d,path in plan.tasks]
            data=sb.inventory(plan,settings,'source.psd',(16,12),records,[],False)
            self.assertFalse(data['reuse']['variantAssignmentsIncluded']);self.assertEqual(data['pathBase'],'index-directory');self.assertNotIn('mediaRoot',data)


if __name__=='__main__':unittest.main()
