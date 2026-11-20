"""Offline audit of sealed handoff inputs and outcomes. Standard library, no network or inference."""
import argparse,collections,gzip,hashlib,importlib.util,json,random,re,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def read(name):
    path=ROOT/name
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)

def sha(value):
    return hashlib.sha256(value if isinstance(value,bytes) else value.encode()).hexdigest()

def canon(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'))

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def verify_lock(name):
    path=ROOT/name
    manifest=read(name)
    for relative,digest in manifest.items():
        assert sha((path.parent/relative).read_bytes())==digest,(name,relative)
    return len(manifest)

def assert_same(actual,expected,context):
    assert actual==expected,context

def inputs():
    locks=['input_lock.json','grade_lock.json','clean_setup_lock.json','clean/input_lock.json',
           'shuffle/input_lock.json','control_grade_lock.json','strict/input_lock.json','strict_grade_lock.json']
    if (ROOT/'label_schema_lock.json').is_file():
        locks.append('label_schema_lock.json')
    lock_counts={name:verify_lock(name) for name in locks}
    writer=load_module('verified_writer',ROOT/'writer.py')
    prepared=load_module('verified_preparer',ROOT/'prepare_solver.py')
    receipt=read('receipts.json.gz')
    records={}
    for path in sorted((ROOT/'records').rglob('*.json.gz')):
        record=read(path.relative_to(ROOT))
        key=record['model']+'|'+record['issue_id']
        assert_same(writer.project(record),receipt[key],('receipt',key))
        assert sha(record['patch'])==record['patch_sha256_utf8']
        records[key]=record
    assert len(records)==len(receipt)==1441
    listing=read('trace_listing.json.gz')
    for item in listing:
        record=records[item['model']+'|'+item['id']]
        assert record['trace_sha256']==item['sha256']
        assert record['trace_url']==item['url']
    issues=read('issues.json')
    clean_ids=sorted(i for i in issues if all(records.get(m+'|'+i,{}).get('traj_submission_matches') is True for m in ('claude','gemini')))
    assert_same(clean_ids,read('clean/cohort.json'),'clean cohort')
    packets={}
    for sub,cohort,mapping in [('',sorted(issues),{'claude':'claude','codex':'codex'}),
                               ('clean',clean_ids,{'claude':'claude','codex':'gemini'})]:
        prefix=sub+'/' if sub else ''
        selected=sorted(cohort,key=lambda i:sha('s4-judge-20261117'+i))[:96]
        expected={}
        for iid in selected:
            expected[iid]={'issue':prepared.anonymize(writer.excerpt(issues[iid]['problem_statement'],2850)),'options':{}}
            for alias,model in mapping.items():
                r=records[model+'|'+iid]; note=receipt[model+'|'+iid]
                expected[iid]['options'][alias]={
                    'patch':prepared.anonymize(writer.excerpt(r['patch'],3450)) or '(empty patch)',
                    'latest':prepared.anonymize(note['latest_note']) or '(no retained verification)',
                    'witness':prepared.anonymize(note['witness_note']) or '(no retained verification)'}
        assert_same(expected,read(prefix+'reader_inputs.json.gz'),('packets',sub))
        packets[sub]=expected
    strict_module=load_module('verified_strict',ROOT/'strict/strict_writer.py')
    strict_receipts=read('strict/receipts.json.gz')
    original_check=writer.check_event
    writer.check_event=strict_module.strict_check
    for key,target in strict_receipts.items():
        assert_same(writer.project(records[key]),target,('strict receipt',key))
    writer.check_event=original_check
    clean=packets['clean']
    strict=read('strict/reader_inputs.json.gz')
    shuffled=read('shuffle/reader_inputs.json.gz')
    donors=read('shuffle/donors.json')
    for iid in clean:
        for target in (strict,shuffled):
            assert target[iid]['issue']==clean[iid]['issue']
        for alias,model in [('claude','claude'),('codex','gemini')]:
            for target in (strict,shuffled):
                for field in ('patch','latest'):
                    assert target[iid]['options'][alias][field]==clean[iid]['options'][alias][field]
            expected=prepared.anonymize(strict_receipts[model+'|'+iid]['witness_note']) or '(no retained verification)'
            assert strict[iid]['options'][alias]['witness']==expected
            order=sorted(clean,key=lambda i:sha('shuffle-v4|'+alias+'|'+i))
            donor=order[(order.index(iid)+1)%len(order)]
            assert donors[alias][iid]==donor!=iid
            assert shuffled[iid]['options'][alias]['witness']==clean[donor]['options'][alias]['witness']
    return {'locks':lock_counts,'receipts':len(records),'strict_receipts':len(strict_receipts),'packet_issues':96},records,issues,receipt

def tie(iid):
    return 'claude' if int(sha('tie-s4|'+iid),16)%2==0 else 'codex'

def output_choice(text):
    match=re.fullmatch(r'\s*(?:candidate\s*)?[(*\x22\x27\x60\[]*([AB])[)*\x22\x27\x60\].!]*\s*',text,re.I)
    return match[1].upper() if match else None

def choices(sub):
    prefix=sub+'/' if sub else ''
    verify_lock(prefix+'reader_lock.json')
    verify_lock(prefix+'input_lock.json')
    rows=read(prefix+'choices.json')
    schedule=read(prefix+'schedule.json')
    assert len(rows)==len(schedule)==(576 if sub in ('','clean') else 192)
    reader=load_module('verified_reader_'+(sub or 'original'),ROOT/prefix/'reader.py')
    packet=read(prefix+'reader_inputs.json.gz')
    for row,job in zip(rows,schedule):
        assert all(row[k]==v for k,v in job.items())
        payload,names=reader.request(job,packet[job['issue']])
        digest=sha(canon(payload))
        assert digest==row['request_hash']
        call=read(prefix+'calls/'+digest+'.json.gz')
        assert_same(payload,call['request'],('request',sub,digest))
        response=call['response']
        assert response['id']==row['response_id']
        assert response['usage']==row['usage']
        letter=output_choice(response['choices'][0]['message']['content'])
        expected=names['AB'.index(letter)] if letter else None
        assert expected==row['choice']
    return rows

def stats(values):
    return {'n':len(values),'success_sum':sum(values),'mean':statistics.mean(values)}

def delta(a,b,groups):
    changes=[x-y for x,y in zip(a,b)]
    buckets=collections.defaultdict(list)
    for group,value in zip(groups,changes):
        buckets[group].append(value)
    keys=list(buckets)
    rng=random.Random(17112026)
    bootstrap=[]
    for _ in range(6000):
        sampled=[buckets[rng.choice(keys)] for _ in keys]
        bootstrap.append(sum(map(sum,sampled))/sum(map(len,sampled)))
    bootstrap.sort()
    return {'difference':statistics.mean(changes),'wins':sum(x>0 for x in changes),
            'losses':sum(x<0 for x in changes),'ties':sum(x==0 for x in changes),
            'repository_cluster_ci95':[bootstrap[150],bootstrap[5850]]}

def verify_labels(require_bytes=False):
    labels=read('labels.json.gz')
    assets=read('asset_listing.json.gz')
    assert len(labels)==sum(key.endswith('|report.json') for key in assets)
    for key,row in labels.items():
        model,iid=key.split('|')
        assert row['model']==model and row['id']==iid
        assert type(row['resolved']) is bool
        official=row['official_report'].get(iid,row['official_report'])
        assert isinstance(official,dict) and type(official.get('resolved')) is bool
        assert row['resolved']==official['resolved']
        assert row['source']==assets[key+'|report.json']
        assert re.fullmatch('[0-9a-f]{64}',row['sha256'])
        assert row==read('grades/'+model+'/'+iid+'.json.gz')
    manifest_path=ROOT/'grade_bytes_manifest.json'
    if require_bytes:
        assert manifest_path.is_file(),'Raw report manifest is required'
    byte_count=0
    if manifest_path.is_file():
        manifest=read('grade_bytes_manifest.json')
        assert set(manifest)==set(labels)
        for key,item in manifest.items():
            compressed=(ROOT/item['path']).read_bytes()
            raw=gzip.decompress(compressed)
            row=labels[key]
            assert sha(compressed)==item['compressed_sha256']
            assert sha(raw)==item['sha256']==row['sha256']
            assert len(raw)==item['size']==row['source']['bytes']
            origin=row['source']
            if 'md5' in origin:
                assert hashlib.md5(raw).hexdigest()==origin['md5']
            if 'git' in origin:
                blob=b'blob '+str(len(raw)).encode()+b'\0'+raw
                assert hashlib.sha1(blob).hexdigest()==origin['git']
            assert json.loads(raw)==row['official_report']
            byte_count+=1
    return labels,byte_count

def verify_pairs(saved,labels,records,issues,receipt):
    contexts={}
    clean=read('clean/cohort.json')
    exact=[iid for iid in sorted(issues) if all(records[m+'|'+iid]['traj_submission_matches'] for m in ('claude','codex'))]
    for key,models,cohort in [('original',['claude','codex'],sorted(issues)),
                               ('clean',['claude','gemini'],clean),
                               ('codex_gemini',['codex','gemini'],clean),
                               ('original_exact',['claude','codex'],exact)]:
        ids=[iid for iid in cohort if all(m+'|'+iid in labels for m in models)]
        groups=[issues[iid]['repo'] for iid in ids]
        picks={model:[model]*len(ids) for model in models}
        picks['hash']=[models[int(sha('tie-s4|'+iid),16)%2] for iid in ids]
        picks['shorter']=[];picks['heldout_repository_prior']=[]
        for field in ('last','fresh_rank','witness_rank'):
            picks[field]=[]
        for j,iid in enumerate(ids):
            preference=picks['hash'][j]
            picks['shorter'].append(min(models,key=lambda m:(len(records[m+'|'+iid]['patch']),m!=preference)))
            for field in ('last','fresh_rank','witness_rank'):
                picks[field].append(max(models,key=lambda m:(receipt[m+'|'+iid][field],m==preference)))
            training=[other for other in ids if issues[other]['repo']!=issues[iid]['repo']]
            average={m:statistics.mean(labels[m+'|'+other]['resolved'] for other in training) if training else 0 for m in models}
            picks['heldout_repository_prior'].append(max(models,key=lambda m:(average[m],m==preference)))
        values={name:[int(labels[m+'|'+iid]['resolved']) for m,iid in zip(selected,ids)] for name,selected in picks.items()}
        values['equal_random_expectation']=[sum(labels[m+'|'+iid]['resolved'] for m in models)/2 for iid in ids]
        values['oracle']=[int(any(labels[m+'|'+iid]['resolved'] for m in models)) for iid in ids]
        expected={'ids':ids,'groups':groups,'choices':picks,'values':values}
        assert_same(expected,saved[key],('pair vectors',key))
        contexts[key]=expected
    return contexts

def verify_reader(sub,rows,labels,issues,reference,saved):
    mapping={'claude':'claude','codex':'codex' if sub=='' else 'gemini'}
    ids=sorted({row['issue'] for row in rows})
    groups=[issues[iid]['repo'] for iid in ids]
    indexed={(row['issue'],row['arm'],row['reverse']):row for row in rows}
    assert len(indexed)==len(rows)
    chosen={};values={};costs={}
    for arm in ('empty','latest','witness'):
        chosen[arm]=[];values[arm]=[];values[arm+'_single']=[]
        total_tokens=invalid=disagreement=0
        for iid in ids:
            pair=[indexed[iid,arm,reverse] for reverse in (False,True)]
            selected=[mapping[row['choice'] or tie(iid)] for row in pair]
            chosen[arm].append(selected)
            values[arm].append(sum(labels[m+'|'+iid]['resolved'] for m in selected)/2)
            selected_one=selected[0] if selected[0]==selected[1] else mapping[tie(iid)]
            values[arm+'_single'].append(int(labels[selected_one+'|'+iid]['resolved']))
            disagreement+=selected[0]!=selected[1]
            invalid+=sum(row['choice'] is None for row in pair)
            total_tokens+=sum(row['usage']['total_tokens'] for row in pair)
        costs[arm]={'nominal_total_tokens':total_tokens,'invalid':invalid,'order_disagreement':disagreement,
                    'unique_requests':len({row['request_hash'] for row in rows if row['arm']==arm})}
    for model in mapping.values():
        values[model]=[int(labels[model+'|'+iid]['resolved']) for iid in ids]
    for name in ('heldout_repository_prior','shorter','hash','last','fresh_rank','witness_rank','equal_random_expectation','oracle'):
        by_issue=dict(zip(reference['ids'],reference['values'][name]))
        values[name]=[by_issue[iid] for iid in ids]
    gate=[pair[0]!=pair[1] for pair in chosen['empty']]
    hash_indices=set(sorted(range(len(ids)),key=lambda j:sha('read-gate-control|'+ids[j]))[:sum(gate)])
    masks={'disagreement':gate,'equal_count_hash':[j in hash_indices for j in range(len(ids))]}
    for name,mask in masks.items():
        values['gate_'+name]=[values['witness'][j] if take else values['empty'][j] for j,take in enumerate(mask)]
        incremental=sum(indexed[iid,'witness',reverse]['usage']['total_tokens'] for j,iid in enumerate(ids) if mask[j] for reverse in (False,True))
        costs['gate_'+name]={'gated_issues':sum(mask),'incremental_tokens':incremental,
                             'total_tokens':costs['empty']['nominal_total_tokens']+incremental,
                             'incremental_assignments':2*sum(mask)}
    expected={'ids':ids,'groups':groups,'values':values,'chosen':chosen,'gate_masks':masks}
    assert_same(expected,saved,('reader vectors',sub))
    return expected,costs

def verify_metrics(report,vectors,contrasts):
    assert_same({name:stats(value) for name,value in vectors['values'].items()},report['metrics'],'metric aggregates')
    for a,b in contrasts:
        assert_same(delta(vectors['values'][a],vectors['values'][b],vectors['groups']),
                    report['contrasts'][a+'_minus_'+b],('contrast',a,b))

def verify_control(sub,rows,labels,main):
    ids=main['ids']
    lookup={(row['issue'],row['reverse']):row for row in rows}
    mapping={'claude':'claude','codex':'gemini'}
    values=[];picked=[];invalid=disagreement=0
    for iid in ids:
        pair=[lookup[iid,reverse] for reverse in (False,True)]
        selected=[mapping[row['choice'] or tie(iid)] for row in pair]
        values.append(sum(labels[m+'|'+iid]['resolved'] for m in selected)/2)
        picked+=selected
        invalid+=sum(row['choice'] is None for row in pair)
        disagreement+=selected[0]!=selected[1]
    assert_same({'ids':ids,'values':values},read(sub+'/score_vectors.json'),('control vectors',sub))
    result=read(sub+'/results.json')
    expected={'n':len(ids),'metrics':stats(values),'invalid':invalid,'order_disagreement':disagreement,
              'picked_source':dict(collections.Counter(picked)),
              'nominal_total_tokens':sum(row['usage']['total_tokens'] for row in rows)}
    for key,value in expected.items():
        assert_same(value,result[key],('control aggregate',sub,key))
    if sub=='shuffle':
        assert_same(delta(main['values']['witness'],values,main['groups']),result['correct_minus_permuted'],'shuffle contrast')
        assert_same(delta(values,main['values']['empty'],main['groups']),result['permuted_minus_empty'],'shuffle empty')
    else:
        for name in ('empty','latest','witness','heldout_repository_prior'):
            assert_same(delta(values,main['values'][name],main['groups']),result['contrasts'][name],('strict contrast',name))

def verify_backend(rows,main):
    runtime=ROOT.parent/'runtime'
    service=json.loads((runtime/'service-resumed.json').read_bytes())
    events=[json.loads(line) for line in (runtime/'requests.jsonl').read_text().splitlines()]
    by_id={event['id']:event for event in events}
    assert len(by_id)==len(events),'Duplicate native response ids'
    boundary=service['utc_epoch']
    log=(runtime/'resumed-native.log').read_text(errors='replace')
    assert 'an illegal memory access was encountered' in log
    assert 'no CUDA-capable device is detected' in log
    counts=collections.Counter()
    per_issue=collections.defaultdict(list)
    for sub,assigned in rows.items():
        prefix=sub+'/' if sub else ''
        for row in assigned:
            event=by_id[row['response_id']]
            call=read(prefix+'calls/'+row['request_hash']+'.json.gz')
            messages=json.dumps(call['request']['messages'],ensure_ascii=False,sort_keys=True).encode()
            assert sha(messages)==event['message_sha256']
            assert event['usage']==row['usage']
            assert event['seed']==17112026
            assert event['temperature']==0
            assert event['chat_template_thinking'] is False
            assert event['max_output']==12 and event['http_status']==200
            backend='CPU_after_CUDA_fault' if event['epoch']>=boundary else 'GPU'
            if sub=='strict':
                counts[backend]+=1
                per_issue[row['issue']].append(backend)
            else:
                assert backend=='GPU',('unexpected primary CPU response',sub,row['issue'])
    ids=sorted(iid for iid,backends in per_issue.items() if backends==['GPU','GPU'])
    strict=read('strict/score_vectors.json')
    by_issue=dict(zip(strict['ids'],strict['values']))
    positions={iid:j for j,iid in enumerate(main['ids'])}
    values=[by_issue[iid] for iid in ids]
    groups=[main['groups'][positions[iid]] for iid in ids]
    reference={name:[main['values'][name][positions[iid]] for iid in ids]
               for name in ('empty','latest','witness','heldout_repository_prior')}
    actual=read('strict/backend_sensitivity.json')
    expected={'assignments_by_backend':dict(counts),
              'native_calls_by_backend':dict(collections.Counter('CPU_after_CUDA_fault' if event['epoch']>=boundary else 'GPU' for event in events)),
              'included_gpu_only_issues':ids,'n_complete_gpu_pairs':len(ids),
              'metrics':{'strict':stats(values),**{name:stats(v) for name,v in reference.items()}},
              'contrasts':{name:delta(values,v,groups) for name,v in reference.items()},
              'backend_boundary':boundary,'primary_clean_all_gpu':True}
    assert_same(expected,actual,'backend sensitivity')
    return {'strict_assignments':dict(counts),'gpu_only_issue_pairs':len(ids),'unique_native_calls':len(events)}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs-only',action='store_true')
    parser.add_argument('--require-report-bytes',action='store_true')
    args=parser.parse_args()
    counts,records,issues,receipt=inputs()
    if args.inputs_only:
        print('PASS inputs only',json.dumps(counts,sort_keys=True))
        return
    # All four reader locks must exist before this verifier opens any label or choice JSON.
    for prefix in ('','clean/','shuffle/','strict/'):
        verify_lock(prefix+'reader_lock.json')
    rows={sub:choices(sub) for sub in ('','clean','shuffle','strict')}
    labels,report_byte_count=verify_labels(args.require_report_bytes)
    verify_lock('result_lock.json')
    stored=read('score_vectors.json.gz');results=read('results.json')
    pairs=verify_pairs(stored['pairs'],labels,records,issues,receipt)
    pair_contrasts=[('fresh_rank','last'),('witness_rank','last'),('witness_rank','fresh_rank'),('witness_rank','heldout_repository_prior')]
    for key,vectors in pairs.items():
        verify_metrics(results['pairs'][key],vectors,pair_contrasts)
    reader_contrasts=[('latest','empty'),('witness','empty'),('witness','latest'),('witness','heldout_repository_prior'),
                      ('gate_disagreement','empty'),('gate_disagreement','gate_equal_count_hash'),('witness_single','empty_single')]
    readers={}
    for key,sub in [('original',''),('clean','clean')]:
        vectors,costs=verify_reader(sub,rows[sub],labels,issues,pairs[key],stored['reader'][key])
        verify_metrics(results['reader'][key],vectors,reader_contrasts)
        assert_same(costs,results['reader'][key]['costs'],('reader costs',key))
        readers[key]=vectors
    for sub in ('shuffle','strict'):
        verify_control(sub,rows[sub],labels,readers['clean'])
    if (ROOT/'BACKEND_AMENDMENT.md').exists():
        backend=verify_backend(rows,readers['clean'])
        print('Backend attribution verified',json.dumps(backend,sort_keys=True))
    print('PASS complete offline audit',json.dumps({'labels':len(labels),'assignments':sum(len(x) for x in rows.values()),'receipts':len(records),'raw_http_reports':report_byte_count},sort_keys=True))
    if report_byte_count:
        print('Original official report bytes verified against SHA-256 and source MD5 or Git blob hashes. Repository tests were not rerun.')
    else:
        print('Only parsed official reports and declared source metadata were checked. Raw report bytes were unavailable. Repository tests were not rerun.')
if __name__=='__main__':
    main()

