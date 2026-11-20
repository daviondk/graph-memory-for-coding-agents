import json,sys,hashlib,time,zipfile,os
from pathlib import Path
here=Path(__file__).resolve().parent
base=Path(os.environ.get('VIBE_BENCH_HOME','D:/CodexResearch/x20-official-vibe/VibeMemBench'))
sys.path.insert(0,str(base/'scripts'));sys.path.insert(0,str(here.parent/'vibe_memory'))
import run_memory as h
from policy import PriorFiles
def main():
    original=h.load_targets()
    focus={'brazilian-utils__brutils-python-125','s-knibbs__dataclasses-jsonschema-64'}
    roster=sorted(original,key=lambda t:(t['instance_id'] not in focus,t['instance_id']))
    rows=[]
    for target in roster:
        mem=PriorFiles();start=time.monotonic()
        r=h.run_one(target,method='prior_files',memory_factory=lambda:mem,top_k=1,out_root=base/'outputs/memory',run_id='x20-prior-files',max_session_mb=64.0,overwrite=True)
        iid=target['instance_id']
        assert r['num_retrieved']<=1
        if r['retrieved']:assert int(r['retrieved'][0]['source_session_id'].rsplit('-',1)[1])<int(iid.rsplit('-',1)[1])
        row={'id':iid,'repo':target['repo'],'language':target['language'],'seconds':round(time.monotonic()-start,4),'histories':r['num_histories_fed'],'returned':r['num_retrieved'],'words':sum(len(s['content'].split()) for s in r['retrieved']),**mem.audit}
        rows.append(row)
        if len(rows) in (2,25,50,75,100,111):print('complete',len(rows),flush=True)
    out=here/'predictions.jsonl';out.write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in rows),encoding='utf8')
    (here/'predictions.sha256').write_text(hashlib.sha256(out.read_bytes()).hexdigest(),encoding='utf8')
    with zipfile.ZipFile(here/'stage_outputs.zip','w',zipfile.ZIP_DEFLATED) as z:
        p=base/'outputs/memory/prior_files'
        for f in p.rglob('*'):
            if f.is_file():z.write(f,f.relative_to(p))
if __name__=='__main__':main()

