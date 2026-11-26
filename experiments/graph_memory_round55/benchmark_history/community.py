"""Use saved author rankings as interchangeable base retrievers; no model/API reruns."""
from concurrent.futures import ThreadPoolExecutor
import gzip
from hashlib import sha256
import json
import statistics
import sys
import tarfile
from urllib.request import urlopen
from expand import ARC,directories,forecast
from extract import HERE,R54,CACHE,save
from grade import metric,paired

OKO="https://raw.githubusercontent.com/bartlomein/oko/9a8094edef23f0c3cb6d31ea511aa6597f430dfd/benchmarks/published/0.9.1/agent-retrieval-bench/details/"
CN="https://huggingface.co/datasets/sysevol-ai/codenib-arb-rankings/resolve/8be160b7258a803bc7e6d21a7f3ef0f981bdd382/rankings/"
ARMS=("dense","hybrid","zoekt","bm25","graph_expansion")
def files():
    requests={}
    def members(url,names):
        text=urlopen(url+"SHA256SUMS",timeout=40).read().decode()
        official={line.split()[1].lstrip("*").split("/")[-1]:line.split()[0] for line in text.splitlines() if line.strip()}
        for name,arm in names:
            requests[arm]=url+name,official[name]
    members(CN,[(m+"_predictions.json.gz","codenib_"+m) for m in ARMS])
    members(OKO,[(f"oko-0.9.1-run{i}_details.jsonl",f"oko{i}") for i in range(1,4)])
    def fetch(item):
        arm,(url,fingerprint)=item
        p=CACHE/url.rsplit("/",1)[1]
        if not p.exists():
            b=urlopen(url,timeout=75).read()
            assert sha256(b).hexdigest()==fingerprint
            p.write_bytes(b)
        b=p.read_bytes()
        assert sha256(b).hexdigest()==fingerprint
        raw=json.loads(gzip.decompress(b)) if p.suffix==".gz" else [json.loads(line) for line in b.splitlines()]
        return arm,{r["sample_id"]:(r["repo"],r["base_commit"],r["ranked_files"]) for r in raw}
    with ThreadPoolExecutor(3) as pool:
        return dict(pool.map(fetch,requests.items())),requests

def lock():
    rankings,sources=files()
    history=json.load(gzip.open(HERE/"history.json.gz"))
    rows=json.load(gzip.open(R54/"forecasts.json.gz"))
    # Extra base revisions may be present in the unmodified 58-sample release.
    full_keys=set()
    with tarfile.open(ARC,"r|zst") as tar:
        for member in tar:
            if member.name=="./benchmark/v2_edit2ripple/samples.jsonl":
                full_keys={r["id"] for r in map(json.loads,tar.extractfile(member))}
                break
    all_bases={rankings["oko1"][key][1] for key in full_keys}
    catalog=directories(all_bases)
    out={};original={}
    for q in sorted(full_keys):
        original[q]={}
        for arm,d in rankings.items():
            repo,base,all_paths=d[q]
            paths=list(dict.fromkeys(all_paths))
            original[q][arm]=[p for p in paths if p in catalog[base]][:5]
            if q not in rows:continue
            r=rows[q]
            assert (repo,base)==(r["repo"],r["commit"])
            pool=[p for p in paths if p in catalog[base] and p!=r["anchor"]][:20]
            if len(pool)<5:
                new=pool
            else:
                result=forecast({**r,"predictions":{"lexical":pool}},history[base]["history"],catalog[base])
                new=result["ranked"]["corroborated"]
            out.setdefault(q,{})[arm]=dict(order=pool,proposed=new)
    save(HERE/"community-ranks.json.gz",out)
    save(HERE/"publisher-top5.json.gz",original)
    save(HERE/"community-seal.json",{"sources":sources,"hashes":{
            p:sha256((HERE/p).read_bytes()).hexdigest() for p in
            ("COMMUNITY_RU.md","community.py","community-ranks.json.gz","publisher-top5.json.gz","expand.py","expanded-seal.json")}})
    print(len(out),len(original),sorted(rankings))

def grade():
    hashes=json.loads((HERE/"community-seal.json").read_bytes())["hashes"]
    assert all(sha256((HERE/p).read_bytes()).hexdigest()==v for p,v in hashes.items())
    runs=json.load(gzip.open(HERE/"community-ranks.json.gz"))
    pub=json.load(gzip.open(HERE/"publisher-top5.json.gz"))
    truths=json.load(gzip.open(R54/"graded-rows.json.gz"))
    with tarfile.open(ARC,"r|zst") as tar:
        for member in tar:
            if member.name=="./eval/v2_edit2ripple/lexical_details.jsonl":
                gold={r["sample_id"]:r["gold_files"] for r in map(json.loads,tar.extractfile(member))}
                break
    assert set(gold)==set(pub) and len(pub)==58 and set(runs)==set(truths)
    assert all(set(r["gold"])==set(gold[q]) for q,r in truths.items())
    names=list(next(iter(pub.values())))
    scores={m:statistics.fmean(metric(orders[m],gold[q])[0] for q,orders in pub.items()) for m in names}
    # Published task means rounded to three decimals. Oko's task mean is across its three runs.
    for m,reported in zip(ARMS,(.409,.372,.342,.108,.108)):
        assert abs(scores["codenib_"+m]-reported)<.00051,(m,scores)
    assert abs(statistics.fmean(scores[f"oko{i}"] for i in range(1,4))-.315)<.00051
    rows={}
    lex=json.load(gzip.open(HERE/"expanded-graded.json.gz"))
    for q,d in runs.items():
        vals={}
        for m,c in d.items():
            vals[m]=metric(c["order"][:5],gold[q])
            vals[m+"_history"]=metric(c["proposed"],gold[q])
        for ext in ("","_history"):
            vals["oko_mean"+ext]=list(map(statistics.fmean,zip(*(vals[f"oko{i}"+ext] for i in range(1,4)))))
        vals["lexical"]=lex[q]["scores"]["lexical"]
        vals["lexical_history"]=lex[q]["scores"]["corroborated"]
        rows[q]=dict(repo=truths[q]["repo"],scores=vals)
    means={m:list(map(statistics.fmean,zip(*(v["scores"][m] for v in rows.values())))) for m in vals}
    comp={m:paired(rows,m+"_history",m) for m in names+["oko_mean","lexical"]}
    absolute={m:paired(rows,"lexical_history",m) for m in names+["oko_mean"]}
    save(HERE/"community-graded.json.gz",rows)
    save(HERE/"community-results.json",dict(original58=scores,means=means,within_method=comp,lexical_history_vs=absolute))
    print({m:tuple(round(100*means[k][0],2) for k in (m,m+"_history")) for m in [*names,"oko_mean","lexical"]})
if __name__=="__main__":
    if sys.argv[1]=="freeze":lock()
    elif sys.argv[1]=="grade":grade()
    else:raise ValueError("expected freeze or grade")
