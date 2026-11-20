"""Freeze first; generate full blind ranked lists over the frozen 300 memories."""
import argparse, csv, datetime, hashlib, importlib.util, json, os, sys, time
from pathlib import Path
from collections import Counter
from contextlib import contextmanager

HERE = Path(__file__).resolve().parent
SRC = Path(os.environ.get("SWE_CONTEXT_BASE", str(HERE.parents[1]/"sota_round"/"swe_context")))
MODEL = Path(os.environ.get("CONTRIEVER_PATH", "D:/CodexResearch/x20-longmemeval-dretr/contriever"))
SEED = "20261116-write-factor-shuffle"


def hash_file(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(name, data):
    out = HERE/name
    tmp = out.with_suffix(out.suffix+".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),encoding="utf8")
    tmp.replace(out)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def frozen_files():
    origins = [("design",HERE,["PROTOCOL.md", "generate.py"]),
               ("original",SRC,["cards.json","queries.json","blind_ranks.json","blind_commit.json","rank.py"]),
               ("model",MODEL,sorted(p.name for p in MODEL.iterdir() if p.is_file()))]
    return {f"{group}/{name}":hash_file(root/name) for group,root,names in origins for name in names}


def freeze():
    path=HERE/"design-lock.json"
    if path.exists():
        assert read(path)["files"]==frozen_files()
        return
    save(path.name,{"utc":utc(),"files":frozen_files(),"permutation_salt":SEED})


def run():
    assert (HERE/"design-lock.json").is_file()
    assert read(HERE/"design-lock.json")["files"]==frozen_files()
    import numpy as np
    import psutil
    import torch
    import transformers
    from transformers import AutoModel,AutoTokenizer
    spec=importlib.util.spec_from_file_location("previous_ranker",SRC/"rank.py")
    old=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    trace=[]
    proc=psutil.Process()
    @contextmanager
    def measure(label):
        start=time.perf_counter()
        t0=proc.cpu_times()
        yield
        t1=proc.cpu_times()
        m=proc.memory_info()
        trace.append({"step":label,"wall_s":time.perf_counter()-start,
                      "cpu_s":t1.user+t1.system-t0.user-t0.system,
                      "rss_at_end":m.rss,"peak_rss_to_step":getattr(m,"peak_wset",None)})
        print(label,round(trace[-1]["wall_s"],2),flush=True)
    keys=[r['key'] for r in read(SRC/"cards.json")]
    cards=read(SRC/"cards.json")
    rows=read(SRC/"queries.json")
    qs=[r['query'] for r in rows]
    assert len(set(keys))==len(keys)==300 and [r['ordinal'] for r in rows]==list(range(357))
    views={f:[r[f] for r in cards] for f in ('symptom','closure','edits')}
    sorted_len=sorted(range(len(keys)),key=lambda j:(len(views["edits"][j].split()), hashlib.sha256((SEED+"|"+keys[j]).encode()).hexdigest()))
    # Swap adjacent after the length block. The lengths and corpus are fixed in advance.
    donor=np.arange(len(keys))
    for x,y in zip(sorted_len[::2],sorted_len[1::2]):
        donor[x],donor[y]=y,x
    assert np.all(donor!=np.arange(len(keys))) and len(set(donor))==len(keys)
    corpus={}
    for f,texts in views.items():
        corpus[f]={"bytes_utf8":sum(len(x.encode()) for x in texts),"words":sum(len(x.split()) for x in texts),
                   "bm25_postings":sum(len(set(old.terms(x))) for x in texts),"bm25_tokens":sum(len(old.terms(x)) for x in texts),
                   "vocabulary":len(set(t for x in texts for t in old.terms(x)))}
    with (HERE/"donors.csv").open("w",encoding="utf8",newline="") as f:
        w=csv.writer(f); w.writerow(["source","edits_from","source_nwords","donor_nwords","same_text"])
        for j,d in enumerate(donor):
            w.writerow([keys[j],keys[d],len(views['edits'][j].split()),len(views['edits'][d].split()),int(views['edits'][j]==views['edits'][d])])
    scores={}
    for field,t in views.items():
        with measure("bm25_"+field):
            scores[field]=old.bm25(t,qs)
    assert np.array_equal(scores['edits'][:,donor],old.bm25([views['edits'][i] for i in donor],qs))
    with measure("load_pinned_Contriever"):
        model=AutoModel.from_pretrained(MODEL,local_files_only=True).eval().to('cpu')
        tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    with measure("embed_queries"):
        qvec=old.encode(qs,model,tok)
    dense={}
    for field in ('symptom','closure'):
        with measure("embed_and_score_"+field):
            dense[field]=qvec@old.encode(views[field],model,tok).T
    with measure("rrf_six_conditions"):
        base=2*old.reciprocal(scores['symptom'])+old.reciprocal(scores['closure'])
        signals={"absent":0,"real":old.reciprocal(scores['edits']),"shuffle":old.reciprocal(scores['edits'][:,donor])}
        rankings={}
        for key,extra in signals.items():
            sparse=base+extra
            rankings["lex_"+key]=old.ranks(sparse).astype(np.uint16)
            rankings["hyb_"+key]=old.ranks(sparse+2*old.reciprocal(dense['symptom'])+old.reciprocal(dense['closure'])).astype(np.uint16)
    old_rows=read(SRC/'blind_ranks.json')
    parity={}
    for new,existing in [('hyb_real','fusion'),('lex_real','sparse_fields')]:
        matched=[all(keys[j]==ref for j,ref in zip(rankings[new][i,:10],r[existing])) for i,r in enumerate(old_rows)]
        parity[new]=sum(matched)
        assert all(matched), (new, [i for i,m in enumerate(matched) if not m][:20])
    save('keys.json',keys)
    np.savez_compressed(HERE/"rankings.npz",**rankings)
    costs={"trace":trace,"corpus":corpus,"rankings":list(rankings),"queries":len(rows),"documents":len(keys),
           "reference_top10_parity":parity,"python":sys.version,"torch":torch.__version__,"transformers":transformers.__version__,
           "numpy":np.__version__,"psutil":psutil.__version__,"torch_intra_threads":torch.get_num_threads(),"torch_inter_threads":torch.get_num_interop_threads(),
           "device":str(model.device),"dense_batch":6,"dense_max_subwords":384,"queries_embeddings_bytes":qvec.nbytes,
           "two_doc_vector_arrays_bytes":2*len(keys)*qvec.shape[1]*qvec.dtype.itemsize,"representation":"float32",
           "rss_peak_process_bytes":getattr(proc.memory_info(),"peak_wset",None)}
    save("costs.json",costs)
    names=["keys.json","rankings.npz","donors.csv","design-lock.json","costs.json"]
    save("predictions-lock.json",{"utc":utc(),"files":{n:hash_file(HERE/n) for n in names}})
    print("parity",parity)
if __name__=="__main__":
    op=argparse.ArgumentParser()
    op.add_argument("mode",choices=["freeze","predict"])
    cmd=op.parse_args().mode
    if cmd=="freeze":freeze()
    else:run()

