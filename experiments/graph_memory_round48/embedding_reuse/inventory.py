"""Build salted, non-reversible public metadata inventory without running code from traces."""
from pathlib import Path
from collections import defaultdict,Counter
import gzip,json,hashlib,struct,itertools
D=Path(__file__).resolve().parent;W=D.parents[1]
BASE=W/'graph_memory_round47/facet_reader';CONF=W/'graph_memory_round47/facet_confirmation';R45=W/'graph_memory_round45/qwen_panel214'
CACHE=Path('D:/CodexResearch/x20-r39-embedding-runtime');TOK=CACHE/'runs-r40-lexical-native-input/matched-tokens.json.gz'
PUB=W/'memory_session5/serbench/upstream/data/cal500'
PROTO='707a6581731d80ca37481a867277bc2d2f0bcbf7f3e26c8bfbd21e29cc1ac741'
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(x):return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def write(k,v):
    b=canonical(v)+b'\n';(D/k).write_bytes(gzip.compress(b,mtime=0,compresslevel=4) if k.endswith('.gz') else b)
def signed(p,k):
    assert sha(p/k)==read(p/'manifest.json')['files'][k];return read(p/k)
def key(config,toks):return digest(bytes.fromhex(config)+struct.pack('<I',len(toks))+struct.pack('<'+'I'*len(toks),*toks))
def predecessors(z,rows,group):
    hist=z['hist'];uniq={}
    if not z['run_known']:return []
    for q in group:
        old=rows[q]['hist']
        if old and len(old)<len(hist) and hist[:len(old)]==old:
            k=tuple(old)
            if k not in uniq or digest('r48-representative'+q)<digest('r48-representative'+uniq[k]):uniq[k]=q
    return [q for h,q in sorted(uniq.items(),key=lambda v:len(v[0]))]
def main():
    assert sha(D/'PROTOCOL_RU.md')==PROTO
    ps=signed(BASE,'panels.json');ns={q:k for k in ('dev','outside') for q in ps[k]};assert len(ns)==305
    signed45=signed(R45,'matched-token-seal.json');assert sha(TOK)==signed45['forecasts_input'];t=read(TOK)
    src=signed(R45,'gpu-seal.json')['inputs'];nspec=dict(weights=src['weights'],runtime=src['exe'],preprocess=src['preprocessing'],tokenizer_gguf=src['weights'],visible_limit=511,eos=151643,
           device='NVIDIA RTX 3090 CUDA',format='4096-float32 normalized, pooling last',serialization='Qwen3 path LF excerpt, uint32 little-endian, trailing EOS',microbatch=2048,parallel=4)
    ns0=digest(canonical(nspec));alt=digest(canonical({**nspec,'visible_limit':510}));assert ns0!=alt
    rows={};lookup={};actual={};altkeys=set();timestamps=Counter();ordinal={k:{} for k in ('token','text','eid','path','span','event')}
    def ix(k,v):
        d=ordinal[k]
        if v not in d:d[v]=len(d)
        return d[v]
    with gzip.open(PUB/'items.jsonl.gz','rt',encoding='utf8') as stream:
        for z in map(json.loads,stream):
            q=z['state_id']
            if q not in ns:continue
            item=t['states'][q];candidates=sorted(z['candidate_evidence'],key=lambda c:c['evidence_id'])
            assert item['ids']==[v['evidence_id'] for v in candidates];docs=[]
            for c,k in zip(candidates,item['doc']):
                if k not in lookup:
                    arr=t['tokens'][k][1];h=key(ns0,arr)
                    if h in actual:assert actual[h]==arr
                    else:actual[h]=arr
                    hk=key(alt,arr);assert h!=hk;altkeys.add(hk);lookup[k]=(ix('token',h),len(arr))
                token,n=lookup[k];path=c['source_path'];span=[path,c.get('line_start'),c.get('line_end')];e=c['evidence_id']
                txt=path+'\n'+c['content_excerpt'];assert digest(txt)==k
                docs.append([token,n,ix('text',k),ix('eid',digest(e)),ix('path',digest(path)),ix('span',digest(canonical(span)))])
            events=z['trajectory_prefix'];runs={e.get('run_id') for e in events};known=len(runs)==1 and bool(next(iter(runs),None))
            g=digest(canonical([ns[q],z['repo'],z['instance_id'],z.get('base_commit'),next(iter(runs)) if known else q]));st=[e.get('step_id') for e in events];times=[e.get('timestamp') for e in events]
            timestamps['events']+=len(times);timestamps['nonempty_event_time']+=sum(bool(v) for v in times)
            rows[q]=dict(panel=ns[q],repo=z['repo'],group=g,run_known=bool(known),step=st[-1] if st else -1,
                 monotonic=all(isinstance(v,int) for v in st) and all(x<y for x,y in zip(st,st[1:])),
                 hist=[ix('event',digest(canonical(e))) for e in events],docs=docs,querylen=len(t['tokens'][item['three']][1]))
    assert set(rows)==set(ns) and not altkeys&set(actual)
    groups=defaultdict(list)
    for q,z in rows.items():groups[z['group']].append(q)
    pre={q:predecessors(z,rows,groups[z['group']]) for q,z in rows.items()}
    pairs=[(a[-1],q) for q,a in pre.items() if a];gs=sorted(pairs,key=lambda x:digest('r48-gpu-pair'+x[0]+'/'+x[1]))
    seen=set();picked=[]
    for x,y in gs:
        if rows[y]['repo'] in seen:continue
        picked.append([x,y]);seen.add(rows[y]['repo'])
        if len(picked)==8:break
    write('inventory.json.gz',rows);write('predecessors.json',pre);write('gpu-panel.json',picked)
    write('input-seal.json',dict(program=sha(Path(__file__)),protocol=PROTO,inventory=sha(D/'inventory.json.gz'),predecessors=sha(D/'predecessors.json'),gpu_panel=sha(D/'gpu-panel.json'),
             source=sha(TOK),r45=sha(R45/'manifest.json'),r47=sha(BASE/'manifest.json'),hardware=sha(CONF/'manifest.json'),config=nspec,namespace=ns0,
             changed_namespace=alt,changed_key_overlap=len(altkeys&set(actual)),keys=len(actual),full_text=len(lookup),timestamp=dict(timestamps),groups=len(groups),eligible_pairs=len(pairs)))
    print('Extracted',len(rows),'states,',len(groups),'trajectory scopes,',len(pairs),'eligible adjacent pairs and',len(picked),'prospective GPU pairs.')
if __name__=='__main__':main()

