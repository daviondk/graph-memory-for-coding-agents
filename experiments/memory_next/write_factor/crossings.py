"""Post-score audit of every Hit@5 crossing in the two registered hybrid contrasts."""
import collections
import csv
import re
from generate import HERE, SRC, read, save, hash_file

def tokenize(s):
    result=[]
    for word in re.findall(r'[A-Za-z0-9_]+',s):
        result.append(word.lower())
        parts=re.sub(r'([a-z])([A-Z])',r'\1 \2',word).replace('_',' ').lower().split()
        if len(parts)>1:result.extend(parts)
    return set(result)

def run():
    assert (HERE/'results.json').exists()
    cards=read(SRC/'cards.json')
    queries=read(SRC/'queries.json')
    key={c['key']:c for c in cards}
    with (SRC/'evaluation_library.csv').open(encoding='utf8',newline='') as f:
        lib={v['instance_id']:v['trace_key'] for v in csv.DictReader(f)}
    evidence=[tokenize(c['edits']) for c in cards]
    df=collections.Counter(token for terms in evidence for token in terms)
    src=list(csv.DictReader((HERE/'per_query.csv').open(encoding='utf8',newline='')))
    columns=['contrast','ordinal','current_issue','repo','gold_source','rank_full','rank_control','shared_edits_query_count',
             'rare_shared_terms','edited_terms_absent_from_both_other_fields']
    rows=[]
    for r in src:
        if r['group']!='lite':continue
        ordinal=int(r['ordinal'])
        q=tokenize(queries[ordinal]['query'])
        for ctrl in ['hyb_absent','hyb_shuffle']:
            if r['hyb_real_hit5']==r[ctrl+'_hit5']:continue
            for source in r['gold_ids'].split('|'):
                if source not in lib:continue
                c=key[lib[source]]
                shared=q&tokenize(c['edits'])
                other=tokenize(c['symptom']) | tokenize(c['closure'])
                ordered=lambda z: sorted(z,key=lambda t:(df[t],t))
                rows.append([ctrl,ordinal,r['instance_id'],r['repo'],source,r['hyb_real_rank'],r[ctrl+'_rank'],len(shared),
                             '|'.join(ordered(shared)[:6]),'|'.join(ordered(shared-other)[:6])])
    with (HERE/'hit5_crossings.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.writer(f);w.writerow(columns);w.writerows(rows)
    print('crossings',len(rows))
if __name__=='__main__':run()

