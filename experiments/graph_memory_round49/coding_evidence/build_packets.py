"""Rank only the observations emitted by the prior calibration session."""
import collections,hashlib,json,math,re,subprocess
from pathlib import Path
from prepare_source import D,P
def key(x):return tuple(x)
def digest(b):return hashlib.sha256(b).hexdigest()
def terms(text):
    text=re.sub(r"([a-z])([A-Z])",r"\1 \2",text)
    return [w.lower() for w in re.findall(r"[A-Za-z]{2,}",text)]
def main():
    meta=json.loads((D/'registration.json').read_bytes())
    run=subprocess.run(['docker','run','--rm','--network','none','-i',meta['image'],'python','-'],input=(D/'historical_session.py').read_bytes(),capture_output=True)
    if run.returncode:raise RuntimeError(run.stderr.decode()[-1800:])
    graph=json.loads(run.stdout);(D/'history.json').write_text(json.dumps(graph,sort_keys=True,indent=2)+'\n',encoding='utf8')
    nodes=sorted(key(z) for z,c in graph['visits']);assert len(nodes)>=4 and graph['calls']
    docs={};raws={}
    for a in nodes:
        path,line,name=a
        lines=(P/'repository'/path).read_bytes().decode().splitlines(keepends=True)
        text=''.join(lines[line-1:line+9])
        head=f'{path}:{line}  {name}\n'
        raws[a]=(head+text).encode()[:399].decode('utf8','ignore')+'\n'
        docs[a]=terms(text)+2*terms(path+' '+name)
    query=collections.Counter(terms((P/'problem.txt').read_text(encoding='utf8')))
    df=collections.Counter(w for a in nodes for w in set(docs[a]))
    mean=sum(map(len,docs.values()))/len(nodes);n=len(nodes)
    bm={}
    for a in nodes:
        d=docs[a];freq=collections.Counter(d)
        bm[a]=sum(q*math.log1p((n-df[w]+.5)/(df[w]+.5))*freq[w]*2.2/(freq[w]+1.2*(.25+.75*len(d)/mean)) for w,q in query.items() if freq[w])
    edges=collections.defaultdict(dict)
    for u,v,c in graph['calls']:edges[key(u)][key(v)]=math.log1p(c)
    z=sum(v+.01 for v in bm.values());prior={a:(bm[a]+.01)/z for a in nodes};rank=prior.copy()
    for _ in range(200):
        lost=sum(rank[a] for a in nodes if not edges[a]);r={a:(.4+.6*lost)*v for a,v in prior.items()}
        for a in nodes:
            if edges[a]:
                mass=.6*rank[a]/sum(edges[a].values())
                for v,t in edges[a].items():r[v]+=mass*t
        if max(abs(r[a]-rank[a]) for a in nodes)<1e-13:
            rank=r;break
        rank=r
    selected={k:sorted(nodes,key=lambda a:(-scores[a],a)) for k,scores in [('graph',rank),('flat',bm)]}
    packets={name:''.join(raws[a] for a in order[:4]).encode() for name,order in selected.items()}
    cap=min(len(x) for x in packets.values())
    for name,buf in packets.items():(P/(name+'.txt')).write_bytes(buf[:cap].decode('utf8','ignore').encode())
    (P/'none.txt').write_bytes(b'')
    assert (P/'flat.txt').stat().st_size==(P/'graph.txt').stat().st_size
    result={'graph_size':[len(nodes),len(graph['calls'])],'successful_actions':graph['actions'],'memory_bytes':cap,'chosen':{name:order[:4] for name,order in selected.items()},'digest':{name:digest((P/(name+'.txt')).read_bytes()) for name in ('graph','flat','none')},'history':digest((D/'history.json').read_bytes()),'builder':digest(Path(__file__).read_bytes())}
    (D/'packet-seal.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf8')
    print(result['graph_size'],result['successful_actions'],cap,'same packets',result['digest']['graph']==result['digest']['flat'])
if __name__=='__main__':main()
