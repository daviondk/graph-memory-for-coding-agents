"""Independent posthoc artifact-gate audit. Derive every gate before loading grades."""
import collections,datetime,gzip,hashlib,json,random,re,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def read(name):
    path=ROOT/name
    raw=path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix=='.gz' else raw)
def sha(raw):
    return hashlib.sha256(raw if isinstance(raw,bytes) else raw.encode()).hexdigest()
def canon(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=True,separators=(',',':'))
def check_lock(name):
    parent=(ROOT/name).parent
    for path,digest in read(name).items():
        assert sha((parent/path).read_bytes())==digest,(name,path)
def stats(values):
    return {'n':len(values),'success_sum':sum(values),'mean':statistics.mean(values)}
def contrast(first,second,groups):
    changes=[x-y for x,y in zip(first,second)]
    cluster=collections.defaultdict(list)
    for group,change in zip(groups,changes):cluster[group].append(change)
    names=list(cluster)
    randomizer=random.Random(17112026)
    bootstrap=[]
    for _ in range(6000):
        sampled=[cluster[randomizer.choice(names)] for name in names]
        bootstrap.append(sum(map(sum,sampled))/sum(map(len,sampled)))
    bootstrap.sort()
    return {'difference':statistics.mean(changes),'wins':sum(x>0 for x in changes),
            'losses':sum(x<0 for x in changes),'ties':sum(x==0 for x in changes),
            'repository_cluster_ci95':[bootstrap[150],bootstrap[5850]]}
def select(text):
    matched=re.fullmatch(r'\s*(?:candidate\s*)?[(*\x22\x27\x60\[]*([AB])[)*\x22\x27\x60\].!]*\s*',text,re.I)
    return matched[1].upper() if matched else None
def derive_gate(rows,packets):
    ids=sorted(packets)
    by={}
    counts=collections.defaultdict(collections.Counter)
    for row in rows:
        call=read('clean/calls/'+row['request_hash']+'.json.gz')
        assert sha(canon(call['request']))==row['request_hash']
        assert call['response']['id']==row['response_id']
        assert call['response']['usage']==row['usage']
        letter=select(call['response']['choices'][0]['message']['content'])
        counts[row['arm']][letter or 'invalid']+=1
        # All observed responses in this cohort are valid A/B.
        assert letter in ('A','B')
        order=['gemini','claude'] if row['reverse'] else ['claude','gemini']
        actual=order['AB'.index(letter)]
        assert {'claude':'claude','codex':'gemini'}[row['choice']]==actual
        by[row['issue'],row['arm'],row['reverse']]=(actual,row['usage']['total_tokens'])
    assert len(by)==len(rows)==576
    equal_full=[];equal_visible=[];flip=[];gate=[]
    for iid in ids:
        patches=[read('records/'+model+'/'+iid+'.json.gz')['patch'] for model in ('claude','gemini')]
        equal_full.append(patches[0]==patches[1])
        equal_visible.append(packets[iid]['options']['claude']['patch']==packets[iid]['options']['codex']['patch'])
        flip.append(by[iid,'empty',False][0]!=by[iid,'empty',True][0])
        gate.append(flip[-1] and not equal_full[-1])
    return ids,by,equal_full,equal_visible,flip,gate,counts
def main():
    for name in ('input_lock.json','clean/input_lock.json','clean/reader_lock.json','result_lock.json'):
        check_lock(name)
    rows=read('clean/choices.json')
    ids,by,equal_full,equal_visible,flip,gate,position=derive_gate(rows,read('clean/reader_inputs.json.gz'))
    gate_signature=sha(canon(list(zip(ids,gate))))
    # Outcomes are opened only after the gate mask is completely fixed.
    labels=read('labels.json.gz')
    issues=read('issues.json')
    groups=[issues[iid]['repo'] for iid in ids]
    values={}
    for arm in ('empty','latest','witness'):
        values[arm]=[sum(labels[by[iid,arm,reverse][0]+'|'+iid]['resolved'] for reverse in (False,True))/2 for iid in ids]
    registered=[values['witness'][j] if flip[j] else values['empty'][j] for j in range(len(ids))]
    actual=[values['witness'][j] if gate[j] else values['empty'][j] for j in range(len(ids))]
    base_cost=sum(by[iid,'empty',reverse][1] for iid in ids for reverse in (False,True))
    incremental=sum(by[iid,'witness',reverse][1] for j,iid in enumerate(ids) if gate[j] for reverse in (False,True))
    mismatched=[labels['claude|'+iid]['resolved']!=labels['gemini|'+iid]['resolved'] for iid in ids]
    records=[{'issue':iid,'same_full_patch':equal_full[j],'same_visible_patch':equal_visible[j],
              'different_grades':mismatched[j],'source_flip':flip[j]} for j,iid in enumerate(ids)]
    assert records==read('patch_identity_rows.json')
    saved=read('score_vectors.json.gz')['reader']['clean']
    assert saved['ids']==ids
    assert saved['gate_masks']['disagreement']==flip
    assert saved['values']['gate_disagreement']==registered
    assert all(saved['values'][arm]==values[arm] for arm in values)
    # Reconstruct the supervised baseline from the entire clean cohort with the target repository held out.
    cohort=read('clean/cohort.json')
    prior=[]
    for iid in ids:
        others=[other for other in cohort if issues[other]['repo']!=issues[iid]['repo']]
        preference=['claude','gemini'][int(sha('tie-s4|'+iid),16)%2]
        averages={model:statistics.mean(labels[model+'|'+other]['resolved'] for other in others) for model in ('claude','gemini')}
        source=max(averages,key=lambda model:(averages[model],model==preference))
        prior.append(int(labels[source+'|'+iid]['resolved']))
    assert prior==saved['values']['heldout_repository_prior']
    values['heldout_repository_prior']=prior
    masks={'same_full_patch':equal_full,'same_visible_patch':equal_visible,'discordant_grades':mismatched}
    subgroups={}
    for name,mask in masks.items():
        indices=[j for j,take in enumerate(mask) if take]
        subgroups[name]={'n':len(indices),'metrics':{arm:stats([values[arm][j] for j in indices]) for arm in values}}
    diagnostics={arm:{'prefers_A':position[arm]['A'],
                     'source_flips_among_distinct_full_patches':sum(by[iid,arm,False][0]!=by[iid,arm,True][0] for j,iid in enumerate(ids) if not equal_full[j])}
                 for arm in ('empty','latest','witness')}
    expected={'counts':{name:sum(mask) for name,mask in masks.items()},
              'position_diagnostics':diagnostics,'subgroups':subgroups,
              'post_result_artifact_gate':{'gated_issues':sum(gate),'success':stats(actual),
                                          'incremental_tokens':incremental,'total_tokens':base_cost+incremental,
                                          'versus_registered_gate':contrast(actual,registered,groups),
                                          'versus_never_read':contrast(actual,values['empty'],groups)},
              'full_patch_equal_but_grade_diff':sum(x and y for x,y in zip(equal_full,mismatched))}
    assert expected==read('patch_identity_results.json')
    assert sha(canon(list(zip(ids,gate))))==gate_signature
    receipt={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,
             'analysis_status':'Post-result exploratory analysis. This verifier fixes the gate before reading grade files.',
             'source_flips':sum(flip),'distinct_patch_flips':sum(gate),'equal_full_patches':sum(equal_full),
             'no_memory_position_B':position['empty']['B'],'no_memory_assignments':192,
             'incremental_tokens':incremental,'total_tokens':base_cost+incremental,
             'gate_mask_sha256_before_loading_grades_in_verifier':gate_signature,'gating_uses_outcome_labels':False,
             'registered_outcome_vector_unchanged':actual==registered,
             'all_patch_identity_fields_recomputed':True,
             'files':{name:sha((ROOT/name).read_bytes()) for name in ('patch_identity.py','patch_identity_rows.json','patch_identity_results.json','verify_patch_identity.py','clean/choices.json','clean/input_lock.json','clean/reader_lock.json','labels.json.gz','score_vectors.json.gz')}}
    (ROOT/'patch_identity_verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='files'},indent=2))
if __name__=='__main__':
    main()

