"""Portable receipt and direct recount independent of aggregate results."""
import base64,statistics,sys
from collections import Counter,defaultdict
from pathlib import Path
from common import ROOT,R9,PANELS,load,put,sha,verify,locks
from reader import read
from ef_direct import lookup
def main():
    primary=load(ROOT/'state_seal.json')
    verify(primary['local']);verify(load(ROOT/'read_seal.json'));verify(load(ROOT/'ef_seal.json'))
    def upstream(path):
        norm=path.replace(chr(92),'/')
        return R9/norm.split('/graph_memory_round9/',1)[-1]
    for path,digest in {**primary['upstream'],**load(ROOT/'input_receipt.json')['files'],**load(ROOT/'results.json')['sources']}.items():assert sha(upstream(path))==digest,path
    olddirs=list((ROOT/'old').rglob('*.gz'));nodes={};queries={};cases=set();panels={};flips={};sw=set()
    qstats=Counter();calls=0;capstates=Counter()
    for p in olddirs:
        o=load(p);t=o['issue'];d=o['direction'];panels[t]=o['panel']
        k=(t,d);union=set().union(*(set(z) for z in o['sets']))
        q=load(ROOT/'future'/o['panel']/p.name)['changed'];provenance=(len(q),sum(word in union for word in q))
        queries[k]=q;nodes[k]=o['nodes'];cases.add(k)
        qstats.update(total_keys=provenance[0],seen_keys=provenance[1],unknown_keys=provenance[0]-provenance[1],fully_known_updates=int(provenance[0]==provenance[1]))
        for z in range(len(o['nodes'])):
            if set(o['sets'][z]).intersection(q):sw.add((t,d,o['nodes'][z]))
    for pn in PANELS:
        for x in load(R9/pn/'outcomes.json'):flips[x['task'],x['direction'],x['node']]=x['changed']
    sumtab=defaultdict(Counter);caps=set();rosters=[]
    for base in ['states','ef_states']:
        for p in (ROOT/base).rglob('*.gz'):
            data=load(p);t=data['issue'];d=data['direction'];names=nodes[t,d]
            if base=='states':rosters.append(data['roster_bytes'])
            for x in data['states']:
                raw=base64.b64decode(x['data'],validate=True);b=x['b'];s=x['salt'];a=x['arm']
                assert raw[1]==len(names) and raw[2]==s and len(raw)==b*len(names)
                result=(read if base=='states' else lookup)(raw,queries[t,d]);calls+=1
                capstates[a]+=1
                for i,node in enumerate(names):
                    key=t,d,node;truth=key in sw;out=bool(result>>i&1)
                    assert out or not truth
                    if key not in flips:continue
                    sumtab[b,s,a].update(n=1,extra=(out and not truth),stale=(not out and flips[key]))
    mainrows=load(ROOT/'results.json')['summary']['pooled'];efrows=load(ROOT/'ef_results.json')['summary']['pooled']
    for b,s,a in sumtab:
        expected=statistics.mean(sumtab[b,z,a]['extra'] for z in range(32))
        reported=efrows[str(b)]['extra_mean'] if a=='elias_fano' else mainrows[str(b)][a]['mean_extra']
        assert expected==reported and sumtab[b,s,a]['n']==len(flips) and sumtab[b,s,a]['stale']==0
    ch=load(ROOT/'challenge_results.json')
    assert ch['256']['xor_map']['verified_salt0']['known']==47406
    assert sum((*flips.values(),))==38 and len(set(flips)&sw)==244 and len(flips)==418
    tracking=[p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pyc'!=p.suffix and p.name not in {'verification.json','MANIFEST_SHA256.json'}]
    put(ROOT/'verification.json',dict(issues=len(panels),snapshots=len(cases),scored=len(flips),changed_outcomes=sum(flips.values()),exact_reruns=len(set(flips)&sw),qstats=dict(qstats),payload_reads=calls,payloads_by_arm=dict(capstates),max_in_budget=True,observed_false_negative=0,observed_unselected_flip=0,roster_bytes_min_p50_max=[min(rosters),statistics.median(rosters),max(rosters)],static_input_receipts_verified=True,ef_direct_parity=load(ROOT/'ef_direct_results.json')['compared']))
    put(ROOT/'MANIFEST_SHA256.json',locks(tracking+[ROOT/'verification.json']))
    print('verified',len(tracking)+1,'files',calls,'payloads')
if __name__=='__main__':main()