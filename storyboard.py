"""Optional Storyboard Studio links and a portable inventory of actual exports."""
from __future__ import annotations
import media_catalog
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import unicodedata
import uuid
import hashlib
import export_core as core
import studio_link as studio

CHAPTER_STYLES=('Number + title','Title only','Source folders',studio.PROJECT_FOLDERS)
NUMBER_MODES=('As shown in Storyboard Studio','Chapter numbers','Global numbers')

def _text(value, label):
    if not isinstance(value,str) or not value.strip() or len(value)>2048:
        raise ValueError(f'Invalid {label} in the Storyboard Studio reference.')
    return value

def validate_reference(data):
    if not isinstance(data,dict) or data.get('format')!='storyboardstudio-reference-v1' or data.get('schemaVersion')!=1:
        raise ValueError('Choose a FolderExporter reference saved by Storyboard Studio.')
    project=data.get('project')
    if not isinstance(project,dict):raise ValueError('The reference has no project.')
    for key in ('id','name'):_text(project.get(key),'project '+key)
    chapters=data.get('chapters')
    if not isinstance(chapters,list) or len(chapters)>10000:raise ValueError('Invalid chapter list.')
    chapter_ids=set();card_ids=set();globals_seen=set();numbers=set()
    for ch in chapters:
        if not isinstance(ch,dict):raise ValueError('Invalid chapter.')
        ident=_text(ch.get('id'),'chapter ID');_text(ch.get('title'),'chapter title')
        number=_text(ch.get('number'),'chapter number')
        if ident in chapter_ids or number in numbers or not re.fullmatch(r'\d+(?:\.\d+)?',number):raise ValueError('Duplicate or invalid chapter numbers/IDs.')
        chapter_ids.add(ident);numbers.add(number)
        cards=ch.get('cards');local=set()
        if not isinstance(cards,list) or len(cards)>100000:raise ValueError('Invalid card list.')
        for card in cards:
            if not isinstance(card,dict):raise ValueError('Invalid card.')
            cid=_text(card.get('id'),'card ID')
            if card.get('sourceCardId') is not None:_text(card['sourceCardId'],'source card ID')
            if 'variantIndex' in card and (type(card['variantIndex']) is not int or not 0<=card['variantIndex']<=10000):raise ValueError('Invalid drawing variant index.')
            if card.get('variantAssetId') is not None:_text(card['variantAssetId'],'drawing variant ID')
            if cid in card_ids:raise ValueError('Duplicate card IDs.')
            card_ids.add(cid)
            for field in ('number','globalNumber','displayNumber'):
                if type(card.get(field)) is not int or card[field]<1:raise ValueError('Invalid card numbers.')
            if card['number'] in local or card['globalNumber'] in globals_seen:raise ValueError('Duplicate card numbers.')
            local.add(card['number']);globals_seen.add(card['globalNumber'])
    by_id={c['id']:c for c in chapters}
    for ch in chapters:
        parent=ch.get('parentId')
        if parent and (parent not in by_id or by_id[parent].get('parentId') or parent==ch['id']):
            raise ValueError('Invalid subchapter hierarchy.')
    return data

def read_reference(path):
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('The reference exceeds 16 MB.')
    try:return validate_reference(json.loads(path.read_text(encoding='utf-8-sig')))
    except (UnicodeError,json.JSONDecodeError) as exc:raise ValueError('The reference is not valid JSON.') from exc

def source_chapter(d):return d.source_chapter if d.source_chapter is not None else d.chapter
def chapter_key(path):return json.dumps(path,ensure_ascii=False,separators=(',',':'))
def frame_key(d):return '/'.join(map(str,d.frame_key))
def frame_match_key(d):return chapter_key(tuple(source_chapter(d))+((d.frame or d.node).name,))
def link_match_key(link):return chapter_key(tuple(link['sourceChapter'])+(link['sourceFrame'],))
def normalize(value):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value)).strip()).casefold()
def chapter_label(ch):return f"{ch['number']} · {ch['title']}"
def card_label(card):return f"Card {card.get('displayLabel',card['displayNumber'])} (local {card.get('frameLabel',card['number'])}, global {card.get('globalFrameLabel',card['globalNumber'])})"

def chapter_number(name):
    values=re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])',name)
    return '.'.join(str(int(n)) for n in values[0].split('.')) if len(values)==1 else None

def frame_number(name,lettered=False):
    # Consume the entire suffix, so 3Chapter never accidentally becomes 3C.
    values=re.findall(r'(?<!\d)(\d+)([a-z]*)(?![a-z\d])',name,re.I)
    if len(values)!=1:return None
    number,suffix=values[0]
    return str(int(number))+suffix.upper() if lettered else int(number) if not suffix else None


def card_number(card,mode):
    return card['number'] if mode=='Chapter numbers' else card['globalNumber'] if mode=='Global numbers' else card['displayNumber']

def source_card_id(card):return card.get('sourceCardId') or card['id']

def reuse_families(reference):
    """Card appearances retain their own identities while sharing a drawing source.

    A source may be archived or unused in SS, so it need not be an active card
    in the reference. These are family references, not variant assignments.
    """
    families=defaultdict(list)
    for ch in reference['chapters']:
        for card in ch['cards']:
            source=source_card_id(card)
            families[source].append({'cardId':card['id'],'sourceCardId':source,
                'chapterId':ch['id'],'chapterNumber':ch['number'],'chapterTitle':ch['title'],
                'cardNumber':card['number'],'globalCardNumber':card['globalNumber'],
                'displayCardNumber':card['displayNumber'],'isReusableCopy':card['id']!=source,
                **({key:card[key] for key in ('variantIndex','variantAssetId') if key in card})})
    return dict(families)

def resolve_links(drawings,reference,overrides=None,number_mode=NUMBER_MODES[0]):
    if number_mode not in NUMBER_MODES:raise ValueError('Choose how CSP frame numbers match storyboard cards.')
    overrides=overrides or {};chapter_overrides=overrides.get('chapters',{});frame_overrides=overrides.get('frames',{})
    chapters=reference['chapters'];by_id={c['id']:c for c in chapters};paths={}
    for d in drawings:paths.setdefault(source_chapter(d),None)
    chapter_links={}
    for path in sorted(paths,key=len):
        key=chapter_key(path)
        if key in chapter_overrides:
            chapter_links[key]=by_id.get(chapter_overrides[key]);continue
        candidates=chapters
        if path[:-1] and chapter_links.get(chapter_key(path[:-1])):
            parent=chapter_links[chapter_key(path[:-1])]['id'];candidates=[c for c in chapters if c.get('parentId')==parent]
        if not path:
            candidates=chapters if len(chapters)==1 else []
        else:
            exact=[c for c in candidates if normalize(path[-1]) in (normalize(c['title']),normalize(core.safe_name(c['title'])),normalize(f"{c['number']} - {c['title']}"))]
            num=chapter_number(path[-1]);candidates=exact if exact else [c for c in candidates if num and c['number']==num]
        chapter_links[key]=candidates[0] if len(candidates)==1 else None
    links={};families=reuse_families(reference)
    for d in drawings:
        key=frame_key(d)
        if key in links:continue
        path=source_chapter(d);ch=by_id.get(overrides.get('frameChapters',{}).get(frame_match_key(d))) or chapter_links.get(chapter_key(path));card=None
        if ch:
            match_key=frame_match_key(d)
            if match_key in frame_overrides:card=next((c for c in ch['cards'] if c['id']==frame_overrides[match_key]),None)
            else:
                lettered=overrides.get('lettered',False)
                number=frame_number((d.frame or d.node).name,lettered)
                field='frameLabel' if number_mode=='Chapter numbers' else 'globalFrameLabel' if number_mode=='Global numbers' else 'displayLabel'
                matches=[c for c in ch['cards'] if number is not None and (str(c.get(field,card_number(c,number_mode)))==str(number) if lettered else card_number(c,number_mode)==number)]
                if len(matches)==1:card=matches[0]
        links[key]={'sourceChapter':path,'sourceFrame':(d.frame or d.node).name,'chapter':ch,'card':card,
            'sourceCardId':source_card_id(card) if card else None,
            'cardReferences':[r for r in families[source_card_id(card)] if 'variantIndex' not in card or r.get('variantIndex')==card['variantIndex'] and r.get('variantAssetId')==card.get('variantAssetId')] if card else []}
    return chapter_links,links

def chapter_path(ch,reference,style,source):
    if style==studio.PROJECT_FOLDERS:
        item=next((item for item in reference.get('chapterDirectories',[]) if item.get('chapterId')==ch['id']),None)
        if item is None:raise ValueError('No shared folder for this chapter. Refresh Studio Link.')
        return tuple(studio.relative_path(item.get('path')).parts)
    if style=='Source folders':return source
    if style not in CHAPTER_STYLES:raise ValueError('Choose a chapter folder style.')
    by_id={c['id']:c for c in reference['chapters']};chain=[];current=ch
    while current:
        chain.insert(0,current['title'] if style=='Title only' else f"{current['number']} - {current['title']}")
        current=by_id.get(current.get('parentId'))
    return tuple(chain)

@dataclass
class ExportPlan:
    tasks: list
    root: Path
    links: dict
    reference: dict | None
    chapter_style: str
    number_mode: str
    workspace: studio.StudioProject | None = None
    naming_mode: str = studio.CUSTOM_NAMES

def make_plan(drawings,selected,destination,settings,reference=None,overrides=None,chapter_style=CHAPTER_STYLES[0],number_mode=NUMBER_MODES[0],workspace=None,naming_mode=studio.CUSTOM_NAMES):
    destination=Path(destination).expanduser().resolve()
    if workspace is not None:
        if destination!=workspace.root:raise ValueError('Studio Link exports must use the connected project folder. Relink it or turn off Storyboard Studio export.')
        if reference is None or reference['project']['id']!=workspace.project_id:raise ValueError('The reference belongs to another project.')
        if settings.project_folder:raise ValueError('Studio Link uses the selected project folder directly.')
    if naming_mode not in studio.NAMING_MODES:raise ValueError('Choose a filename mode.')
    root=destination/core.safe_name(settings.project_folder) if settings.project_folder.strip() else destination
    links={};planned=drawings
    if reference is not None:
        _,links=resolve_links(drawings,reference,overrides,number_mode)
        selected_frames={frame_key(d) for d in drawings if d.node.key in selected}
        used=set();folders={};source_names=set()
        for key in selected_frames:
            link=links[key]
            name_key=link_match_key(link)
            if name_key in source_names:raise ValueError('Two selected CSP frame folders have the same name in a chapter. Give them different names before linking.')
            source_names.add(name_key)
            if not link['chapter'] or not link['card']:
                raise ValueError('Review storyboard matches: '+('/'.join(link['sourceChapter'])+' / ' if link['sourceChapter'] else '')+link['sourceFrame']+' is not linked to a card.')
            pair=(link['chapter']['id'],link['card']['id'])
            if pair in used:raise ValueError('Two selected frames point to the same storyboard card. Review matches before exporting.')
            used.add(pair)
            path=chapter_path(link['chapter'],reference,chapter_style,link['sourceChapter'])
            canonical=tuple(core.safe_name(p).casefold() for p in path)
            if settings.separate and canonical in folders and folders[canonical]!=link['chapter']['id']:
                raise ValueError('Two chapter folder names collide. Choose Number + title or use different source folders.')
            folders[canonical]=link['chapter']['id']
        planned=[replace(d,source_chapter=source_chapter(d),chapter=chapter_path(links[frame_key(d)]['chapter'],reference,chapter_style,source_chapter(d)),storyboard_number=links[frame_key(d)]['card']['displayNumber']) if frame_key(d) in selected_frames else d for d in drawings]
    name_builder=None
    if naming_mode==studio.PROJECT_NAMES:
        if reference is None or not reference.get('naming'):raise ValueError('Connect a project folder to use shared card names.')
        def name_builder(d,s,n):
            link=links[frame_key(d)];return studio.shared_card_stem(reference,link['chapter'],link['card'],d,s)
    return ExportPlan(core.plan(planned,selected,destination,settings,name_builder=name_builder,preserve_chapter_paths=chapter_style==studio.PROJECT_FOLDERS,reuse_existing=workspace is not None),root,links,reference,chapter_style,number_mode,workspace,naming_mode)

def inventory(plan,settings,source,canvas_size,records,failures,cancelled):
    frames={};ref=plan.reference;export_id=str(uuid.uuid4());exported_at=media_catalog.stamp()
    chapter_order={c['id']:i for i,c in enumerate(ref['chapters'])} if ref else {}
    for drawing,path,size in records:
        key=frame_key(drawing);link=plan.links.get(key,{});ch=link.get('chapter');card=link.get('card')
        if key not in frames:
            frames[key]={'sourceFrameKey':list(drawing.frame_key),'sourceFrameName':(drawing.frame or drawing.node).name,
                'sourceChapterFolders':list(source_chapter(drawing)),'chapterId':ch['id'] if ch else None,
                'chapterNumber':ch['number'] if ch else None,'chapterTitle':ch['title'] if ch else (source_chapter(drawing)[-1] if source_chapter(drawing) else ''),
                'cardId':card['id'] if card else None,'cardNumber':card['number'] if card else None,
                'globalCardNumber':card['globalNumber'] if card else None,'displayCardNumber':card['displayNumber'] if card else None,
                'sourceCardId':link.get('sourceCardId'),**({key:card[key] for key in ('variantIndex','variantAssetId') if key in card} if card else {}),'cardReferences':link.get('cardReferences',[]),
                'frameLabel':card.get('frameLabel') if card else None,'exportIndex':drawing.frame_index,'exportId':export_id,'exportedAt':exported_at,'files':[]}
        relative=Path(path).resolve().relative_to(plan.root).as_posix()
        frames[key]['files'].append({'kind':'component' if drawing.is_component else 'whole-frame','managed':plan.naming_mode==studio.PROJECT_NAMES and plan.chapter_style==studio.PROJECT_FOLDERS and settings.separate and not settings.frame_folders,'componentSuffix':('_'+str(drawing.label or drawing.node.name)+(('_'+str(drawing.component_index).zfill(settings.padding)) if drawing.component_index else '')) if drawing.is_component else '',
            'sourceComponentKey':list(drawing.node.key),'sourceComponentName':drawing.node.name,'label':drawing.label,
            'stackOrder':drawing.stack_order if drawing.is_component else None,
            'componentIndex':drawing.component_index or None,'repeatedLabelIndex':drawing.label_index or None,
            'filename':Path(path).name,'path':relative,'width':size[0],'height':size[1],'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None})
    ordered=list(frames.values())
    ordered.sort(key=lambda f:(chapter_order.get(f['chapterId'],len(chapter_order)),f['cardNumber'] or f['exportIndex']))
    expected=Counter(frame_key(d) for d,path in plan.tasks)
    for f in ordered:
        f['files'].sort(key=lambda item:(item['stackOrder'] is not None,item['stackOrder'] or 0))
        f['expectedFileCount']=expected['/'.join(map(str,f['sourceFrameKey']))]
        f['complete']=len(f['files'])==f['expectedFileCount']
    source_counts=Counter(f['sourceCardId'] for f in ordered if f['sourceCardId'])
    return {'format':'folderexporter-index-v1','schemaVersion':1,'exportId':export_id,
        'createdAt':exported_at,'generator':'FolderExporter 1.10.0',
        'pathBase':'media-root' if plan.workspace else 'index-directory',**({'mediaRoot':'.','studioProjectId':plan.workspace.project_id} if plan.workspace else {}),'componentOrder':'bottom-to-top',
        'reuse':{'mode':'source-family','variantAssignmentsIncluded':bool(ref) and all('variantIndex' in c for ch in ref['chapters'] for c in ch['cards']),
            'multipleExportsForSource':[source for source,count in source_counts.items() if count>1]},
        'source':{'id':studio.source_id(source,plan.workspace),'filename':Path(source).name,'canvasWidth':canvas_size[0],'canvasHeight':canvas_size[1]},
        'storyboardReference':{'project':ref['project'],'structuralSignature':ref.get('structuralSignature'),'exportedAt':ref.get('exportedAt'),'chapters':ref['chapters']} if ref else None,
        'chapters':[{k:c.get(k) for k in ('id','parentId','number','title')} for c in ref['chapters']] if ref else [],
        'naming':{'mode':plan.naming_mode,'sharedProfile':ref.get('naming') if ref else None,'slots':[asdict(slot) for slot in settings.slots],'separators':list(settings.separators),
            'start':settings.start,'padding':settings.padding,'reverseFrames':settings.reverse,'resetPerChapter':settings.reset,
            'componentIndexMode':'stack-order' if settings.component_stack_order else 'repeated-label'},
        'organization':{'studioLink':plan.workspace is not None,'projectFolder':settings.project_folder,'chapterFolders':settings.separate,'chapterFolderStyle':plan.chapter_style,'frameFolders':settings.frame_folders,'cardNumberMode':plan.number_mode},
        'complete':not cancelled and not failures,'cancelled':bool(cancelled),
        'failures':[{'name':name,'error':error} for name,error in failures], 'frames':ordered}

def write_index(root,data):
    """Publish completed JSON in one step where hard links are supported.

    The portable fallback still uses exclusive-create, never replacement of
    someone else's output. Temporary/incomplete files are cleaned on failure.
    """
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8')
    temp=root/f'.folderexporter-index-{uuid.uuid4().hex}.tmp'
    try:
        with temp.open('xb') as output:output.write(payload);output.flush();os.fsync(output.fileno())
        attempt=1
        while True:
            path=root/('folderexporter-index'+('' if attempt==1 else f' - {attempt}')+'.json')
            try:
                os.link(temp,path)
                return path
            except FileExistsError:attempt+=1;continue
            except OSError:
                # For filesystems without hard links, retain collision safety.
                try:output=path.open('xb')
                except FileExistsError:attempt+=1;continue
                try:
                    with output:output.write(payload);output.flush();os.fsync(output.fileno())
                except Exception:path.unlink(missing_ok=True);raise
                return path
    finally:temp.unlink(missing_ok=True)


def _prior_indexes(plan,source_id):
    folder=plan.workspace.root/studio.LINK_FOLDER
    for path in folder.glob('folderexporter-index*.json'):
        try:data=studio.read_json(path)
        except (ValueError,OSError):continue
        pid=data.get('studioProjectId') or (data.get('storyboardReference') or {}).get('project',{}).get('id')
        if data.get('format')=='folderexporter-index-v1' and pid==plan.workspace.project_id and data.get('source',{}).get('id')==source_id:yield path,data


def linked_image_writer(plan,source):
    if plan.workspace is None:return None
    owners=media_catalog.known_owners(plan.workspace)
    media_catalog.archive_storyboards(plan.workspace,{frame_key(d):plan.links[frame_key(d)] for d,_ in plan.tasks})
    def write(drawing,target,temp):
        rel=target.relative_to(plan.root).as_posix();studio.relative_path(rel)
        if not target.parent.resolve(strict=True).is_relative_to(plan.root):raise ValueError('An output folder points outside this project.')
        if target.is_symlink():raise ValueError('An output image points outside this project.')
        link=plan.links.get(frame_key(drawing),{});card=link.get('card') or {};identity=media_catalog.key(link.get('sourceCardId') or card.get('id'),card.get('variantIndex',0))
        if target.exists():
            owner=owners.get(rel)
            if not owner or owner!=identity:raise ValueError(f'{target.name} belongs to another drawing. Choose a distinct naming pattern.')
        else:owners[rel]=identity
        os.replace(temp,target)
        owners[rel]=identity
        return target
    return write


def write_plan_index(plan,data):
    if plan.workspace is None:return write_index(plan.root,data)
    studio.validate_output_root(plan.workspace)
    folder=plan.workspace.root/studio.LINK_FOLDER
    if not folder.resolve(strict=True).is_relative_to(plan.workspace.root):raise ValueError('Studio Link points outside this project.')
    previous=list(_prior_indexes(plan,data['source']['id']))
    frames={}
    for _,old in sorted(previous,key=lambda p:p[1].get('createdAt','')):
        for frame in old.get('frames',[]):frames[tuple(frame['sourceFrameKey'])]={**frame,'exportedAt':frame.get('exportedAt',old.get('createdAt')),'exportId':frame.get('exportId',old.get('exportId'))}
    for frame in data['frames']:frames[tuple(frame['sourceFrameKey'])]=frame
    data={**data,'frames':list(frames.values())}
    name='folderexporter-index-'+hashlib.sha256(data['source']['id'].encode()).hexdigest()[:16]+'.json'
    target=folder/name
    if target.exists() and target not in [p for p,_ in previous]:raise ValueError('The image index filename is owned by another source.')
    temp=folder/('.'+name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('xb') as out:out.write(json.dumps(data,ensure_ascii=False,indent=2).encode());out.flush();os.fsync(out.fileno())
        os.replace(temp,target)
    finally:temp.unlink(missing_ok=True)
    for path,_ in previous:
        if path!=target:path.unlink(missing_ok=True)
    media_catalog.publish(plan.workspace,data)
    return target

def binding_drift(plan,overrides):
    """A reused CSP folder name is ambiguous after renumbering; never silently retarget."""
    known=(overrides or {}).get('frames',{});lettered=(overrides or {}).get('lettered',False);out=[]
    for drawing,_ in plan.tasks:
        link=plan.links.get(frame_key(drawing),{});card=link.get('card')
        if not card or frame_match_key(drawing) not in known:continue
        field='frameLabel' if plan.number_mode=='Chapter numbers' else 'globalFrameLabel' if plan.number_mode=='Global numbers' else 'displayLabel'
        current=str(card.get(field,card_number(card,plan.number_mode))) if lettered else str(card_number(card,plan.number_mode))
        parsed=frame_number((drawing.frame or drawing.node).name,lettered)
        if parsed is not None and str(parsed)!=current:out.append((frame_match_key(drawing),link['sourceFrame'],current))
    return list(dict.fromkeys(out))
