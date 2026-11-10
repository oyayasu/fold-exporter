"""Local regression checks. No original user projects are ever read or modified."""
from __future__ import annotations
from tempfile import TemporaryDirectory
from pathlib import Path
from PIL import Image
import export_core as core

class FakeGroup(list):
    kind='group'
    visible=True
    def __init__(self,name,children=(),rgba=(0,0,0,0)):
        super().__init__(children)
        self.name=name
        self.rgba=rgba
        for child in self:child.parent=self
    def is_group(self):return True

class FakeProject(list):
    width=16
    height=12
    def __init__(self,children):
        super().__init__(children)
        for child in self:child.parent=self
    def composite(self,viewport=None,force=False,alpha=None,color=None,layer_filter=None):
        assert viewport==(0,0,16,12) and force and alpha==0.0
        output=Image.new('RGBA',(16,12),(0,0,0,0))
        def paint(node):
            if layer_filter(node):
                if node.rgba[3]:
                    overlay=Image.new('RGBA',(16,12),node.rgba)
                    output.alpha_composite(overlay)
                    overlay.close()
                for child in node:paint(child)
        for child in self:paint(child)
        return output

def names(tasks,dest):
    return [p.relative_to(dest).as_posix() for _,p in tasks]

def slot_settings(*slots, **kwargs):
    return core.Settings(slots=tuple(core.NameSlot(*slot) for slot in slots), **kwargs)


def run():
    first=FakeGroup('Image',rgba=(255,30,30,255))
    second=FakeGroup('Image',rgba=(0,255,40,130))
    third=FakeGroup('Image',rgba=(0,30,255,255))
    fourth=FakeGroup('Another',rgba=(70,80,90,255))
    project=FakeProject([
        FakeGroup('Chapter 12',[fourth,third]),
        FakeGroup('Chapter 3',[second,first]),
    ])
    tree=core.folder_tree(project,False)
    assert [node.name for node in tree]==['Chapter 3','Chapter 12']
    drawings=core.discover(tree,'CHAPTER')
    assert [d.chapter for d in drawings]==[
        ('Chapter 3',),('Chapter 3',),('Chapter 12',),('Chapter 12',)]
    selected={d.node.key for d in drawings}
    with TemporaryDirectory() as folder:
        dest=Path(folder)/'exports'
        default=core.Settings()
        assert (default.quality,default.scale,default.padding)==(100,100,3)
        assert names(core.plan(drawings,selected,dest,default),dest)==[
            'Chapter 3/001.png','Chapter 3/002.png',
            'Chapter 12/001.png','Chapter 12/002.png']
        reverse=core.Settings(reverse=True)
        assert names(core.plan(drawings,selected,dest,reverse),dest)==[
            'Chapter 3/002.png','Chapter 3/001.png',
            'Chapter 12/002.png','Chapter 12/001.png']
        global_reverse=core.Settings(reset=False,reverse=True,padding=1)
        assert names(core.plan(drawings,selected,dest,global_reverse),dest)==[
            'Chapter 3/4.png','Chapter 3/3.png','Chapter 12/2.png','Chapter 12/1.png']
        for width,expected in ((1,'1'),(2,'01'),(3,'001')):
            assert core.name_for(drawings[0],core.Settings(padding=width),1)==expected
        # No inserted separators. Four independent slots, and the original name
        # can be placed anywhere without needing a naming-mode switch.
        exact=slot_settings(('Folder name',),('Custom text','.'),('Index',),('None',),padding=2)
        assert core.name_for(drawings[0],exact,1)=='Image.01'
        exact=slot_settings(('Custom text','Animation'),('Index',),('Folder name',),('None',),
                            separators=('_','',''),padding=1)
        assert core.name_for(drawings[0],exact,1)=='Animation_1Image'
        exact=slot_settings(('Custom text','PRE_'),('Index',),('None',),('Custom text','_POST'))
        assert core.name_for(drawings[0],exact,1)=='PRE_001_POST'
        # Separate fields must contribute exactly the typed characters and no
        # implicit punctuation. Adjacent None/empty values suppress separators.
        separated=slot_settings(('Index',),('Component',),('None',),('None',),
                                separators=(' - ','.','_'))
        assert core.name_for(drawings[0],separated,1)=='001'
        # Empty runtime values differ from slots configured as None.  A
        # connector belongs to its right-hand slot and still applies when
        # that slot is nonempty, even if the previous component was absent.
        frame=core.Node((45,), 'Frame 2', None)
        with_component=core.Drawing(frame,(),frame=frame,label='BG',component_index=1)
        without_component=core.Drawing(frame,(),frame=frame)
        inline=slot_settings(('Index',),('Component',),('Folder name',),('None',),
                             separators=(' - ','_',''),padding=3)
        assert core.name_for(with_component,inline,1)=='001 - BG_Frame 2'
        assert core.name_for(without_component,inline,1)=='001_Frame 2'
        for empty in ('None','Component'):
            # Missing slot 2/3 use only the connector closest to the next
            # actual token, not every unused connector.
            sparse=slot_settings(('Index',),(empty,),('None',),('Folder name',),
                                 separators=(' - ','~','.'),padding=1)
            assert core.name_for(without_component,sparse,1)=='1.Frame 2'
        leading=slot_settings(('Component',),('None',),('Folder name',),('None',),
                              separators=(' - ','_',''))
        assert core.name_for(without_component,leading,1)=='Frame 2'

        try:
            slot_settings(('Index',),('Component',),('None',),('None',),
                          separators=('four','', '')).slots
            core.name_for(drawings[0],slot_settings(('Index',),('Component',),('None',),('None',),
                          separators=('four','', '')),1)
            assert False,'Long separator should have failed'
        except ValueError:pass
        start=slot_settings(('Index',),('None',),('None',),('None',),start=5)
        assert names(core.plan(drawings,selected,dest,start),dest)==[
            'Chapter 3/005.png','Chapter 3/006.png',
            'Chapter 12/005.png','Chapter 12/006.png']
        source=Path(folder)/'source.psd'
        source.write_bytes(b'ORIGINAL MUST NEVER CHANGE')
        tasks=core.plan(drawings,selected,dest,default)
        images,failed,cancelled=core.export(project,False,tasks,default)
        assert not failed and not cancelled and len(images)==4
        assert source.read_bytes()==b'ORIGINAL MUST NEVER CHANGE'
        with Image.open(dest/'Chapter 3'/'001.png') as image:
            assert image.getpixel((1,1))==(255,30,30,255)
        with Image.open(dest/'Chapter 3'/'002.png') as image:
            assert image.getpixel((1,1))==(0,255,40,130)
        new_tasks=core.plan(drawings,selected,dest,default)
        assert new_tasks[0][1].name=='001 - 2.png'
        mat=core.render(project,drawings[1],False,core.Settings(white=True))
        try:assert mat.getpixel((1,1))[3]==255
        finally:mat.close()
        for kind in ('PNG','WEBP','TIFF','JPEG'):
            out=core.render(project,drawings[0],False,core.Settings(format=kind))
            try:assert out.mode==('RGB' if kind=='JPEG' else 'RGBA')
            finally:out.close()
    print('Core checks PASS: read-only PSD, four formats, four slots, exact punctuation,')
    print('three index widths, reverse numbering, chapter resets and no overwrites.')


def test_component_rules():
    N=core.Node
    tree=[N((0,), 'Chapter 1',None,True,[
        N((0,0),'1',None,True,[
            N((0,0,0),'Background',None,False,[
                N((0,0,0,0),'Color',None),
                N((0,0,0,1),'Part - Trees',None)]),
            N((0,0,1),'Sketch',None),
            N((0,0,2),'Character',None),
        ]),
        N((0,1),'2',None,False,[N((0,1,0),'Shadow',None)]),
        N((0,2),'work #3',None,True,[N((0,2,0),'Foreground',None)]),
    ])]
    rules=[core.ComponentRule('Background','BG'),
           core.ComponentRule('Part - *','P - {match}'),
           core.ComponentRule('Foreground','F')]
    drawings=core.discover(tree,'chapter',True,rules)
    assert [d.node.name for d in drawings]==['Background','Part - Trees','2','Foreground']
    assert [d.frame.name for d in drawings]==['1','1','2','work #3']
    assert drawings[0].excluded==((0,0,0,1),)
    assert drawings[1].label=='P - Trees'
    assert core.match_rule('Part - 🌳',rules[1])=='🌳'
    assert core.match_rule('Character',rules[0]) is None
    with TemporaryDirectory() as tmp:
        dest=Path(tmp)
        settings=core.Settings()
        chosen={d.node.key for d in drawings}
        expected=['Chapter 1/001BG.png','Chapter 1/001P - Trees.png',
                  'Chapter 1/002.png','Chapter 1/003F.png']
        assert names(core.plan(drawings,chosen,dest,settings),dest)==expected
        settings.reverse=True
        assert names(core.plan(drawings,chosen,dest,settings),dest)==[
            'Chapter 1/003BG.png','Chapter 1/003P - Trees.png',
            'Chapter 1/002.png','Chapter 1/001F.png']
        # If the user wants plain concatenation, it must not add punctuation.
        simple=slot_settings(('Index',),('Component',),('None',),('None',))
        assert core.name_for(drawings[0],simple,1)=='001BG'
        # Names inside the PSD are free-form and component suffixes can use
        # {match}. Normal loose layers and unmatched component names are ignored.
        root=[N((4,), 'work #1',None,True,[N((4,0),'Background',None)]),
              N((5,), 'work #2',None)]
        flat=core.discover(root,'chapter',True,rules)
        assert [d.node.name for d in flat]==['Background','work #2']
        assert all(d.chapter==() for d in flat)
        assert names(core.plan(flat,{d.node.key for d in flat},dest,core.Settings()),dest)==[
            '001BG.png','002.png']
        assert len(core.discover(root,'chapter',True,[core.ComponentRule('Absent','ZZ')]))==2
        assert core.discover(root,'',True,[])[0].node.name=='work #1'
    # Three modes: separate only, separate and combined, combined only.
    both=core.discover(tree,'chapter',True,rules,'Separate + whole frame')
    assert [d.node.name for d in both]==['1','Background','Part - Trees','2','work #3','Foreground']
    assert [d.label for d in both]==['','BG','P - Trees','','','F']
    complete=core.discover(tree,'chapter',True,rules,'Whole frame only')
    assert [d.node.name for d in complete]==['1','2','work #3']
    with TemporaryDirectory() as td:
        paths=core.plan(both,{d.node.key for d in both},Path(td),core.Settings())
        assert names(paths,Path(td))==[
            'Chapter 1/001.png','Chapter 1/001BG.png',
            'Chapter 1/001P - Trees.png','Chapter 1/002.png',
            'Chapter 1/003.png','Chapter 1/003F.png']
    print('Component checks PASS: nested patterns, labels, optional chapters,')
    print('unmatched folders ignored, shared indices, combined + separate modes.')


class CompositingLayer(list):
    """API-level PSD compositor stand-in for visibility/filter regression."""
    def __init__(self,name,rgba=(0,0,0,0),visible=True,clipping=False,children=()):
        super().__init__(children)
        self.name=name
        self.rgba=rgba
        self.visible=visible
        self.clipping=clipping
        self.parent=None
        for child in self:child.parent=self
    def is_group(self):return True
    @property
    def clip_layers(self):
        if self.parent is None:return []
        i=self.parent.index(self)
        output=[]
        for other in self.parent[i+1:]:
            if other.clipping:output.append(other)
            else:break
        return output

class CompositingPSD(CompositingLayer):
    width=16
    height=12
    def composite(self,viewport=None,force=False,alpha=None,color=None,layer_filter=None):
        assert force and viewport==(0,0,16,12) and callable(layer_filter)
        output=Image.new('RGBA',(16,12),(0,0,0,0))
        def visit(layer):
            if layer_filter(layer):
                # Synthetic paint through the filter; not a real PSD blender.
                if layer.rgba[3]:output.alpha_composite(Image.new('RGBA',(16,12),layer.rgba))
                for ch in layer:visit(ch)
        for child in self:visit(child)
        return output


def test_visibility_clipping():
    """Hidden parents + selected hidden folder must render; loose sketch excluded."""
    base=CompositingLayer('Background',(10,80,240,255),visible=False)
    clipped=CompositingLayer('Overlay',(255,0,0,50),clipping=True)
    sketch=CompositingLayer('Sketch',(0,255,0,255),visible=True)
    parent=CompositingLayer('Frame 2',children=[base,clipped,sketch],visible=False)
    chapter=CompositingLayer('Chapter 1',children=[parent],visible=False)
    psd=CompositingPSD('PSD',children=[chapter])
    chapter.parent=psd
    drawing=core.Drawing(core.Node((0,0,0),'Background',base,False),('Chapter 1',),
                         frame=core.Node((0,0),'Frame 2',parent,False),label='BG')
    out=core.render(psd,drawing,False,core.Settings())
    try:
        red,green,blue,al=out.getpixel((0,0))
        assert al==255 and red>10 and green<100 and blue>100, (red,green,blue,al)
        assert green!=255, 'Loose unclipped sketch mistakenly rendered'
    finally:out.close()
    # Deliberately hidden descendant still remains hidden.
    hidden=CompositingLayer('Hidden child',(0,250,0,255),visible=False)
    hidden.parent=base
    base.append(hidden)
    out=core.render(psd,drawing,False,core.Settings())
    try:assert out.getpixel((0,0))[1]<100
    finally:out.close()
    # A named nested component is an independent export and is subtracted
    # from its parent component's export, including clips attached to it.
    trees=CompositingLayer('P - Trees',(0,255,0,255))
    trees_overlay=CompositingLayer('Effect',(255,255,0,50),clipping=True)
    bg=CompositingLayer('Background',(20,20,255,255),children=[trees,trees_overlay])
    frame=CompositingLayer('Frame',children=[bg])
    psd2=CompositingPSD('PSD',children=[frame]);frame.parent=psd2
    background=core.Drawing(core.Node((0,0),'Background',bg),(),
                            frame=core.Node((0,),'Frame',frame),excluded=((0,0,0),))
    parent=core.render(psd2,background,False,core.Settings())
    try:assert parent.getpixel((0,0))==(20,20,255,255)
    finally:parent.close()
    standalone=core.Drawing(core.Node((0,0,0),'P - Trees',trees),(),
                            frame=core.Node((0,),'Frame',frame))
    child_image=core.render(psd2,standalone,False,core.Settings())
    try:assert child_image.getpixel((0,0))[1]>100
    finally:child_image.close()
    print('Hidden PSD ancestors, selected hidden component, clipped sibling,')
    print('unclipped loose layer exclusion and hidden internal layers: PASS')


def test_new_naming_and_cropping():
    N=core.Node
    tree=[N((0,), 'Chapter 4',None,True,[
        N((0,0),'Frame 1',None,True,[
            N((0,0,0),'Part A',None),
            N((0,0,1),'Part B',None),
            N((0,0,2),'Part C',None),
        ]),
        N((0,1),'Frame 2',None,True,[N((0,1,0),'Part X',None)])
    ])]
    rules=[core.ComponentRule('Part *','P-{match}',True)]
    drawings=core.discover(tree,'chapter',True,rules)
    assert [d.component_index for d in drawings]==[0,0,0,0], 'Unique export labels must have NO index'
    assert [d.component_crop for d in drawings]==[True,True,True,True]
    settings=slot_settings(('Chapter',),('Index',),('Component',),('Component index',),
                           separators=('_','_','.'),padding=2)
    with TemporaryDirectory() as temp:
        names_found=names(core.plan(drawings,{d.node.key for d in drawings},Path(temp),settings),Path(temp))
        assert names_found==[
            'Chapter 4/Chapter 4_01_P-A.png',
            'Chapter 4/Chapter 4_01_P-B.png',
            'Chapter 4/Chapter 4_01_P-C.png',
            'Chapter 4/Chapter 4_02_P-X.png',
        ], names_found
    no_chapter=core.Drawing(N((3,),'Frame 1',None),(),component_index=0)
    assert core.name_for(no_chapter,settings,1)=='01'

    class PartialPSD(CompositingPSD):
        def composite(self,**kwargs):
            assert callable(kwargs.get('layer_filter'))
            image=Image.new('RGBA',(16,12))
            image.paste((160,30,80,255),(3,2,10,8))
            return image
    frame=CompositingLayer('Frame')
    item=CompositingLayer('Part A')
    frame.append(item);item.parent=frame
    psd=PartialPSD('PSD',children=[frame])
    whole=core.Drawing(N((0,), 'Frame',frame),())
    component=core.Drawing(N((0,0,), 'Part A',item),(),frame=N((0,), 'Frame',frame),
                           component_index=1,component_crop=True)
    no_crop=core.Drawing(N((0,0,), 'Part A',item),(),frame=N((0,), 'Frame',frame),
                         component_index=1,component_crop=False)
    cases=[
        (whole,False,'All',(16,12)),
        (whole,True,'All',(7,6)),
        (component,True,'Components only',(7,6)),
        (whole,True,'Components only',(16,12)),
        (component,True,'Some components',(7,6)),
        (no_crop,True,'Some components',(16,12)),
        (whole,True,'Some components',(16,12)),
    ]
    for drawing,crop,scope,size in cases:
        im=core.render(psd,drawing,False,core.Settings(crop=crop,crop_scope=scope))
        try:assert im.size==size,(scope,drawing.component_index,crop,im.size,size)
        finally:im.close()
    print('Chapter slot, unique labels without indices, and selective crop PASS')




def test_repeated_export_labels_and_clipped_rows():
    """A component index distinguishes identical labels only, within each frame."""
    N=core.Node
    frame=N((0,), 'Frame 1', None, True, [
        N((0,0),'Food - Apples',None),
        N((0,1),'Food - Bananas',None),
        N((0,2),'Dog',None),
        N((0,3),'Food - Carrots',None),
    ])
    next_frame=N((1,), 'Frame 2', None, True, [
        N((1,0),'Food - Dinner',None),
        N((1,1),'Food - Lunch',None),
        N((1,2),'Dog',None),
    ])
    rules=[core.ComponentRule('Food - *','Food'),core.ComponentRule('Dog','Dog')]
    drawings=core.discover([frame,next_frame],'',True,rules)
    assert [d.label for d in drawings]==['Food','Food','Dog','Food','Food','Food','Dog']
    assert [d.component_index for d in drawings]==[1,2,0,3,1,2,0]
    # The positions of slots and connectors stay fully user configurable.
    settings=slot_settings(('Component',),('Component index',),('None',),('None',),
                           separators=('.', '', ''),padding=1)
    with TemporaryDirectory() as td:
        dest=Path(td)
        assert names(core.plan(drawings,{d.node.key for d in drawings},dest,settings),dest)==[
            'Food.1.png','Food.2.png','Dog.png','Food.3.png',
            'Food.1 - 2.png','Food.2 - 2.png','Dog - 2.png'
        ], 'Filename collisions across frames should be protected, not overwrite.'
    custom=slot_settings(('Index',),('Component',),('Component index',),('Folder name',),
                         separators=('_', '.', ' - '),padding=1)
    assert [core.name_for(d,custom,1) for d in drawings[:4]]==[
        '1_Food.1 - Frame 1','1_Food.2 - Frame 1',
        '1_Dog - Frame 1','1_Food.3 - Frame 1'
    ]
    # A single selected Food needs no component index.
    with TemporaryDirectory() as td:
        selected={drawings[3].node.key,drawings[2].node.key}
        assert names(core.plan(drawings,selected,Path(td),settings),Path(td))==[
            'Dog.png','Food.png']
    # A non-group clipped PSD layer attaches to the next folder below it.
    class RasterLayer:
        def __init__(self,name,clipping=False,visible=True):
            self.name=name
            self.clipping=clipping
            self.visible=visible
            self.parent=None
        def is_group(self):return False
    class Folder(list):
        def __init__(self,name,children=()):
            super().__init__(children)
            self.name=name;self.visible=True;self.parent=None
            for c in self:c.parent=self
        def is_group(self):return True
        @property
        def clip_layers(self):
            if self.parent is None:return []
            i=next(i for i,x in enumerate(self.parent) if x is self)
            output=[]
            for sibling in self.parent[i+1:]:
                if getattr(sibling,'clipping',False):output.append(sibling)
                else:break
            return output
    bg=Folder('Background')
    overlay=RasterLayer('Overlay',True)
    glow=RasterLayer('Glow',True,False)
    loose=RasterLayer('Unclipped Sketch')
    top=Folder('Frame 1',[bg,overlay,glow,loose])
    project=Folder('PSD',[top]);top.parent=project
    tree=core.folder_tree(project,False)
    attached=tree[0].children[0].clipped_layers
    assert [(c.name,c.visible) for c in attached]==[('Overlay',True),('Glow',False)]
    assert [x.name for x in tree[0].children]==['Background']
    assert core.discover(tree,'',True,[core.ComponentRule('Background','BG')])[0].label=='BG'
    print('Label-specific component indices; unique labels omitted; PSD clips discovered: PASS')


if __name__=='__main__':
    test_repeated_export_labels_and_clipped_rows()
    run()
    test_component_rules()
    test_visibility_clipping()
    test_new_naming_and_cropping()
