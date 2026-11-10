"""Studio Link v1: exact shared names/paths; no writes to another app's handoffs."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import unicodedata

LINK_FOLDER='Studio Link'
PROJECT_FOLDERS='Use Storyboard Studio folders'
PROJECT_NAMES='Use project card names'
CUSTOM_NAMES='Custom filename slots'
NAMING_MODES=(PROJECT_NAMES,CUSTOM_NAMES)
DEFAULT_NAMING={'chapter':'{chapter_number} - {chapter_title}','card':'{card_number}','component':'{card_name}_component-{component_index}',
                'sheet':'{project}_Storyboard_{page}','timeline':'{project}_Timeline','archiveFolder':'{chapter_number} - {chapter_title}_storyboard','archiveCard':'{card_number}{slight_modify_index}_storyboard','padding':1}
TOKENS={'card_name','component_index','component_name','project','chapter_number','chapter_title','card_number','global_number','slight_modify_index','variant','page'}


def read_json(path):
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError(f'{path.name} exceeds 16 MB.')
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (UnicodeError,json.JSONDecodeError) as exc:raise ValueError(f'{path.name} is not readable JSON.') from exc


def relative_path(value):
    if not isinstance(value,str) or not value or len(value)>4096 or any(ord(c)<32 for c in value) or '\\' in value or ':' in value or value.startswith('/') or any(p in ('','.','..') for p in value.split('/')):
        raise ValueError('A Studio Link path must stay inside the project folder.')
    return PurePosixPath(value)


def file_leaf(value):
    value=unicodedata.normalize('NFC',str(value))
    value=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',value).rstrip('. ').strip() or 'Untitled'
    if value in ('.','..'):value='Untitled'
    if re.match(r'^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)',value,re.I):value='_'+value
    out=''
    for char in value:
        if len((out+char).encode('utf-8'))>120:break
        out+=char
    return out or 'Untitled'


def naming_profile(raw):
    if not isinstance(raw,dict):raise ValueError('Studio Link has no valid file naming profile.')
    profile={**DEFAULT_NAMING,**raw}
    for field in ('chapter','card','component','archiveFolder','archiveCard','sheet','timeline'):
        pattern=profile[field]
        if not isinstance(pattern,str) or not pattern.strip() or len(pattern)>160 or re.search(r'[\\/\x00-\x1f]',pattern):raise ValueError('Invalid shared file naming pattern.')
        if any(t not in TOKENS for t in re.findall(r'\{([^{}]+)\}',pattern)) or re.search(r'[{}]',re.sub(r'\{[^{}]+\}','',pattern)):raise ValueError('Unknown or incomplete shared file naming field.')
    if type(profile['padding']) is not int or not 1<=profile['padding']<=6:raise ValueError('Shared number padding must be between 1 and 6.')
    return profile


def render_name(profile,field,context):
    profile=naming_profile(profile)
    if field=='component':context={**context,'card_name':render_name(profile,'card',context)}
    def token(match):
        key=match[1];value=context.get(key,1 if key in ('card_number','global_number','component_index','page') else '')
        return str(value).zfill(profile['padding']) if key in ('card_number','global_number','component_index','page') else str(value)
    pattern=profile[field]
    if field in ('card','archiveCard','component') and context.get('slight_modify_index') and '{slight_modify_index}' not in pattern:pattern=re.sub(r'\{(card_number|global_number)\}',lambda m:m[0]+'{slight_modify_index}',pattern,count=1)
    return file_leaf(re.sub(r'\{([^{}]+)\}',token,pattern))


@dataclass(frozen=True)
class StudioProject:
    root: Path
    project_id: str
    reference: dict
    naming: dict
    chapter_directories: dict
    manifest: dict


def read_project(directory,expected_project_id=None):
    root=Path(directory).expanduser().resolve(strict=True)
    if root.name==LINK_FOLDER:root=root.parent
    if not root.is_dir():raise ValueError('Choose the main project folder.')
    link=(root/LINK_FOLDER).resolve(strict=True)
    if not link.is_relative_to(root) or not link.is_dir():raise ValueError('Studio Link points outside this project.')
    manifest=read_json(link/'project.json')
    if not isinstance(manifest,dict) or manifest.get('format')!='studio-link-project-v1' or manifest.get('schemaVersion')!=1:raise ValueError('Choose a project folder connected in Storyboard Studio.')
    project=manifest.get('project',{});pid=project.get('id')
    if not isinstance(pid,str) or not pid or len(pid)>2048:raise ValueError('Invalid Studio Link project identity.')
    if expected_project_id and pid!=expected_project_id:raise ValueError('This folder belongs to another project. Disconnect first to switch projects.')
    ref_path=link/relative_path(manifest.get('files',{}).get('reference','storyboard.ssreference.json'))
    ref_path=ref_path.resolve(strict=True)
    if not ref_path.is_relative_to(link):raise ValueError('The reference points outside Studio Link.')
    import storyboard as sb
    reference=sb.read_reference(ref_path)
    if reference['project']['id']!=pid:raise ValueError('The manifest and storyboard reference belong to different projects. Refresh Storyboard Studio first.')
    # project.json is written last by SS. Read again so a racing update cannot
    # pair two project versions without detection.
    latest=read_json(link/'project.json')
    if latest!=manifest:raise ValueError('Storyboard Studio is updating this folder. Refresh again in a moment.')
    naming=naming_profile(manifest.get('naming',reference.get('naming')))
    if reference.get('naming') is not None and naming_profile(reference['naming'])!=naming:
        raise ValueError('Studio Link naming is being updated. Refresh again in a moment.')
    directories={};used={}
    entries=manifest.get('chapterDirectories')
    if not isinstance(entries,list) or len(entries)>10000:raise ValueError('Invalid shared chapter folder list.')
    for entry in entries:
        if not isinstance(entry,dict):raise ValueError('Invalid shared chapter folder.')
        ident=entry.get('chapterId');rel=str(relative_path(entry.get('path')))
        if not isinstance(ident,str) or not ident or ident in directories:raise ValueError('Duplicate or invalid shared chapter identity.')
        canonical=unicodedata.normalize('NFC',rel).casefold()
        if canonical in used and used[canonical]!=ident:raise ValueError('Two chapters use the same shared folder.')
        target=(root/rel).resolve()
        if not target.is_relative_to(root) or target.exists() and not target.is_dir():raise ValueError('A chapter folder is missing, blocked or points outside the project.')
        directories[ident]=rel;used[canonical]=ident
    if any(ch['id'] not in directories for ch in reference['chapters']):raise ValueError('A chapter folder is missing from Studio Link. Refresh Storyboard Studio first.')
    reference={**reference,'naming':naming,'chapterDirectories':entries}
    return StudioProject(root,pid,reference,naming,directories,manifest)


def source_id(source,workspace=None):
    source=Path(source).expanduser().resolve()
    identity=(workspace.project_id+'/'+source.relative_to(workspace.root).as_posix()) if workspace and source.is_relative_to(workspace.root) else str(source)
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]


def validate_output_root(project):
    current=read_project(project.root,project.project_id)
    if current.naming!=project.naming or current.chapter_directories!=project.chapter_directories or current.reference.get('structuralSignature')!=project.reference.get('structuralSignature'):
        raise ValueError('Storyboard Studio changed while exporting. Images are kept; refresh and export again to create the matching index.')
    return current


def shared_card_stem(reference,chapter,card,drawing,settings):
    profile=reference['naming']
    context={'project':reference['project']['name'],'chapter_number':chapter['number'],
             'chapter_title':chapter['title'],'card_number':card.get('exportNumber',card['number']),'slight_modify_index':card.get('slightModifyIndex',''),
             'global_number':card.get('globalExportNumber',card['globalNumber']),'variant':chr(65+card.get('variantIndex',0)), 'page':1}
    base=render_name(profile,'card',context)
    if drawing.is_component:
        return render_name(profile,'component',{**context,'component_index':drawing.stack_order or drawing.component_index or 1,'component_name':drawing.label or drawing.node.name})
    return base
