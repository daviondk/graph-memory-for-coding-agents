"""Verify literal byte frames on synthetic messages and length/equality surrogates on trace frames."""
from collections import Counter
from random import Random
from cache import ARMS,Cache,encode,decode
from compact import FileCache,serialize,unpack
from replay import HERE,PAST,load,save

def check_plain(c,strings,expected_size):
    data=encode(c,strings);assert len(data)==expected_size
    paths,keys=c.ordered()
    p,rows=decode(data)
    assert p==paths
    assert rows==[(k[0],k[1],strings[c.cells[k].uid],c.cells[k].protected) for k in keys]

def check_compact(c,strings,expected_size):
    raw=serialize(c,strings);assert len(raw)==expected_size
    p,rows=unpack(raw)
    paths=sorted(c.files,key=c.files.get,reverse=True)
    assert paths==p
    expected=[]
    for path in paths:
        keys=sorted((k for k in c.cells if k[0]==path),key=lambda k:c.cells[k].tick,reverse=True)
        expected.extend((key[0],key[1],strings[c.cells[key].uid]) for key in keys)
    assert expected==rows

def synthetic():
    rng=Random(58017);literal={i:x for i,x in enumerate((b"\n",b"item\n",b"x"*137,b"\0\xfe",b"value"))}
    lookup=list(literal);frames=0
    for scheme in (*ARMS,"packed/file","packed/all","packed/none"):
        c=FileCache(256,scheme.split("/")[1]) if scheme.startswith("packed") else Cache(scheme,256)
        for tick in range(250):
            if tick%61==0:c.clear()
            p=rng.choice(("a.py","long/path.py","пример.py"));start=rng.randint(0,12000)
            obs=[(start+n,uid,len(literal[uid])) for n,uid in enumerate(rng.choices(lookup,k=rng.randint(2,19)))]
            if tick%5==4:obs=last;p=last_p
            last=obs;last_p=p
            used=c.update(p,obs)[0]
            (check_compact if scheme.startswith("packed") else check_plain)(c,literal,used);frames+=1
    return frames

def actual():
    n=0;rows=load(HERE/"windows.json.gz");extra=load(HERE/"compact-windows.json.gz")
    for tr in load(PAST/"prefixes.json.gz"):
        counts=Counter();strings={}
        plain=[Cache(a,16384) for a in ("file","file_intern")]
        modes=("all","file","none");compact=[FileCache(16384,g) for g in modes]
        for t,e in enumerate(tr["events"]):
            if e[0]=="barrier":
                for c in plain+compact:c.clear()
            if len(e)!=3:continue
            _,p,obs=e
            for line,uid,size in obs:
                if uid not in strings:
                    strings[uid]=counts[size].to_bytes(size,"little");counts[size]+=1
                assert len(strings[uid])==size
            for c,k in zip(plain,("16384_12_file","16384_12_file_intern")):
                assert c.serve(p,obs)==rows[n]["score"][k]
                used=c.update(p,obs)[0]
                assert used==rows[n]["state"][k][0]
                check_plain(c,strings,used)
            for c,m in zip(compact,modes):
                k="16384_"+m
                assert c.serve(p,obs)==extra[n]["score"][k]
                used=c.update(p,obs)[0]
                assert used==extra[n]["occupancy"][k][0]
                check_compact(c,strings,used)
            assert (tr["actor"],tr["issue"],t)==(rows[n]["actor"],rows[n]["issue"],rows[n]["at"])
            n+=1
    assert n==len(rows)==len(extra)
    return n

if __name__=="__main__":
    syn=synthetic();real=actual()
    out=dict(literal_roundtrips=syn,windows=real,fixed_surrogate_roundtrips=2*real,packed_surrogate_roundtrips=3*real)
    save(HERE/"frame-audit.json",out,False);print(out)
