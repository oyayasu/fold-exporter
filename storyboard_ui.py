"""Optional Storyboard Studio controls and the Studio Link folder connection."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import storyboard as sb
import studio_link as studio

class StoryboardBridge:
    def __init__(self,app):
        self.app=app;self.reference=None;self.overrides={'chapters':{},'frames':{}}
        self.workspace=None;self.directory='';self.project_id=None;self.problem='';self.refresh_job=None
        self.enabled=tk.BooleanVar(value=False)
        self.chapter_style=tk.StringVar(value=sb.CHAPTER_STYLES[0])
        self.number_mode=tk.StringVar(value=sb.NUMBER_MODES[0])
        self.naming_mode=tk.StringVar(value=studio.CUSTOM_NAMES)
        self.lettered=tk.BooleanVar(value=False)
        self.loose_chapter=tk.StringVar(value='Auto detect')
        self.label=tk.StringVar(value='No project connected.')
        self.path_label=tk.StringVar(value='')
        self.restoring=False
        for var in (self.enabled,self.chapter_style,self.number_mode,self.naming_mode,self.lettered):var.trace_add('write',lambda *_:self.changed())

    def build(self,parent):
        a=self.app;self.holder=tk.Frame(parent,bg='#C0C0C0',bd=2,relief='groove');self.holder.pack(fill='x',pady=(8,0))
        self.enable_check=a.check(self.holder,'STORYBOARD STUDIO EXPORT',self.enabled)
        self.enable_check.pack(anchor='w',padx=12,pady=(4,4))
        self.box=box=a.panel(self.holder,'STORYBOARD STUDIO',fill='x')
        row=tk.Frame(box,bg='#C0C0C0');row.pack(fill='x',padx=12,pady=(2,5))
        make=lambda text,fn:tk.Button(row,text=text,command=fn,bg='#C0C0C0',bd=2,relief='raised',padx=8,pady=4)
        self.folder_button=make('Choose project folder...',self.choose_project);self.folder_button.pack(side='left')
        self.refresh_button=make('Refresh',lambda:self.refresh(quiet=False));self.refresh_button.pack(side='left',padx=6)
        self.clear_button=make('Disconnect',self.clear);self.clear_button.pack(side='left')
        self.path_widget=a.label(box,variable=self.path_label,small=True);self.path_widget.configure(wraplength=440);self.path_widget.pack(fill='x',padx=12,pady=(0,4))
        self.status_widget=a.label(box,variable=self.label,small=True);self.status_widget.configure(wraplength=440);self.status_widget.pack(fill='x',padx=12,pady=(0,6))
        a.label(box,'Card numbers used in CSP folders',small=True).pack(anchor='w',padx=12)
        self.number_picker=a.choose(box,self.number_mode,sb.NUMBER_MODES);self.number_picker.pack(fill='x',padx=12,pady=(2,6))
        a.check(box,'Recognize lettered frames (3A, 3B…) as Slight modify cards',self.lettered).pack(anchor='w',padx=12,pady=(0,6))
        a.label(box,'Chapter for drawings outside chapter folders',small=True).pack(anchor='w',padx=12)
        self.loose_picker=a.choose(box,self.loose_chapter,['Auto detect']);self.loose_picker.pack(fill='x',padx=12,pady=(2,6))
        self.loose_picker.bind('<<ComboboxSelected>>',lambda e:self.set_loose_chapter())
        a.label(box,'Chapter folders',small=True).pack(anchor='w',padx=12)
        self.chapter_picker=a.choose(box,self.chapter_style,sb.CHAPTER_STYLES);self.chapter_picker.pack(fill='x',padx=12,pady=(2,6))
        a.label(box,'File naming',small=True).pack(anchor='w',padx=12)
        self.naming_picker=a.choose(box,self.naming_mode,studio.NAMING_MODES);self.naming_picker.pack(fill='x',padx=12,pady=(2,4))
        tip=a.label(box,'Project names use the shared component pattern, numbered from bottom to top. Whole frames use the shared card name. Custom slots above remain available.',small=True);tip.configure(wraplength=440);tip.pack(fill='x',padx=12,pady=(0,7))
        a.check(box,'Give each frame its own folder',a.frame_folders).pack(anchor='w',padx=12)
        a.index_check=a.check(box,'Create image index (.json)',a.export_index);a.index_check.pack(anchor='w',padx=12,pady=(0,8))
        tk.Button(box,text='Workflow rules',command=self.show_manual).pack(anchor='w',padx=12,pady=(0,8))
        a.bind('<FocusIn>',self.focus,add='+');self.sync()

    def sync(self):
        if not hasattr(self,'folder_button'):return
        a=self.app;available=self.reference is not None;active=self.enabled.get()
        if active and not self.box.winfo_manager():self.box.pack(fill='x')
        if not active and self.box.winfo_manager():self.box.pack_forget()
        linked=active and bool(self.directory)
        if hasattr(a,'dest_entry'):
            a.dest_entry.configure(state='disabled' if linked else 'normal');a.dest_button.configure(state='disabled' if linked else 'normal')
        a.index_check.configure(state='disabled' if available and active else 'normal')
        if available and active and not a.export_index.get():a.export_index.set(True)
        self.clear_button.configure(state='normal' if available or self.directory else 'disabled')
        self.refresh_button.configure(state='normal' if self.directory and not a.busy else 'disabled')
        self.folder_button.configure(text='Relink folder...' if self.directory else 'Choose project folder...')
        for picker in (self.number_picker,self.chapter_picker):picker.configure(state='readonly' if available else 'disabled')
        self.naming_picker.configure(state='readonly' if available and self.reference.get('naming') else 'disabled')
        if self.problem:self.label.set(self.problem)
        elif available:self.label.set(self.reference['project']['name']+f" · {len(self.reference['chapters'])} chapters")
        else:self.label.set('Choose the main project folder to discover its reference automatically.')
        self.path_label.set(self.directory)
        self.status_widget.configure(fg='#A00000' if self.problem else '#555555')

    def changed(self):
        if self.restoring or self.app._restoring:return
        if self.enabled.get() and self.directory:self.app.dest.set(self.directory)
        self.overrides['lettered']=self.lettered.get()
        self.sync();self.app._preview();self.app._schedule_preferences();self.save_binding()

    def focus(self,event):
        if event.widget is not self.app or not self.enabled.get() or not self.directory or self.app.busy:return
        if self.refresh_job is not None:self.app.after_cancel(self.refresh_job)
        self.refresh_job=self.app.after(350,lambda:self.refresh(quiet=True))

    def choose_project(self):
        if self.app.busy:return
        path=filedialog.askdirectory(title='Choose the main project folder',initialdir=self.directory or self.app.dest.get() or str(Path.home()))
        if path:self.connect_path(path)

    def connect_path(self,path):
        try:workspace=studio.read_project(path,self.project_id if self.directory else None)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            messagebox.showerror('Project folder could not be connected',str(exc)+'\nSelect the main project folder that Storyboard Studio connected.');return False
        fresh=not self.directory
        self._accept_workspace(workspace)
        self.restoring=True;self.enabled.set(True)
        if fresh:self.chapter_style.set(studio.PROJECT_FOLDERS);self.naming_mode.set(studio.PROJECT_NAMES);self.app.separate.set(True)
        self.app.dest.set(str(workspace.root));self.restoring=False;self.changed()
        self.app.status.set('Project connected. Reliable chapter/card matches are automatic.');return True

    def _accept_workspace(self,workspace):
        if self.reference and self.reference['project']['id']!=workspace.project_id:self.overrides={'chapters':{},'frames':{}}
        if hasattr(self,'loose_picker'):self.loose_picker.configure(values=['Auto detect']+[sb.chapter_label(ch) for ch in workspace.reference['chapters']])
        chosen=next((ch for ch in workspace.reference['chapters'] if ch['id']==self.overrides.get('chapters',{}).get(sb.chapter_key(()))),None);self.loose_chapter.set(sb.chapter_label(chosen) if chosen else 'Auto detect')
        self.workspace=workspace;self.directory=str(workspace.root);self.project_id=workspace.project_id;self.reference=workspace.reference;self.problem=''

    def refresh(self,quiet=True,for_export=False,force=False):
        if self.refresh_job is not None:
            try:self.app.after_cancel(self.refresh_job)
            except tk.TclError:pass
        self.refresh_job=None
        if not self.directory or self.app.busy and not force:return self.workspace
        try:
            workspace=studio.read_project(self.directory,self.project_id);self._accept_workspace(workspace)
            if self.enabled.get() and self.app.dest.get()!=self.directory:
                self.restoring=True;self.app.dest.set(self.directory);self.restoring=False
            self.sync();self.app._preview();self.save_binding();return workspace
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.workspace=None;self.problem='Project folder unavailable or changed. Relink folder. '+str(exc);self.sync();self.app._preview()
            if for_export:raise ValueError(self.problem) from exc
            if not quiet:messagebox.showwarning('Studio Link needs attention',self.problem)
            return None

    def clear(self,force=False):
        if self.app.busy and not force:return
        self.restoring=True;self.workspace=None;self.directory='';self.project_id=None;self.problem='';self.reference=None;self.overrides={'chapters':{},'frames':{}};self.naming_mode.set(studio.CUSTOM_NAMES);self.chapter_style.set(sb.CHAPTER_STYLES[0]);self.restoring=False
        self.changed()

    def binding_path(self):
        return self.app._project_rules_path(self.app.source).with_suffix('.storyboard.json') if self.app.source else None

    def save_binding(self):
        if self.restoring or self.app._restoring:return
        path=self.binding_path()
        if path is None:return
        try:
            if self.reference is None:path.unlink(missing_ok=True);return
            path.parent.mkdir(parents=True,exist_ok=True)
            data={'version':2,'reference':self.reference,'overrides':self.overrides,'enabled':self.enabled.get(),
                  'lettered':self.lettered.get(),'chapterStyle':self.chapter_style.get(),'numberMode':self.number_mode.get(),
                  'studioDirectory':self.directory,'studioProjectId':self.project_id,'outputDirectory':self.app.dest.get(),'namingMode':self.naming_mode.get(),'frameFolders':self.app.frame_folders.get()}
            temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');temp.replace(path)
        except OSError as exc:self.app.status.set(f'Could not save storyboard links: {exc}')

    def source_opened(self,previous_source):
        path=self.binding_path()
        if not path.is_file():
            if previous_source is not None and previous_source!=self.app.source:self.overrides={'chapters':{},'frames':{},'lettered':self.lettered.get()}
            if self.directory:self.refresh(quiet=True,force=True)
            elif self.reference is None:
                self.restoring=True;self.naming_mode.set(studio.CUSTOM_NAMES)
                if self.chapter_style.get()==studio.PROJECT_FOLDERS:self.chapter_style.set(sb.CHAPTER_STYLES[0])
                self.restoring=False
            self.sync();return
        self.restoring=True
        try:
            if path.stat().st_size>20*1024*1024:raise ValueError('Saved storyboard links exceed 20 MB.')
            data=json.loads(path.read_text(encoding='utf-8'))
            if data.get('version') not in (1,2):raise ValueError('Unsupported saved storyboard links.')
            reference=sb.validate_reference(data['reference']);overrides=data.get('overrides',{})
            if not isinstance(overrides,dict) or any(not isinstance(overrides.get(k,{}),dict) for k in ('chapters','frames')):raise ValueError('Invalid saved matches.')
            self.workspace=None;self.reference=reference;self.overrides=overrides;self.lettered.set(bool(data.get('lettered',False)));self.overrides['lettered']=self.lettered.get();self.problem=''
            self.directory=str(data.get('studioDirectory',''));self.project_id=reference['project']['id']
            self.enabled.set(bool(data.get('enabled',True)))
            self.chapter_style.set(data.get('chapterStyle') if data.get('chapterStyle') in sb.CHAPTER_STYLES else sb.CHAPTER_STYLES[0])
            self.number_mode.set(data.get('numberMode') if data.get('numberMode') in sb.NUMBER_MODES else sb.NUMBER_MODES[0])
            self.naming_mode.set(data.get('namingMode') if data.get('namingMode') in studio.NAMING_MODES else studio.CUSTOM_NAMES)
            self.app.frame_folders.set(bool(data.get('frameFolders',False)))
            if isinstance(data.get('outputDirectory'),str) and data['outputDirectory'].strip():self.app.dest.set(data['outputDirectory'])
        except (OSError,ValueError,KeyError,TypeError) as exc:
            self.workspace=None;self.directory='';self.reference=None;self.overrides={'chapters':{},'frames':{}};self.enabled.set(False)
            messagebox.showwarning('Saved storyboard links could not be loaded',str(exc))
        finally:self.restoring=False;self.sync()
        if self.directory:self.refresh(quiet=True,force=True)

    def remember_links(self,bundle):
        if bundle.reference is None:return
        for drawing,_ in bundle.tasks:
            link=bundle.links.get(sb.frame_key(drawing))
            if link and link.get('card'):
                self.overrides['chapters'].setdefault(sb.chapter_key(link['sourceChapter']),link['chapter']['id'])
                self.overrides['frames'].setdefault(sb.link_match_key(link),link['card']['id'])
        self.save_binding()


    def show_manual(self):
        import sys,re
        path=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'WORKFLOW_MANUAL.md'
        try:text=path.read_text(encoding='utf8')
        except OSError as exc:messagebox.showerror('Workflow rules',str(exc));return
        text=re.sub(r'(?m)^#{1,6} ','',text).replace('**','').replace('`','')
        win=tk.Toplevel(self.app);win.title('Workflow rules');win.geometry('720x620');area=tk.Text(win,wrap='word',padx=16,pady=14);bar=tk.Scrollbar(win,command=area.yview);area.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');area.pack(fill='both',expand=True);area.insert('1.0',text);area.configure(state='disabled');tk.Button(win,text='Close',command=win.destroy).pack(pady=8)

    def set_loose_chapter(self):
        if not self.reference:return
        chapter=next((ch for ch in self.reference['chapters'] if sb.chapter_label(ch)==self.loose_chapter.get()),None)
        for drawing in self.app.drawings:
            if not sb.source_chapter(drawing):
                self.overrides.setdefault('frameChapters',{}).pop(sb.frame_match_key(drawing),None);self.overrides['frames'].pop(sb.frame_match_key(drawing),None)
        if chapter:self.overrides['chapters'][sb.chapter_key(())]=chapter['id']
        else:self.overrides['chapters'].pop(sb.chapter_key(()),None)
        self.changed()

    def resolve_unmatched(self):
        if not self.enabled.get() or not self.reference:return True
        _,links=sb.resolve_links(self.app.drawings,self.reference,self.overrides,self.number_mode.get())
        chosen={sb.frame_key(d) for d in self.app.drawings if d.node.key in self.app.selected}
        pending=[(key,l) for key,l in links.items() if key in chosen and (not l['chapter'] or not l['card'])]
        if not pending:return True
        win=tk.Toplevel(self.app);win.title('Assign loose drawings');win.geometry('720x550');win.transient(self.app);win.grab_set()
        tk.Label(win,text='Choose the chapter and card for each unmatched drawing.',wraplength=660).pack(pady=12)
        canvas=tk.Canvas(win);bar=tk.Scrollbar(win,command=canvas.yview);canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(fill='both',expand=True);body=tk.Frame(canvas);canvas.create_window((0,0),window=body,anchor='nw');body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        from tkinter import ttk
        rows=[];chapters=self.reference['chapters'];labels=[sb.chapter_label(ch) for ch in chapters]
        for key,link in pending:
            row=tk.LabelFrame(body,text=' / '.join((*link['sourceChapter'],link['sourceFrame'])));row.pack(fill='x',padx=12,pady=6)
            cv=tk.StringVar(value=sb.chapter_label(link['chapter']) if link['chapter'] else '');dv=tk.StringVar()
            cp=ttk.Combobox(row,textvariable=cv,values=labels,state='readonly',width=28);cp.pack(side='left',padx=8,pady=8)
            dp=ttk.Combobox(row,textvariable=dv,state='readonly',width=28);dp.pack(side='left',padx=8)
            def update(e=None,cv=cv,dv=dv,dp=dp,link=link):
                ch=next((c for c in chapters if sb.chapter_label(c)==cv.get()),None);dp.configure(values=[sb.card_label(c) for c in ch['cards']] if ch else [])
                n=sb.frame_number(link['sourceFrame'],self.lettered.get());field='frameLabel' if self.number_mode.get()=='Chapter numbers' else 'globalFrameLabel' if self.number_mode.get()=='Global numbers' else 'displayLabel'
                matches=[c for c in ch['cards'] if str(c.get(field,sb.card_number(c,self.number_mode.get())))==str(n)] if ch else [];dv.set(sb.card_label(matches[0]) if len(matches)==1 else '')
            cp.bind('<<ComboboxSelected>>',update);update();rows.append((link,cv,dv))
            def preview(key=key,row=row):
                try:
                    from PIL import ImageTk
                    import export_core as core
                    from dataclasses import replace
                    drawing=next(d for d in self.app.drawings if sb.frame_key(d)==key)
                    if drawing.frame is not None:drawing=replace(drawing,node=drawing.frame,frame=None,excluded=())
                    image=core.render(self.app.project,drawing,core.is_clip(self.app.source),self.app._settings());image.thumbnail((250,140));photo=ImageTk.PhotoImage(image);label=tk.Label(row,image=photo);label.image=photo;label.pack(side='bottom')
                except Exception as exc:messagebox.showwarning('Preview unavailable',str(exc),parent=win)
            tk.Button(row,text='Preview',command=preview).pack(side='left',padx=3)
        result=[False]
        def apply():
            entries=[]
            for link,cv,dv in rows:
                ch=next((c for c in chapters if sb.chapter_label(c)==cv.get()),None);card=next((c for c in ch['cards'] if sb.card_label(c)==dv.get()),None) if ch else None
                if not card:messagebox.showwarning('Choose a card','Assign a chapter and card for every listed drawing.',parent=win);return
                entries.append((link,ch,card))
            for link,ch,card in entries:self.overrides.setdefault('frameChapters',{})[sb.link_match_key(link)]=ch['id'];self.overrides['frames'][sb.link_match_key(link)]=card['id']
            result[0]=True;self.save_binding();win.destroy()
        foot=tk.Frame(win);foot.pack(fill='x');tk.Button(foot,text='Cancel',command=win.destroy).pack(side='right',padx=8,pady=10);tk.Button(foot,text='Use assignments',command=apply).pack(side='right',padx=8);self.app.wait_window(win);return result[0]
