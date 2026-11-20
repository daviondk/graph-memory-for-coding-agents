"""Select graph-memory reads. No labels, solution, patches or remote inference."""
import ast
from collections import Counter,defaultdict
import math
import re
import json
import textwrap
from pathlib import Path
from transformers import AutoTokenizer
from source import ROOT,R8,CACHE,inputs,base,member,h,load_json,write_json
from rank import extract
METHODS=['dense','bm25','ids','one','corroborated','two_callers','matched']
def read_edges(doc):
    lines=doc.splitlines()[1:]
    first=next((i for i,x in enumerate(lines) if re.match(r'^\s*(?:async\s+)?def\s+',x)),None)
    if first is None:return None
    src='\n'.join(lines[first:])
    try:tree=ast.parse(textwrap.dedent(src))
    except (SyntaxError,ValueError,RecursionError):return None
    methods=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    if len(methods)!=1:return None
    result=set()
    def visit(n):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Lambda,ast.ClassDef)):return
        if isinstance(n,ast.Call):
            if isinstance(n.func,ast.Attribute):result.add(n.func.attr)
            elif isinstance(n.func,ast.Name):result.add(n.func.id)
        for kid in ast.iter_child_nodes(n):visit(kid)
    for expr in methods[0].body:visit(expr)
    return result
def rank_band(k):
    return 0 if k<=20 else 1 if k<=40 else 2 if k<=80 else 3
def predict(t,tokenizer):
    record=load_json(ROOT/'dense'/(t+'.json'))
    order=[r['id'] for r in sorted(record['candidates'],key=lambda r:(-r['dot'],r['id']))]
    lex=[r['id'] for r in sorted(record['candidates'],key=lambda r:(-r['bm25'],r['id']))]
    raw=member(base(t)+'corpus.jsonl')
    assert h(raw)==record['corpus_sha256']
    parsed=[json.loads(x) for x in raw.splitlines()]
    docs={r['_id']:r['text'] for r in parsed}
    assert set(order)==set(docs)
    rank={s:i for i,s in enumerate(order,1)}
    seed=order[:6]
    suffix={s:s.split('/')[-1] for s in docs}
    counts=Counter(suffix.values())
    address={n:s for s,n in suffix.items() if counts[n]==1}
    exact=extract(inputs(t)[0])
    observed=defaultdict(list); failed=[]
    for src in seed:
        matches=read_edges(docs[src])
        if matches is None:failed.append(src);continue
        for n in sorted(matches):
            target=address.get(n)
            if target and target!=src:observed[target].append(src)
    outsiders=order[10:]
    implic=[s for s in outsiders if suffix[s] in exact]
    suggestions={'dense':[],'bm25':[],'ids':implic[:2]}
    supported=sorted((s for s in outsiders if observed.get(s)),key=lambda s:(-(len(observed[s])+int(suffix[s] in exact)),rank[s]))
    suggestions['one']=supported[:2]
    suggestions['corroborated']=[s for s in supported if len(observed[s])+int(suffix[s] in exact)>=2][:2]
    suggestions['two_callers']=sorted((s for s in supported if len(observed[s])>=2),key=lambda s:(-len(observed[s]),rank[s]))[:2]

    # Evaluate the degree-matched control only after the genuine decision was made.
    indegree=Counter()
    graph_parse_ok=0
    for src,doc in docs.items():
        calls=read_edges(doc)
        if calls is None:continue
        graph_parse_ok+=1
        for n in calls:
            dst=address.get(n)
            if dst and src!=dst:indegree[dst]+=1
    def dbin(s):return int(math.log2(indegree[s]+1))
    pairs=[]
    corr=suggestions['corroborated']
    pool=set(outsiders)-set(corr)
    for genuine in corr:
        if not pool:break
        sister=min(pool,key=lambda s:(abs(rank_band(rank[s])-rank_band(rank[genuine])),abs(dbin(s)-dbin(genuine)),abs(rank[s]-rank[genuine]),h(t+'|'+genuine+'|'+s)))
        pool.remove(sister)
        pairs.append({'original':genuine,'null':sister,'same_rank_bin':rank_band(rank[sister])==rank_band(rank[genuine]),'same_degree_bin':dbin(sister)==dbin(genuine),'rank_orig':rank[genuine],'rank_null':rank[sister],'degree_orig':indegree[genuine],'degree_null':indegree[sister]})
    suggestions['matched']=[p['null'] for p in pairs]
    ranking={}
    for m,picks in suggestions.items():
        if m=='bm25':ranking[m]=lex;continue
        cut=10-len(picks)
        ranking[m]=order[:cut]+picks+[c for c in order[cut:] if c not in picks]
        assert len(ranking[m])==len(set(ranking[m]))==len(order) and ranking[m][:8]==order[:8]
    triples=[[src,suffix[dst],dst] for dst,srcs in sorted(observed.items()) for src in sorted(srcs)]
    bytes_seed=sum(len(docs[c].encode('utf-8')) for c in seed)
    tok=sum(len(tokenizer(docs[c],add_special_tokens=False,truncation=False,verbose=False)['input_ids']) for c in seed)
    return {'issue':t,'n_corpus':len(order),'seed':seed,'seed_bytes':bytes_seed,'seed_wordpieces':tok,'stored_edges':triples,'serialized_triple_bytes':len(json.dumps(triples,ensure_ascii=False,separators=(',',':')).encode()),'failed_seed_ast':failed,'evaluation_only_globally_parsed':graph_parse_ok,'evaluation_only_scan_n':len(docs),'query_identifiers':exact,'null_pairs':pairs,'suggestions':suggestions,'ranks':ranking}
def main():
    import warnings;warnings.filterwarnings('ignore',category=SyntaxWarning)
    tokenizer=AutoTokenizer.from_pretrained(str(CACHE/'model'),local_files_only=True)
    sample=load_json(ROOT/'sample.json')['selected']
    out=ROOT/'predictions';out.mkdir(exist_ok=True)
    for r in sample:
        t=r['issue']; p=out/(t+'.json')
        if (ROOT/'dense'/(t+'.json')).exists() and not p.exists():
            rec=predict(t,tokenizer)
            write_json(p,rec)
            print(t,'proposed',len(rec['suggestions']['corroborated']),flush=True)
    if len(list(out.glob('*.json')))==len(sample):
        scripts=['FORMAT_AUDIT.md','PROTOCOL.md','source.py','sample.py','embed.py','predict.py','score.py','sample.json']
        paths=[ROOT/s for s in scripts]+list((ROOT/'dense').glob('*.json'))+list(out.glob('*.json'))
        upstream=['acquire.py','encoder.py','pool_rank.py','prepare.py','rank.py','model_manifest.json','backend_manifest.json']
        write_json(ROOT/'blind_seal.json',{'local':{p.relative_to(ROOT).as_posix():h(p.read_bytes()) for p in paths},'r8':{f:h((R8/f).read_bytes()) for f in upstream}})
if __name__=='__main__':main()
