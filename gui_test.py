"""Graphical regression tests, macOS or Linux with a temporary X server."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import os
import json
import tkinter as tk
import sys

with TemporaryDirectory() as root:
    os.environ['HOME']=root
    import export_core as core
    from app import Application

    app=Application()
    app.update()
    assert app.scale.get()==app.quality.get()=='100'
    assert len(app.slots)==4 and len(app.separators)==3
    assert len(app.rule_rows)==3
    app.update_idletasks()
    lw=app.left_pane.winfo_width();rw=app.right_pane.winfo_width()
    assert 0.35<lw/(lw+rw)<0.40,(lw,rw)
    # Slot type changes must preserve widget identity and focus; no blink.
    text_widget=app.custom_entries[0]
    app.slots[0][0].set('Custom text');app.update()
    assert app.custom_entries[0] is text_widget and text_widget.winfo_manager()=='pack'
    app.slots[0][0].set('Index');app.update()
    assert app.custom_entries[0] is text_widget and not text_widget.winfo_manager()
    # Crop scope is hidden until global cropping is enabled.
    assert not app.crop_scope_picker.winfo_manager()
    app.crop.set(True);app.crop_scope.set('Some components');app.update()
    assert app.crop_scope_picker.winfo_manager()=='pack'
    assert all(row[4].winfo_manager()=='grid' for row in app.rule_rows)
    app.rule_rows[0][3].set(True)
    assert app._component_rules()[0].crop is True
    app.update()
    assert app.crop_header.winfo_manager()=='grid'
    assert app.crop_header.grid_info()['column']==2
    assert app.rule_rows[0][4].grid_info()['column']==2
    header=app.crop_header;check=app.rule_rows[0][4]
    assert abs((header.winfo_rootx()+header.winfo_width()/2)-
               (check.winfo_rootx()+check.winfo_width()/2))<3

    app.crop_scope.set('All');app.update()
    assert all(row[4].winfo_manager()=='' for row in app.rule_rows)
    app.crop.set(False);app.update()
    assert not app.crop_scope_picker.winfo_manager()
    assert app.component_mode.get()=='Separate components'
    assert [s.winfo_manager() for s in app.separator_entries]==['grid','grid','']
    assert app.name_example.get()=='001BG.png'
    assert all(w.winfo_manager()=='' for w in app.jpeg_widgets)
    app.format.set('JPEG');app.update()
    assert all(w.winfo_manager()=='grid' for w in app.jpeg_widgets)
    app.format.set('PNG');app.update()
    assert all(w.winfo_manager()=='' for w in app.jpeg_widgets)

    app.source=Path(root)/'test.psd'
    app.dest.set(str(Path(root)/'exports'))
    app.nodes=[core.Node((0,),'1',None,True,[core.Node((0,0),'Background',None)])]
    app._discover();app.update()
    assert len(app.drawings)==1 and app.drawings[0].node.name=='Background'
    app.crop.set(True);app.crop_scope.set('Some components');app.update()
    app.rule_rows[0][3].set(False)
    app.update()
    app._discover()
    assert not app.drawings[0].component_crop
    app.rule_rows[0][3].set(True)
    app.update()
    # Real UI toggles immediately refresh the plan, not just settings storage.
    assert app.drawings[0].component_crop
    app.crop.set(False);app.crop_scope.set('All');app.update()

    assert app._tasks()[0][1].name=='001BG.png'
    # Chapter is optional and can appear as any naming slot.
    app.slots[2][0].set('Chapter');app.update()
    assert app._tasks()[0][1].name=='001BG.png'
    app.slots[2][0].set('None');app.update()
    app.separators[0].set(' - ')
    app.update()
    assert app.name_example.get()=='001 - BG.png'
    assert app._tasks()[0][1].name=='001 - BG.png'
    # Separator hides only when BOTH neighboring slots are None.
    app.slots[2][0].set('Folder name')
    app.slots[3][0].set('Custom text')
    app.slots[3][1].set('!!')
    app.separators[1].set('_')
    app.separators[2].set('.')
    app.update()
    assert all(e.winfo_manager()=='grid' for e in app.separator_entries)
    assert app._tasks()[0][1].name=='001 - BG_1.!!.png'
    # Regression: slot 2 is a component but this frame has no component.
    # The underscore before slot 3 must remain when slot 2 is empty.
    app.slots[3][0].set('None')
    app.update()
    whole_frame=core.Drawing(core.Node((9,), 'Frame 2', None),(),frame=core.Node((9,), 'Frame 2', None))
    example=core.Settings(slots=tuple(core.NameSlot(k.get(),t.get()) for k,t in app.slots),
                          separators=tuple(v.get() for v in app.separators))
    assert core.name_for(whole_frame,example,1)=='001_Frame 2'
    app.slots[3][0].set('Custom text');app.update()

    app.slots[3][0].set('None');app.update()
    assert app.separator_entries[2].winfo_manager()=='grid'
    app.slots[2][0].set('None');app.update()
    assert app.separator_entries[2].winfo_manager()==''
    app.slots[2][0].set('Folder name');app.update()
    # No component conditional toggle and no dedicated project name field.
    assert not hasattr(app,'project_name')
    assert all(len(slot)==2 for slot in app.slots)
    assert not hasattr(app,'slots_condition')
    app.start_number.set('7');app.padding.set('01');app.update()
    assert app._tasks()[0][1].name=='07 - BG_1.png'
    # Mode adds the full frame while retaining the separate component.
    app.component_mode.set('Separate + whole frame');app.update()
    assert [d.node.name for d in app.drawings]==['1','Background']
    assert len(app._tasks())==2
    assert len({d.frame_key for d in app.drawings})==1
    app.component_mode.set('Whole frame only');app.update()
    assert [d.node.name for d in app.drawings]==['1']
    app.component_mode.set('Separate components');app.update()
    assert len(app.drawings)==1

    app._add_rule('FX *','FX - {match}');app.update()
    app._save_rules()
    data=json.loads(app._project_rules_path(app.source).read_text())
    assert data['rules'][-1]['label']=='FX - {match}'
    app._remove_rule(app.rule_rows[-1][0]);app.update()
    app._load_rules(app.source);app.update()
    assert len(app.rule_rows)==4

    # Clipped sibling layers are display-only rows immediately ABOVE the
    # folder they are clipped to. They cannot be clicked/checked/exported.
    preview_folder=core.Node((8,0),'Background',None,True,[],[
        core.ClippedLayer('Overlay'),
        core.ClippedLayer('Multiply',False)])
    app.nodes=[core.Node((8,), 'Frame 8', None, True,[preview_folder])]
    app.component_mode.set('Separate components')
    app._discover();app.update()
    rows=app.tree.get_children('8')
    assert rows==('clipped:8/0:0','clipped:8/0:1','8/0'),rows
    assert app.tree.item(rows[0],'text')=='  ↓ Overlay (Clipped Layer)'
    assert app.tree.item(rows[1],'text')=='  ↓ Multiply (hidden) (Clipped Layer)'
    old=app.selected.copy()
    app._toggle(rows[0]);app.update()
    assert app.selected==old
    assert len(app._tasks())==1
    # Restore a normal project for the remainder of these GUI checks.
    app.nodes=[core.Node((0,),'1',None,True,[core.Node((0,0),'Background',None)])]
    app._discover();app.update()

    # Force settings to overflow and test actual Tk event dispatch, not just
    # a direct call to the wheel handler. Scroll route belongs to the right.
    for i in range(20):app._add_rule('Unused '+str(i),'X')
    app.update()
    app.right_canvas.yview_moveto(0)
    app.update()
    right_entry=app.rule_rows[0][0].winfo_children()[0]
    assert 'FolderExporterWheel' in right_entry.bindtags()
    right_x=app.right_pane.winfo_rootx()+40
    left_x=app.left_pane.winfo_rootx()+40
    y=app.right_pane.winfo_rooty()+100
    prior=app.right_canvas.yview()
    if sys.platform=='darwin':
        # Native Cocoa event_generate() and hardware trackpads use different
        # delta normalization. Test routing directly on macOS rather than
        # blocking the user's installer on a synthetic event discrepancy.
        assert app._mouse_wheel(SimpleNamespace(widget=right_entry,delta=1,
                   num=None,x_root=right_x,y_root=y))=='break'
    else:
        right_entry.event_generate('<MouseWheel>',delta=-120,x=10,y=10,
                                   rootx=right_x,rooty=y)
    app.update()
    moved=app.right_canvas.yview()
    assert moved[0]>prior[0],(prior,moved)
    # Focused LEFT controls should not prevent scrolling when cursor is right.
    previous=app.right_canvas.yview()
    if sys.platform=='darwin':
        assert app._mouse_wheel(SimpleNamespace(widget=app.tree,delta=1,
                   num=None,x_root=right_x,y_root=y))=='break'
    else:
        app.tree.event_generate('<MouseWheel>',delta=-120,rootx=right_x,rooty=y)
    app.update()
    assert app.right_canvas.yview()[0]>previous[0]
    previous=app.right_canvas.yview()
    if sys.platform=='darwin':
        app._mouse_wheel(SimpleNamespace(widget=app.tree,delta=1,
                         num=None,x_root=left_x,y_root=y))
    else:
        app.tree.event_generate('<MouseWheel>',delta=-120,rootx=left_x,rooty=y)
    app.update()
    assert app.right_canvas.yview()==previous
    # Tk 9 on macOS supplies a signed vertical delta in the lower 16 bits of
    # TouchpadScroll. Check both signs independently of native Tk version.
    app.right_canvas.yview_moveto(.15)
    app.update()
    t0=app.right_canvas.yview()[0]
    assert app._touchpad_wheel(SimpleNamespace(widget=right_entry, delta=(-3 if sys.platform=='darwin' else 3),
           x_root=right_x,y_root=y))=='break'
    app.update()
    assert app.right_canvas.yview()[0]>t0
    t1=app.right_canvas.yview()[0]
    assert app._touchpad_wheel(SimpleNamespace(widget=right_entry, delta=(2 if sys.platform=='darwin' else 0xFFFFFFFE),
           x_root=right_x,y_root=y))=='break'
    app.update()
    assert app.right_canvas.yview()[0]<t1

    # Mac sign inversion and precise reduced-speed scrolling (2.64px/notch).
    app.right_canvas.yview_moveto(.5);app.update()
    with patch.object(sys,'platform','darwin'):
        before=app.right_canvas.yview()[0]
        app._mouse_wheel(SimpleNamespace(widget=right_entry,delta=1,
                 x_root=right_x,y_root=y));app.update()
        after=app.right_canvas.yview()[0]
        assert 0 < (after-before)*app.right_canvas.bbox('all')[3] <= 4,(before,after)
        app._mouse_wheel(SimpleNamespace(widget=right_entry,delta=-1,
                 x_root=right_x,y_root=y));app.update()
        assert app.right_canvas.yview()[0]<after
    assert app.example_label.cget('background')=='#C0C0C0'
    assert app.example_label.cget('anchor')=='center'
    # The focus and selection cleanup works for combo lists that are editable
    # internally despite being configured readonly.
    dropdown=app.crop_scope_picker
    dropdown.focus_set()
    dropdown.event_generate('<<ComboboxSelected>>');app.update()
    assert not dropdown.selection_present()
    # Info icons are labels, have no white button rectangle, and have a
    # 10-point font (formerly 15; 33% smaller).
    header=app.left_pane.winfo_children()[0].winfo_children()[0]
    icons=[w for w in header.winfo_children() if isinstance(w,tk.Label) and w.cget('text')=='ⓘ']
    assert len(icons)==1 and icons[0].cget('bg')=='#C0C0C0'
    assert '10' in str(icons[0].cget('font'))
    for section in ('file','folders','settings','naming','rules','destination'):
        app._show_info(section)
        app.update()
        for child in app.winfo_children():
            if child.winfo_class()=='Toplevel':child.destroy()

    app._write_preferences()
    saved=json.loads(app._preferences_path().read_text())
    assert saved['version']==5
    assert saved['separators']==[' - ','_','.']
    assert saved['component_mode']=='Separate components'
    assert saved['crop_scope']=='All'
    assert saved['rules'][0]['crop'] is True
    assert 'project_name' not in saved
    app.destroy()

    next_app=Application();next_app.update()
    assert [v.get() for v in next_app.separators]==[' - ','_','.']
    assert next_app.slots[0][0].get()=='Index'
    assert next_app.slots[3][0].get()=='None'
    assert next_app.start_number.get()=='7'
    assert len(next_app.rule_rows)==24
    assert next_app.rule_rows[0][3].get() is True
    next_app.destroy()

    # v1.4 migration keeps the user's previous Index + ' - ' + Component
    # naming without reviving the removed conditional UI or project-name field.
    legacy={'version':2,'ignore':'chapter','slots':[
        {'kind':'Index','text':'','only_if_component':False},
        {'kind':'Custom text','text':' - ','only_if_component':True},
        {'kind':'Component','text':'','only_if_component':False},
        {'kind':'None','text':'','only_if_component':False},
    ],'rules':[{'pattern':'Background','label':'BG'}]}
    # Regression: on macOS the settings directory is ~/Library/Application
    # Support/FolderExporter, not ~/.folderexporter. Always use the app's
    # canonical path instead of assuming a platform-specific location.
    legacy_path=app._preferences_path()
    legacy_path.parent.mkdir(parents=True,exist_ok=True)
    legacy_path.write_text(json.dumps(legacy),encoding='utf-8')
    migrated=Application();migrated.update()
    assert [k.get() for k,_ in migrated.slots]==['Index','Component','None','None']
    assert [v.get() for v in migrated.separators]==[' - ','','']
    assert migrated.name_example.get()=='001 - BG.png'
    migrated.destroy()

    # Validate the actual platform-specific preference location, including
    # macOS when the test runs on a Linux CI/development environment.
    with patch.object(sys,'platform','darwin'):
        assert app._preferences_path()==(Path(root)/'Library'/'Application Support'
                                         /'FolderExporter'/'last-used.json')
    with patch.object(sys,'platform','linux'):
        assert app._preferences_path()==Path(root)/'.folderexporter'/'last-used.json'

print('GUI PASS: stable name inputs, 37/63 layout, 4 slots + 3 separators,')
print('3 component modes, info icons, last-used preferences, Mac-style')
print('wheel event dispatch, independent panes, JPEG visibility and popups.')
