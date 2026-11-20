"""Build and persist every transition before grading; query panel is never loaded here."""
import base64,json,struct
from collections import Counter
from util12 import D,R10,load,dump,sha,event_raw
from store12 import ARMS,initial,update
SEEDS=[0,7,19,31];BS=[64,256]
def frames(events,n):
    raw=bytearray();offset=[None]*n;snapshots=[]
    for ev in events:
        block=event_raw(ev['words']);size=4+len(block)
        assert size==ev['archive_bytes']
        current=len(raw);snapshots.append((offset.copy(),size,current))
        raw+=struct.pack('<I',len(block))+block;offset[ev['i']]=current
    return bytes(raw),snapshots
def chunks(raw,position):
    size=struct.unpack_from('<I',raw,position)[0]
    return json.loads(raw[position+4:position+4+size]),4+size
def pages(regions,unit):return len({j for a,b in regions for j in range(a//unit,(b-1)//unit+1)})*unit
def main():
    local={};assert not (D/'state_seal.json').exists()
    for path in sorted((D/'events').glob('*.gz')):
        evs=load(path);t=evs['task'];events=evs['events'];n=evs['n'];archive,meta=frames(events,n)
        arc=D/'archive'/f'{t}.bin';arc.parent.mkdir(exist_ok=True);arc.write_bytes(archive);local[arc]=sha(arc)
        rows=[]
        for b in BS:
            for s in SEEDS:
                for gate in (0,1):
                    for arm in ARMS:
                        raw=initial(arm,n,b,s)
                        for ev,(offs,size,end) in zip(events,meta):
                            reads=[];r=ev['i']
                            def fetch(i):
                                pos=offs[i];assert pos is not None and pos<end
                                values,amount=chunks(archive,pos);reads.append([i,pos,amount]);return values
                            new,rg,info=update(raw,r,ev['words'],fetch,bool(gate))
                            assert len(new)==len(raw)==n*b
                            logical=sum(y-x for x,y in rg)
                            delta=sum(x!=y for x,y in zip(new,raw))
                            assert delta<=logical
                            stats=dict(**info,emitted=logical,byte_changes=delta,pages64=pages(rg,64),pages4096=pages(rg,4096),replay_bytes=sum(o[2] for o in reads),arch_append=size,archive_so_far=end+size,offset_bytes=4*n,table_write=4,cow_index_peak=n*b+logical,whole_copy_index_peak=n*b*(2 if logical else 1))
                            rows.append([ev['step'],ev['phase'],b,s,gate,arm,base64.b64encode(new).decode(),rg,reads,stats])
                            raw=new
        out=D/'states'/path.name;dump(out,dict(task=t,n=n,rows=rows));local[out]=sha(out);local[path]=sha(path)
    for name in ['PROTOCOL.md','ADDITIONAL_CONTROL.md','prepare.py','store12.py','util12.py','write.py','input_receipt.json']:
        local[D/name]=sha(D/name)
    ext={name:sha(R10/name) for name in ['structures.py','common.py','reader.py']}
    dump(D/'state_seal.json',dict(local={p.relative_to(D).as_posix():h for p,h in local.items()},r10=ext))
if __name__=='__main__':main()