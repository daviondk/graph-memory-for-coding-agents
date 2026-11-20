"""Grade already locked choices against separately downloaded official test reports."""
import collections,itertools,random,statistics
from common import *

def outcome(d):
    return {r['id']:r for r in d}

def cluster_interval(deltas,groups,n=6000):
    by=collections.defaultdict(list)
    for x,g in zip(deltas,groups):by[g].append(x)
    units=list(by);rng=random.Random(17112026)
    vals=[]
    for _ in range(n):
        sample=[by[rng.choice(units)] for j in units]
        vals.append(sum(map(sum,sample))/sum(map(len,sample)))
    vals.sort()
    return [vals[int(n*.025)],vals[int(n*.975)]]

def stats(v):
    return {'n':len(v),'success_sum':sum(v),'mean':statistics.mean(v)}

def delta(a,b,groups):
    ds=[x-y for x,y in zip(a,b)]
    return {'difference':statistics.mean(ds),'wins':sum(x>0 for x in ds),'losses':sum(x<0 for x in ds),
            'ties':sum(x==0 for x in ds),'repository_cluster_ci95':cluster_interval(ds,groups)}

def grade_pair(m1,m2,ids,labels,receipts,issues):
    models=[m1,m2]
    keep=[i for i in ids if all(m+'|'+i in labels for m in models)]
    groups=[issues[i]['repo'] for i in keep]
    ys={m:[int(labels[m+'|'+i]['resolved']) for i in keep] for m in models}
    picks={m:[m]*len(keep) for m in models}
    picks['hash']=[models[int(sha('tie-s4|'+i),16)%2] for i in keep]
    picks['shorter']=[]
    for i in keep:
        lengths={m:len(read('records/'+m+'/'+i+'.json.gz')['patch']) for m in models}
        picks['shorter'].append(min(models,key=lambda m:(lengths[m],m!=models[int(sha('tie-s4|'+i),16)%2])))
    for key in ['last','fresh_rank','witness_rank']:
        picks[key]=[max(models,key=lambda m:(receipts[m+'|'+i][key],m!=models[1-int(sha('tie-s4|'+i),16)%2])) for i in keep]
    picks['heldout_repository_prior']=[]
    for i in keep:
        r=issues[i]['repo']
        other=[j for j in keep if issues[j]['repo']!=r]
        vals={m:sum(labels[m+'|'+j]['resolved'] for j in other)/len(other) if other else 0 for m in models}
        picks['heldout_repository_prior'].append(max(models,key=lambda m:(vals[m],m==models[int(sha('tie-s4|'+i),16)%2])))
    values={k:[int(labels[m+'|'+i]['resolved']) for m,i in zip(ms,keep)] for k,ms in picks.items()}
    values['equal_random_expectation']=[(ys[m1][j]+ys[m2][j])/2 for j in range(len(keep))]
    values['oracle']=[max(ys[m1][j],ys[m2][j]) for j in range(len(keep))]
    report={'models':models,'n':len(keep),'missing_label_ids':sorted(set(ids)-set(keep)),
            'joint':dict(collections.Counter(str(a)+str(b) for a,b in zip(ys[m1],ys[m2]))),
            'metrics':{k:stats(v) for k,v in values.items()},
            'contrasts':{k+'_minus_'+base:delta(values[k],values[base],groups) for k,base in [('fresh_rank','last'),('witness_rank','last'),('witness_rank','fresh_rank'),('witness_rank','heldout_repository_prior')]}}
    return report,{'ids':keep,'groups':groups,'choices':picks,'values':values}

def grade_reader(sub,mapping,labels,issues,reference):
    root=ROOT/sub
    lock=json.loads((root/'reader_lock.json').read_text())
    assert all(sha((root/k).read_bytes())==v for k,v in lock.items())
    rows=json.loads((root/'choices.json').read_text())
    ids=sorted({r['issue'] for r in rows});groups=[issues[i]['repo'] for i in ids]
    by={(r['issue'],r['arm'],r['reverse']):r for r in rows}
    assert len(rows)==576==len(by)
    masks={};chosen={};values={};costs={}
    for a in ('empty','latest','witness'):
        chosen[a]=[];values[a]=[];values[a+'_single']=[]
        costs[a]={'nominal_total_tokens':0,'unique_requests':len({r['request_hash'] for r in rows if r['arm']==a}),
                  'invalid':0,'order_disagreement':0}
        for i in ids:
            pair=[by[i,a,rev] for rev in (False,True)]
            sources=[mapping[r['choice'] or pick(i)] for r in pair]
            chosen[a].append(sources)
            values[a].append(sum(labels[m+'|'+i]['resolved'] for m in sources)/2)
            one=sources[0] if sources[0]==sources[1] else mapping[pick(i)]
            values[a+'_single'].append(int(labels[one+'|'+i]['resolved']))
            costs[a]['order_disagreement']+=sources[0]!=sources[1]
            costs[a]['invalid']+=sum(r['choice'] is None for r in pair)
            costs[a]['nominal_total_tokens']+=sum(r['usage']['total_tokens'] for r in pair)
    for m in mapping.values():values[m]=[int(labels[m+'|'+i]['resolved']) for i in ids]
    for name in ('heldout_repository_prior','shorter','hash','last','fresh_rank','witness_rank','equal_random_expectation','oracle'):
        lookup=dict(zip(reference['ids'],reference['values'][name]));values[name]=[lookup[i] for i in ids]
    gate=[p[0]!=p[1] for p in chosen['empty']]
    random_indices=set(sorted(range(len(ids)),key=lambda j:sha('read-gate-control|'+ids[j]))[:sum(gate)])
    masks={'disagreement':gate,'equal_count_hash':[j in random_indices for j in range(len(ids))]}
    for name,mask in masks.items():
        values['gate_'+name]=[values['witness'][j] if mask[j] else values['empty'][j] for j in range(len(ids))]
        marginal=sum(by[i,'witness',rev]['usage']['total_tokens'] for j,i in enumerate(ids) if mask[j] for rev in (False,True))
        costs['gate_'+name]={'gated_issues':sum(mask),'incremental_tokens':marginal,'total_tokens':costs['empty']['nominal_total_tokens']+marginal,
                            'incremental_assignments':2*sum(mask)}
    contrasts=[('latest','empty'),('witness','empty'),('witness','latest'),('witness','heldout_repository_prior'),
               ('gate_disagreement','empty'),('gate_disagreement','gate_equal_count_hash'),('witness_single','empty_single')]
    result={'mapping':mapping,'n':len(ids),'repositories':dict(collections.Counter(groups)),
            'metrics':{k:stats(v) for k,v in values.items()},'costs':costs,
            'contrasts':{a+'_minus_'+b:delta(values[a],values[b],groups) for a,b in contrasts},
            'joint':dict(collections.Counter(str(int(labels[mapping['claude']+'|'+i]['resolved']))+str(int(labels[mapping['codex']+'|'+i]['resolved'])) for i in ids))}
    return result,{'ids':ids,'groups':groups,'values':values,'chosen':chosen,'gate_masks':masks}

def main():
    for sub in ('','clean'):check(('' if not sub else sub+'/')+'input_lock.json') if not sub else None
    inputs=read('grade_lock.json');assert inputs==seal(inputs),'changed grading script'
    labels=read('labels.json.gz');rec=read('receipts.json.gz');iss=read('issues.json')
    clean=read('clean/cohort.json');allids=sorted(iss)
    pairs={};vectors={}
    for key,a,b,ids in [('original','claude','codex',allids),('clean','claude','gemini',clean),('codex_gemini','codex','gemini',clean)]:
        pairs[key],vectors[key]=grade_pair(a,b,ids,labels,rec,iss)
    exact=[i for i in allids if all(read('records/'+m+'/'+i+'.json.gz')['traj_submission_matches'] for m in ('claude','codex'))]
    pairs['original_exact'],vectors['original_exact']=grade_pair('claude','codex',exact,labels,rec,iss)
    llm={};lvec={}
    for key,path,mp in [('original','',{'claude':'claude','codex':'codex'}),('clean','clean',{'claude':'claude','codex':'gemini'})]:
        llm[key],lvec[key]=grade_reader(path,mp,labels,iss,vectors[key])
    write('results.json',{'pairs':pairs,'reader':llm})
    write('score_vectors.json.gz',{'pairs':vectors,'reader':lvec})
    write('result_lock.json',seal(['results.json','score_vectors.json.gz','labels.json.gz','grade.py','grade_lock.json']))
    print(canon({'main':llm['clean'],'rules':pairs['clean']}))
if __name__=='__main__':main()
