"""Offline checks of exact trajectory identities, relation ordering, and actual model costs."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text(encoding='utf8'))

def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line]

def table(path):
    with path.open(encoding='utf8', newline='') as fp:
        return list(csv.DictReader(fp))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main(primary_only=False):
    library={r['trace_key']:r['instance_id'] for r in table(HERE/'evaluation_library.csv')}
    related=defaultdict(list)
    for row in table(HERE/'evaluation_relations.csv'):
        ids=related[row['related_instance_id']]
        if row['experience_instance_id'] not in ids:
            ids.append(row['experience_instance_id'])
    lite={int(row['ordinal']):row for row in table(HERE/'per_query.csv') if row['group']=='lite'}
    primary={r['ordinal']:r for r in records(HERE/'qwen_calls.jsonl')}
    assert len(library)==300 and set(primary)==set(lite)==set(range(99))
    available=set(library.values())
    sens=read(HERE/'gold_sensitivity.json')
    for key in ['any','first_in_dated_release','last_in_dated_release']:
        hit=covered=0
        for i,row in lite.items():
            gold=related[row['instance_id']]
            assert set(gold)==set(row['gold_ids'].split('|'))
            selected=gold if key=='any' else gold[:1] if key.startswith('first') else gold[-1:]
            hit+=library[primary[i]['choice']] in selected
            covered+=bool(available.intersection(selected))
        assert sens[key]=={'match1':hit,'in_library':covered},key
    singles=[i for i,row in lite.items() if len(related[row['instance_id']])==1]
    fixed=sum(library[primary[i]['choice']] in related[lite[i]['instance_id']] for i in singles)
    assert sens['single_link_only']=={'n':len(singles),'match1':fixed}
    assert sens['all_possible_one_per_task']==[fixed,sens['any']['match1']]
    print('Gold interpretation checked independently against source-order labels:',sens)
    if primary_only:
        return
    match=HERE/'matched_reader'; freeze=read(match/'freeze.json');lock=read(match/'blind_commit.json')
    for folder,receipt in [(match,freeze['local']),(HERE,freeze['parent'])]:
        for name,value in receipt.items():assert sha(folder/name)==value,(folder,name)
    assert sha(match/'calls.jsonl')==lock['predictions'] and sha(match/'freeze.json')==lock['freeze']
    slates={(r['arm'],r['ordinal']):r for r in read(match/'slates.json')}
    calls=records(match/'calls.jsonl')
    assert len(calls)==len(slates)==len(set(r['response_id'] for r in calls))==198
    assert set(slates)=={(a,i) for a in ['no_edits','recall_five'] for i in lite}
    assert len({(r['arm'],r['ordinal']) for r in calls})==198
    pairs={int(r['ordinal']):r for r in table(match/'paired.csv')}
    result=read(match/'results.json')
    assert len(pairs)==result['n']==99 and result['locked_predictions_sha256']==lock['predictions']
    for r in calls:
        name=r['arm'];i=r['ordinal'];s=slates[name,i];gold=related[lite[i]['instance_id']]
        assert all(r[k]==s[k] for k in ['base_slate','order','payload_sha256'])
        assert len(set(r['order']))==5 and r['choice'] in r['order']
        assert int(pairs[i][name+'_1'])==int(library[r['choice']] in gold)
        assert int(pairs[i][name+'_top5'])==any(library[k] in gold for k in r['base_slate'])
        assert int(pairs[i][name+'_retriever_1'])==int(library[r['base_slate'][0]] in gold)
        assert int(pairs[i][name+'_changed'])==int(r['choice']!=primary[i]['choice'])
    for name in ['primary','no_edits','recall_five']:
        arm=list(primary.values()) if name=='primary' else [r for r in calls if r['arm']==name]
        stats=result['costs'][name]
        assert stats['n']==len(arm)==99
        assert stats['input']==sum(r['usage']['prompt_tokens'] for r in arm)
        assert stats['output']==sum(r['usage']['completion_tokens'] for r in arm)
        assert stats['fallback']==sum(r['fallback'] for r in arm)
    for key,value in result['counts'].items():
        assert sum(int(r[key]) for r in pairs.values())==value,key
    print('198 matched-reader choices, candidate lists, official IDs and usage checked.')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--primary-only',action='store_true')
    main(p.parse_args().primary_only)
