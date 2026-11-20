import collections,gzip,json
from driver import D,read,lock
from score_cpu import pair

def main():
    ids=read(D/'cohort.json')['ids'][:12]
    rows=[]
    for i in ids:
        d=D/'tasks'/i/'grades_v2';control=read(d/'control.json');solver=read(d/'solver.json')
        base=control['base']['tests'];gold=control['gold']['tests']
        bf=base['FAIL_TO_PASS'];gf=gold['FAIL_TO_PASS']
        valid=bool(bf['complete'] and bf['failed'] and gf['complete'] and not gf['failed'])
        row=dict(id=i,valid=valid,base_f2p=bf,gold_f2p=gf,arms={})
        for arm in ['flat','evidence']:
            item=solver[arm];f=item['tests']['FAIL_TO_PASS'];p=item['tests']['PASS_TO_PASS']
            row['arms'][arm]=dict(valid_pass=int(valid and item['applied'] and f['complete'] and not f['failed']),applied=int(item['applied']),reason=item['reason'],passed_f2p=len(f['passed']),regressions=len(set(base['PASS_TO_PASS']['passed'])&set(p['failed'])),missing_p2p=len(set(base['PASS_TO_PASS']['passed'])-set(p['passed'])))
        rows.append(row)
    totals={a:{k:sum(r['arms'][a][k] for r in rows) for k in ['valid_pass','applied','passed_f2p','regressions','missing_p2p']} for a in ['flat','evidence']}
    calls=[json.loads(gzip.decompress(f.read_bytes())) for f in (D/'calls').glob('*.gz')]
    result=dict(n=len(rows),valid=sum(r['valid'] for r in rows),totals=totals,pair=pair(rows,'evidence','flat','valid_pass'),calls=len(calls),identical_pairs=sum(len(set(x.values()))==1 for x in read(D/'assign.json').values()),tokens={k:sum(j['response']['usage'][k] for j in calls) for k in ['prompt_tokens','completion_tokens']})
    (D/'gpu_rows.json').write_text(json.dumps(rows,indent=1));(D/'gpu_results.json').write_text(json.dumps(result,indent=1));print(json.dumps(result))


if __name__=='__main__':main()
