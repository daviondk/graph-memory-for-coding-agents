import collections,concurrent.futures,gzip,hashlib,importlib.util,json,sys,time,urllib.request,urllib.error
from pathlib import Path
HERE=Path(__file__).resolve().parent;R5=HERE.parent;OLD=R5.parent/'graph_memory_round4'/'writer'
sys.path.insert(0,str(OLD/'source_kimi'));from acquire_k import A,B,D,ROOT,acquire,localize,read,save,sha,write
AP=R5/'action_probe'
spec=importlib.util.spec_from_file_location('r5_terminal_raw',AP/'acquire.py');rawproj=importlib.util.module_from_spec(spec);spec.loader.exec_module(rawproj)
def download(meta):
    iid=meta['instance_id'];url=ROOT+iid+'.traj';rc={'id':iid,'repo':meta['repo'],'url':url}
    for trial in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'public-memory-study'}),timeout=40) as res:
                payload=res.read(acquire.LIMIT+1)
            if len(payload)>acquire.LIMIT:return None,None,{**rc,'status':'oversize'}
            rc.update(sha256=hashlib.sha256(payload).hexdigest(),bytes=len(payload));native=json.loads(payload)
            ok,ct=localize(native)
            if not ok:return None,None,{**rc,'status':'invalid_turn_match'}
            project,st=acquire.project(native,meta);rc['project']=dict(st)
            if not project:return None,None,{**rc,'status':'filtered_editor'}
            pair,counts=rawproj.extract(project,payload)
            assert pair[0]==iid and len(pair[1])==len(project['events'])
            return project,pair,{**rc,'terminal':dict(counts),'status':'ok'}
        except (urllib.error.URLError,OSError,ValueError,KeyError) as exc:
            if trial>=2:return None,None,{**rc,'status':type(exc).__name__,'message':str(exc)[:120]}
            time.sleep(.4*(trial+1))
def main():
    previous=[OLD/'source_kimi'/'selection.json',R5/'writer'/'roster.json']
    veto={x['instance_id'] for p in previous for x in read(p)}
    candidates={x['instance_id']:x for p in [A,B,D] for x in read(p/'selection.json')}
    groups=collections.defaultdict(list)
    for iid in sorted(candidates.keys()-veto,key=lambda i:hashlib.sha256(('r5-terminal-external|'+i).encode()).hexdigest()):
        groups[candidates[iid]['repo']].append(candidates[iid])
    selected=[groups[k][j] for j in range(33) for k in sorted(groups) if j<len(groups[k])]
    assert len(selected)==98 and not veto.intersection(x['instance_id'] for x in selected)
    save(HERE/'roster.json',selected);save(HERE/'roster_lock.json',dict(time=rawproj.stamp(),prior=len(veto),n=len(selected),repos=collections.Counter(x['repo'] for x in selected),inputs={str(p):sha(p) for p in [HERE/'PROTOCOL.md',HERE/'collect.py',HERE/'roster.json',*previous,AP/'acquire.py',AP/'policy.py',AP/'method_lock.json',OLD/'source_kimi'/'acquire_k.py',A/'acquire.py']}))
    fout=[gzip.open(HERE/f'source_{j}.gz','wt',encoding='utf8',compresslevel=3) for j in range(8)]
    fraw=[gzip.open(HERE/f'terminal_{j}.gz','wt',encoding='utf8',compresslevel=3) for j in range(8)]
    receipts=[];ct=collections.Counter()
    with concurrent.futures.ThreadPoolExecutor(10) as pool:
        for j,(project,pair,rc) in enumerate(pool.map(download,selected)):
            if project:write(fout[j%8],project);write(fraw[j%8],pair)
            receipts.append(rc);ct[rc['status']]+=1
            if (j+1)%16==0:print(j+1,ct,flush=True)
    for fp in fout+fraw:fp.close()
    save(HERE/'receipts.json',receipts);save(HERE/'sources_lock.json',dict(time=rawproj.stamp(),n=ct,receipts=sha(HERE/'receipts.json'),data={p.name:sha(p) for glob in ('source_*.gz','terminal_*.gz') for p in HERE.glob(glob)}))
    print(ct,flush=True)
if __name__=='__main__':main()
