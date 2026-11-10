"""Regression tests for links, physical stack order and real saved inventories."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
from itertools import product
import json
import threading
import shutil
import unittest
from unittest.mock import patch
from PIL import Image
import export_core as core
import storyboard as sb

def reference():
    def card(ch,n,g):return {'id':f'{ch}-card{n}','number':n,'globalNumber':g,'displayNumber':n}
    return {'format':'storyboardstudio-reference-v1','schemaVersion':1,'exportedAt':'2026-11-02T00:00:00Z',
        'structuralSignature':'sample-signature','project':{'id':'project-original','name':'My Story','numbering':'chapter','ratio':'16:9'},
        'componentOrder':{'direction':'bottom-to-top','startIndex':1},'chapters':[
        {'id':'opening','number':'1','title':'Opening','parentId':None,'cards':[card('opening',1,1),card('opening',2,2)]},
        {'id':'detail','number':'1.1','title':'Detail','parentId':'opening','cards':[card('detail',1,3)]},
        {'id':'ending','number':'2','title':'Ending','parentId':None,'cards':[card('ending',1,4)]}]}

def drawings():
    # folder_tree exposes the CSP panel from top to bottom.
    top=core.Node((0,1,2),'Character',None)
    middle=core.Node((0,1,1),'Object',None)
    bottom=core.Node((0,1,0),'Background',None)
    frame2=core.Node((0,1),'Frame 2',None,children=[top,middle,bottom])
    frame1=core.Node((0,0),'Frame 1',None)
    chapter=core.Node((0,),'Chapter 1',None,children=[frame2,frame1])
    rules=[core.ComponentRule('Character','Character'),core.ComponentRule('Object','Object'),core.ComponentRule('Background','Background')]
    return core.discover([chapter],rules=rules)

def hidden_psd(path,flags=(False,False,False),clip_overlay=False):
    """Actual serialized PSD, not a compositor mock: hidden branches cache boxes."""
    from psd_tools import PSDImage
    from psd_tools.api.layers import Group,PixelLayer
    doc=PSDImage.new('RGBA',(16,12));ch=Group.new(doc,'Chapter 1');frame=Group.new(ch,'Frame 1')
    bg=Group.new(frame,'Background');PixelLayer.frompil(Image.new('RGBA',(16,12),'blue'),bg,'Paint')
    hidden=Group.new(bg,'Hidden inner group');PixelLayer.frompil(Image.new('RGBA',(16,12),'green'),hidden,'Hidden paint');hidden.visible=False
    if clip_overlay:
        overlay=PixelLayer.frompil(Image.new('RGBA',(16,12),(255,0,0,128)),frame,'Clipped overlay');overlay.clipping=True
    character=Group.new(frame,'Character');PixelLayer.frompil(Image.new('RGBA',(4,4),'red'),character,'Paint',top=2,left=5)
    other=Group.new(ch,'Frame 2');PixelLayer.frompil(Image.new('RGBA',(16,12),'green'),other,'Unselected drawing')
    PixelLayer.frompil(Image.new('RGBA',(16,12),'yellow'),doc,'Unclipped loose layer')
    ch.visible,frame.visible,bg.visible=flags;doc.save(path)
    return core.open_project(path)

def visibility_snapshot(doc):
    result=[]
    def visit(container):
        for layer in container:
            result.append((id(layer),layer.visible))
            if layer.is_group():visit(layer)
    visit(doc);return result

def frame_one_drawings(doc,mode='Separate components'):
    return [d for d in core.discover(core.folder_tree(doc,False),rules=[core.ComponentRule('Background','BG'),core.ComponentRule('Character','Character')],component_mode=mode) if (d.frame or d.node).name=='Frame 1']

class IntegrationTests(unittest.TestCase):
    def test_real_psd_hidden_target_and_ancestors_render_in_every_visibility_combination(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'hidden.psd'
            for flags in product((False,True),repeat=3):
                with self.subTest(visibility=flags):
                    doc=hidden_psd(path,flags);before=visibility_snapshot(doc);digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    drawing=next(d for d in frame_one_drawings(doc) if d.label=='BG')
                    # Prime the real compositor's visibility-dependent cache.
                    for group in (doc[0],doc[0][0],doc[0][0][0]):_ = group.bbox
                    image=core.render(doc,drawing,False,core.Settings())
                    try:self.assertEqual(image.getpixel((0,0)),(0,0,255,255))
                    finally:image.close()
                    self.assertEqual(visibility_snapshot(doc),before)
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)

    def test_hidden_frame_and_components_export_real_pixels_and_distinct_index_entries(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'hidden.psd';doc=hidden_psd(path,(False,False,True));before=visibility_snapshot(doc)
            digest=hashlib.sha256(path.read_bytes()).hexdigest();ds=frame_one_drawings(doc,'Separate + whole frame')
            settings=core.Settings(component_mode='Separate + whole frame');plan=sb.make_plan(ds,{d.node.key for d in ds},Path(tmp)/'out',settings,reference());records=[]
            made,failed,cancelled=core.export(doc,False,plan.tasks,settings,on_saved=lambda d,p,size:records.append((d,p,size)))
            self.assertEqual(failed,[]);self.assertEqual(len(made),3)
            for drawing,file,size in records:
                with Image.open(file) as image:
                    self.assertIsNotNone(image.getchannel('A').getbbox())
                    if not drawing.is_component:
                        self.assertEqual(image.getpixel((0,0)),(0,0,255,255));self.assertEqual(image.getpixel((5,2)),(255,0,0,255))
                    elif drawing.label=='Character':self.assertEqual(image.getpixel((0,0))[3],0)
            data=sb.inventory(plan,settings,path,(16,12),records,failed,cancelled)
            self.assertEqual([f['kind'] for f in data['frames'][0]['files']],['whole-frame','component','component'])
            self.assertEqual(visibility_snapshot(doc),before);self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)

    def test_hidden_component_crop_uses_rendered_bounds(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'hidden.psd';doc=hidden_psd(path,(False,False,True))
            char=next(d for d in frame_one_drawings(doc) if d.label=='Character');target=doc
            for index in char.node.key:target=target[index]
            target.visible=False;before=visibility_snapshot(doc)
            image=core.render(doc,char,False,core.Settings(crop=True,crop_scope='Components only'))
            try:self.assertEqual(image.size,(4,4));self.assertEqual(image.getpixel((0,0)),(255,0,0,255))
            finally:image.close()
            self.assertEqual(visibility_snapshot(doc),before)

    def test_visibility_is_restored_on_real_psd_compositor_failure_and_retry(self):
        with TemporaryDirectory() as tmp:
            doc=hidden_psd(Path(tmp)/'hidden.psd');drawing=next(d for d in frame_one_drawings(doc) if d.label=='BG');before=visibility_snapshot(doc)
            with patch.object(type(doc),'composite',side_effect=RuntimeError('Compositor failed')):
                with self.assertRaisesRegex(RuntimeError,'Compositor failed'):core.render(doc,drawing,False,core.Settings())
            self.assertEqual(visibility_snapshot(doc),before)
            image=core.render(doc,drawing,False,core.Settings())
            try:self.assertEqual(image.getpixel((0,0)),(0,0,255,255))
            finally:image.close()

    def test_real_psd_hidden_component_keeps_clipped_overlay_and_excludes_unrelated_art(self):
        with TemporaryDirectory() as tmp:
            doc=hidden_psd(Path(tmp)/'hidden.psd',clip_overlay=True);drawing=next(d for d in frame_one_drawings(doc) if d.label=='BG');before=visibility_snapshot(doc)
            image=core.render(doc,drawing,False,core.Settings())
            try:
                red,green,blue,alpha=image.getpixel((5,2))
                self.assertEqual(alpha,255);self.assertGreater(red,50);self.assertGreater(blue,50);self.assertLess(green,10)
            finally:image.close()
            self.assertEqual(visibility_snapshot(doc),before)

    def test_reference_validation_and_bad_files(self):
        ref=reference();self.assertIs(sb.validate_reference(ref),ref)
        for mutate in (lambda r:r.update(format='other'),lambda r:r['chapters'].append(deepcopy(r['chapters'][0])),
            lambda r:r['chapters'][1].update(parentId='missing'),lambda r:r['chapters'][0]['cards'][0].update(number=True),
            lambda r:r['chapters'][0]['cards'][0].update(sourceCardId=[])):
            bad=deepcopy(ref);mutate(bad)
            with self.assertRaises(ValueError):sb.validate_reference(bad)
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/'ref.json';p.write_text('\ufeff'+json.dumps(ref),encoding='utf-8');self.assertEqual(sb.read_reference(p),ref)
            p.write_text('{broken',encoding='utf-8')
            with self.assertRaises(ValueError):sb.read_reference(p)

    def test_bottom_to_top_index_is_independent_of_frame_reverse(self):
        ds=drawings();sel={d.node.key for d in ds}
        with TemporaryDirectory() as tmp:
            for reverse in (False,True):
                settings=core.Settings(component_stack_order=True,reverse=reverse,slots=(core.NameSlot('Folder name'),core.NameSlot('Component'),core.NameSlot('Component index'),core.NameSlot()),separators=('_','_',''),padding=1)
                tasks=core.plan(ds,sel,Path(tmp),settings)
                numbered={d.node.name:(d.component_index,d.stack_order,p.name) for d,p in tasks if d.is_component}
                self.assertEqual(numbered['Background'],(1,1,'Frame 2_Background_1.png'))
                self.assertEqual(numbered['Character'],(3,3,'Frame 2_Character_3.png'))
            legacy=core.plan(ds,sel,Path(tmp),core.Settings())
            self.assertTrue(all(d.component_index==0 for d,p in legacy))
            selected={d.node.key for d in ds if d.node.name in ('Character','Background')}
            subset=core.plan(ds,selected,Path(tmp),core.Settings(component_stack_order=True))
            self.assertEqual({d.node.name:d.stack_order for d,p in subset},{'Character':2,'Background':1})

    def test_nested_parent_export_is_below_its_separate_child(self):
        child=core.Node((0,0,0,0),'Child',None)
        parent=core.Node((0,0,0),'Parent',None,children=[child])
        frame=core.Node((0,0),'Frame 1',None,children=[parent]);ch=core.Node((0,),'Chapter 1',None,children=[frame])
        ds=core.discover([ch],rules=[core.ComponentRule('*','{component}')])
        self.assertEqual({d.node.name:d.stack_order for d in ds},{'Parent':1,'Child':2})

    def test_links_use_source_numbers_and_survive_custom_names(self):
        ds=drawings();ref=reference();selected={d.node.key for d in ds}
        with TemporaryDirectory() as tmp:
            settings=core.Settings(project_folder='Custom project',frame_folders=True,component_stack_order=True,
                reverse=False,slots=(core.NameSlot('Custom text','My custom'),core.NameSlot('Component'),core.NameSlot('Component index'),core.NameSlot()),separators=('_','_',''),padding=1)
            plan=sb.make_plan(ds,selected,tmp,settings,ref)
            link=plan.links[sb.frame_key(ds[0])];self.assertEqual(link['card']['id'],'opening-card2')
            self.assertEqual(plan.root,Path(tmp).resolve()/'Custom project')
            self.assertIn('1 - Opening',str(plan.tasks[0][1]));self.assertIn('001',core._index(1,3))
            records=[(d,p,(32,24)) for d,p in plan.tasks]
            data=sb.inventory(plan,settings,'source.psd',(100,100),records,[],False)
            self.assertEqual([f['cardId'] for f in data['frames']],['opening-card1','opening-card2'])
            parts=data['frames'][1]['files'];self.assertEqual([p['label'] for p in parts],['Background','Object','Character'])
            self.assertEqual([p['stackOrder'] for p in parts],[1,2,3])
            self.assertEqual(data['storyboardReference']['structuralSignature'],'sample-signature')
            self.assertEqual(data['naming']['slots'][0]['text'],'My custom')
            self.assertTrue(all(not Path(p['path']).is_absolute() for f in data['frames'] for p in f['files']))

    def test_chapter_metadata_remains_when_folders_are_disabled(self):
        ds=drawings();tree=core.Node((0,),'Chapter 1',None,children=[core.Node((0,0),'Frame 1',None)])
        discovered=core.discover([tree],separate=False)
        self.assertEqual(discovered[0].chapter,());self.assertEqual(discovered[0].source_chapter,('Chapter 1',))
        with TemporaryDirectory() as tmp:
            s=core.Settings(separate=False)
            plan=sb.make_plan(discovered,{discovered[0].node.key},tmp,s,reference())
            self.assertEqual(plan.tasks[0][1].parent,Path(tmp).resolve())

    def test_symlinked_destination_and_index_share_the_physical_root(self):
        with TemporaryDirectory() as tmp:
            base=Path(tmp).resolve();physical=base/'physical';physical.mkdir()
            alias=base/'alias'
            try:alias.symlink_to(physical,target_is_directory=True)
            except (OSError,NotImplementedError) as exc:self.skipTest(f'Symlinks unavailable: {exc}')
            ds=drawings();s=core.Settings(project_folder='Project')
            plan=sb.make_plan(ds,{ds[-1].node.key},alias,s,reference())
            self.assertEqual(plan.root,physical/'Project');records=[]
            with patch.object(core,'render',return_value=Image.new('RGBA',(9,7),'blue')):
                made,failed,cancelled=core.export(None,False,plan.tasks,s,on_saved=lambda d,p,size:records.append((d,p,size)))
            self.assertEqual(failed,[]);self.assertEqual(len(made),1)
            data=sb.inventory(plan,s,'source.psd',(9,7),records,failed,cancelled)
            index=sb.write_index(plan.root,data)
            self.assertTrue(index.samefile(alias/'Project'/index.name))
            for frame in data['frames']:
                for item in frame['files']:
                    self.assertTrue((alias/'Project'/item['path']).samefile(physical/'Project'/item['path']))
                    self.assertFalse(Path(item['path']).is_absolute())
            self.assertEqual(plan.links['0/0']['card']['id'],'opening-card1')

    def test_root_and_subchapter_manual_matches(self):
        f=core.Node((0,),'My drawing',None);ds=[core.Drawing(f,(),frame=f)]
        _,links=sb.resolve_links(ds,reference());self.assertIsNone(links['0']['chapter'])
        override={'chapters':{sb.chapter_key(()):'detail'},'frames':{sb.frame_match_key(ds[0]):'detail-card1'}}
        with TemporaryDirectory() as tmp:
            plan=sb.make_plan(ds,{(0,)},tmp,core.Settings(),reference(),override)
            self.assertIn('1 - Opening/1.1 - Detail',plan.tasks[0][1].as_posix())
            self.assertEqual(sb.source_chapter(plan.tasks[0][0]),())
        self.assertIsNone(sb.frame_number('1.3'))
        self.assertEqual(sb.frame_number('003 - Door'),3)
        self.assertEqual(sb.chapter_number('Chapter 01.02 - Hello'),'1.2')

    def test_unmatched_duplicate_and_folder_collision_are_blocked(self):
        ds=drawings();selected={d.node.key for d in ds};ref=reference()
        with TemporaryDirectory() as tmp:
            bad=deepcopy(ref);bad['chapters'][0]['cards']=bad['chapters'][0]['cards'][:1]
            with self.assertRaisesRegex(ValueError,'not linked'):sb.make_plan(ds,selected,tmp,core.Settings(),bad)
            overrides={'frames':{sb.frame_match_key(ds[0]):'opening-card1'}}
            with self.assertRaisesRegex(ValueError,'same storyboard'):sb.make_plan(ds,selected,tmp,core.Settings(),ref,overrides)
            ref['chapters'][2]['title']='Opening';extra=core.Node((1,0),'Frame 1',None)
            more=ds+[core.Drawing(extra,('Chapter 2',),frame=extra)]
            with self.assertRaisesRegex(ValueError,'collide'):sb.make_plan(more,{d.node.key for d in more},tmp,core.Settings(),ref,chapter_style='Title only')

    def test_global_number_matching_is_explicit(self):
        f=core.Node((1,0),'Frame 4',None);ds=[core.Drawing(f,('Chapter 2',),frame=f)]
        _,links=sb.resolve_links(ds,reference(),number_mode='Global numbers')
        self.assertEqual(links['1/0']['card']['id'],'ending-card1')
        _,links=sb.resolve_links(ds,reference(),number_mode='Chapter numbers')
        self.assertIsNone(links['1/0']['card'])

    def test_saved_manual_links_follow_folder_names_when_csp_positions_change(self):
        ds=drawings();old=ds[0];overrides={'frames':{sb.frame_match_key(old):'opening-card1'}}
        moved_frame=core.Node((0,8),'Frame 2',None)
        moved=replace(old,node=core.Node((0,8,2),'Character',None),frame=moved_frame)
        inserted_frame=core.Node((0,1),'Frame 3',None)
        inserted=core.Drawing(inserted_frame,('Chapter 1',),frame=inserted_frame)
        _,links=sb.resolve_links([inserted,moved],reference(),overrides)
        self.assertEqual(links['0/8']['card']['id'],'opening-card1')
        self.assertIsNone(links['0/1']['card'])

    def test_card_number_slot_is_independent_of_subset_and_start_index(self):
        ds=drawings();selected={ds[0].node.key}
        s=core.Settings(start=80,padding=2,slots=(core.NameSlot('Card number'),core.NameSlot('Component'),core.NameSlot(),core.NameSlot()),separators=('_','',''))
        with TemporaryDirectory() as tmp:
            plan=sb.make_plan(ds,selected,tmp,s,reference())
            self.assertEqual(plan.tasks[0][1].name,'02_Character.png')
            self.assertEqual(plan.tasks[0][0].frame_index,80)
            self.assertEqual(plan.tasks[0][0].storyboard_number,2)

    def test_reusable_copies_share_one_export_across_chapters(self):
        ref=reference()
        for ch in ref['chapters'][1:]:ch['cards'][0]['sourceCardId']='opening-card1'
        sb.validate_reference(ref);ds=drawings();selected={ds[-1].node.key}
        with TemporaryDirectory() as tmp:
            s=core.Settings();plan=sb.make_plan(ds,selected,tmp,s,ref)
            self.assertEqual(len(plan.tasks),1)
            data=sb.inventory(plan,s,'art.psd',(24,16),[(d,p,(24,16)) for d,p in plan.tasks],[],False)
            self.assertEqual(len(data['frames']),1)
            frame=data['frames'][0];self.assertEqual(frame['sourceCardId'],'opening-card1')
            self.assertEqual([c['cardId'] for c in frame['cardReferences']],['opening-card1','detail-card1','ending-card1'])
            self.assertEqual([c['chapterNumber'] for c in frame['cardReferences']],['1','1.1','2'])
            self.assertEqual([c['isReusableCopy'] for c in frame['cardReferences']],[False,True,True])
            self.assertEqual(len(frame['files']),1)
            self.assertEqual(data['reuse']['multipleExportsForSource'],[])
            self.assertFalse(data['reuse']['variantAssignmentsIncluded'])

    def test_reuse_source_can_be_archived_while_copies_remain_active(self):
        ref=reference();ref['chapters'][0]['cards']=ref['chapters'][0]['cards'][1:]
        for ch in ref['chapters'][1:]:ch['cards'][0]['sourceCardId']='opening-card1'
        sb.validate_reference(ref)
        node=core.Node((0,),'Frame 1',None);ds=[core.Drawing(node,(),frame=node)]
        overrides={'chapters':{sb.chapter_key(()):'detail'}}
        with TemporaryDirectory() as tmp:
            s=core.Settings();plan=sb.make_plan(ds,{(0,)},tmp,s,ref,overrides)
            self.assertEqual(plan.links['0']['sourceCardId'],'opening-card1')
            self.assertEqual([c['cardId'] for c in plan.links['0']['cardReferences']],['detail-card1','ending-card1'])
            self.assertEqual(len(plan.tasks),1)

    def test_csp_can_skip_card_numbers_used_only_by_reusable_copies(self):
        ref=reference();ref['chapters'][0]['cards'][1]['sourceCardId']='opening-card1'
        ref['chapters'][0]['cards'].append({'id':'opening-card3','number':3,'globalNumber':3,'displayNumber':3})
        for index,card in enumerate((c for ch in ref['chapters'] for c in ch['cards']),1):card['globalNumber']=index
        sb.validate_reference(ref)
        chapter=core.Node((0,),'Chapter 1',None,children=[core.Node((0,1),'Frame 3',None),core.Node((0,0),'Frame 1',None)])
        ds=core.discover([chapter]);s=core.Settings(padding=1,slots=(core.NameSlot('Card number'),core.NameSlot(),core.NameSlot(),core.NameSlot()))
        with TemporaryDirectory() as tmp:
            plan=sb.make_plan(ds,{d.node.key for d in ds},tmp,s,ref)
            self.assertEqual({p.name for d,p in plan.tasks},{'1.png','3.png'})
            one=next(link for link in plan.links.values() if link['card']['number']==1)
            self.assertEqual([c['cardNumber'] for c in one['cardReferences']],[1,2])
            self.assertEqual(len(plan.tasks),2)

    def test_multiple_exports_of_one_reuse_source_require_later_review(self):
        ref=reference();ref['chapters'][0]['cards'][1]['sourceCardId']='opening-card1'
        ds=drawings();selected={ds[0].node.key,ds[-1].node.key}
        with TemporaryDirectory() as tmp:
            s=core.Settings();plan=sb.make_plan(ds,selected,tmp,s,ref)
            data=sb.inventory(plan,s,'art.psd',(24,16),[(d,p,(24,16)) for d,p in plan.tasks],[],False)
            self.assertEqual(len(plan.tasks),2)
            self.assertEqual(data['reuse']['multipleExportsForSource'],['opening-card1'])
            self.assertTrue(all(f['sourceCardId']=='opening-card1' for f in data['frames']))

    def test_actual_saved_paths_partial_failure_cancellation_and_no_overwrites(self):
        ds=drawings();selected={d.node.key for d in ds};settings=core.Settings(component_stack_order=True)
        with TemporaryDirectory() as tmp:
            plan=sb.make_plan(ds,selected,Path(tmp)/'original-export',settings,reference());records=[]
            # A file appears after the preview. The index must use the collision-resolved name.
            first=plan.tasks[0][1];first.parent.mkdir(parents=True);first.write_bytes(b'keep-existing')
            def render(project,d,clip,s):
                if d.node.name=='Object':raise RuntimeError('simulated rendering failure')
                return Image.new('RGBA',(9,7),'red')
            with patch.object(core,'render',render):
                made,failed,cancelled=core.export(None,False,plan.tasks,settings,on_saved=lambda d,p,size:records.append((d,p,size)))
            self.assertEqual(first.read_bytes(),b'keep-existing');self.assertEqual(len(records),3);self.assertEqual(len(failed),1)
            self.assertEqual(made[0].stem,first.stem+' - 2')
            data=sb.inventory(plan,settings,'source.psd',(20,20),records,failed,cancelled);self.assertFalse(data['complete'])
            listed=[plan.root/f['path'] for frame in data['frames'] for f in frame['files']]
            self.assertCountEqual(listed,made)
            p1=sb.write_index(plan.root,data);original=p1.read_bytes();p2=sb.write_index(plan.root,data)
            self.assertNotEqual(p1,p2);self.assertEqual(p1.read_bytes(),original)
            moved=Path(tmp)/'moved-project';shutil.move(plan.root,moved)
            self.assertTrue(all((moved/f['path']).is_file() for frame in data['frames'] for f in frame['files']))
            self.assertEqual(json.loads((moved/p2.name).read_text())['pathBase'],'index-directory')
            cancel=threading.Event();cancel.set()
            made,failed,cancelled=core.export(None,False,plan.tasks,settings,cancel=cancel)
            self.assertEqual(made,[]);self.assertTrue(cancelled)

    def test_real_psd_roundtrip_source_is_unchanged(self):
        from psd_tools import PSDImage
        from psd_tools.api.layers import Group,PixelLayer
        with TemporaryDirectory() as tmp:
            tmp=Path(tmp);source=tmp/'art.psd';psd=PSDImage.new('RGBA',(24,16))
            chapter=Group.new(psd,'Chapter 1');frame=Group.new(chapter,'Frame 1')
            bg=Group.new(frame,'Background');char=Group.new(frame,'Character')
            PixelLayer.frompil(Image.new('RGBA',(24,16),'blue'),bg,'Paint')
            PixelLayer.frompil(Image.new('RGBA',(6,6),'red'),char,'Paint',top=2,left=4)
            psd.save(source);before=hashlib.sha256(source.read_bytes()).hexdigest()
            doc=core.open_project(source);ds=core.discover(core.folder_tree(doc,False),rules=[core.ComponentRule('Background','BG'),core.ComponentRule('Character','Character')]);s=core.Settings(component_stack_order=True)
            plan=sb.make_plan(ds,{d.node.key for d in ds},tmp/'out',s,reference());records=[]
            made,failed,cancelled=core.export(doc,False,plan.tasks,s,on_saved=lambda d,p,size:records.append((d,p,size)))
            self.assertEqual(failed,[]);self.assertEqual(len(made),2)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
            data=sb.inventory(plan,s,source,(24,16),records,failed,cancelled);sb.write_index(plan.root,data)
            self.assertEqual([x['label'] for x in data['frames'][0]['files']],['BG','Character'])
            with Image.open(records[0][1]) as im:self.assertEqual(im.getpixel((5,3)),(255,0,0,255));self.assertEqual(im.getpixel((0,0))[3],0)

if __name__=='__main__':unittest.main(verbosity=2)
