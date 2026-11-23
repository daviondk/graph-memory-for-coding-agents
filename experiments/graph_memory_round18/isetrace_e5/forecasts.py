"""Reconstitute original requests, with native float64 dot and stable ID ties."""
from collections import defaultdict
import gzip,hashlib,json,sqlite3,sys
import numpy as np
from inventory import ROOT,OFF,CACHE,db,key,load,put,pilot,split,audit_ids
from project import reqs,rank
from graph_memory.retrieval.methods.flat.dense import DenseTaskRetriever

class Lookup:
    def __init__(self,conn,prec):
        self.conn=conn;self.prec=prec
    def encode(self,texts,**opts):
        assert opts==dict(batch_size=64,normalize_embeddings=True,show_progress_bar=False)
        keys=list(map(key,texts));uk=list(set(keys));vec={}
        for i in range(0,len(uk),400):
            block=uk[i:i+400];marks=','.join('?' for _ in block)
            for k,v in self.conn.execute('select k,v from vectors where prec=? and k in ('+marks+')',[self.prec,*block]):
                vec[k]=np.frombuffer(v,dtype='<f4')
        return np.stack([vec[k] for k in keys])
def plan():
    names=['PROTOCOL_RU.md','project.py','inventory.py','encode.py','forecasts.py','inventory.json','throughput.json']
    put(ROOT/'plan-seal.json',{n:pilot.sha(ROOT/n) for n in names})
def forecast():
    for n,h in load(ROOT/'plan-seal.json').items():assert pilot.sha(ROOT/n)==h
    mode=load(ROOT/'throughput.json')['primary_precision'];conn=db()
    tokenizer=pilot.Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json'))
    audit=audit_ids();checks={}
    for name,prec,audit_only in [('main',mode,False)]+([('audit-fp32','fp32',True)] if mode=='mixed' else []):
        retriever=DenseTaskRetriever(model_name=str(CACHE),device='cuda',encoder=Lookup(conn,prec))
        cnt=0;seen=set()
        for i in range(8):
            lines=[]
            for p in sorted((CACHE/'projection').glob(f'{i}-*.json.gz')):
                t=p.name[2:-8]
                if audit_only and t not in audit:continue
                row=load(p);assert t==row['t']
                requests=reqs(row)
                src={c.item_id:c for c in requests[0].candidates}
                meta={k:c.metadata for k,c in src.items()}
                context=dict(fields=row['fields'],tokenizer=tokenizer,offset_by_event={})
                for r in requests:
                    assert r.task_id not in seen;seen.add(r.task_id)
                    rr=pilot.assemble_ranked_result(request=r,method='dense',ranked_nodes=retriever.rank(r),top_k=len(src),latency_ms=0,retrieved_edges=[],native_trace=None).ranked_nodes
                    arms={a:[n.node_id for n in pilot.pack(rr,meta,2048,a)] for a in ('prefix','skip','value','related')}
                    extra=rank.clipped(rr,src,pilot.pack(rr,meta,2048,'prefix'),'provenance',context)
                    arms['clip']=arms['prefix']+([extra.node_id] if extra is not None else [])
                    lines.append(dict(q=r.task_id,t=t,rr=[n.model_dump() for n in rr],partial=extra.model_dump() if extra is not None else None,arms=arms))
                    cnt+=1
            n=f'forecasts-{name}-{i}.json.gz';put(ROOT/n,lines)
            checks[n]=pilot.sha(ROOT/n)
        expect={q for q,t in split().items() if not audit_only or t in audit}
        assert seen==expect
        print(name,cnt,flush=True)
    put(ROOT/'forecast-seal.json',dict(plan=pilot.sha(ROOT/'plan-seal.json'),forecasts=checks))
if __name__=='__main__':{'plan':plan,'run':forecast}[sys.argv[1]]()
