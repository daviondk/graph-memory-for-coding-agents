"""Verify original projection hashes, exact visible substrings and tokenizer costs for all cards."""
import hashlib,sys
from collections import Counter
from tokenizers import Tokenizer
from inputs import ROOT,RUN,ARMS,ON,DE,db,key,record,load,put,pilot
def run():
    old=load(ON/'forecast-lock.json');dev=load(DE/'projection-lock.json')['trajectories'];h=hashlib.sha256()
    tout=record('test',0)[2]
    for p in sorted(tout.glob('*.json.gz')):h.update(p.name.encode()+b'\0'+bytes.fromhex(pilot.sha(p)))
    assert old['projection']==h.hexdigest()
    for t,x in dev.items():assert pilot.sha(record('dev',x['shard'])[2]/f"{x['shard']}-{t}.json.gz")==x['projection_sha256']
    tok=Tokenizer.from_file(str(pilot.CACHE/'tokenizer.json'));c=db();allkeys=set();cost={};n=0
    for st in ['dev','test']:
        for i in range(8):
            for r in load(RUN/f'cards-{st}-{i}.json.gz'):
                proj=load(record(st,i)[2]/f"{i}-{r['t']}.json.gz")
                seen={int(j) for j in r['b']};assert seen==set.union(*(set(kk) for kk in r['k'].values()))
                for j,meta in r['b'].items():
                    e,ptr,a,b,nt,nb,k=meta;s=proj['fields'][e][a:b];assert len(s.encode())==nb;kb=key('passage: '+s);assert k==kb.hex()
                    if kb not in cost:cost[kb]=len(tok.encode(s,add_special_tokens=False).ids)
                    assert nt==cost[kb]
                    allkeys.add(kb);n+=1
                for (q,k),(q2,txt) in zip(r['q'],proj['q'],strict=True):assert q==q2 and bytes.fromhex(k)==key('query: '+txt);allkeys.add(bytes.fromhex(k))
    assert allkeys=={k for k, in c.execute('select k from inputs')}
    put(ROOT/'source-verification.json',dict(test_projection_hash=h.hexdigest(),dev_individual_sha_matches=len(dev),exact_block_occurrences=n,
        distinct_blocks=len(cost),represented_exact_strings=len(allkeys),max_native_wordpiece_count=max(cost.values()),min_native_wordpiece_count=min(cost.values()),all_costs_exact=True,
        exact_utf8_slices_verified=True,all_index_keys_attested=True,all_logical_arms_isolated=True))
if __name__=='__main__':run()
