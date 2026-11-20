"""Check candidate ordering, public crops and duplicate prompts across strata and training without labels."""
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from run import D,R,author_function,digest,load,now,panel_name,readgz,rows,save,writegz
from data_io import gz
sha_text=lru_cache(4096)(digest)

def main():
    crop=author_function('repo_author_utils.py','crop_code_lines')
    plan=load(D/'roster.json'); train=set();old=load(D/'method_lock.json')
    entries=[]; counts=Counter()
    for path,parts in plan.items():
        p=Path(path); reverse={}
        for stage,items in parts.items():
            for j,i in items:reverse.setdefault(j,[]).append((stage,i))
        for j,row in enumerate(rows(p,['code','context','repo_name'])):
            if j not in reverse:continue
            q='\n'.join(row['code'].splitlines()[-3:]);aq=crop(row['code'],3)
            doc=[sha_text(s) for s in row['context']]
            # All digests are fixed-width 64-char hex, so concatenation of signatures is injective.
            ident=digest(digest(q)+''.join(sorted(doc)))
            ordered=digest(digest(q)+''.join(doc));amb=len(set(doc))!=len(doc)
            for stage,i in reverse[j]:
                if stage=='train':train.add(ident)
                else:entries.append((stage,panel_name(p.stem),i,row['repo_name'],ident,ordered,int(amb),int(q!=aq)))
    rows_out=[[*r,int(r[4] in train)] for r in entries];writegz('stimulus_audit.jsonl.gz',rows_out)
    by={}
    for stage in sorted({r[0] for r in entries}):
        for lang in sorted({r[1].split('_')[0] for r in entries if r[0]==stage}):
            rs=[r for r in rows_out if r[0]==stage and r[1].startswith(lang)]
            by[stage+'_'+lang]=dict(n=len(rs),unique_order_insensitive=len({r[4] for r in rs}),
                unique_order_sensitive=len({r[5] for r in rs}),duplicates_inside_choice_set=sum(r[6] for r in rs),
                different_author_crop=sum(r[7] for r in rs),exact_train_matches=sum(r[8] for r in rs))
    dec={(r['panel'],r['idx']):r for r in readgz(D/'decisions.jsonl.gz') if r['stage']=='archive'}
    jj=rr=hh=0
    for p,i,repo,h,arms in gz(R/'archive.pred.jsonl.gz'):
        if (p,i) not in dec:continue
        r=dec[p,i]; assert repo==r['project']
        jj+=int(arms['jaccard']==r['orders']['jaccard']);rr+=int(arms['graph']==r['orders']['r4']);hh+=int(h==r['query_hash'])
    save('input_audit.json',dict(utc=now(),summary=by,archive_original=dict(n=len(dec),exact_jaccard=jj,exact_graph=rr,exact_crop=hh)))
if __name__=='__main__':main()
