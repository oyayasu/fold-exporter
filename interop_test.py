"""Optional check against an actual Storyboard Studio source ZIP (requires Node)."""
from pathlib import Path
from tempfile import TemporaryDirectory
from dataclasses import replace
import argparse,json,subprocess,zipfile
import export_core as core
import storyboard as sb
from studio_link_test import shared
from integration_test import hidden_psd
import studio_link as studio

parser=argparse.ArgumentParser();parser.add_argument('storyboard_zip');args=parser.parse_args()
with TemporaryDirectory() as tmp:
    tmp=Path(tmp);root=tmp/'My Project';root.mkdir();workspace=shared(root)
    # One cleaned drawing is reused in another chapter; another appearance uses a different variant.
    ref=workspace.reference;origin=ref['chapters'][0]['cards'][0]
    for ch in ref['chapters'][1:]:
        card=ch['cards'][0];card['sourceCardId']=origin['id'];card['variantAssetId']=origin['variantAssetId']
    ref['chapters'][1]['cards'][0]['variantIndex']=1;ref['chapters'][1]['cards'][0]['variantAssetId']='other-variant'
    (root/'Studio Link/storyboard.ssreference.json').write_text(json.dumps(ref));workspace=studio.read_project(root)
    source=tmp/'Clean.psd';doc=hidden_psd(source)
    ds=core.discover(core.folder_tree(doc,False),rules=[core.ComponentRule('Background','BG'),core.ComponentRule('Character','Character')],component_mode='Separate + whole frame')
    settings=core.Settings(component_stack_order=True,component_mode='Separate + whole frame');plan=sb.make_plan(ds,{d.node.key for d in ds},root,settings,workspace.reference,chapter_style=studio.PROJECT_FOLDERS,workspace=workspace,naming_mode=studio.PROJECT_NAMES);records=[]
    made,failures,cancelled=core.export(doc,False,plan.tasks,settings,on_saved=lambda d,p,size:records.append((d,p,size)),output_root=root)
    assert not failures
    data=sb.inventory(plan,settings,source,core.dimension(doc),records,failures,cancelled);index=sb.write_plan_index(plan,data)
    with zipfile.ZipFile(args.storyboard_zip) as z:
        z.extractall(tmp/'ss')
    source_dir=next((tmp/'ss').rglob('src/image-assembly-model.js')).parent
    js=r'''
import fs from 'node:fs';import {pathToFileURL} from 'node:url';
const [source,indexPath,root]=process.argv.slice(2),{parseImageIndex,addImageBatch,resolveCardImages}=await import(pathToFileURL(source+'/image-assembly-model.js')),{exportDefaults,buildTimelinePlan,materializeTimeline,timelineXml}=await import(pathToFileURL(source+'/timeline-export-model.js')),{timingSignature}=await import(pathToFileURL(source+'/video-timing-model.js'));
const raw=JSON.parse(fs.readFileSync(indexPath)),ref=raw.storyboardReference,project={id:ref.project.id,name:ref.project.name,ratio:ref.project.ratio,chapters:ref.chapters.map(ch=>({id:ch.id,name:ch.title,parentId:ch.parentId,highlighter:{text:'',marks:[],assignments:[]}})),stories:[],unassigned:[],lost:[],archived:[],highlighter:{categories:[]}};
const sources=new Map();for(const ch of ref.chapters)for(const c of ch.cards){const sourceId=c.sourceCardId||c.id;if(!sources.has(sourceId))sources.set(sourceId,[]);sources.get(sourceId)[c.variantIndex||0]={assetId:c.variantAssetId};}
for(const ch of ref.chapters)for(const c of ch.cards)project.stories.push({id:c.id,chapterId:ch.id,activeVariant:c.variantIndex||0,reuseOf:c.sourceCardId&&c.sourceCardId!==c.id?c.sourceCardId:null,variants:c.sourceCardId&&c.sourceCardId!==c.id?[]:sources.get(c.id)});
const parsed=parseImageIndex(raw),batch=addImageBatch(project,parsed,{directory:root,sourceMode:'native'});batch.sourceStatus='ok';for(const frame of batch.frames)for(const f of frame.files){if(!fs.existsSync(root+'/'+f.path))throw Error('Indexed image missing');batch.fileStates[f.path]={state:'ok',size:100,modified:1};}
const statuses=Object.fromEntries(project.stories.map(c=>[c.id,resolveCardImages(project,c).status]));if(statuses['opening-card1']!=='ready'||statuses['opening-card2']!=='ready'||statuses['ending-card1']!=='ready'||statuses['detail-card1']!=='unmatched')throw Error('Wrong reuse/variant association: '+JSON.stringify(statuses));
const ids=['opening-card1','opening-card2','ending-card1'],cues=[];ids.forEach((id,i)=>{const c=project.stories.find(c=>c.id===id),ch=project.chapters.find(ch=>ch.id===c.chapterId);ch.highlighter.text+='Word ';const end=ch.highlighter.text.length;const assignment={id:'a'+i,from:end-5,to:end-1,cardId:id};ch.highlighter.assignments.push(assignment);cues.push({id:'cue'+i,assignmentId:assignment.id,chapterId:ch.id,cardId:id,spokenText:'Word',start:i,end:i+1,issues:[],reviewed:false});});
const chapterIds=[...new Set(cues.map(c=>c.chapterId))];project.videoTiming={version:1,tracks:[{id:'recording',audioPath:root+'/Synthetic.wav',source:{name:'Synthetic.wav',duration:3,channels:1,sampleRate:16000},chapterIds,cues,signature:timingSignature(project,chapterIds)}]};const plan=buildTimelinePlan(project,{...exportDefaults(),drawingMode:'cleanups'});if(plan.errors.length)throw Error(JSON.stringify(plan.errors));if(plan.media.length!==3||plan.videoTracks!==3||plan.cues[0].files[0].key!==plan.cues[2].files[0].key)throw Error('Incorrect track/media reuse '+JSON.stringify({media:plan.media.length,tracks:plan.videoTracks,keys:plan.cues.map(c=>c.files.map(f=>f.key))}));const xml=timelineXml(materializeTimeline(plan,root,{recording:{path:root+'/Synthetic.wav',name:'Synthetic.wav',duration:3,channels:1,sampleRate:16000}}));if(/<linkclipref>video-/.test(xml))throw Error('Components unexpectedly linked');if(xml.includes('<marker>'))throw Error('Unexpected timeline range markers');console.log(JSON.stringify({cues:plan.cues.length,media:plan.media.length,tracks:plan.videoTracks,statuses}));
'''
    test=tmp/'check.mjs';test.write_text(js);result=subprocess.run(['node',str(test),str(source_dir),str(index),str(root)],text=True,capture_output=True)
    if result.returncode:raise AssertionError(result.stderr)
    print('PASS: actual Storyboard Studio parser and timeline exporter accept FolderExporter output; variant snapshots, shared media, bottom-to-top layers and independent components.',result.stdout.strip())
