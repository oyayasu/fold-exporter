"""Shared active cleanup choices. Per-source indexes remain export inventories."""
from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
import json,os,time,uuid
import studio_link as studio

FORMAT='studio-media-index-v1'
def stamp():return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
def key(source,index):return json.dumps([source,index],ensure_ascii=False,separators=(',',':'))
def read(project):
    path=project.root/studio.LINK_FOLDER/'media-index.json'
    if not path.exists():return {'format':FORMAT,'schemaVersion':1,'projectId':project.project_id,'entries':{}}
    data=studio.read_json(path)
    if data.get('format')!=FORMAT or data.get('schemaVersion')!=1 or data.get('projectId')!=project.project_id or not isinstance(data.get('entries'),dict):raise ValueError('Invalid cleanup catalog or different project.')
    return data

@contextmanager
def lock(project):
    path=project.root/studio.LINK_FOLDER/'.media-index.lock'
    for attempt in range(100):
        try:path.mkdir();break
        except FileExistsError:
            try:
                if time.time()-path.stat().st_mtime>60:path.rmdir()
            except (FileNotFoundError,OSError):pass
            time.sleep(.02)
    else:raise ValueError('Another app is updating cleanup links. Try again shortly.')
    try:yield
    finally:path.rmdir()

def publish(project,index):
    with lock(project):
        data=read(project);old_managed=[f for e in data['entries'].values() if not e.get('removed') for f in e.get('files',[])+e.get('referenceFiles',[]) if f.get('managed')]
        for frame in index.get('frames',[]):
            # Retained frames from a partial export must not reclaim newer manual choices.
            if frame.get('exportId')!=index['exportId'] or not frame.get('complete',True):continue
            source=frame.get('sourceCardId') or frame.get('cardId')
            if not source:continue
            variant=frame.get('variantIndex',0);identity=key(source,variant)
            components=sorted((f for f in frame['files'] if f['kind']=='component'),key=lambda f:f['stackOrder'])
            selected=components or [f for f in frame['files'] if f['kind']=='whole-frame'];files=[]
            for i,f in enumerate(selected):
                relative=str(studio.relative_path(f['path']));path=(project.root/relative).resolve(strict=True)
                if not path.is_relative_to(project.root):raise ValueError('Cleanup output points outside this project.')
                stat=path.stat();files.append({'id':str(uuid.uuid5(uuid.NAMESPACE_URL,project.project_id+'/'+source+'/'+str(variant)+'/'+str(f.get('sourceComponentKey',f['path'])))),'managed':f.get('managed',False),'componentSuffix':f.get('componentSuffix',''),'componentIndex':(f.get('stackOrder') or f.get('componentIndex')) if f.get('kind')=='component' else None,'componentName':f.get('label') or f.get('sourceComponentName'),'name':f['filename'],'path':str(path),'relativePath':relative,'kind':'image','width':f['width'],'height':f['height'],'size':stat.st_size,'modified':stat.st_mtime_ns//1000000,'sha256':f.get('sha256'),'stackOrder':i+1,'state':'ok','missing':False})
            reference_files=[]
            if components:
                for f in frame['files']:
                    if f['kind']!='whole-frame':continue
                    path=project.root/str(studio.relative_path(f['path']));stat=path.stat();reference_files.append({'id':str(uuid.uuid5(uuid.NAMESPACE_URL,project.project_id+'/'+source+'/'+str(variant)+'/whole')),'name':f['filename'],'path':str(path),'relativePath':f['path'],'kind':'image','managed':f.get('managed',False),'componentSuffix':'','size':stat.st_size,'modified':stat.st_mtime_ns//1000000})
            entry={'referenceFiles':reference_files,'sourceCardId':source,'variantIndex':variant,'variantAssetId':frame.get('variantAssetId'),'source':'folderexporter','sourceId':index['source']['id'],'exportId':index['exportId'],'updatedAt':frame['exportedAt'],'revision':str(uuid.uuid4()),'files':files}
            previous=data['entries'].get(identity)
            if previous is None or entry['updatedAt']>=previous['updatedAt']:data['entries'][identity]=entry
        target=project.root/studio.LINK_FOLDER/'media-index.json';temp=target.with_name('.media-index-'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('x',encoding='utf8') as out:json.dump(data,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
            os.replace(temp,target)
        finally:temp.unlink(missing_ok=True)
    active={f.get('relativePath') for e in data['entries'].values() for f in e.get('files',[])+e.get('referenceFiles',[]) if not e.get('removed')}
    for f in old_managed:
        rel=f.get('relativePath')
        if not rel or rel in active:continue
        path=project.root/str(studio.relative_path(rel))
        try:
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(project.root):continue
            stat=path.stat()
            if stat.st_size==f.get('size') and stat.st_mtime_ns//1000000==f.get('modified'):path.unlink()
        except OSError:pass
    return target

def known_owners(project):
    owners={}
    for path in (project.root/studio.LINK_FOLDER).glob('folderexporter-index*.json'):
        try:index=studio.read_json(path)
        except (OSError,ValueError):continue
        pid=index.get('studioProjectId') or (index.get('storyboardReference') or {}).get('project',{}).get('id')
        if pid!=project.project_id:continue
        for frame in index.get('frames',[]):
            source=frame.get('sourceCardId') or frame.get('cardId')
            if source:
                for f in frame.get('files',[]):owners[f['path']]=key(source,frame.get('variantIndex',0))
    for identity,entry in read(project)['entries'].items():
        for f in entry.get('ignoredFiles',[]):
            if f.get('managed') and f.get('relativePath'):owners[str(studio.relative_path(f['relativePath']))]=identity
        if entry.get('removed'):continue
        for f in entry.get('files',[])+entry.get('referenceFiles',[]):
            relative=f.get('relativePath')
            if relative:owners[relative]=identity
    return owners

def atomic_json(path,data):
    path=Path(path);temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('x',encoding='utf8') as out:json.dump(data,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def process_alive(pid):
    if os.name=='nt':
        import ctypes
        handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,pid)
        if not handle:return False
        code=ctypes.c_ulong();ok=ctypes.windll.kernel32.GetExitCodeProcess(handle,ctypes.byref(code));ctypes.windll.kernel32.CloseHandle(handle);return bool(ok and code.value==259)
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True

@contextmanager
def workflow_lock(project):
    if project is None:yield;return
    path=project.root/studio.LINK_FOLDER/'.workflow.lock'
    for attempt in range(100):
        try:path.mkdir();(path/'owner').write_text(str(os.getpid()));break
        except FileExistsError:
            try:
                pid=int((path/'owner').read_text())
                if not process_alive(pid):(path/'owner').unlink(missing_ok=True);path.rmdir();continue
            except (OSError,ValueError):pass
            time.sleep(.02)
    else:raise ValueError('Storyboard Studio or FolderExporter is saving. Wait for it to finish, then retry.')
    try:recover_organization(project);yield
    finally:(path/'owner').unlink(missing_ok=True);path.rmdir()

def recover_organization(project):
    link=project.root/studio.LINK_FOLDER;journal=link/'organization-journal.json'
    if not journal.exists():return
    data=studio.read_json(journal)
    def local(rel):
        target=project.root/str(studio.relative_path(rel))
        if target.is_symlink() or not target.resolve().is_relative_to(project.root):raise ValueError('File recovery points outside the project.')
        return target
    if data.get('phase')=='installing':
        for m in data['moves']:
            stage=local(m['stage']);target=local(m['to'])
            if not stage.exists() and target.exists():os.rename(target,stage)
    for m in data['moves']:
        stage=local(m['stage']);before=local(m['from'])
        if stage.exists():
            if before.exists():raise ValueError('A recovery location is occupied. Keep the organization journal and contact support.')
            before.parent.mkdir(parents=True,exist_ok=True);os.rename(stage,before)
    for name,doc in data.get('documents',{}).items():
        rel=studio.relative_path(name)
        if len(rel.parts)!=1:raise ValueError('Invalid recovery metadata name.')
        atomic_json(link/name,doc)
    journal.unlink()

def conflicts(plan,source):
    if plan.workspace is None:return set()
    entries=read(plan.workspace)['entries'];sid=studio.source_id(source,plan.workspace);bad=set()
    import storyboard as sb
    for drawing,_ in plan.tasks:
        link=plan.links[sb.frame_key(drawing)];card=link['card'];identity=key(link['sourceCardId'],card.get('variantIndex',0));old=entries.get(identity)
        if old and not old.get('removed') and old.get('files') and (old.get('sourceId')!=sid or old.get('source')!='folderexporter'):bad.add(sb.frame_key(drawing))
    return bad

def archive_storyboards(project,links):
    """Move only tracked rough exports, using configured archive names."""
    link=project.root/studio.LINK_FOLDER;manifest=studio.read_json(link/'project.json');registry_path=link/'storyboard-outputs.json'
    if not registry_path.exists():return
    registry=studio.read_json(registry_path);active_paths={f.get('relativePath') for e in read(project)['entries'].values() if not e.get('removed') for f in e.get('files',[])+e.get('referenceFiles',[])};metadata_changed=False;wanted={value.get('sourceCardId'):value for value in links.values() if value.get('card')};changes=[]
    for record_key,record in manifest.get('storyboards',{}).items():
        if record.get('missing'):continue
        match=wanted.get(record.get('sourceCardId'))
        if not match:continue
        card=next((c for ch in project.reference['chapters'] for c in ch['cards'] if c['id']==record.get('cardId')),match['card']);ch=next((ch for ch in project.reference['chapters'] if any(c['id']==card['id'] for c in ch['cards'])),match['chapter'])
        context={'project':project.reference['project']['name'],'chapter_number':ch['number'],'chapter_title':ch['title'],'card_number':card.get('exportNumber',card['number']),'global_number':card.get('globalExportNumber',card['globalNumber']),'slight_modify_index':card.get('slightModifyIndex',''),'variant':chr(65+card.get('variantIndex',0)),'page':1}
        old=record['relativePath'];new=studio.render_name(project.naming,'archiveFolder',context)+'/'+studio.render_name(project.naming,'archiveCard',context)+record.get('exportSuffix','')+'.png'
        if old==new:continue
        before=project.root/str(studio.relative_path(old));after=project.root/str(studio.relative_path(new));owner=registry.get('files',{}).get(old)
        if not before.exists() or old in active_paths:
            record.update(relativePath=new,path=str(after),missing=True,archived=True);metadata_changed=True;continue
        if not owner or owner.get('project')!=project.project_id:raise ValueError(f'{old} is not a tracked storyboard export. Refresh Storyboard Studio.')
        if after.exists():raise ValueError(f'{new} already exists. Choose a distinct storyboard archive name.')
        if not before.resolve().is_relative_to(project.root) or not after.parent.resolve().is_relative_to(project.root):raise ValueError('Storyboard archive points outside the project.')
        changes.append((record,old,new,before,after,owner))
    if not changes:
        if metadata_changed:atomic_json(link/'project.json',manifest)
        return
    original_manifest=studio.read_json(link/'project.json');original_registry=studio.read_json(registry_path)
    moves=[{'from':old,'to':new,'stage':studio.LINK_FOLDER+'/.organization-fe-'+uuid.uuid4().hex+'.tmp'} for _,old,new,_,_,_ in changes]
    journal={'phase':'staging','moves':moves,'documents':{'project.json':original_manifest,'storyboard-outputs.json':original_registry}}
    atomic_json(link/'organization-journal.json',journal)
    try:
        for m in moves:os.rename(project.root/m['from'],project.root/m['stage'])
        journal['phase']='installing';atomic_json(link/'organization-journal.json',journal)
        for (record,old,new,before,after,owner),m in zip(changes,moves):
            after.parent.mkdir(parents=True,exist_ok=True);os.rename(project.root/m['stage'],after);stat=after.stat();owner={**owner,'size':stat.st_size,'modified':stat.st_mtime_ns//1000000};del registry['files'][old];registry['files'][new]=owner;record.update(relativePath=new,path=str(after),size=owner['size'],modified=owner['modified'],archived=True)
        atomic_json(registry_path,registry);atomic_json(link/'project.json',manifest);(link/'organization-journal.json').unlink()
    except Exception:
        recover_organization(project);raise
