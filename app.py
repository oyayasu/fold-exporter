"""FolderExporter: compact Windows 95-inspired English-only macOS interface."""
from __future__ import annotations
import media_catalog
import queue
import json
import hashlib
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk
import export_core as core
import storyboard as sb
import studio_link as studio
from storyboard_ui import StoryboardBridge

FACE='#C0C0C0'
NAVY='#000080'
WHITE='#FFFFFF'
DARK='#181818'
GREY='#777777'

HELP = {
    'file': ('Project file',
        'Choose a PSD or PSB file from Clip Studio Paint or Photoshop. Direct CLIP reading is experimental; PSD is recommended for complex drawings.\n\nThe source is opened read-only. FolderExporter never saves or changes the original project.'),
    'folders': ('How FolderExporter chooses artwork',
        'FolderExporter finds FOLDERS and layers clipped to those folders. Regular layers inside a selected folder belong to that folder. Loose layers outside the folder hierarchy are ignored unless they are clipped to an exported folder.\n\nOrganizational folder keywords are optional. For example, “chapter” finds Chapter 1 and Chapter 2, then uses their children as frames. Leave this blank if frames are already at the PSD root.\n\nClipped layers are listed just above their target folder with a downward arrow, but are never exported separately. The Folders Found panel lets you select folders, including hidden ones.'),
    'settings': ('Image export settings',
        'Choose PNG, WEBP, TIFF or JPEG. Scale defaults to 100%. JPEG quality and background appear for JPEG only.\n\nWhen cropping is on, choose All, Components only, or Some components. In Some components mode, check Crop next to whichever component rules need it. Cropping removes transparent margins and changes image dimensions. Keep cropping OFF to preserve alignment in your video editor.\n\nWhite background replaces transparency with opaque white pixels. JPEG is always opaque.'),
    'naming': ('Build a filename from four slots',
        'Choose Folder name, Chapter, Component, Index, Component index, Card number, Custom text or None for each of four slots. '
        'Three small fields between the slots accept up to three characters each, such as a space, underscore, or hyphen. '
        'Leave them blank to join names without a gap.\n\n'
        'A separator field is hidden only if BOTH adjacent slots are set to None. When a slot has no value, its own preceding connector is skipped; the connector before the next nonempty slot is kept. For example, Index - Component _ Folder name exports as Index_Folder name when Component is absent.\n\n'
        'The example inside this panel updates while you edit. All components in the same frame share a frame Index, while Component index appears only when more than one component shares the same export label within a frame; each label has its own counter starting at 1. '
        'Turn on the component-order checkbox to number EVERY selected component from bottom to top instead. This is independent of the frame numbering direction. The Card number slot uses the linked card number as displayed in Storyboard Studio, even when exporting only some frames. It is empty without a storyboard link. Start index and index width are on the same row.'),
    'rules': ('Component export rules',
        'Each rule has a folder-name pattern, an output label, and (when selective cropping is active) a Crop checkbox. Add as many rules as you want. For example, Background → BG, Foreground → F and Part * → P - {match}.\n\nThe asterisk (*) matches any text. In Part * → P - {match}, a folder named Part Trees becomes a component labeled P - Trees. The “{match}” placeholder means the text matched by the first asterisk.\n\nRules apply to nested folders. If no nested component matches, the entire frame is exported as one drawing. With matching components you can export them separately, export both components and the full frame, or export only the whole frame. Other nested folders are not exported as individual files unless matched by a rule. Unclipped loose layers outside folders are ignored.\n\nYou can save rules for the current PSD without modifying the PSD itself.'),
    'destination': ('Destination and preview',
        'Choose your output folder directly. Storyboard Studio export can connect the main project folder and reuse its naming settings. Chapter folders can use Storyboard Studio titles, numbers plus titles, or the original CSP folder names. Frame folders are optional; leave them off to keep all chapter images together.\n\nWith Studio Link, the image index sits in Studio Link; otherwise it sits beside the exported images and records the files actually saved, their storyboard links, and bottom-to-top order. Move the entire export folder together to keep those file links working. With a storyboard reference, review unresolved or duplicate matches before exporting.\n\nThe preview follows your four naming slots. Existing images and older indices are never overwritten.'),
}


def btn(parent,text,cmd,**kw):
    return tk.Button(parent,text=text,command=cmd,relief='raised',bd=2,bg=FACE,fg=DARK,
                     activebackground='#DEDEDE',padx=10,pady=4,highlightthickness=0,**kw)


class SegmentedProgress(tk.Frame):
    """Classic Windows-style rectangular progress indicator, without an X button."""
    def __init__(self,parent,sections=20):
        super().__init__(parent,bg=FACE)
        track=tk.Frame(self,bd=2,relief='sunken',bg=WHITE)
        track.pack(side='left',fill='x',expand=True)
        self.cells=[]
        for _ in range(sections):
            cell=tk.Frame(track,bg=FACE,bd=1,relief='flat',height=14)
            cell.pack(side='left',fill='both',expand=True,padx=1,pady=2)
            self.cells.append(cell)
        self.percent=tk.StringVar(value='0%')
        tk.Label(self,textvariable=self.percent,bg=FACE,fg=DARK,
                 font=('Geneva',10),width=5,anchor='e').pack(side='right',padx=(6,0))
        self.set(0)

    def set(self,value):
        amount=max(0,min(100,float(value)))
        filled=int((amount*len(self.cells))/100)
        for i,cell in enumerate(self.cells):
            cell.configure(bg=NAVY if i<filled else FACE,
                           relief='raised' if i<filled else 'flat')
        self.percent.set(f'{int(round(amount))}%')


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('FolderExporter')
        self.geometry('1200x760')
        self.minsize(940,610)
        self.configure(bg=FACE)
        self.option_add('*Font','{Geneva} 10' if sys.platform=='darwin' else '{Arial} 10')
        self.project=None
        self.source=None
        self.nodes=[]
        self.drawings=[]
        self.selected=set()
        self.events=queue.Queue()
        self.cancel=threading.Event()
        self.busy=False
        self.icon=None
        self.file_label=tk.StringVar(value='No project selected')
        self.status=tk.StringVar(value='Ready.')
        self.count=tk.StringVar(value='0 drawings selected')
        self.ignore=tk.StringVar(value='chapter, section')
        self.separate=tk.BooleanVar(value=True)
        self.dest=tk.StringVar(value='')
        self.format=tk.StringVar(value='PNG')
        self.scale=tk.StringVar(value='100')
        self.quality=tk.StringVar(value='100')
        self.crop=tk.BooleanVar(value=False)
        self.crop_scope=tk.StringVar(value='All')
        self.white=tk.BooleanVar(value=False)
        self.jpeg=tk.StringVar(value='White')
        self.start_number=tk.StringVar(value='1')
        self.padding=tk.StringVar(value='001')
        self.reverse=tk.BooleanVar(value=False)
        self.reset=tk.BooleanVar(value=True)
        self.component_stack_order=tk.BooleanVar(value=False)
        self.frame_folders=tk.BooleanVar(value=False)
        self.export_index=tk.BooleanVar(value=True)
        self.slots=[(tk.StringVar(value=slot.kind),tk.StringVar(value=slot.text))
                    for slot in core.DEFAULT_SLOTS]
        self.separators=[tk.StringVar(value='') for _ in range(3)]
        self.component_mode=tk.StringVar(value='Separate components')
        self.name_example=tk.StringVar(value='002BG.png')
        self.preview_text=tk.StringVar(value='Choose a file to preview exports.')
        self.rule_rows=[]
        self._rule_job=None
        self._loading_rules=False
        self._restoring=True
        self._save_job=None
        self._event_job=None
        self._wheel_remainder={'left':0.0,'right':0.0}
        self.storyboards=StoryboardBridge(self)
        self._load_preferences()
        self._ui()
        self.ignore.trace_add('write',lambda *_:self._on_structure_change())
        self.separate.trace_add('write',lambda *_:self._on_structure_change())
        self.component_mode.trace_add('write',lambda *_:self._on_structure_change())
        for var in (self.dest,self.format,self.scale,self.quality,self.crop,self.crop_scope,self.white,self.jpeg,
                    self.start_number,self.padding,self.reverse,self.reset,self.component_stack_order,
                    self.frame_folders,self.export_index):
            var.trace_add('write',lambda *_:self._refresh_settings())
        for slot_type,slot_text in self.slots:
            for var in (slot_type,slot_text):
                var.trace_add('write',lambda *_:self._filename_changed())
        for separator in self.separators:
            separator.trace_add('write',lambda *_:self._filename_changed())
        self._restoring=False
        self._event_job=self.after(120,self._events)
        self.protocol('WM_DELETE_WINDOW',self._close)
        if len(sys.argv)>1 and Path(sys.argv[1]).is_file():
            self.after(100,lambda:self._open(Path(sys.argv[1])))

    def label(self,parent,text=None,variable=None,small=False):
        return tk.Label(parent,text=text,bg=FACE,fg=GREY if small else DARK,
                        textvariable=variable,anchor='w',justify='left',font=('Geneva',9) if small else None)

    def help_icon(self, parent, key):
        # A text-only label deliberately avoids native macOS button chrome.
        icon=tk.Label(parent,text='ⓘ',bg=FACE,fg=NAVY,bd=0,
                      relief='flat',padx=0,pady=0,highlightthickness=0,
                      font=('Geneva',10,'bold'),cursor='hand2')
        icon.bind('<Button-1>',lambda _:self._show_info(key))
        icon.bind('<Enter>',lambda _:icon.configure(fg='#3333A0'))
        icon.bind('<Leave>',lambda _:icon.configure(fg=NAVY))
        return icon

    def panel(self,parent,title,subtitle=None,info=None,**pack):
        box=tk.Frame(parent,bg=FACE,bd=2,relief='raised')
        box.pack(**pack)
        header=tk.Frame(box,bg=FACE)
        header.pack(fill='x',padx=12,pady=(8,7))
        tk.Label(header,text=title,bg=FACE,fg=DARK,font=('Geneva',10,'bold'),anchor='w').pack(side='left')
        if subtitle:
            tk.Label(header,text=subtitle,bg=FACE,fg=GREY,
                     font=('Geneva',9),anchor='w').pack(side='left',padx=(9,0))
        if info:self.help_icon(header,info).pack(side='right')
        return box

    def _show_info(self, key):
        title,explanation=HELP[key]
        popup=tk.Toplevel(self)
        popup.title('FolderExporter Help — '+title)
        popup.configure(bg=FACE)
        popup.geometry('490x440')
        popup.minsize(360,300)
        popup.transient(self)
        body=tk.Frame(popup,bg=FACE,padx=16,pady=14)
        body.pack(fill='both',expand=True)
        tk.Label(body,text=title,bg=NAVY,fg=WHITE,font=('Geneva',12,'bold'),
                 anchor='w',padx=11,pady=8).pack(fill='x',pady=(0,12))
        box=tk.Frame(body,bg=WHITE,relief='sunken',bd=2)
        box.pack(fill='both',expand=True)
        scroller=tk.Canvas(box,bg=WHITE,bd=0,highlightthickness=0)
        scrollbar=ttk.Scrollbar(box,command=scroller.yview)
        scrollbar.pack(side='right',fill='y')
        scroller.pack(side='left',fill='both',expand=True)
        scroller.configure(yscrollcommand=scrollbar.set)
        inner=tk.Frame(scroller,bg=WHITE,padx=11,pady=11)
        win=scroller.create_window((0,0),anchor='nw',window=inner)
        inner.bind('<Configure>',lambda _:scroller.configure(scrollregion=scroller.bbox('all')))
        scroller.bind('<Configure>',lambda e:scroller.itemconfigure(win,width=e.width))
        tk.Label(inner,text=explanation,bg=WHITE,fg=DARK,justify='left',
                 anchor='nw',wraplength=400,font=('Geneva',10)).pack(fill='x')
        if key in ('folders','settings','naming'):
            diagram=tk.Canvas(inner,bg=WHITE,height=95,highlightthickness=0)
            diagram.pack(fill='x',pady=(13,2))
            if key=='settings':
                diagram.create_rectangle(5,6,185,87,fill='#E7EEF9',outline=GREY)
                diagram.create_rectangle(66,20,126,72,fill='#7FA7D6',outline=NAVY)
                diagram.create_rectangle(241,14,305,79,fill='#7FA7D6',outline=NAVY)
                diagram.create_text(93,85,text='Full canvas',anchor='s')
                diagram.create_text(273,91,text='Cropped',anchor='s')
            elif key=='naming':
                x=6
                for token,width in [('002',67),(' - ',51),('BG',55)]:
                    diagram.create_rectangle(x,15,x+width,55,fill='#E2E7F5',outline=NAVY)
                    diagram.create_text(x+width/2,35,text=token,font=('Geneva',11,'bold'))
                    x+=width+6
                diagram.create_text(5,72,text='→ 002 - BG.png',anchor='w',font=('Geneva',11))
            else:
                diagram.create_text(8,7,text='FRAME 2',anchor='nw',font=('Geneva',10,'bold'))
                diagram.create_rectangle(16,32,163,58,fill='#E2E7F5',outline=NAVY)
                diagram.create_text(25,45,text='Background folder',anchor='w')
                diagram.create_text(180,45,text='+ clipped layers',anchor='w')
                diagram.create_text(16,76,text='Unclipped loose layer → ignored',anchor='w',fill=GREY)
        btn(body,'Close',popup.destroy).pack(side='right',pady=(10,0))
        # Popups have their own mouse-wheel viewport.
        def wheel(event):
            if getattr(event,'num',None) in (4,5): dy=(-2 if event.num==4 else 2)
            else: dy=(-2 if getattr(event,'delta',0)>0 else 2)
            scroller.yview_scroll(dy,'units')
            return 'break'
        def bind_info(widget):
            for event_type in ('<MouseWheel>','<Button-4>','<Button-5>'):
                widget.bind(event_type,wheel)
            for child in widget.winfo_children():bind_info(child)
        bind_info(popup)

    def entry(self,parent,var):
        return tk.Entry(parent,textvariable=var,relief='sunken',bd=2,bg=WHITE,fg=DARK,highlightthickness=0)

    def choose(self,parent,var,values):
        combo=ttk.Combobox(parent,textvariable=var,state='readonly',values=values,width=20)
        combo.bind('<<ComboboxSelected>>',lambda _e,control=combo:
                   self.after_idle(lambda:self._clear_combo_focus(control)),add='+')
        return combo

    def _clear_combo_focus(self,control):
        """Prevent Aqua from selecting/highlighting combobox text after picking."""
        try:
            if not control.winfo_exists():return
            control.selection_clear()
            # Remove the bright focused control ring without changing its value.
            self.focus_set()
        except tk.TclError:
            pass

    def check(self,parent,text,var):
        return tk.Checkbutton(parent,text=text,variable=var,bg=FACE,fg=DARK,
                              activebackground=FACE,selectcolor=FACE,anchor='w',highlightthickness=0)

    def labeled(self,parent,title,widget,row,col):
        label=self.label(parent,title,small=True)
        label.grid(row=row,column=col,sticky='ew',padx=6,pady=(2,3))
        widget.grid(row=row+1,column=col,sticky='ew',padx=6,pady=(0,9))
        return label,widget

    def _ui(self):
        header=tk.Frame(self,bg=NAVY,height=42)
        header.pack(fill='x',side='top',padx=6,pady=(6,3))
        header.pack_propagate(False)
        try:
            icon_path=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'folder.png'
            image=Image.open(icon_path).convert('RGBA')
            image.thumbnail((30,30),Image.Resampling.NEAREST)
            self.icon=ImageTk.PhotoImage(image)
            tk.Label(header,image=self.icon,bg=NAVY).pack(side='left',padx=(8,4))
        except Exception:pass
        tk.Label(header,text='FolderExporter',bg=NAVY,fg='white',font=('Geneva',12,'bold')).pack(side='left')
        tk.Label(header,text='CLASSIC 1.10.0',bg=NAVY,fg='#DDDDEF',font=('Geneva',9)).pack(side='right',padx=12)

        footer=tk.Frame(self,bg=FACE,bd=2,relief='raised')
        footer.pack(side='bottom',fill='x',padx=6,pady=(3,6))
        foot_left=tk.Frame(footer,bg=FACE)
        foot_left.pack(side='left',fill='both',expand=True,padx=10,pady=8)
        self.label(foot_left,variable=self.status,small=True).pack(anchor='w')
        self.progress=SegmentedProgress(foot_left)
        self.progress.pack(fill='x',pady=(4,0))
        self.export_button=btn(footer,'Export All',self._export)
        self.export_button.pack(side='right',padx=13,pady=11)

        # The panes occupy independent grid cells: no PanedWindow sash or
        # shared scrolling owner can intercept a right-pane wheel event.
        layout=tk.Frame(self,bg=FACE)
        layout.pack(fill='both',expand=True,padx=6,pady=3)
        layout.grid_columnconfigure(0,weight=37,minsize=320)
        layout.grid_columnconfigure(1,weight=63,minsize=560)
        layout.grid_rowconfigure(0,weight=1)
        left=tk.Frame(layout,bg=FACE)
        right=tk.Frame(layout,bg=FACE)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,4))
        right.grid(row=0,column=1,sticky='nsew',padx=(4,0))
        self.left_pane=left
        self.right_pane=right

        file_panel=self.panel(left,'01   FILE',subtitle='(This program works best with .psd files)',info='file',fill='x')
        chooser=tk.Frame(file_panel,bg=FACE)
        chooser.pack(fill='x',padx=12,pady=(2,11))
        self.label(chooser,variable=self.file_label,small=True).pack(side='left',fill='x',expand=True)
        self.open_btn=btn(chooser,'Choose File...',self._choose)
        self.open_btn.pack(side='right')

        folders=self.panel(left,'02   FOLDERS FOUND',info='folders',fill='both',expand=True,pady=(8,0))
        self.label(folders,'Organizational folder keywords (Optional)',small=True).pack(fill='x',padx=12)
        self.entry(folders,self.ignore).pack(fill='x',padx=12,pady=(3,4))
        select_row=tk.Frame(folders,bg=FACE)
        select_row.pack(fill='x',padx=10,pady=(8,6))
        self.label(select_row,variable=self.count,small=True).pack(side='left')
        btn(select_row,'All',lambda:self._select_all(True)).pack(side='right',padx=(5,0))
        btn(select_row,'None',lambda:self._select_all(False)).pack(side='right')
        tree_holder=tk.Frame(folders,bd=2,relief='sunken',bg=WHITE)
        tree_holder.pack(fill='both',expand=True,padx=11,pady=(0,11))
        ttk.Style(self).configure('Win95.Treeview',font=('Geneva',10),rowheight=24)
        self.tree=ttk.Treeview(tree_holder,show='tree',style='Win95.Treeview',selectmode='browse')
        bar=ttk.Scrollbar(tree_holder,orient='vertical',command=self.tree.yview)
        bar.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side='left',fill='both',expand=True)
        self.tree.bind('<ButtonRelease-1>',self._click)
        self.tree.bind('<space>',self._space)

        # Independently scrolling settings; the footer always remains visible.
        side=tk.Frame(right,bg=FACE)
        side.pack(fill='both',expand=True)
        canvas=tk.Canvas(side,bg=FACE,bd=0,highlightthickness=0,yscrollincrement=1)
        side_scroll=ttk.Scrollbar(side,orient='vertical',command=canvas.yview)
        side_scroll.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=side_scroll.set)
        inner=tk.Frame(canvas,bg=FACE)
        win=canvas.create_window((0,0),window=inner,anchor='nw')
        inner.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        self.right_canvas=canvas
        self._settings_panels(inner)
        self._example_name()
        # The custom bindtag runs ahead of native ttk widget bindings on Aqua.
        # A global fallback catches wheel events delivered to the root.
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind_class('FolderExporterWheel',sequence,self._mouse_wheel)
            # Some macOS Tk distributions deliver wheel events to root or a
            # focused widget. The global fallback also covers new controls.
            self.bind_all(sequence,self._mouse_wheel,add='+')
        # Tk 9 dispatches trackpad gestures as packed 32-bit deltas instead
        # of MouseWheel. Tk 8.6 doesn't recognize this physical event type.
        try:
            self.bind_class('FolderExporterWheel','<TouchpadScroll>',self._touchpad_wheel)
            self.bind_all('<TouchpadScroll>',self._touchpad_wheel,add='+')
        except tk.TclError:
            pass
        self.after_idle(self._bind_wheels)

    def _settings_panels(self,inner):
        settings=self.panel(inner,'03   EXPORT SETTINGS',info='settings',fill='x')
        grid=tk.Frame(settings,bg=FACE)
        grid.pack(fill='x',padx=9)
        grid.grid_columnconfigure(0,weight=1)
        grid.grid_columnconfigure(1,weight=1)
        self.labeled(grid,'Image format',self.choose(grid,self.format,['PNG','WEBP','TIFF','JPEG']),0,0)
        self.labeled(grid,'Scale (%)',self.choose(grid,self.scale,['25','50','75','100','150','200','300']),0,1)
        self.jpeg_widgets=[]
        self.jpeg_widgets.extend(self.labeled(grid,'JPEG quality',
            self.choose(grid,self.quality,['70','80','90','95','100']),2,0))
        self.jpeg_widgets.extend(self.labeled(grid,'JPEG background',
            self.choose(grid,self.jpeg,['White','Black']),2,1))
        self._update_jpeg_fields()
        crop_row=tk.Frame(settings,bg=FACE)
        crop_row.pack(fill='x',padx=13)
        self.check(crop_row,'Crop to drawing bounds',self.crop).pack(side='left')
        self.crop_scope_picker=self.choose(crop_row,self.crop_scope,core.CROP_SCOPES)
        self.crop_scope_picker.configure(width=19)
        self.crop_scope_picker.pack(side='left',padx=(12,0))
        self._update_crop_fields()
        self.check(settings,'White background (otherwise transparent)',self.white).pack(anchor='w',padx=13,pady=(0,10))
        naming=tk.Frame(settings,bg=FACE,bd=2,relief='groove')
        naming.pack(fill='x',padx=11,pady=(0,10))
        naming_header=tk.Frame(naming,bg=FACE)
        naming_header.pack(fill='x',padx=9,pady=(9,4))
        tk.Label(naming_header,text='FILE NAMING',bg=FACE,fg=DARK,
                 font=('Geneva',10,'bold')).pack(side='left')
        self.help_icon(naming_header,'naming').pack(side='right')
        self.name_panel=tk.Frame(naming,bg=FACE)
        self.name_panel.pack(fill='x',padx=8,pady=(3,8))
        self._name_widgets()
        naming_flags=tk.Frame(naming,bg=FACE)
        naming_flags.pack(fill='x',padx=11,pady=(0,9))
        self.check(naming_flags,'Restart numbering in each chapter',self.reset).pack(anchor='w')
        self.check(naming_flags,'Number from bottom to top',self.reverse).pack(anchor='w')
        self.check(naming_flags,'Component index: number every exported component bottom to top',self.component_stack_order).pack(anchor='w')
        self.label(naming_flags,'Uses the Component index slot. Off = number repeated labels only.',small=True).pack(anchor='w',padx=20)

        rules_panel=self.panel(inner,'COMPONENT EXPORT RULES',info='rules',fill='x',pady=(8,0))
        mode_row=tk.Frame(rules_panel,bg=FACE)
        mode_row.pack(fill='x',padx=12,pady=(0,8))
        self.label(mode_row,'Component export mode',small=True).pack(side='left',padx=(0,8))
        self.choose(mode_row,self.component_mode,core.COMPONENT_MODES).pack(side='left',fill='x',expand=True)
        header=tk.Frame(rules_panel,bg=FACE)
        header.pack(fill='x',padx=12)
        header.grid_columnconfigure(0,weight=2)
        header.grid_columnconfigure(1,weight=2)
        header.grid_columnconfigure(2,minsize=52)
        header.grid_columnconfigure(3,minsize=70)
        self.label(header,'Folder pattern',small=True).grid(row=0,column=0,sticky='w',padx=(0,4))
        self.label(header,'Export label',small=True).grid(row=0,column=1,sticky='w',padx=(0,4))
        self.crop_header=self.label(header,'Crop',small=True)
        self.crop_header.grid(row=0,column=2,sticky='')
        self.rules_list=tk.Frame(rules_panel,bg=FACE)
        self.rules_list.pack(fill='x',padx=12)
        controls=tk.Frame(rules_panel,bg=FACE)
        controls.pack(fill='x',padx=12,pady=(7,10))
        btn(controls,'+ Add Rule',self._add_rule).pack(side='left')
        btn(controls,'Save Project Rules',self._save_rules).pack(side='right')
        self._loading_rules=True
        presets=getattr(self,'_saved_rules',None)
        if not isinstance(presets,list):
            presets=[{'pattern':'Background','label':'BG'},
                     {'pattern':'Foreground','label':'F'},
                     {'pattern':'Part *','label':'P - {match}'}]
        for item in presets[:200]:
            if isinstance(item,dict):
                self._add_rule(str(item.get('pattern','')),str(item.get('label','')),bool(item.get('crop',False)))
        self._loading_rules=False
        self._update_crop_fields()

        self.storyboards.build(inner)
        output=self.panel(inner,'04   DESTINATION & PREVIEW',info='destination',fill='x',pady=(8,0))
        browse=tk.Frame(output,bg=FACE)
        browse.pack(fill='x',padx=12,pady=(3,9))
        self.dest_entry=self.entry(browse,self.dest);self.dest_entry.pack(side='left',fill='x',expand=True)
        self.dest_button=btn(browse,'Browse...',self._browse);self.dest_button.pack(side='right',padx=(8,0))
        self.check(output,'Separate drawings into chapter folders',self.separate).pack(anchor='w',padx=12,pady=(0,9))
        self.label(output,'Live export preview',small=True).pack(fill='x',padx=12)
        preview_box=tk.Frame(output,relief='sunken',bd=2,bg=WHITE)
        preview_box.pack(fill='x',padx=12,pady=(4,12))
        tk.Label(preview_box,textvariable=self.preview_text,bg=WHITE,fg=DARK,justify='left',anchor='nw',wraplength=420).pack(fill='x',padx=9,pady=9)

    def _name_widgets(self):
        """Build fields once. Changing a dropdown must NEVER destroy the panel."""
        slots_box=tk.Frame(self.name_panel,bg=FACE)
        slots_box.pack(fill='x')
        for c in range(7):slots_box.grid_columnconfigure(c,weight=1 if c%2==0 else 0)
        self.custom_entries=[]
        for i,(slot_type,slot_text) in enumerate(self.slots):
            col=tk.Frame(slots_box,bg=FACE)
            col.grid(row=0,column=i*2,sticky='new',padx=2)
            self.label(col,f'Slot {i+1}',small=True).pack(anchor='w')
            combobox=self.choose(col,slot_type,core.SLOT_TYPES)
            combobox.configure(width=12)
            combobox.pack(fill='x',pady=(3,2))
            text_entry=self.entry(col,slot_text)
            text_entry.pack(fill='x',pady=(3,3))
            self.custom_entries.append(text_entry)
        self.separator_entries=[]
        validate=(self.register(lambda value:len(value)<=3),'%P')
        for i,var in enumerate(self.separators):
            entry=tk.Entry(slots_box,textvariable=var,width=4,justify='center',
                           bg=WHITE,fg=DARK,relief='sunken',bd=2,
                           highlightthickness=0,validate='key',validatecommand=validate)
            entry.grid(row=1,column=i*2+1,padx=1,pady=(5,7),sticky='ew')
            self.separator_entries.append(entry)
        extra=tk.Frame(self.name_panel,bg=FACE)
        extra.pack(fill='x',pady=(8,6))
        extra.grid_columnconfigure(0,weight=1)
        extra.grid_columnconfigure(1,weight=1)
        self.labeled(extra,'Start index at',self.entry(extra,self.start_number),0,0)
        self.labeled(extra,'Index format',self.choose(extra,self.padding,['1','01','001']),0,1)
        self.label(self.name_panel,'Example filename',small=True).pack(anchor='w',pady=(1,3))
        self.example_label=tk.Label(self.name_panel,textvariable=self.name_example,
                                    bg=FACE,fg=DARK,anchor='center',justify='center',
                                    font=('Geneva',11,'bold'))
        self.example_label.pack(fill='x',pady=(4,10))
        self._update_name_layout()

    def _update_name_layout(self):
        """Only change visibility; avoid destroy/rebuild flicker and focus loss."""
        for i,(kind,_) in enumerate(self.slots):
            widget=self.custom_entries[i]
            if kind.get()=='Custom text':
                if not widget.winfo_manager():widget.pack(fill='x',pady=(3,3))
            else:
                if widget.winfo_manager():widget.pack_forget()
        for i,widget in enumerate(self.separator_entries):
            a=self.slots[i][0].get()
            b=self.slots[i+1][0].get()
            if a=='None' and b=='None':
                widget.grid_remove()
            else:
                widget.grid()

    def _example_name(self):
        try:
            example=next((d for d in self.drawings if d.node.key in self.selected),None)
            if example is None:
                frame=core.Node((0,),'Frame 2',None)
                example=core.Drawing(frame,(),frame=frame,label='BG')
            settings=self._settings()
            # Example index is the starting value, not an output file count.
            number=settings.start
            self.name_example.set(core.name_for(example,settings,number)+core.EXT[settings.format])
        except (ValueError,KeyError,TypeError) as exc:
            self.name_example.set('Check filename options: '+str(exc))

    def _update_jpeg_fields(self):
        if not hasattr(self,'jpeg_widgets'):return
        is_jpeg=self.format.get()=='JPEG'
        for widget in self.jpeg_widgets:
            if is_jpeg:widget.grid()
            else:widget.grid_remove()

    def _attach_wheel_tags(self,widget):
        # Recursively add our handler BEFORE widget/class bindings, because
        # Aqua ttk::combobox can consume macOS MouseWheel events itself.
        tags=widget.bindtags()
        if 'FolderExporterWheel' not in tags:
            widget.bindtags(('FolderExporterWheel',)+tags)
        for child in widget.winfo_children():
            # Help windows scroll themselves and must keep their own bindings.
            if isinstance(child,tk.Toplevel):continue
            self._attach_wheel_tags(child)

    def _bind_wheels(self):
        if self.winfo_exists():self._attach_wheel_tags(self)

    def _touchpad_wheel(self,event):
        """Tk 9: decode signed touchpad vertical axis, then route in pixels."""
        raw=int(getattr(event,'delta',0)) & 0xFFFFFFFF
        vertical=raw & 0xFFFF
        if vertical>=0x8000:vertical-=0x10000
        if not vertical:return None
        # macOS native direction differs from the older Tk wheel path.
        sign=-1 if sys.platform=='darwin' else 1
        return self._route_scroll(event,sign*vertical*2.64,pixels=True)

    def _mouse_wheel(self,event):
        if getattr(event,'num',None) in (4,5):
            # One ratchet notch = 2.64px (70% slower than v1.6.1).
            amount=-2.64 if event.num==4 else 2.64
        else:
            delta=int(getattr(event,'delta',0))
            if not delta:return None
            unit=1 if sys.platform=='darwin' else 120
            # Correct inverted scrolling seen on Apple Silicon: on macOS the
            # sign exposed by this Tk build is opposite to the old handler.
            direction=1 if sys.platform=='darwin' else -1
            amount=direction*(delta/unit)*2.64
        return self._route_scroll(event,amount,pixels=True)

    def _route_scroll(self,event,steps,pixels=False):
        try:
            widget=event.widget
            if widget.winfo_toplevel() is not self:return None
            x=getattr(event,'x_root',None)
            y=getattr(event,'y_root',None)
            if x is None or y is None:
                x,y=self.winfo_pointerx(),self.winfo_pointery()
            pane=None
            for frame,side in ((self.right_pane,'right'),(self.left_pane,'left')):
                if (frame.winfo_rootx()<=x<frame.winfo_rootx()+frame.winfo_width()
                    and frame.winfo_rooty()<=y<frame.winfo_rooty()+frame.winfo_height()):
                    pane=side
                    break
            if pane is None:
                ancestor=widget
                while ancestor is not None:
                    if ancestor is self.right_pane:pane='right';break
                    if ancestor is self.left_pane:pane='left';break
                    ancestor=getattr(ancestor,'master',None)
            if pane is None:return None
            view=self.right_canvas if pane=='right' else self.tree
            if pane=='right':
                bounds=view.bbox('all')
                if not bounds or bounds[3]-bounds[1]<=view.winfo_height():return 'break'
            # Retain fractional wheel deltas so small trackpad gestures don't
            # disappear and old ratcheted mouse wheels no longer jump 22px.
            amount=float(steps)
            if pane=='left' and pixels:
                amount/=22.0  # Treeview's unit is a whole row, not a pixel.
            total=self._wheel_remainder[pane]+amount
            integral=int(total)
            self._wheel_remainder[pane]=total-integral
            if integral:
                view.yview_scroll(integral,'units')
            return 'break'
        except (tk.TclError,AttributeError):return None

    def _schedule_discover(self):
        if self._loading_rules or self._restoring:return
        if self._rule_job is not None:self.after_cancel(self._rule_job)
        self._rule_job=self.after(240,self._discover)
        self._schedule_preferences()

    def _crop_rule_changed(self):
        """Checkmarks are immediate; never export with a stale crop choice."""
        if self._loading_rules or self._restoring:return
        if self._rule_job is not None:
            self.after_cancel(self._rule_job)
            self._rule_job=None
        self._discover()
        self._schedule_preferences()

    def _add_rule(self,pattern='',label='',crop=False):
        row=tk.Frame(self.rules_list,bg=FACE)
        row.pack(fill='x',pady=2)
        row.grid_columnconfigure(0,weight=2)
        row.grid_columnconfigure(1,weight=2)
        row.grid_columnconfigure(2,minsize=52)
        row.grid_columnconfigure(3,minsize=70)
        pattern_var=tk.StringVar(value=pattern)
        label_var=tk.StringVar(value=label)
        crop_var=tk.BooleanVar(value=crop)
        self.entry(row,pattern_var).grid(row=0,column=0,sticky='ew',padx=(0,4))
        self.entry(row,label_var).grid(row=0,column=1,sticky='ew',padx=(0,4))
        crop_check=self.check(row,'',crop_var)
        crop_check.grid(row=0,column=2,sticky='',padx=0)
        btn(row,'×',lambda:self._remove_rule(row)).grid(row=0,column=3)
        for var in (pattern_var,label_var):
            var.trace_add('write',lambda *_:self._schedule_discover())
        crop_var.trace_add('write',lambda *_:self._crop_rule_changed())
        self.rule_rows.append((row,pattern_var,label_var,crop_var,crop_check))
        self._update_crop_fields()
        self.after_idle(lambda row=row: self._attach_wheel_tags(row) if row.winfo_exists() else None)
        self._schedule_discover()

    def _remove_rule(self,row):
        self.rule_rows=[item for item in self.rule_rows if item[0] is not row]
        row.destroy()
        self._schedule_discover()

    def _component_rules(self):
        return [core.ComponentRule(pattern.get().strip(),label.get(),crop.get())
                for _,pattern,label,crop,_ in self.rule_rows if pattern.get().strip()]

    def _update_crop_fields(self):
        if not hasattr(self,'crop_scope_picker'):return
        enabled=self.crop.get()
        some=enabled and self.crop_scope.get()=='Some components'
        if enabled:
            if not self.crop_scope_picker.winfo_manager():
                self.crop_scope_picker.pack(side='left',padx=(12,0))
        else:
            self.crop_scope_picker.pack_forget()
        if hasattr(self,'crop_header'):
            if some:self.crop_header.grid()
            else:self.crop_header.grid_remove()
        for _,_,_,_,widget in self.rule_rows:
            if some:widget.grid()
            else:widget.grid_remove()

    def _settings_dir(self):
        if sys.platform=='darwin':
            return Path.home()/'Library'/'Application Support'/'FolderExporter'
        return Path.home()/'.folderexporter'

    def _preferences_path(self):
        return self._settings_dir()/'last-used.json'

    def _prefs_dict(self):
        return {
            'version':5, 'ignore':self.ignore.get(), 'separate':self.separate.get(),
            'dest':self.dest.get(), 'format':self.format.get(),
            'scale':self.scale.get(), 'quality':self.quality.get(),
            'crop':self.crop.get(), 'crop_scope':self.crop_scope.get(), 'white':self.white.get(), 'jpeg':self.jpeg.get(),
            'start_number':self.start_number.get(),
            'padding':self.padding.get(), 'reverse':self.reverse.get(),
            'reset':self.reset.get(), 'component_mode':self.component_mode.get(),
            'component_stack_order':self.component_stack_order.get(),'storyboard_enabled':self.storyboards.enabled.get(),
            'naming_mode':self.storyboards.naming_mode.get(),'frame_folders':self.frame_folders.get(),
            'export_index':self.export_index.get(),'chapter_style':self.storyboards.chapter_style.get(),
            'card_number_mode':self.storyboards.number_mode.get(),
            'slots':[{'kind':kind.get(),'text':text.get()}
                     for kind,text in self.slots],
            'separators':[var.get() for var in self.separators],
            'rules':[{'pattern':r.pattern,'label':r.label,'crop':r.crop}
                     for r in self._component_rules()]
        }

    def _load_preferences(self):
        path=self._preferences_path()
        if not path.is_file():return
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            version=data.get('version')
            if version not in (2,3,4,5):raise ValueError('Invalid preferences version.')
            simple={'ignore':self.ignore,'separate':self.separate,'dest':self.dest,
                    'format':self.format,'scale':self.scale,'quality':self.quality,
                    'crop':self.crop,'crop_scope':self.crop_scope,'white':self.white,'jpeg':self.jpeg,
                    'start_number':self.start_number,'padding':self.padding,
                    'reverse':self.reverse,'reset':self.reset,
                    'component_mode':self.component_mode,'component_stack_order':self.component_stack_order,
                    'storyboard_enabled':self.storyboards.enabled,'naming_mode':self.storyboards.naming_mode,
                    'frame_folders':self.frame_folders,'export_index':self.export_index,
                    'chapter_style':self.storyboards.chapter_style,'card_number_mode':self.storyboards.number_mode}
            for name,var in simple.items():
                if name in data:
                    value=data[name]
                    if isinstance(var,tk.BooleanVar):value=bool(value)
                    else:value=str(value)
                    var.set(value)
            # Migrate the removed nesting option into a direct destination.
            # Existing exports stay in the same folder, with no hidden toggle.
            if version in (2,3,4) and data.get('use_project_folder') and str(data.get('project_folder_name','')).strip() and self.dest.get().strip():
                self.dest.set(str(Path(self.dest.get())/core.safe_name(data['project_folder_name'])))
            old_slots=data.get('slots',[])
            if version==2 and (len(old_slots)>=3 and
                   old_slots[0].get('kind')=='Index' and
                   old_slots[1].get('kind')=='Custom text' and
                   old_slots[2].get('kind')=='Component' and
                   old_slots[1].get('only_if_component')):
                # Convert the common v1.4 layout into the same v1.5 filename:
                # Index + inter-slot separator + Component.
                self.slots[0][0].set('Index')
                self.slots[1][0].set('Component')
                self.slots[2][0].set('None')
                self.slots[3][0].set('None')
                self.separators[0].set(str(old_slots[1].get('text',''))[:3])
            else:
                for i,slot in enumerate(old_slots[:4]):
                    if not isinstance(slot,dict):continue
                    kind,text=self.slots[i]
                    value=str(slot.get('kind','None'))
                    if value=='Project name':
                        value='Custom text'
                        text.set(str(data.get('project_name',''))[:500])
                    elif value in core.SLOT_TYPES:
                        text.set(str(slot.get('text',''))[:500])
                    if value in core.SLOT_TYPES:kind.set(value)
                for i,value in enumerate(data.get('separators',[])[:3]):
                    self.separators[i].set(str(value)[:3])
            self._saved_rules=data.get('rules',[])
        except (ValueError,TypeError,OSError,KeyError,IndexError,AttributeError) as exc:
            self._saved_rules=[]
            print(f'Could not load preferences: {exc}',file=sys.stderr)

    def _schedule_preferences(self):
        if self._restoring or self._loading_rules:return
        if self._save_job is not None:self.after_cancel(self._save_job)
        self._save_job=self.after(600,self._write_preferences)

    def _write_preferences(self):
        if self._restoring:return
        if self._save_job is not None:
            self.after_cancel(self._save_job)
            self._save_job=None
        try:
            path=self._preferences_path()
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self._prefs_dict(),ensure_ascii=False,indent=2),encoding='utf-8')
            tmp.replace(path)
            self.storyboards.save_binding()
        except OSError as exc:
            self.status.set(f'Could not save preferences: {exc}')

    def _project_rules_path(self,project:Path) -> Path:
        # Hash the *path*, not the artwork. No source file is modified.
        key=hashlib.sha256(str(project.expanduser().resolve()).encode('utf-8')).hexdigest()[:24]
        return self._settings_dir()/'Projects'/f'{key}.json'

    def _save_rules(self):
        if self.source is None:
            messagebox.showwarning('No project','Open a PSD before saving project-specific rules.')
            return
        path=self._project_rules_path(self.source)
        data={'version':1,'organizers':self.ignore.get(),
              'rules':[{'pattern':r.pattern,'label':r.label,'crop':r.crop}
                       for r in self._component_rules()]}
        try:
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(path)
            self.status.set('Project rules saved locally. The PSD was not modified.')
        except OSError as exc:messagebox.showerror('Could not save project rules',str(exc))

    def _load_rules(self,source:Path):
        path=self._project_rules_path(source)
        if not path.exists():return
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            if data.get('version')!=1:raise ValueError('Unsupported project rules version.')
            rows=data.get('rules',[])
            if not isinstance(rows,list) or len(rows)>500:raise ValueError('Invalid rules file.')
            self._loading_rules=True
            for row,*_ in self.rule_rows:row.destroy()
            self.rule_rows=[]
            for rule in rows:
                self._add_rule(str(rule['pattern']),str(rule['label']),bool(rule.get('crop',False)))
            self.ignore.set(str(data.get('organizers','')))
        except (OSError,ValueError,KeyError,TypeError) as exc:
            messagebox.showwarning('Project rules could not be loaded',str(exc))
        finally:self._loading_rules=False

    def _on_structure_change(self):
        if self._restoring or self._loading_rules:return
        self._discover()
        self._schedule_preferences()

    def _filename_changed(self):
        if self._restoring:return
        if self.storyboards.enabled.get() and self.storyboards.naming_mode.get()==studio.PROJECT_NAMES:
            self.storyboards.naming_mode.set(studio.CUSTOM_NAMES)
        self._refresh_settings()

    def _refresh_settings(self):
        if self._restoring:return
        kinds=tuple(var.get() for var,_ in self.slots)
        if kinds!=getattr(self,'_shown_slot_kinds',None):
            self._shown_slot_kinds=kinds
            self._update_name_layout()
        self._update_jpeg_fields()
        self._update_crop_fields()
        self.storyboards.sync()
        self._preview()
        self._schedule_preferences()

    def _choose(self):
        p=filedialog.askopenfilename(title='Choose Project',filetypes=[
             ('PSD, PSB and CLIP','*.psd *.psb *.clip'),('Photoshop','*.psd *.psb'),
             ('Clip Studio (experimental)','*.clip'),('All files','*.*')])
        if p:self._open(Path(p))

    def _open(self,p):
        if self.busy:return
        if not p.is_file() or p.suffix.lower() not in ('.psd','.psb','.clip'):
            messagebox.showerror('File error','Choose a valid PSD, PSB or CLIP project.')
            return
        self.busy=True
        self.open_btn.configure(state='disabled')
        self.status.set('Reading project without modifying it...')
        def work():
            try:
                doc=core.open_project(p)
                nodes=core.folder_tree(doc,core.is_clip(p))
                self.events.put(('opened',(p,doc,nodes)))
            except Exception as exc:self.events.put(('load_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def _discover(self):
        if not self.nodes:return
        old=self.selected.copy()
        was_all=bool(self.drawings) and old=={x.node.key for x in self.drawings}
        self.drawings=core.discover(self.nodes,self.ignore.get(),self.separate.get(),self._component_rules(),self.component_mode.get())
        keys={x.node.key for x in self.drawings}
        self.selected=keys if (not getattr(self,'discovery_initialized',False) or was_all) else (old & keys)
        self.discovery_initialized=True
        self.storyboards.sync()
        self._fill_tree()

    def _fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        words=core.keywords(self.ignore.get())
        exportable={d.node.key:d for d in self.drawings}
        components={}
        for drawing in self.drawings:
            if drawing.frame is not None and drawing.node.key != drawing.frame.key:
                components.setdefault(drawing.frame_key,[]).append(drawing)
        self.tree.tag_configure('internal',foreground=GREY)
        self.tree.tag_configure('clipped',foreground='#555555')
        def add(nodes,parent='',frame=None):
            for node in nodes:
                organizer=(frame is None and bool(words) and
                           any(w in node.name.casefold() for w in words))
                if organizer:
                    marker='[+] '
                    suffix=' (organizer)'
                    tag=()
                    next_frame=None
                    expand=True
                elif frame is None:
                    owns=components.get(node.key,[])
                    marker='[+] ' if owns else ('[x] ' if node.key in self.selected else '[ ] ')
                    suffix=f' ({len(owns)} components)' if owns else ''
                    tag=()
                    next_frame=node
                    expand=bool(owns)
                elif node.key in exportable:
                    drawing=exportable[node.key]
                    marker='[x] ' if node.key in self.selected else '[ ] '
                    suffix=f' -> {drawing.label}' if drawing.label else ''
                    tag=()
                    next_frame=frame
                    expand=False
                else:
                    marker='    '
                    suffix=' (internal; not exported separately)'
                    tag=('internal',)
                    next_frame=frame
                    expand=False
                if not node.visible:suffix+=' (hidden)'
                item='/'.join(map(str,node.key))
                # Clipped layers sit ABOVE their clipping base in PSD order.
                # They are informational rows: no checkboxes or independent
                # export, and the arrow points down to the folder below.
                for i,layer in enumerate(node.clipped_layers):
                    layer_name=layer.name + (' (hidden)' if not layer.visible else '')
                    self.tree.insert(parent,'end',iid=f'clipped:{item}:{i}',
                                     text=f'  ↓ {layer_name} (Clipped Layer)',
                                     tags=('clipped',))
                self.tree.insert(parent,'end',iid=item,text=marker+node.name+suffix,
                                 open=expand,tags=tag)
                if organizer:
                    add(node.children,item,None)
                else:
                    add(node.children,item,next_frame)
        add(self.nodes)
        self.count.set(f'{len(self.selected)} of {len(self.drawings)} exports selected')
        self._preview()

    def _toggle(self,item):
        if self.busy or item.startswith('clipped:'):return
        key=tuple(map(int,item.split('/')))
        eligible={d.node.key for d in self.drawings if d.node.key==key or d.node.key[:len(key)]==key}
        if eligible:
            if eligible<=self.selected:self.selected-=eligible
            else:self.selected|=eligible
            self._fill_tree()

    def _click(self,event):
        item=self.tree.identify_row(event.y)
        if item and self.tree.identify('element',event.x,event.y)!='Treeitem.indicator':
            self._toggle(item)

    def _space(self,event):
        rows=self.tree.selection()
        if rows:self._toggle(rows[0])
        return 'break'

    def _select_all(self,yes):
        if self.busy:return
        self.selected={d.node.key for d in self.drawings} if yes else set()
        self._fill_tree()

    def _browse(self):
        folder=filedialog.askdirectory(title='Choose Export Folder',initialdir=self.dest.get() or str(Path.home()))
        if folder:self.dest.set(folder)

    def _settings(self):
        return core.Settings(
            format=self.format.get(),scale=int(self.scale.get()),
            quality=int(self.quality.get()) if self.format.get()=='JPEG' else 100,
            crop=self.crop.get(),crop_scope=self.crop_scope.get(),white=self.white.get(),jpeg_bg=self.jpeg.get(),
            slots=tuple(core.NameSlot(kind.get(),text.get())
                        for kind,text in self.slots),
            separators=tuple(var.get() for var in self.separators),
            component_mode=self.component_mode.get(),
            start=int(self.start_number.get()),padding=len(self.padding.get()),
            reverse=self.reverse.get(),reset=self.reset.get(),separate=self.separate.get(),
            component_stack_order=self.component_stack_order.get(),
            frame_folders=self.frame_folders.get() if self.storyboards.enabled.get() else False)

    def _tasks(self):
        return self._export_plan().tasks

    def _export_plan(self):
        if not self.dest.get().strip():raise ValueError('Choose an export destination.')
        bridge=self.storyboards
        if bridge.enabled.get() and bridge.directory and bridge.workspace is None:raise ValueError(bridge.problem or 'Reconnect the project folder before exporting.')
        return sb.make_plan(self.drawings,self.selected,Path(self.dest.get()),self._settings(),
            reference=bridge.reference if bridge.enabled.get() else None,overrides=bridge.overrides,
            chapter_style=bridge.chapter_style.get() if bridge.enabled.get() else sb.CHAPTER_STYLES[0],number_mode=bridge.number_mode.get(),workspace=bridge.workspace if bridge.enabled.get() else None,naming_mode=bridge.naming_mode.get() if bridge.enabled.get() else studio.CUSTOM_NAMES)

    def _preview(self):
        self._example_name()
        if not self.source:
            self.preview_text.set('Choose a file to preview exports.')
            return
        try:
            bundle=self._export_plan();tasks=bundle.tasks
            root=Path(self.dest.get()).expanduser().resolve()
            names=[str(dest.relative_to(root)) for _,dest in tasks[:5]]
            if tasks:
                # Use the planned filename, not the pre-selection component
                # index, so the example reflects per-label counting exactly.
                self.name_example.set(tasks[0][1].name)
            if len(tasks)>5:names.append(f'... and {len(tasks)-5} more')
            self.preview_text.set('\n'.join(names) if names else 'No drawing folders selected.')
        except Exception as exc:self.preview_text.set(f'Check settings: {exc}')

    def _export(self):
        if self.busy:
            self.cancel.set()
            self.status.set('Cancellation requested...')
            return
        try:
            if not self.source:raise ValueError('Choose a source file first.')
            if self.storyboards.enabled.get() and self.storyboards.directory:self.storyboards.refresh(for_export=True)
            if not self.storyboards.resolve_unmatched():return
            s=self._settings()
            bundle=self._export_plan();tasks=bundle.tasks
            if not tasks:raise ValueError('Select at least one drawing folder.')
            drift=sb.binding_drift(bundle,self.storyboards.overrides) if bundle.reference else []
            if drift:
                answer=messagebox.askyesnocancel('Card numbering changed','Known drawing connections were retained after renumbering:\n'+ '\n'.join(f'{name} → Card {label}' for _,name,label in drift[:8])+'\n\nYes: keep these permanent card connections.\nNo: match these folders using their current names.\nCancel: export nothing.')
                if answer is None:return
                if not answer:
                    for key,_,_ in drift:self.storyboards.overrides['frames'].pop(key,None)
                    bundle=self._export_plan();tasks=bundle.tasks

            dest=bundle.root
            include_index=self.storyboards.enabled.get() and self.export_index.get()
            if bundle.reference and not include_index:raise ValueError('Storyboard links require the image index. Enable Create image index.')
            if dest.exists() and not dest.is_dir():raise ValueError('Destination must be a directory.')
            conflicting=media_catalog.conflicts(bundle,self.source)
            if conflicting:
                answer=messagebox.askyesnocancel('Existing cleanup connections',f'{len(conflicting)} card(s) already have a cleanup from another source or a manual attachment.\nYes: replace those cleanups.\nNo: keep the existing cleanups and export the other cards.\nCancel: export nothing.')
                if answer is None:return
                if not answer:
                    bundle.tasks=[task for task in bundle.tasks if sb.frame_key(task[0]) not in conflicting];tasks=bundle.tasks
                    if not tasks:self.status.set('Existing cleanups kept. Nothing to export.');return
                    selected_keys={sb.frame_key(d) for d,_ in tasks};bundle.links={k:v for k,v in bundle.links.items() if k in selected_keys}

        except Exception as exc:
            messagebox.showwarning('Check settings',str(exc))
            return
        self.busy=True
        self.storyboards.sync()
        self.cancel.clear()
        self.export_button.configure(text='Cancel Export')
        self.open_btn.configure(state='disabled')
        self.progress.set(0)
        self.status.set(f'Exporting {len(tasks)} drawings...')
        source=self.source
        def work():
            try:
                # Source is reopened read-only inside the export thread.
                with media_catalog.workflow_lock(bundle.workspace):
                    if bundle.workspace:studio.validate_output_root(bundle.workspace)
                    doc=core.open_project(source)
                    records=[]
                    made,failures,cancelled=core.export(doc,core.is_clip(source),tasks,s,
                        progress=lambda i,n,name,error:self.events.put(('progress',(i,n,name,error))),cancel=self.cancel,
                        on_saved=lambda drawing,path,size:records.append((drawing,path,size)),output_root=bundle.root if bundle.workspace else None,output_writer=sb.linked_image_writer(bundle,source))
                    index_path=None;index_error=None
                    if include_index and records:
                        try:index_path=sb.write_plan_index(bundle,sb.inventory(bundle,s,source,core.dimension(doc),records,failures,cancelled))
                        except Exception as exc:index_error=str(exc)
                self.events.put(('finished',(made,failures,cancelled,dest,index_path,index_error,bundle)))
            except Exception as exc:self.events.put(('export_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def _events(self):
        try:
            while True:
                kind,payload=self.events.get_nowait()
                if kind=='opened':
                    previous_source=self.source
                    self.source,self.project,self.nodes=payload
                    self.file_label.set(self.source.name)
                    if not self.dest.get().strip():
                        self.dest.set(str(self.source.parent/'FolderExporter Exports'))
                    self.discovery_initialized=False
                    self.selected=set()
                    self._load_rules(self.source)
                    self.storyboards.source_opened(previous_source)
                    self._discover()
                    self._schedule_preferences()
                    self.status.set(f'{self.source.name}  •  {self.project.width} × {self.project.height} px')
                    self.busy=False
                    self.open_btn.configure(state='normal')
                elif kind=='load_error':
                    self.busy=False
                    self.open_btn.configure(state='normal')
                    self.status.set('Unable to read project.')
                    messagebox.showerror('Open error',payload)
                elif kind=='progress':
                    i,n,name,error=payload
                    self.progress.set(100*i/n)
                    self.status.set(f'{i}/{n}  {name}'+(f' — {error}' if error else ''))
                elif kind=='finished':
                    made,failed,cancelled,dest,index_path,index_error,bundle=payload
                    self._end_export()
                    if made:self.storyboards.remember_links(bundle)
                    self.status.set(f'{len(made)} images exported, {len(failed)} failed.')
                    summary=f'Exported: {len(made)}\nFailed: {len(failed)}\nDestination: {dest}'
                    if index_path:summary+=f'\nImage index: {index_path.name}'
                    if index_error:summary+=f'\n\nImages were kept, but the image index could not be saved: {index_error}'
                    if cancelled:summary='Cancelled.\n'+summary
                    if failed:summary+='\n\n'+'\n'.join(f'{name}: {err}' for name,err in failed[:8])
                    messagebox.showinfo('Export Results',summary)
                    self._preview()
                elif kind=='export_error':
                    self._end_export()
                    self.status.set('Export failed.')
                    messagebox.showerror('Export error',payload)
        except queue.Empty:pass
        if self.winfo_exists():
            self._event_job=self.after(120,self._events)

    def _end_export(self):
        self.busy=False
        self.export_button.configure(text='Export All')
        self.open_btn.configure(state='normal')
        self.storyboards.sync()

    def _close(self):
        if self.busy:
            self.cancel.set()
            messagebox.showwarning('Operation in progress','The active operation must finish before closing.')
            return
        self._write_preferences()
        self.destroy()

    def destroy(self):
        # Stop root-owned background callbacks before destroying Tk widgets.
        for job in (self._event_job,self._save_job,self._rule_job):
            if job is not None:
                try:self.after_cancel(job)
                except tk.TclError:pass
        self._event_job=self._save_job=self._rule_job=None
        job=getattr(getattr(self,'storyboards',None),'refresh_job',None)
        if job is not None:
            try:self.after_cancel(job)
            except tk.TclError:pass
        super().destroy()


if __name__=='__main__':
    Application().mainloop()
