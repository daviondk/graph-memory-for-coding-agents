"""Rebuild both controllers from published inputs and compare all sealed retrieval outputs to the annotations."""
from collections import Counter,defaultdict
from pathlib import Path
import gzip,hashlib,json,math,re
import pyarrow.parquet as pq
from tokenizers import Tokenizer
D=Path(__file__).resolve().parent
BASE=D.parent
TOK=Path("D:/CodexResearch/x20-r23-multidoc2dial/model/tokenizer.json")
A="local_static";B="mention_title"
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix==".gz" else p.read_bytes())
def write(p,data):
    b=(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b)
def examples(name,path):
    if name=="observed_transfer":
        for batch in pq.ParquetFile(path).iter_batches(batch_size=256,columns=["_id","question","context","supporting_facts"]):
            for r in batch.to_pylist():
                q=r["_id"];ctx=json.loads(r["context"])
                order=sorted(range(len(ctx)),key=lambda j:hashlib.sha256((q+"|"+ctx[j][0]).encode()).digest())
                yield q,r["question"],{ix:(ctx[j][0]," ".join(ctx[j][1])) for ix,j in enumerate(order)}, {x[0] for x in json.loads(r["supporting_facts"])},True,order
    else:
        with path.open(encoding="utf8") as fd:
            for line in fd:
                r=json.loads(line);q=r["id"];ps=r["paragraphs"]
                order=sorted(ps,key=lambda p:hashlib.sha256((q+"|musique|"+str(p["idx"])).encode()).digest())
                yield q,r["question"],{p["idx"]:(p["title"],p["paragraph_text"]) for p in order},{p["idx"] for p in ps if p["is_supporting"]},False,None
def words(txt):return re.findall(r"[^\W_]+",txt.lower())
def reconstruct(question,cat,tok):
    title={k:words(v[0]) for k,v in cat.items()};avg=sum(map(len,title.values()))/len(title) or 1
    df=Counter(w for doc in title.values() for w in set(doc));idf={t:math.log(1+(len(title)-v+.5)/(v+.5)) for t,v in df.items()}
    q=set(words(question));bm={}
    for i,terms in title.items():
        counts=Counter(terms)
        bm[i]=sum(idf[t]*n*2.2/(n+1.2*(.25+.75*len(terms)/avg)) for t,n in counts.items() if t in q)
    ordered=sorted(bm,key=bm.get,reverse=True);first,*others=ordered
    text=cat[first][1];offsets=tok.encode(text,add_special_tokens=False).offsets[:192]
    body=words(text[:offsets[-1][1]]) if offsets else [];residual={x for x in q.difference(title[first]) if len(x)>2}
    links={};weight={}
    for j in others:
        v=title[j];L=len(v);ix=[k for k in range(len(body)-L+1) if L and len("".join(v))>=3 and body[k:k+L]==v]
        if ix:
            links[j]=ix;weight[j]=max(sum(idf.get(w,1) for w in sorted(residual.intersection(body[max(0,k-12):k+L+12]))) for k in ix)
    bas=next((j for j in others if j in links),others[0]);loc=max(others,key=lambda j:(j in links,weight.get(j,0)))
    return first,bas,loc,links,weight,len(offsets)
def exam(name,path):
    fold=BASE/name;plan=read(fold/"plan.json");seal=read(fold/"seal.json")
    assert digest(path)==plan["source"] and digest(TOK)==plan["tokenizer"] and digest(fold/"predictions.json.gz")==seal["predictions"] and digest(fold/"plan.json")==seal["plan"]
    pred=read(fold/"predictions.json.gz");ref=read(fold/"results.json");tok=Tokenizer.from_file(str(TOK))
    counter=defaultdict(Counter);summary=Counter();cases={};observed=set()
    for q,question,cat,gold,bytitle,order in examples(name,path):
        observed.add(q);rec=pred[q];seed,b,l,link,score,n=reconstruct(question,cat,tok)
        assert (seed,b,l,n,len(link))==(rec["seed"],rec["next"][B],rec["next"][A],rec["tokens"],rec["n_links"]),q
        if bytitle:assert rec["order"]==order
        ids=lambda x:{cat[i][0] for i in x} if bytitle else set(x)
        assert gold and len(gold)<=4
        summary["n"]+=1;summary["two"]+=len(gold)==2;summary["token_sum"]+=n
        summary["multi"]+=len(link)>1;summary["two_multi"]+=len(gold)==2 and len(link)>1
        for k,v in rec["next"].items():
            assert v in cat and v!=seed
            selected=ids((seed,v));g=len(gold);hits=len(selected&gold)
            z=counter[k];z["both"]+=(selected==gold and g==2);z["recall_sum"]+=hits/g;z["f1_sum"]+=2*hits/(len(selected)+g)
        if b!=l:
            assert b in link and l in link and score[l]>score[b]
            hb=int(ids((seed,b))==gold);hl=int(ids((seed,l))==gold)
            cases[q]=dict(seed=seed,base=b,local=l,base_title=cat[b][0],local_title=cat[l][0],base_position=link[b],local_position=link[l],base_weight=score[b],local_weight=score[l],g=len(gold),delta=hl-hb,duplicate_name=(cat[b][0]==cat[l][0]))
    assert observed==set(pred) and len(pred)==ref['n'] and summary["two"]==ref['n_two']
    for k,z in counter.items():
        if name=="observed_transfer":
            assert z['both']==ref['two'][k]['both'] and math.isclose(z['recall_sum']/summary['n']*100,ref['all'][k]['recall_pct'],abs_tol=1e-9)
        else:assert z['both']==ref['score'][k]['two_exact'] and math.isclose(z['f1_sum']/summary['n'],ref['score'][k]['author_support_f1'],abs_tol=1e-9)
    two=[r for r in cases.values() if r["g"]==2];deltas=Counter(r["delta"] for r in two);nt=deltas[1]+deltas[-1]
    pm=min(1.,2*sum(math.comb(nt,i) for i in range(min(deltas[1],deltas[-1])+1))/2**nt) if nt else 1.
    sig=ref['primary'] if bytitle else ref['local_minus'][B]
    assert [deltas[1],deltas[-1]]==[sig['wins'],sig['losses']]
    return dict(summary=summary,counts=counter,different_all=len(cases),different_two=len(two),outcomes_changed=dict(deltas),exact_mcnemar_two_sided=pm,duplicate_title_flips=sum(c['duplicate_name'] for c in cases.values()),code_sha=digest(Path(__file__)),prediction_sha=seal["predictions"]),cases
def main():
    results={};records={}
    for k,src in [('observed_transfer','D:/CodexResearch/x20-r32-2wiki/dev.parquet'),('musique_links','D:/CodexResearch/x20-r32-musique/musique.jsonl')]:
        results[k],records[k]=exam(k,Path(src))
    write(D/"audit.json",results);write(D/"disagreements.json.gz",records)
    for k,r in results.items():print(k,r["summary"],r['different_all'],r['different_two'],r['outcomes_changed'],r['exact_mcnemar_two_sided'],r['duplicate_title_flips'])
if __name__=="__main__":main()