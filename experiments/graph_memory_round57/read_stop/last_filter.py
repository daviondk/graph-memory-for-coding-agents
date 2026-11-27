"""Fetch only the final event's Bloom metadata, after consuming the exact prefix."""
from collections import Counter,deque
from run import HERE,INPUTS,load,save
from stop import UNIT,encode,decode,prepare_meta,test_order,bits

def main():
    old=load(HERE/"queries.json.gz");outputs={}
    for panel,(p,_) in INPUTS.items():
        agg={};records={}
        for repo,stream in load(p).items():
            cases={r["t"]:r for r in old[panel][repo]};ids={};freq=Counter();win=deque()
            archive={};records[repo]=[]
            for t,(sha,raw) in enumerate(stream):
                ps=raw if len(raw)<=64 else []
                if t in cases:
                    row=cases[t];js=row["events"];full=row["full_bytes"];a=row["anchor"]
                    trace={"sha":sha}
                    for width in (32,64):
                        unit=width//8
                        if js and len(archive[js[-1]][0])>unit:
                            q=Counter();x=js[-1]
                            for j in js[:-1]:
                                paths,buf=archive[j]
                                for f in decode(buf,len(paths)):q[f]+=UNIT//(len(paths)-1)
                            e,payload=archive[x];w=UNIT//(len(e)-1)
                            mask=int.from_bytes(prepare_meta("bloom"+str(width),e,payload),"little")
                            rank0,least0,exact0=test_order(len(ids),q,lambda _:w,freq,a)
                            ranked,least,exact=test_order(len(ids),q,lambda f:w if mask&bits(f,width)==bits(f,width) else 0,freq,a)
                            prefix=full-len(payload)
                            opts={}
                            for target,cert0,cert in (("ids",least0,least),("score",exact0,exact)):
                                if cert0:
                                    assert rank0==row["rank"]
                                    total=prefix;requests=int(len(js)>1);charged=0
                                else:
                                    assert not cert or ranked==row["rank"]
                                    charged=unit
                                    total=prefix+unit+(0 if cert else len(payload))
                                    requests=int(len(js)>1)+1+int(not cert)
                                opts[target]=(total,requests,charged,cert0 or cert)
                        else:opts={x:(full,int(bool(js)),0,False) for x in ("ids","score")}
                        trace["bloom"+str(width)]=opts
                        for target,(cost,requests,charged,cert) in opts.items():
                            g=agg.setdefault(str(width)+"_"+target,Counter())
                            g.update(dict(queries=1,bytes=cost,commands=requests,with_commands=cost+requests,
                                          meta=charged,filtered=charged>0,saved=cost<full,tied=cost==full,worse=cost>full,
                                          avoided=cert,oracle_gain=max(0,full-cost),oracle_gain_with_commands=max(0,full+int(bool(js))-(cost+requests))))
                    records[repo].append(trace)
                codes=[ids.setdefault(f,len(ids)) for f in ps]
                if len(win)==32:freq.subtract(win.popleft())
                freq.update(codes);win.append(codes)
                if len(codes)>=2:archive[t]=(codes,encode(codes))
        outputs[panel]={k:dict(v) for k,v in agg.items()}
        save(HERE/("last-"+panel+".json.gz"),records,False)
    save(HERE/"last-results.json",outputs,False)
    for panel,z in outputs.items():print(panel,{k:(v["bytes"],v["saved"],v["worse"],v["filtered"],v["oracle_gain"],v["commands"]) for k,v in z.items()})
if __name__=="__main__":main()
