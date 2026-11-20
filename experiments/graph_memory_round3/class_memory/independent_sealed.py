"""Check the committed requests, own-arm state at every method, and functional outcomes."""
import ast
import concurrent.futures
from collections import Counter
from pathlib import Path

from independent_audit import (HERE, check_memory, defs, digest, execute, get, matches, memories,
                              parse, parse_candidate, request, req_key, write)

TEACHER="decision_lock.json"
ONLINE="online_decision_lock.json"
ARMS=("graph", "bm25_line", "full")


def load_seals():
    if not all((HERE / x).is_file() for x in (TEACHER,ONLINE)):
        raise SystemExit("No completion, outcome, or partial program inspected. Waiting for both decision locks.")
    return {'teacher':matches(TEACHER, HERE/'calls'),'online':matches(ONLINE)}


def clean_reply(record):
    return record["reply"]["choices"][0]["message"].get("content") or ""


def normalized(src, name):
    try:
        return ast.unparse(parse_candidate(src,name)),True
    except (SyntaxError,ValueError,TypeError,IndentationError):
        return f"def {name}(self, *args, **kwargs):\n    raise NotImplementedError",False


def check_record(arm, expected, folder, key):
    assert req_key(expected)==key
    rec=get(folder+'/'+key+'.json.gz')
    assert rec['key']==key and rec['request']==expected
    return rec


def base_payload(r, name, test_name, suite, source=None):
    return {'name':name,'class':r['class_name'],'tests':suite,'testclass':test_name,
            'source':r['solution_code'] if source is None else source,'imports':r['import_statement']}


def run_all(payloads):
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        return dict(zip(payloads,pool.map(execute,payloads.values())))


def result_tallies(data):
    return {k:v for k,v in data.items() if k not in ('failures','why')}


def teacher_replay(raw):
    visible={v['id']:v for v in get('visible.json')}
    packets={p['id']:p for p in get('packets.json')}
    planned={a['id']:a['arms'] for a in get('assignment.json')}
    jobs={};counts=Counter();scores={};totals={};paired={}
    for i,arms in planned.items():
        v=visible[i];ti,name=i.split('/');r=raw[ti];m=next(m for m in r['methods_info'] if m['method_name']==name)
        totals[i]=get('calibration.json')[i][1]['total']
        suite=base_payload(r,name,m['test_class'],m['test_code'])
        for arm,key in arms.items():
            rec=check_record(arm,request(v,packets[i]['mem'][arm]),'calls',key)
            jobs[key]=dict(suite,grade='generated',candidate=clean_reply(rec))
            counts[arm]+=1
    assert {k+'.json.gz' for k in jobs}==set(get(TEACHER))
    observed=run_all(jobs)
    pub=get('grading.json.gz') if (HERE/'grading.json.gz').exists() else None
    if pub is not None:assert set(pub)==set(observed)
    if pub is not None:assert all(result_tallies(pub[k])==result_tallies(observed[k]) for k in jobs)
    for arm in counts:
        passed=[int(observed[arms[arm]]['status']=='pass') for arms in planned.values()]
        testcounts=[observed[arms[arm]].get('passed',0) for arms in planned.values()]
        scores[arm]={'methods':sum(passed),'tests':sum(testcounts),'denominator_methods':len(passed),'denominator_tests':sum(totals.values())}
    for other in counts:
        mdiff=[int(observed[arms['graph']]['status']=='pass')-int(observed[arms[other]]['status']=='pass') for arms in planned.values()]
        paired[other]={'method_wins':mdiff.count(1),'method_losses':mdiff.count(-1)}
    if (HERE/'results.json').is_file():
        aggregates=get('results.json')['main']['scores']
        for a,summary in scores.items():
            assert summary['tests']==aggregates[a]['passed'] and summary['methods']==aggregates[a]['pass_all'] and summary['denominator_tests']==aggregates[a]['total']
    return {'counts':scores,'graph_vs':paired,'unique_reexecuted':len(observed),'compared_with_saved_grading':pub is not None}


def online_replay(raw):
    selected=get('online_visible.json')
    programs={c['id']:c for c in get('online_programs.json.gz')};assert set(programs)=={v['id'] for v in selected}
    jobs={}; callkeys=set();counts=Counter();fallback=Counter();provenance={}
    for c in selected:
        i=c['id'];r=raw[i];program=programs[i];provenance[i]={}
        declared={m['test_class']:m['method_name'] for m in r['methods_info']}
        testmap=defs(parse(r['test']),ast.ClassDef);assert set(testmap)==set(r['test_classes'])
        for arm in ARMS:
            history=[];ordered=[]
            for target,log in zip(c['targets'],program['logs'][arm],strict=True):
                name,desc=target;rid=f'{i}/{name}';key=log['key']
                assert log['name']==name
                view={**c,'id':rid,'name':name,'desc':desc,'previous':history}
                only_own_source=memories(view)[arm] if history else ''
                assert only_own_source==log['memory']
                check_memory(only_own_source,view,arm)
                rec=check_record(arm,request(view,only_own_source),'online_calls',key)
                src,valid=normalized(clean_reply(rec),name)
                assert bool(log['valid'])==valid
                if not valid:fallback[arm]+=1
                history.append({'method':name,'src':src});counts[arm]+=1;callkeys.add(key);ordered.append(key)
            assert history==program['histories'][arm]
            provenance[i][arm]=ordered
            prior={h['method']:parse(h['src']).body[0] for h in history}
            tree=parse(r['skeleton']);cl=defs(tree,ast.ClassDef)[r['class_name']]
            for j,decl in enumerate(cl.body):
                if not isinstance(decl,ast.FunctionDef) or decl.name not in prior:continue
                exact=prior[decl.name];exact.decorator_list=decl.decorator_list;cl.body[j]=exact
            source=ast.unparse(cl)
            for suite in r['test_classes']:
                key=(i,arm,suite,'method' if suite in declared else 'integration')
                jobs[key]=dict(base_payload(r,c['targets'][0][0],suite,ast.unparse(testmap[suite]),source),grade='reference')
    assert {p.name for p in (HERE/'online_calls').glob('*.json.gz')}=={k+'.json.gz' for k in callkeys}
    results=run_all(jobs)
    pub=({v['id']:v['values'] for v in get('online_scored.json.gz')} if (HERE/'online_scored.json.gz').exists() else None)
    from collections import defaultdict
    stats=defaultdict(Counter);classes={a:{} for a in ARMS};flows=Counter()
    for c in selected:
        i=c['id']
        for arm in ARMS:
            subset={k:v for k,v in results.items() if k[:2]==(i,arm)}
            ref=get('online_reference.json')[i]
            total=sum(v['receipt']['total'] for v in ref.values())
            for k,receipt in subset.items():
                if pub is not None: assert result_tallies(pub[i][arm]['suites'][k[2]]['receipt'])==result_tallies(receipt)
            integ=[v['status']=='pass' for k,v in subset.items() if k[-1]=='integration']
            mets=[v['status']=='pass' for k,v in subset.items() if k[-1]=='method']
            assert integ and mets
            all_ok=int(all(integ+mets));classes[arm][i]=all_ok
            stats[arm].update(dict(pass_all=all_ok,integration=int(all(integ)),method=sum(mets),methods=len(mets),
                                    tests=sum(v.get('passed',0) for v in subset.values()),total=total))
        baseline=provenance[i]['bm25_line'];alternative=provenance[i]['graph']
        flows['distinct_graph_bm25_prompts']+=sum(x!=y for x,y in zip(baseline,alternative,strict=True))
        flows['classes_with_distinct_graph_bm25_prompt']+=int(baseline!=alternative)
    if (HERE/'online_results.json').is_file():
        reported=get('online_results.json')['scores']
        for a in ARMS:
            for k,num in stats[a].items():assert reported[a][k]==num
    paired={}
    for a in ARMS:
        dif=[classes['graph'][i]-classes[a][i] for i in programs]
        paired[a]={'class_wins':dif.count(1),'class_losses':dif.count(-1)}
    return dict(class_ids=classes,counts=dict(stats),graph_vs=paired,unique_calls=len(callkeys),method_arm_decisions=sum(counts.values()),
                suites_reexecuted=len(results),observed_different_traces=flows,parser_fallbacks=fallback,compared_with_saved_grading=pub is not None)


def audit_sealed():
    seal=load_seals()
    raw={r['task_id']:r for r in get('ClassEval_data.json')}
    data={'decision_hashes':seal,'teacher':teacher_replay(raw),'online':online_replay(raw)}
    write('independent_sealed.json',data)
    print('Sealed replay complete', flush=True)


if __name__=='__main__':
    audit_sealed()

