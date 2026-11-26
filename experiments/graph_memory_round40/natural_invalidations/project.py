"""Freeze every pre-invalidation state using only released visible observations and lengths."""
from collections import Counter
import gzip,hashlib,json
from pathlib import Path

D=Path(__file__).resolve().parent;W=D.parents[1];R38=W/'graph_memory_round38/edit_ready';R37=W/'graph_memory_round37'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    v=p.read_bytes();return json.loads(gzip.decompress(v) if p.suffix=='.gz' else v)
def save(p,v):
    data=(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode();data=gzip.compress(data,mtime=0) if p.suffix=='.gz' else data
    if p.exists():assert data==p.read_bytes(),p
    else:p.write_bytes(data)
def chunk(rows):
    out=[];group=[];previous=None
    for number,_digest,length,next_witnessed in rows:
        if group and (len(group)==8 or number!=previous+1):out.append(group);group=[]
        group.append((number,length,next_witnessed));previous=number
    if group:out.append(group)
    return [(g[0][0],g[-1][0],sum(r[1] for r in g)+sum(r[2] for r in g[:-1])) for g in out]

def freeze(active):
    ordered=[]
    for path,(last,hits,blocks) in sorted(active.items(),key=lambda item:(-item[1][0],item[0])):
        for start,end,size in blocks:
            rank=len(ordered);ordered.append([path,start,end,size,1+32*min(8,hits)+128//(rank+1)])
    return ordered

def main():
    m=read(R38/'manifest.json')['files'];files=['schedule.json.gz','visible.json.gz']
    for f in files:assert sha(R38/f)==m[f]
    schedule,visible=[read(R38/f) for f in files];out={};count=Counter()
    for rid,v in schedule.items():
        active={};states={};last=-1
        for ev in v['events']:
            i,kind,*args=ev;assert i>last;last=i
            if kind=='reset':active.clear();continue
            if kind=='view':
                path=args[0];old=active.get(path);rows=visible[rid][str(i)];blocks=chunk(rows);assert blocks
                active[path]=(i,1+(old[1] if old else 0),blocks);count['views']+=1
            else:
                assert kind in ('invalidate','snapshot+invalidate')
                states[str(i)]=freeze(active);count['states']+=1
                active.pop(args[0],None)
        out[rid]=states
    save(D/'plans.json.gz',out);save(D/'plan-seal.json',dict(protocol=sha(D/'PROTOCOL_RU.md'),project=sha(Path(__file__)),plans=sha(D/'plans.json.gz'),inputs={n:m[n] for n in files},runs=len(out),counts=dict(count)))
    print('Frozen',len(out),count)
if __name__=='__main__':main()
