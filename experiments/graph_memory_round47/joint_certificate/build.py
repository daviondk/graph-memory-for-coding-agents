"""Freeze the metadata-only sample, independently of joint packet outcomes."""
from pathlib import Path
from itertools import combinations
from collections import defaultdict
from hashlib import sha256
import gzip,json,sqlite3,struct
from geometry import INF
D=Path(__file__).resolve().parent
def dig(p):return sha256(p.read_bytes()).hexdigest()
def save(name,dat):
    raw=(json.dumps(dat,sort_keys=True,separators=(',',':'))+'\n').encode()
    (D/name).write_bytes(gzip.compress(raw,mtime=0) if name.endswith('.gz') else raw)
def load(name):
    b=(D/name).read_bytes();return json.loads(gzip.decompress(b) if name.endswith('.gz') else b)
def db(path):return sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
def main():
    r=load('registration.json');w=D.parents[1]
    assert dig(D/'PROTOCOL_RU.md')==r['protocol']
    for key,path in r['path'].items():assert dig(w/path)==r['sha256'][key],key
    rd,ix,view=(db(w/r['path'][k]) for k in ('reader','intervals','indices'))
    data={}
    for q,tr in rd.execute('select q,trajectory_hash from query order by q'):
        nodes=rd.execute('select id,tokens,utility from node where q=? order by rank',(q,)).fetchall()
        head=[];cost=0
        while len(head)<len(nodes) and cost+nodes[len(head)][1]<=1024:
            ident,c,_=nodes[len(head)];cost+=c;head.append(ident)
        tail=[[n,c,round(u*2**32)] for n,c,u in nodes[len(head):]];cap=2048-cost
        assert sum(abs(u)+(1<<31) for _,_,u in tail)<(1<<62)
        source=defaultdict(set)
        for ident,s in rd.execute('select distinct id,source from span where q=?',(q,)):source[s].add(ident)
        eligible={n for n,c,u in tail if c<=cap}
        opt={s:v&eligible for s,v in source.items()}
        limits={s:[lo,hi] for s,lo,hi in ix.execute('select source,lo,hi from valid where q=?',(q,))}
        order=sorted(combinations(sorted(source),2),key=lambda p:sha256(f"470531|{q}|{p[0]}|{p[1]}".encode()).digest())
        prim=order[:32];rest=order[32:];pairs=[(*p,'primary') for p in prim]
        for label in ('overlap','disjoint'):
            extra=[(a,b) for a,b in rest if opt[a] and opt[b] and bool(opt[a]&opt[b])==(label=='overlap')]
            pairs.extend((*p,label) for p in extra[:8])
        key=sorted(source)[0]
        raw=view.execute('select p.members from edge e join packet p on p.id=e.packet_id where q=? and source=? and start<=0 order by start desc limit 1',(q,key)).fetchone()[0]
        original=[v for v, in struct.iter_unpack('<H',raw)]
        assert original[:len(head)]==head
        chosen=set(original[len(head):]);old=''.join(str(int(n in chosen)) for n,c,u in tail)
        data[q]=dict(tr=tr,cap=cap,head=head,tail=tail,source={s:sorted(v) for s,v in source.items()},
            limits=limits,old=old,pairs=pairs,available=len(order),all_optional_overlap=sum(bool(opt[a]&opt[b]) for a,b in order),
            all_disjoint_active=sum(bool(opt[a] and opt[b] and not opt[a]&opt[b]) for a,b in order))
    assert len(data)==40
    save('sample.json.gz',data);save('sample-seal.json',{'sha256':dig(D/'sample.json.gz'),'n':len(data),'primary':sum(sum(p[2]=='primary' for p in x['pairs']) for x in data.values()),'generator':dig(Path(__file__))})
    print(load('sample-seal.json'))
if __name__=='__main__':main()
