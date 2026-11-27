"""Independent logical accounting for the two main competing LRU representations."""
import argparse
from collections import defaultdict
from pathlib import Path

from run_lazy import HERE,cases,load,prepare,save


def width(x):
    return max(1,(x.bit_length()+6)//7)


class Ledger:
    def __init__(self,limit,joint,fence):
        self.limit,self.joint,self.fence=limit,joint,fence
        self.order=[]
        self.entries={}
        self.size=0
        self.known=set()

    def lookup(self,kind,key):
        ident=(kind,key)
        if ident not in self.entries:return None
        self.order.remove(ident);self.order.append(ident)
        return self.entries[ident]

    def put(self,kind,k,n,anchor,refresh):
        key=(kind,k)
        charge=1+width(k+1)+width(n)+n
        if key in self.entries:
            self.size-=self.entries[key][0]
            if refresh or charge>self.limit:self.order.remove(key)
            del self.entries[key]
        if charge>self.limit:return
        if key not in self.order:self.order.append(key)
        self.entries[key]=(charge,n,anchor);self.size+=charge
        while self.size>self.limit:
            victim=self.order.pop(0);self.size-=self.entries.pop(victim)[0]

    def append(self,j,files):
        if not self.joint:return
        for f in files:
            record=self.entries.get(("list",f))
            if record is not None:self.put("list",f,record[1]+width(j),None,False)

    def query(self,f,all_ids,hot,bytes_per_event):
        counts=[0]*12
        pres=any(j<self.fence for j in all_ids)
        late=[j for j in all_ids if j>=self.fence]
        hot_here=set(late)&hot
        counts[10]=len(hot_here)
        if f not in self.known or len(late)>len(hot_here):
            prior=self.lookup("list",f) if self.joint else None
            length=sum(map(width,all_ids))
            if prior is None:
                counts[0]=1;counts[2]=length
            else:
                assert prior[1]==length
                counts[8]=1
            pending=[]
            for j in all_ids:
                if j in hot_here:continue
                match=self.lookup("body",j)
                if match is None:pending.append(j)
                else:
                    counts[5]+=1
                    if match[2]!=f:
                        counts[6]+=1;counts[7]+=bytes_per_event[j]
            counts[1]=(len(pending)+399)//400
            counts[3]=sum(bytes_per_event[j] for j in pending)
            counts[4]=len(pending)
            for j in pending:self.put("body",j,bytes_per_event[j],f,True)
            if self.joint:self.put("list",f,length,None,True)
            if not pres:self.known.add(f)
        counts[-1]=self.size
        return counts


def run():
    raw=load(HERE/"runs.json.gz")["cases"]
    report={}
    for group,repo,schedule,stream in cases():
        key=group+"/"+repo
        logged=raw[key]
        ops,oracle=prepare(stream,schedule)
        assert oracle==logged["oracle"]
        fence=logged["fence"]
        facts=defaultdict(list);after=defaultdict(list);weight=[]
        handles={f"B8-{name}-{size}":Ledger(size,name=="joint",fence)
                 for size in (1024,4096) for name in ("events","joint")}
        q=0
        for op in ops:
            if op[0]=="w":
                _,j,sha,files=op
                weight.append(sum(map(width,files)))
                for f in files:
                    facts[f].append(j)
                    if j>=fence:after[f].append(j)
                if j>=fence:
                    for h in handles.values():h.append(j,files)
            elif len(weight)>=fence:
                f=op[1]
                hot={j for history in after.values() for j in history[-8:]}
                for name,h in handles.items():
                    work=h.query(f,facts[f],hot,weight)
                    assert work==logged["reads"][name][q],(key,q,name,work,logged["reads"][name][q])
                q+=1
        assert len(logged["ids"])==q
        report[key]=dict(queries=q,checked=q*len(handles))
    return report


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--verify",action="store_true")
    verify=parser.parse_args().verify
    report=run()
    if verify:assert report==load(HERE/"audit.json")
    else:save(HERE/"audit.json",report)
    print(sum(r["checked"] for r in report.values()),"per-query records match independent membership and LRU replay.")
