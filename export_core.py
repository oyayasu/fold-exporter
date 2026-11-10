"""Read-only PSD/PSB and conservative CLIP batch rendering. All output is new files."""
from __future__ import annotations
import re
import uuid
from pathlib import Path
from dataclasses import dataclass, field, replace
from collections import Counter, defaultdict
from typing import Any
from PIL import Image


@dataclass(frozen=True)
class ClippedLayer:
    """Informational row: an attached PSD layer, never an export target."""
    name: str
    visible: bool = True


@dataclass
class Node:
    key: tuple[int, ...]
    name: str
    ref: Any
    visible: bool = True
    children: list['Node'] = field(default_factory=list)
    clipped_layers: tuple[ClippedLayer, ...] = ()

@dataclass(frozen=True)
class ComponentRule:
    """Per-project filename pattern and label. '*' captures arbitrary text."""
    pattern: str
    label: str
    crop: bool = False

@dataclass
class Drawing:
    node: Node
    chapter: tuple[str, ...]
    frame: Node | None = None
    label: str = ''
    excluded: tuple[tuple[int, ...], ...] = ()
    component_index: int = 0
    component_crop: bool = False
    source_chapter: tuple[str, ...] | None = None
    stack_order: int = 0
    label_index: int = 0
    frame_index: int = 0
    storyboard_number: int = 0

    @property
    def frame_key(self):
        return (self.frame or self.node).key

    @property
    def is_component(self) -> bool:
        return self.frame is not None and self.node.key != self.frame.key

@dataclass(frozen=True)
class NameSlot:
    """A single concatenated filename token; no implicit punctuation."""
    kind: str = 'None'
    text: str = ''


SLOT_TYPES = ('None', 'Folder name', 'Chapter', 'Component', 'Index', 'Component index', 'Card number', 'Custom text')
DEFAULT_SLOTS = (
    NameSlot('Index'), NameSlot('Component'),
    NameSlot('None'), NameSlot('None'),
)


@dataclass
class Settings:
    format: str = 'PNG'
    scale: int = 100
    quality: int = 100
    crop: bool = False
    crop_scope: str = 'All'
    white: bool = False
    jpeg_bg: str = 'White'
    slots: tuple[NameSlot, ...] = DEFAULT_SLOTS
    separators: tuple[str, str, str] = ('', '', '')
    component_mode: str = 'Separate components'
    start: int = 1
    padding: int = 3
    reverse: bool = False
    reset: bool = True
    separate: bool = True
    component_stack_order: bool = False
    project_folder: str = ''
    frame_folders: bool = False

COMPONENT_MODES = ('Separate components', 'Separate + whole frame', 'Whole frame only')
CROP_SCOPES = ('All', 'Components only', 'Some components')

EXT = {'PNG': '.png', 'WEBP': '.webp', 'TIFF': '.tif', 'JPEG': '.jpg'}
INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}


def safe_name(name: str) -> str:
    value = INVALID.sub('_', str(name)).strip().rstrip(' .')[:110].rstrip(' .') or 'Untitled'
    return '_' + value if value.upper().split('.')[0] in RESERVED else value


def keywords(raw: str) -> tuple[str, ...]:
    return tuple(x.strip().casefold() for x in re.split(r'[,;\n]+', raw) if x.strip())


def open_project(path: Path):
    """Only input-file reads. Never saves or changes source on disk."""
    path = Path(path)
    if path.suffix.lower() == '.clip':
        import clipparse
        reader = clipparse.ClipFile()
        if not reader.load(str(path)):
            raise ValueError('The CLIP reader could not open this project. Try exporting a PSD.')
        return reader
    if path.suffix.lower() in ('.psd','.psb'):
        from psd_tools import PSDImage
        return PSDImage.open(str(path))
    raise ValueError('Choose a PSD, PSB, or CLIP project.')


def is_clip(path: Path) -> bool:
    return Path(path).suffix.lower() == '.clip'


def dimension(project) -> tuple[int,int]:
    return (int(project.width),int(project.height))


def folder_tree(project, clip: bool) -> list[Node]:
    if clip:
        def walk(parent: int|None, route: tuple[int,...]) -> list[Node]:
            children = project.roots if parent is None else project.children(parent)
            output=[]
            for position in reversed(list(children)):
                layer=project.layers[position]
                if bool(layer.is_group):
                    key=route+(int(position),)
                    # Clipped CLIP layers cannot currently be rendered directly,
                    # but their names can still be shown when attached to a folder.
                    siblings=list(children)
                    try:
                        offset=siblings.index(position)+1
                    except ValueError:
                        offset=len(siblings)
                    attached=[]
                    for sibling_index in siblings[offset:]:
                        other=project.layers[sibling_index]
                        if not bool(getattr(other,'clipping',False)):
                            break
                        attached.append(ClippedLayer(str(other.name),bool(other.visible)))
                    output.append(Node(key,str(layer.name),int(position),bool(layer.visible),
                                       walk(position,key),tuple(reversed(attached))))
            return output
        return walk(None,())
    def walk(container,route: tuple[int,...]):
        output=[]
        for i in reversed(range(len(container))):
            layer=container[i]
            group=getattr(layer,'is_group',None)
            matches=group() if callable(group) else getattr(layer,'kind',None) in ('group','artboard')
            if matches:
                key=route+(i,)
                # psd-tools resolves attached siblings through the clipping base's
                # clip_layers property. Keep them visible in the tree, never in
                # the independent-export folder list.
                attached=tuple(ClippedLayer(str(item.name),bool(getattr(item,'visible',True)))
                               for item in (getattr(layer,'clip_layers',()) or ())
                               if bool(getattr(item,'clipping',True)))
                output.append(Node(key,str(layer.name),layer,bool(getattr(layer,'visible',True)),
                                   walk(layer,key),attached))
        return output
    return walk(project,())


def match_rule(name: str, rule: ComponentRule) -> str | None:
    """Return the first wildcard capture (or empty string) on case-insensitive match."""
    pattern = rule.pattern.strip()
    if not pattern:
        return None
    parts = pattern.split('*')
    regex = '^' + '(.*?)'.join(re.escape(x) for x in parts) + '$'
    matched = re.match(regex, name, re.IGNORECASE | re.DOTALL)
    return matched.group(1) if matched and len(parts) > 1 else ('' if matched else None)


def component_matches(frame: Node, rules: list[ComponentRule]) -> list[tuple[Node, ComponentRule, str]]:
    """Rules are explicit. No fuzzy inference that silently exports extra groups."""
    matches = []
    def walk(nodes):
        for node in nodes:
            for rule in rules:
                suffix = match_rule(node.name, rule)
                if suffix is not None:
                    matches.append((node, rule, suffix))
                    break
            walk(node.children)
    walk(frame.children)
    return matches


def discover(tree:list[Node], ignore:str='chapter, section',separate:bool=True,
             rules: list[ComponentRule] | None = None,
             component_mode: str = 'Separate components') -> list[Drawing]:
    """Organizers are optional. Each immediate non-organizer is a frame.

    With no matching component folders, export that frame whole. If matching
    components exist, export only those; unmatched nested groups remain internal.
    """
    if component_mode not in COMPONENT_MODES:
        raise ValueError('Unknown component export mode.')
    terms=keywords(ignore)
    rules=rules or []
    drawings=[]
    def walk(nodes,chapter):
        for node in nodes:
            if terms and any(term in node.name.casefold() for term in terms):
                walk(node.children, chapter+(node.name,))
                continue
            matches = component_matches(node,rules) if component_mode != 'Whole frame only' else []
            if not matches or component_mode == 'Separate + whole frame':
                drawings.append(Drawing(node,chapter if separate else (),frame=node,source_chapter=chapter))
            if matches:
                # A component index is only meaningful for labels that repeat
                # inside the SAME frame. A solitary "Dog" has no index even
                # when there are three "Food" components alongside it.
                labeled=[]
                for matched,rule,captured in matches:
                    label=rule.label.replace('{match}',captured).replace('{component}',matched.name)
                    if not label.strip():label=matched.name
                    labeled.append((matched,rule,label))
                totals=Counter(safe_name(label).casefold() for _,_,label in labeled)
                next_index=defaultdict(int)
                bottom_order={}
                matched_keys={n.key for n,_,_ in matches}
                def bottom_up(nodes):
                    for child in reversed(nodes):
                        if child.key in matched_keys:bottom_order[child.key]=len(bottom_order)+1
                        bottom_up(child.children)
                bottom_up(node.children)
                for matched,rule,label in labeled:
                    key=safe_name(label).casefold()
                    if totals[key]>1:
                        next_index[key]+=1
                        component_number=next_index[key]
                    else:
                        component_number=0
                    # A separate nested component must not be included in its parent.
                    excluded = tuple(n.key for n,_,_ in matches if n.key != matched.key
                                     and n.key[:len(matched.key)] == matched.key)
                    drawings.append(Drawing(matched,chapter if separate else (),frame=node,label=label,
                                            excluded=excluded,component_index=component_number,
                                            component_crop=rule.crop,source_chapter=chapter,
                                            stack_order=bottom_order[matched.key],label_index=component_number))
    walk(tree,())
    return drawings


def _index(num: int, width: int) -> str:
    if width not in (1, 2, 3):
        raise ValueError('Choose a number format: 1, 01, or 001.')
    return str(num).zfill(width)


def name_for(d: Drawing, settings: Settings, num: int) -> str:
    """Join four slots using only the user's three editable separators.

    Each separator is active only if BOTH adjacent slots have a value. An
    empty component therefore never leaves a dangling separator. Literal
    custom-text slots are never modified by the engine.
    """
    if len(settings.slots) != 4 or len(settings.separators) != 3:
        raise ValueError('Filename needs four slots and three separators.')
    if any(len(separator) > 3 for separator in settings.separators):
        raise ValueError('Each separator must contain at most three characters.')
    number = _index(num, settings.padding)
    values = {
        'Folder name': (d.frame or d.node).name,
        'Component': d.label,
        'Chapter': d.chapter[-1] if d.chapter else '',
        'Index': number,
        'Component index': _index(d.component_index, settings.padding) if d.component_index else '',
        'Card number': _index(d.storyboard_number, settings.padding) if d.storyboard_number else '',
    }
    pieces = []
    for slot in settings.slots:
        if slot.kind not in SLOT_TYPES:
            raise ValueError(f'Unknown filename slot: {slot.kind}')
        pieces.append(slot.text if slot.kind == 'Custom text' else values.get(slot.kind, ''))
    # Each connector belongs to the slot on its RIGHT. If a component or
    # chapter value is missing, skip that slot AND its preceding connector,
    # but retain the connector immediately before the next populated slot.
    # Example: Index / Component / Folder with connectors " - " and "_":
    #   a component -> 001 - BG_Frame 2
    #   no component -> 001_Frame 2
    # Never emit a connector before the first nonempty value.
    result = ''
    for index, piece in enumerate(pieces):
        if not piece:
            continue
        if result and index:
            result += settings.separators[index-1]
        result += piece
    return safe_name(result)


def plan(drawings:list[Drawing],selected:set[tuple[int,...]],destination:Path,s:Settings,*,name_builder=None,preserve_chapter_paths=False,reuse_existing=False):
    if s.padding not in (1,2,3) or not 0<=s.start<=999999999 or not 10<=s.scale<=400 or not 1<=s.quality<=100:
        raise ValueError('Check starting number, number format, image scale and quality.')
    if s.format not in EXT:raise ValueError('Unsupported image format')
    base=Path(destination)
    if s.project_folder.strip():base=base/safe_name(s.project_folder)
    seen=set()
    chosen=[d for d in drawings if d.node.key in selected]
    # Number per label among components actually being exported. If only one
    # Food remains selected, it does not acquire an unnecessary ".1".
    totals=Counter((d.frame_key,safe_name(d.label).casefold()) for d in chosen if d.is_component)
    next_index=defaultdict(int)
    component_stacks=defaultdict(list)
    for d in chosen:
        if d.is_component:component_stacks[d.frame_key].append(d)
    stack_numbers={}
    for key,components in component_stacks.items():
        for index,d in enumerate(sorted(components,key=lambda d:(d.stack_order or 10**9,d.node.key)),1):
            stack_numbers[d.node.key]=index
    normalized=[]
    for d in chosen:
        if d.is_component:
            key=(d.frame_key,safe_name(d.label).casefold())
            if totals[key]>1:
                next_index[key]+=1
                d=replace(d,component_index=next_index[key],label_index=next_index[key])
            else:
                d=replace(d,component_index=0,label_index=0)
            d=replace(d,stack_order=stack_numbers[d.node.key],component_index=stack_numbers[d.node.key] if s.component_stack_order else d.component_index)
        normalized.append(d)
    chosen=normalized
    # All components of a frame share one ordinal, even if other frames have no
    # matching components or the export order is reversed.
    frames_by_bucket={}
    for d in chosen:
        bucket=d.chapter if s.reset and s.separate else ()
        frames_by_bucket.setdefault(bucket,[])
        if d.frame_key not in frames_by_bucket[bucket]:
            frames_by_bucket[bucket].append(d.frame_key)
    counters={}
    for bucket,frames in frames_by_bucket.items():
        total=len(frames)
        counters.update(((bucket,key),(total-i if s.reverse else i+1)+s.start-1)
                        for i,key in enumerate(frames))
    output=[]
    for drawing in chosen:
        chapter=drawing.chapter if s.separate else ()
        bucket=chapter if s.reset else ()
        ordinal=counters[bucket,drawing.frame_key]
        drawing=replace(drawing,frame_index=ordinal)
        folder=base
        for level in chapter:
            if preserve_chapter_paths:
                if not isinstance(level,str) or level in ('','.','..') or INVALID.search(level):raise ValueError('Invalid shared chapter path.')
                folder=folder/level
            else:folder=folder/safe_name(level)
        if s.frame_folders:folder=folder/safe_name(f'{_index(ordinal,s.padding)} - {(drawing.frame or drawing.node).name}')
        stem=name_builder(drawing,s,ordinal) if name_builder else name_for(drawing,s,ordinal)
        n=1
        while True:
            suffix='' if n==1 else f' - {n}'
            target=folder/f'{stem}{suffix}{EXT[s.format]}'
            key=str(target).casefold()
            if key not in seen and (reuse_existing or not target.exists()):break
            n+=1
        seen.add(key)
        output.append((drawing,target))
    return output


def _clip_render(reader, index:int, width:int,height:int)->Image.Image:
    def compose(which:int, force_visible:bool=False)->Image.Image:
        layer=reader.layers[which]
        image=Image.new('RGBA',(width,height),(0,0,0,0))
        try:
            if not force_visible and not layer.visible: return image
            if bool(getattr(layer,'is_filter',False)) or bool(getattr(layer,'clipping',False)):
                raise ValueError('This CLIP folder uses adjustments/clipping. Export to PSD first.')
            if layer.is_group:
                if bool(getattr(layer,'has_mask',False)) or int(getattr(layer,'composite_raw',0)) not in (0,30):
                    raise ValueError('Unsupported CLIP folder mask or blending. Export to PSD first.')
                for child in reader.children(which):
                    piece=compose(child)
                    try: image.alpha_composite(piece)
                    finally: piece.close()
            else:
                if int(getattr(layer,'composite_raw',0)) != 0:
                    raise ValueError('Unsupported CLIP layer blend mode. Export to PSD first.')
                w,h=int(layer.width),int(layer.height)
                if w<=0 or h<=0: raise ValueError('Non-raster CLIP layer. Export to PSD first.')
                data=reader.layer_image(which,'masked')
                if len(data)!=w*h*4: raise ValueError('CLIP pixels unavailable. Export to PSD first.')
                piece=Image.frombytes('RGBA',(w,h),data,'raw','BGRA')
                try: image.paste(piece,(int(layer.left),int(layer.top)))
                finally: piece.close()
            op=max(0,min(255,int(getattr(layer,'opacity',255))))
            if op!=255:
                a=image.getchannel('A').point(lambda x: (x*op+127)//255)
                try: image.putalpha(a)
                finally: a.close()
            return image
        except BaseException:
            image.close()
            raise
    return compose(index,True)


def render(project, drawing:Drawing, clip:bool, settings:Settings) -> Image.Image:
    w,h=dimension(project)
    if clip: image=_clip_render(project,int(drawing.node.ref),w,h)
    else:
        # psd-tools' default layer_filter uses is_visible(), which inherits
        # visibility from hidden parent groups. Force only the selected branch
        # into view, while keeping deliberately hidden INSIDE layers hidden.
        # Render from the whole PSD to retain loose sibling layers clipped to
        # the selected component folder (and never unrelated/unclipped siblings).
        branch=[]
        parent=project
        for idx in drawing.node.key:
            parent=parent[idx]
            branch.append(parent)
        branch_ids={id(layer) for layer in branch}
        target=branch[-1]
        excluded=set(drawing.excluded)
        clip_siblings=tuple(getattr(target,'clip_layers',()) or ())
        clip_ids={id(layer) for layer in clip_siblings}
        clip_child_roots={id(layer) for layer in clip_siblings}

        def include(layer):
            # Ancestors of the target are the only other folders composited.
            if id(layer) in branch_ids:return True
            if id(layer) in clip_ids:return bool(getattr(layer,'visible',True))
            # Reject anything except descendants of the selected folder.
            chain=[]
            cursor=layer
            while cursor is not None and cursor is not target:
                chain.append(cursor)
                cursor=getattr(cursor,'parent',None)
                if cursor is project:break
            if cursor is not target:
                # Descendants of an attached clipping group are also allowed.
                cursor=layer
                chain=[]
                while cursor is not None and id(cursor) not in clip_child_roots:
                    chain.append(cursor)
                    cursor=getattr(cursor,'parent',None)
                if cursor is None:return False
                chain.append(cursor)
            # Inner hidden layers stay hidden, regardless of their outer
            # folder's visibility; excludes named child components as needed.
            if any(not bool(getattr(item,'visible',True)) for item in chain):return False
            for item in chain:
                if id(item) in excluded_ids or id(item) in excluded_clip_ids:return False
            return True

        # For nested component exports, exclude other independently exported
        # child components by identity, not name (duplicate names are valid).
        excluded_ids=set()
        excluded_clip_ids=set()
        for route in excluded:
            item=project
            for idx in route:item=item[idx]
            excluded_ids.add(id(item))
            excluded_clip_ids.update(id(c) for c in (getattr(item,'clip_layers',()) or ()))
        # The filter alone is insufficient: PSD group bounding boxes also use
        # inherited visibility. Public visibility setters invalidate those
        # cached boxes. Enable only the target and its ancestor path for this
        # render, then restore it, including on a compositor error. Inner hidden
        # layers retain their flags and the source document is never saved.
        visibility=[(layer,bool(getattr(layer,'visible',True))) for layer in branch]
        try:
            for layer,visible in visibility:
                if not visible:layer.visible=True
            source=project.composite(viewport=(0,0,w,h),force=True,alpha=0.0,
                                     color=1.0,layer_filter=include)
        finally:
            for layer,visible in reversed(visibility):
                if bool(getattr(layer,'visible',True))!=visible:layer.visible=visible
        if source is None:raise ValueError('Could not render drawing folder')
        image=source.convert('RGBA')
        if image is not source:source.close()
    if settings.crop_scope not in CROP_SCOPES:
        image.close()
        raise ValueError('Choose a valid crop scope.')
    should_crop=(settings.crop and (
        settings.crop_scope == 'All' or
        (drawing.is_component and (
            settings.crop_scope == 'Components only' or
            (settings.crop_scope == 'Some components' and drawing.component_crop)
        ))
    ))
    if should_crop:
        bbox=image.getchannel('A').getbbox()
        if bbox:
            updated=image.crop(bbox)
            image.close()
            image=updated
    if settings.scale!=100:
        size=(max(1,round(image.width*settings.scale/100)),max(1,round(image.height*settings.scale/100)))
        updated=image.resize(size,Image.Resampling.LANCZOS)
        image.close()
        image=updated
    if settings.format=='JPEG':
        color=(0,0,0) if settings.jpeg_bg=='Black' else (255,255,255)
        updated=Image.new('RGB',image.size,color)
        updated.paste(image,mask=image.getchannel('A'))
        image.close()
        image=updated
    elif settings.white:
        updated=Image.new('RGBA',image.size,(255,255,255,255))
        updated.alpha_composite(image)
        image.close()
        image=updated
    return image


def export(project,clip:bool,tasks:list,s:Settings,progress=None,cancel=None,on_saved=None,output_root=None,output_writer=None):
    made=[]
    failed=[]
    cancelled=False
    for index,(drawing,initial) in enumerate(tasks,1):
        if cancel is not None and cancel.is_set():
            cancelled=True
            break
        temp=None
        reserved=None
        current_error=''
        try:
            if output_root is None:initial.parent.mkdir(parents=True,exist_ok=True)
            else:
                root=Path(output_root).resolve(strict=True)
                if not root.is_dir():raise ValueError('The project folder is missing. Relink it.')
                relative=initial.parent.relative_to(root);parent=root
                for part in relative.parts:
                    parent=parent/part
                    if parent.exists():
                        if not parent.resolve().is_relative_to(root) or not parent.is_dir():raise ValueError('An output folder points outside this project.')
                    else:parent.mkdir()
                if not initial.parent.resolve().is_relative_to(root):raise ValueError('An output folder points outside this project.')
            image=render(project,drawing,clip,s)
            image_size=image.size
            try:
                temp=initial.parent/f'.folderexporter-{uuid.uuid4().hex}{initial.suffix}'
                kw={}
                if s.format=='JPEG': kw={'quality':s.quality,'subsampling':0}
                if s.format=='WEBP': kw={'quality':s.quality,'method':4}
                if s.format=='TIFF':kw={'compression':'tiff_deflate'}
                image.save(temp,format=s.format,**kw)
            finally:
                image.close()
            destination=initial
            attempt=2
            if output_writer is not None:
                destination=output_writer(drawing,initial,temp)
            while output_writer is None:
                try:
                    with destination.open('xb') as out,temp.open('rb') as inp:
                        reserved=destination
                        while block:=inp.read(1024*1024):out.write(block)
                    break
                except FileExistsError:
                    destination=initial.with_name(f'{initial.stem} - {attempt}{initial.suffix}')
                    attempt+=1
            if on_saved:on_saved(drawing,destination,image_size)
            made.append(destination)
        except Exception as exc:
            if reserved is not None:
                try:reserved.unlink(missing_ok=True)
                except OSError:pass
            current_error=str(exc)
            failed.append((drawing.node.name,current_error))
        finally:
            if temp is not None:
                try:temp.unlink(missing_ok=True)
                except OSError:pass
        if progress: progress(index,len(tasks),drawing.node.name,current_error)
    return made,failed,cancelled
