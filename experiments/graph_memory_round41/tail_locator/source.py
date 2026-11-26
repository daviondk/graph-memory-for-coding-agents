"""Freeze display-only tail hashes and all covered views before consulting any backend payload."""
from bisect import bisect_right
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
import gzip
import json
import re
import sys

import pyarrow.parquet as pq

D=Path(__file__).resolve().parent;W=D.parents[1];RAW=Path('D:/CodexResearch/x20-r31-handoff')
FID=W/'graph_memory_round40/view_fidelity';sys.path.insert(0,str(FID))
from detector import gate
from examine import display
def h(s):return sha256(s.encode()).hexdigest()
def digest(p):return sha256(p.read_bytes()).hexdigest()
def read(p):
    raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def save(name,x):
    p=D/name;data=(json.dumps(x,sort_keys=True,separators=(',',':'))+'\n').encode()
    if p.suffix=='.gz':data=gzip.compress(data,mtime=0)
    if p.exists():assert data==p.read_bytes(),p
    else:p.write_bytes(data)
    return digest(p)
def signed(p):
    r=read(p.parent/'manifest.json');assert digest(p)==r.get('files',r)[p.name];return read(p)
def parse(ob):
    if not isinstance(ob.get('path'),str) or not isinstance(ob.get('content'),list):return None
    try:
        rows,headers,_=display(ob)
        if not rows or not headers:return None
        _,desc=gate(ob)
    except (ValueError,AssertionError):return {'rows':0,'status':'unparseable','tail':[]}
    cut=desc['cut'];status='uncut';tail=[]
    if cut is not None:
        addresses=sorted(n for n in rows if n>=cut)
        if headers!=1 or len(desc['markers'])!=1 or not addresses or any(n!=addresses[0]+i for i,n in enumerate(addresses)):status='ambiguous_display'
        else:
            status='tail';tail=[[len(rows[n].encode()),h(rows[n])] for n in addresses]
    return dict(rows=len(rows),status=status,tail=tail)
def request_range(action):
    vr=action.get('view_range')
    if vr is None or vr==[]:return ['eof',None]
    if not isinstance(vr,list) or len(vr)!=2 or any(type(x)is not int for x in vr):return ['unknown',None]
    low,end=vr
    if low<1:return ['unknown',None]
    if end==-1:return ['eof',None]
    return ['finite',end] if end>=low else ['unknown',None]
def main():
    demand=W/'graph_memory_round37/edit_demand';visdir=W/'graph_memory_round37/code_visibility'
    cs=signed(visdir/'events.json.gz');pairs=signed(demand/'followup.json.gz');known=signed(W/'graph_memory_round40/span_updates/scored.json.gz')
    assert len(pairs)==4117 and len(known)==2696
    prior={(x['rid'],x['receipt'],x['view']) for x in known}
    mandatory={(x['rid'],x['prev'],x['edit']):['known' if (x['rid'],x['edit'],x['prev']) in prior else 'novel',x['prefix']] for x in pairs}
    assert Counter(v[0] for v in mandatory.values())=={'known':2696,'novel':1421}
    reg={(rid,e[0]) for rid,o in cs.items() for e in o['events'] if e[1]=='read'}
    bars={rid:[e[0] for e in o['events'] if e[1]=='barrier'] for rid,o in cs.items()}
    assert len(reg)==19655 and len(cs)==3307
    requests={};receipts={};writes=defaultdict(lambda:defaultdict(list));views={};lookup={};raw_counts=Counter()
    hashes=read(RAW/'files.json');assert digest(RAW/'files.json')==signed(W/'graph_memory_round38/edit_ready/input-seal.json')['source_manifest']
    for entry in hashes['events']:
        p=RAW/entry['file'];assert digest(p)==entry['sha']
        for b in pq.ParquetFile(p).iter_batches(columns=['run_id','event_index','event_type','event_json','source_json_valid'],batch_size=256):
            runs,ats,kinds,ev,valid=b.columns
            for i,(r,at,k,ok) in enumerate(zip(runs.to_pylist(),ats.to_pylist(),kinds.to_pylist(),valid.to_pylist())):
                if k not in ('ActionEvent','ObservationEvent') or not ok:continue
                if r not in lookup:lookup[r]=h(r)
                rid=lookup[r]
                if rid not in cs:continue
                raw=json.loads(ev[i].as_py()).get('raw',{});acting=k=='ActionEvent'
                part=raw.get('action' if acting else 'observation',{});cmd=part.get('command');path=part.get('path')
                if not isinstance(path,str) or not cmd or part.get('kind') not in ('FileEditorAction','FileEditorObservation'):continue
                ident=(rid,raw.get('id' if acting else 'action_id'),raw.get('tool_call_id'))
                if not ident[1]:continue
                path_hash=h(path)
                if acting:
                    if cmd=='view':requests[ident]=[at,path_hash,request_range(part)]
                    else:writes[rid][path_hash].append([at,ident,cmd])
                elif cmd=='view' and not part.get('is_error'):
                    raw_counts['successful_view_receipts']+=1;parsed=parse(part)
                    if parsed:views[rid,at]=[path_hash,ident,parsed]
                elif cmd=='str_replace' and not part.get('is_error'):
                    receipts[ident]=[at,path_hash]
    assert reg<=set(views)
    for bypath in writes.values():
        for paths in bypath.values():paths.sort(key=lambda x:x[0])
    out=[];reqs=Counter();matched=set();census=Counter();tails={}
    for (rid,view),(path,identity,parseout) in sorted(views.items()):
        op=requests.get(identity);form=op[2] if op and op[0]<view and op[1]==path else ['unknown',None]
        parsed=parseout['status']!='unparseable'
        ws=writes[rid].get(path,[]);i=bisect_right(ws,view,key=lambda e:e[0])
        ack=None;attempt=ws[i][0] if i<len(ws) else None
        if i<len(ws) and ws[i][2]=='str_replace':
            rr=receipts.get(ws[i][1])
            if rr and rr[1]==path and rr[0]>ws[i][0]:ack=rr[0]
        cohort=mandatory.get((rid,view,ack),['extra','unlabeled'])
        # Every primary pairing is checked separately below, even in case the wider next-write rule differs.
        if cohort[0]!='extra':matched.add((rid,view,ack))
        run=ridx=rid
        if parseout['tail']:
            t=parseout['tail'];serial=json.dumps(t,separators=(',',':'));key=h(serial);tails[key]=t
        else:key=None
        barriers=bars[rid];opaque=bool(attempt is not None and bisect_right(barriers,attempt-1)>bisect_right(barriers,view))
        row=[rid,view,ack,attempt,h(cs[rid]['issue']),path,form[0],form[1],parseout['status'],key,parseout['rows'],(rid,view) in reg,cohort[0],cohort[1],opaque]
        out.append(row);reqs[form[0]]+=1;census['all']+=1;census['parsed']+=parsed;census['have_ack']+=ack is not None
    diff=set(mandatory)-matched
    # R37 may look back across a failed/unconfirmed attempt. Preserve the registered pair explicitly,
    # tagged as primary_only. It is excluded from the general closest-attempt census.
    indexed={(r[0],r[1]):r for r in out}
    for rid,view,ack in sorted(diff):
        old=indexed[rid,view];copy=old.copy();copy[2]=ack;copy[3]=None;copy[12:14]=mandatory[rid,view,ack]
        copy.append('primary_only');out.append(copy)
    assert sum(x[12] in ('known','novel') for x in out)==4117
    seal=dict(protocol=digest(D/'PROTOCOL_RU.md'),source_code=digest(Path(__file__)),raw_manifest=digest(RAW/'files.json'),files=dict(panel=save('panel.json.gz',out),tails=save('tails.json.gz',tails)),mandatory=len(mandatory),registered=len(reg),raw_counts=raw_counts,census=census,extra_primary_pairs=len(diff),requests=reqs)
    save('panel-seal.json',seal);print(dict(census),len(tails),len(diff),dict(raw_counts))
if __name__=='__main__':main()
