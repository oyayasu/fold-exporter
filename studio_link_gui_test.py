"""Real Tk/PSD workflow; no user artwork or settings are read."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib,json,os,shutil
from PIL import Image,ImageGrab
from app import Application
import export_core as core
import storyboard as sb
import studio_link as studio
from studio_link_test import shared
from integration_test import hidden_psd
# Helpers deliberately have no import-time GUI side effects.
import time,tkinter as tk

def wait(app,predicate):
    end=time.monotonic()+12
    while not predicate():
        if time.monotonic()>end:raise AssertionError('UI operation timed out')
        app.update();time.sleep(.015)
    app.update()

with TemporaryDirectory() as tmp,patch.object(Path,'home',return_value=Path(tmp)):
    home=Path(tmp).resolve();root=home/'Main project';root.mkdir();project=shared(root)
    source=home/'clean.psd';hidden_psd(source);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    results=[];warnings=[];errors=[]
    with patch('app.messagebox.showinfo',side_effect=lambda *a:results.append(a)),patch('app.messagebox.showwarning',side_effect=lambda *a:warnings.append(a)),patch('app.messagebox.showerror',side_effect=lambda *a:errors.append(a)),patch('storyboard_ui.messagebox.showerror',side_effect=lambda *a:errors.append(a)):
        app=Application();app.report_callback_exception=lambda *a:errors.append(a);app.update()
        assert not app.storyboards.enabled.get();assert not app.storyboards.box.winfo_manager();assert app.storyboards.holder.winfo_manager();assert app.storyboards.enable_check.cget('text')=='STORYBOARD STUDIO EXPORT';assert not hasattr(app.storyboards,'review_button')
        assert app.index_check.master is app.storyboards.box
        assert not hasattr(app,'use_project_folder') and not hasattr(app,'project_folder_name')
        app._open(source);wait(app,lambda:app.source==source and not app.busy)
        app._add_rule('Character','Character');app._discover();app.update()
        ordinary=home/'ordinary';app.dest.set(str(ordinary));app.frame_folders.set(True);app.update()
        assert app._settings().frame_folders is False
        app._export();wait(app,lambda:not app.busy and results)
        assert not list(ordinary.rglob('*.json'));assert list(ordinary.rglob('*.png'))
        assert app.storyboards.connect_path(root/'Studio Link');app.update()
        assert app.storyboards.enabled.get() and app.storyboards.box.winfo_manager()=='pack'
        assert app.dest.get()==str(root.resolve())
        assert str(app.dest_entry.cget('state'))=='disabled' and str(app.dest_button.cget('state'))=='disabled'
        assert app.storyboards.chapter_style.get()==studio.PROJECT_FOLDERS
        assert app.storyboards.naming_mode.get()==studio.PROJECT_NAMES
        app.frame_folders.set(False);app.component_stack_order.set(True);app.component_mode.set('Separate + whole frame');app.update()
        tasks=app._tasks();assert len(tasks)==4
        assert all(path.parent==root/'1 - Opening' for d,path in tasks)
        assert {'Drawing_001_BG_001.png','Drawing_001_Character_002.png','Drawing_001_Clean.png','Drawing_002_Clean.png'}=={path.name for d,path in tasks}
        before_results=len(results);app._export();wait(app,lambda:not app.busy and len(results)>before_results)
        indexes=list((root/'Studio Link').glob('folderexporter-index*.json'));assert len(indexes)==1
        data=json.loads(indexes[0].read_text());assert data['pathBase']=='media-root' and data['mediaRoot']=='.'
        assert data['complete'] and len(data['frames'])==2
        assert all((root/f['path']).is_file() for frame in data['frames'] for f in frame['files'])
        assert data['storyboardReference']['chapters'][0]['cards'][0]['variantAssetId']=='art-opening-card1'
        assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
        # A custom slot edit switches modes instead of appearing to do nothing.
        app.slots[0][0].set('Custom text');app.slots[0][1].set('Mine');app.update()
        assert app.storyboards.naming_mode.get()==studio.CUSTOM_NAMES
        assert any('Mine' in path.name for d,path in app._tasks())
        app.storyboards.naming_mode.set(studio.PROJECT_NAMES)
        # Refresh reads names anew; folder paths stay the ones SS recorded.
        ref=project.reference;ref['naming']['card']='New_{card_number}';ref['chapters'][0]['title']='Renamed opening'
        # Insert a chapter before the existing one: remembered source/card IDs win over old CSP numbers.
        ref['chapters'][0]['number']='2';ref['chapters'][1]['number']='2.1';ref['chapters'][2]['number']='3'
        ref['chapters'].insert(0,{'id':'new','number':'1','title':'Inserted','parentId':None,'cards':[]})
        ref['chapterDirectories'].append({'chapterId':'new','path':'1 - Inserted'})
        ref['structuralSignature']='new-order';manifest=project.manifest;manifest['naming']=ref['naming'];manifest['chapterDirectories']=ref['chapterDirectories']
        (root/'Studio Link/project.json').write_text(json.dumps(manifest));(root/'Studio Link/storyboard.ssreference.json').write_text(json.dumps(ref))
        app.event_generate('<FocusIn>');wait(app,lambda:app.storyboards.reference.get('structuralSignature')=='new-order');plan=app._export_plan()
        assert all(link['chapter']['id']=='opening' for link in plan.links.values())
        assert all(path.parent==root/'1 - Opening' and path.name.startswith('New_') for d,path in plan.tasks)
        # Switching off hides the panel and integration-only output behavior.
        app.storyboards.enabled.set(False);app.update();assert not app.storyboards.box.winfo_manager()
        assert str(app.dest_entry.cget('state'))=='normal';app.frame_folders.set(True);assert not app._settings().frame_folders
        app.storyboards.enabled.set(True);app.frame_folders.set(False);app.update()
        moved=home/'Moved project';shutil.move(root,moved)
        app.event_generate('<FocusIn>');wait(app,lambda:app.storyboards.workspace is None)
        assert 'Relink' in app.storyboards.label.get();before_results=len(results)
        app._export();app.update();assert not app.busy and len(results)==before_results and warnings
        warnings.clear();assert not root.exists(),'the old moved folder must not be recreated'
        assert app.storyboards.connect_path(moved);assert app.dest.get()==str(moved.resolve())
        before_results=len(results);app._export();wait(app,lambda:not app.busy and len(results)>before_results)
        assert len(list((moved/'Studio Link').glob('folderexporter-index*.json')))==1
        app._write_preferences();binding=app.storyboards.binding_path();prefs=json.loads(app._preferences_path().read_text())
        assert 'use_project_folder' not in prefs and 'project_folder_name' not in prefs
        assert json.loads(binding.read_text())['studioDirectory']==str(moved.resolve())
        output=os.getenv('FE_TEST_OUTPUT')
        if output:
            app.right_canvas.yview_moveto(.68);app.update();ImageGrab.grab(xdisplay=os.environ.get('DISPLAY')).save(Path(output)/'studio-link-main.png')
            app.storyboards.enabled.set(False);app.right_canvas.yview_moveto(.7);app.update();ImageGrab.grab(xdisplay=os.environ.get('DISPLAY')).save(Path(output)/'standalone-main.png');app.storyboards.enabled.set(True)
        app.destroy()
        reopened=Application();reopened.report_callback_exception=lambda *a:errors.append(a);reopened.update();reopened._open(source);wait(reopened,lambda:not reopened.busy and reopened.source==source)
        assert reopened.storyboards.workspace and reopened.storyboards.directory==str(moved.resolve())
        assert reopened.storyboards.naming_mode.get()==studio.PROJECT_NAMES
        assert 'New_' in reopened.preview_text.get()
        reopened.destroy()
        # Removed project nesting is migrated once into the direct destination.
        prefs_path=home/'.folderexporter/last-used.json'
        prefs_path.write_text(json.dumps({'version':4,'dest':str(home/'exports'),'use_project_folder':True,'project_folder_name':'Old project'}))
        migrated=Application();migrated.report_callback_exception=lambda *a:errors.append(a);migrated.update()
        assert migrated.dest.get()==str(home/'exports/Old project');assert not hasattr(migrated,'use_project_folder')
        migrated._write_preferences();assert json.loads(prefs_path.read_text())['version']==5;migrated.destroy()
        assert not errors,errors;assert not warnings,warnings
print('Studio Link GUI PASS: optional panel, removed project nesting, standalone export, real hidden PSD, shared/custom naming, component order, actual index/variant snapshots, stable matches across renumbering, relink, saved settings and reopen.')
