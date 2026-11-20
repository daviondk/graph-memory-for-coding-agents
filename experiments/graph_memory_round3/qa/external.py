"""Use the publisher's ID construction and gold-resolution rules; verify the released query digest."""
import gzip,hashlib,json,sys,re
import numpy as np
from collections import defaultdict
from prepare import P,read,write,sha
from evaluate import hits
def main():
    anchored=read('upstream/mode_a.json');raw=read('upstream/locomo10.json');pred=json.loads(gzip.decompress((P/'predictions.json.gz').read_bytes()));cq=hashlib.sha256();docs=hashlib.sha256()
    rows=defaultdict(list);turns={};all_s=[]
    for c in raw:
        C=c['conversation'];s=c['sample_id'];turns[s]=set()
        for k in sorted([x for x in C if re.fullmatch(r"session_\d+",x)],key=lambda x:int(x.split('_')[1])):
            for t in C[k]:
                i=t['dia_id'];turns[s].add(i);txt=t["text"];cap=t.get("blip_caption")
                if cap:txt+=" [shares a photo: "+cap+"]"
                txt="["+C[k+"_date_time"]+"] "+t['speaker']+": "+txt
                docs.update(f"{s}\x1f{i}\x1f{txt}\x1e".encode())
        for j,q in enumerate(c['qa']):
            ids=[e for e in q['evidence'] if e in turns[s]] if q["category"]!=5 else []
            cq.update(f"{s}#{j}\x1f{q['question']}\x1f{','.join(ids)}\x1e".encode())
            if ids:
                g=set(ids)
                for a,(turn,_) in pred[f"{s}:{j}"].items():
                    m=hits(turn,g,5);m["mrr@30"]=next((1/p for p,x in enumerate(turn,1) if x in g),0);rows[a].append(m)
    assert cq.hexdigest()==anchored["provenance"]["query_sha256"]
    assert sha((P/'upstream/locomo10.json').read_bytes())==anchored['provenance']['dataset_sha256']
    n=len(rows['graph']);assert n==1531
    ours={a:{k:sum(x[k] for x in vs)/n for k in vs[0]} for a,vs in rows.items()}
    refs={r['system']:{'all@5':r['overall']['allGoldAt']['5'],'recall@5':r['overall']['recallAt']['5'],'mrr@30':r['overall']['mrr']} for r in anchored['systems']}
    session={s:read('upstream/'+s+'.json')['balanced']['core_four_categories'] for s in ['locomo_flat_bm25','locomo_minilm','locomo_memoria_windowed']}
    write("external_results.json",dict(n=n,trace_dataset_sha=sha((P/'upstream/locomo10.json').read_bytes()),publisher_query_sha=cq.hexdigest(),publisher_reference_text_sha=docs.hexdigest(),verified_reference_text_match=(docs.hexdigest()==anchored["provenance"]["corpus_sha256"]),ours=ours,modeA_publication=refs,session_publication=session))
if __name__=='__main__':main()