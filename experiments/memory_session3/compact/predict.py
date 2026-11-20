"""Write memories from pre-boundary histories only. This module never opens annotation files."""
from pathlib import Path
from collections import defaultdict
import argparse
import gzip
import hashlib
import json
import math
import sys
import time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source'))
import cb_common as author
INPUT_CAP=400_000
TYPES=['path','sha','pr','error','url','kv','ip']
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def dumps(obj):return json.dumps(obj,ensure_ascii=False,separators=(',',':'))
def code_digest():
    return {n:sha_bytes((ROOT/n).read_bytes()) for n in ['PROTOCOL.md','source/cb_common.py','predict.py','histories.jsonl.gz','source_manifest.json']}
def features(history):
    raw=json.dumps(history,ensure_ascii=False)[:INPUT_CAP]
    attrs=author.atoms_in_text(raw)
    ordered=[(k,v) for k,vs in attrs.items() for v in sorted(vs)]
    pattern_40=[(k,v) for k,vs in attrs.items() for v in sorted(vs)[:40]]
    official='\n'.join(f'- {k}: {v}' for k,v in pattern_40)
    assert author.anchor_baseline(history)==official
    authors_extra=[a for a in ordered if a not in set(pattern_40)]
    author_order=pattern_40+authors_extra
    pos=1;seen=defaultdict(list);roles=defaultdict(set);m_count=0
    for i,msg in enumerate(history):
        if pos>=len(raw):break
        msg_json=json.dumps(msg,ensure_ascii=False)
        part=msg_json[:len(raw)-pos]
        assert raw[pos:pos+len(part)]==part
        pos+=len(msg_json)+2
        m_count+=1
        for category,vals in author.atoms_in_text(part).items():
            for value in vals:
                tok=(category,value);seen[tok].append(i);roles[tok].add(msg.get('role','unknown'))
    features_={}
    for a in ordered:
        positions=seen[a]
        bins=len({min(7,8*j//max(1,m_count)) for j in positions})
        recent=(positions[-1]+1)/max(1,m_count) if positions else 0.
        freq=len(positions)
        val=2*math.log1p(bins)+math.log1p(len(roles[a]))+math.log1p(freq)+.5*recent
        features_[a]=(val,recent,freq)
    witness=sorted(ordered,key=lambda a:(-features_[a][0],*a))
    recent=sorted(ordered,key=lambda a:(-features_[a][1],*a))
    freq=sorted(ordered,key=lambda a:(-features_[a][2],*a))
    shuffle=sorted(ordered,key=lambda a:sha_bytes(('20261117|'+a[0]+'|'+a[1]).encode()))
    bytype=[[(k,v) for v in sorted(attrs.get(k,[]))] for k in TYPES]
    balanced=[items[i] for i in range(max((len(v) for v in bytype),default=0)) for items in bytype if len(items)>i]
    return raw,official,pattern_40,{'witness_grouped':witness,'witness_lines':witness,'author_grouped':author_order,'round_robin':balanced,'recent':recent,'frequency':freq,'shuffle':shuffle}
def pack(order,cap,grouped):
    groups=defaultdict(list); selected=[];used=0
    for k,v in order:
        if grouped:
            extra=len(v)+1+(len(k)+3 if not groups.get(k) else 0)
            # Material layout is "[kind]\nvalue\n...", without the terminal newline.
            size=used+extra
            if size-1>cap:continue
            groups[k].append(v);used=size
        else:
            extra=len(f'- {k}: {v}')+1
            if used+extra-1>cap:continue
            used+=extra
        selected.append((k,v))
    if grouped:
        summary='\n'.join(line for k,items in groups.items() for line in [f'[{k}]',*items])
    else:
        summary='\n'.join(f'- {k}: {v}' for k,v in selected)
    assert len(summary)==max(0,used-1) and len(summary)<=cap
    return selected,summary
def build(i,h):
    raw,official,official_items,orders=features(h)
    for budget,fixed in [('natural',None),('1024',1024),('4096',4096)]:
        cap=len(official) if fixed is None else min(len(official),fixed)
        item_count=0;length=0
        for k,v in official_items:
            new_len=length+len(f'- {k}: {v}')+(1 if item_count else 0)
            if new_len>cap:break
            length=new_len;item_count+=1
        summary=official[:length]
        methods={'author_index':(official_items[:item_count],summary),'raw_tail':([],raw[-cap:] if cap else '')}
        for a,ordered in orders.items():methods[a]=pack(ordered,cap,a!='witness_lines')
        for a,(selected,S) in methods.items():
            yield {'i':i,'budget':budget,'arm':a,'cap':cap,'input_chars':len(raw),'n_candidates':len(orders['witness_grouped']),'items':selected,'S':S}
def main():
    timer=time.perf_counter();cpu=time.process_time()
    with gzip.open(ROOT/'histories.jsonl.gz','rt',encoding='utf8') as histories,gzip.open(ROOT/'predictions.jsonl.gz','wt',encoding='utf8',compresslevel=5) as out:
        for i,line in enumerate(histories):
            data=json.loads(line)
            assert set(data)=={'i','H'} and i==data['i']
            for r in build(i,data['H']):out.write(dumps(r)+'\n')
    seal={'inputs':code_digest(),'predictions_sha256':sha_bytes((ROOT/'predictions.jsonl.gz').read_bytes()),'n_cases':i+1,'wall_s':time.perf_counter()-timer,'cpu_s':time.process_time()-cpu,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (ROOT/'prediction_lock.json').write_text(json.dumps(seal,indent=1),encoding='utf8')
    print(seal,flush=True)
if __name__=='__main__':main()

