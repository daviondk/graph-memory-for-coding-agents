"""Join only current public file coordinates, opened paths and visibility to hashed cache keys."""
from pathlib import Path
import sys,hashlib,json,gzip,posixpath
D=Path(__file__).resolve().parent
W=D.parents[1];OLD=W/'graph_memory_round49/cache_controls';sys.path.insert(0,str(OLD))
def put(name,value):
    b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    (D/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith('.gz') else b)

def read(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):
    s=s.replace('\\','/').strip()
    return posixpath.normpath(s).removeprefix('./')
def digest(s):return hashlib.sha256(s.encode()).hexdigest()[:16]

def main():
    from experiment import panels
    pp=panels();pan={q:(p,v) for p,rs in pp.items() for q,v in rs.items()}
    oldinv=read(W/'graph_memory_round48/embedding_reuse/inventory.json.gz')
    keys=read(W/'graph_memory_round48/cache_admission/key-digests.json.gz')
    r49=read(W/'graph_memory_round49/long_gpu/transfer-inputs.json.gz')
    with gzip.open(W/'memory_session5/serbench/upstream/data/cal500/items.jsonl.gz','rt',encoding='utf8') as f:
        rows={};hashes={}
        for item in map(json.loads,f):
            q=item['state_id']
            if q not in pan:continue
            p,(d,repo,total,prev)=pan[q]
            raw=sorted(item['candidate_evidence'],key=lambda x:x['evidence_id'])
            ids=[(keys[str(v[0])],v[1]) for v in oldinv[q]['docs']] if p=='R48' else r49[q]['docs']
            assert len(ids)==len(raw)
            opened={norm(s) for s in item['opened_files'] if isinstance(s,str)}
            rt={};order=[]
            for c,(key,n) in zip(raw,ids):
                path=norm(c['source_path']);path_id=digest(path)
                assert hashes.setdefault(path_id,path)==path
                # No excerpt, file name, command string or next-state field is retained.
                parts=path.lower().split('/')
                test=any(t in ('test','tests','testing') for t in parts) or parts[-1].startswith('test_') or parts[-1].endswith('_test.py')
                val=[n,path_id,int(c.get('line_start') or 0),int(c.get('line_end') or 0),int(test),int(path.lower().endswith('.py')),int(c.get('observed_by_state',False))]
                assert d[key]==n
                if key in rt:
                    assert rt[key][1]==path_id
                    rt[key][-1]=max(rt[key][-1],val[-1])
                else:rt[key]=val;order.append(key)
            assert order==list(d)
            inpacket=total-sum(v[1] for v in ids)
            within=total-inpacket-sum(v[0] for v in rt.values())
            rows[q]=dict(repo=repo,panel=p,prev=prev,total=total,within=within,opened=sorted({digest(s) for s in opened}),
                         docs=rt,order=order)
    assert len(rows)==484
    put('inputs.json.gz',rows)
    print(len(rows),'states,', len(hashes),'distinct observed file paths,',sum(bool(z['prev']) for z in rows.values()),'transitions')


if __name__=='__main__':main()

