"""Frozen, seed-specific native Dense-FT training and resumable FP32 embedding cache."""
from pathlib import Path
from collections import defaultdict
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time

for var in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","RAYON_NUM_THREADS"):
    os.environ[var]="1"
os.environ.setdefault("HF_HUB_OFFLINE","1")
os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
R19=WORK/"graph_memory_round19/trained_rank"
R20=WORK/"graph_memory_round20"
R18=WORK/"graph_memory_round18"
sys.path.insert(0,str(R19))
import train as base
from prepare import pilot
sys.path.insert(0,str(R20/"factor_reader"))
import factor as f
from factor import np,load,save,sha
from project import CACHE,reqs,format_dense_query,format_dense_passage
PRIVATE=Path("D:/CodexResearch/x20-isetrace-multiseed")
SEEDS=(13,17,29,37,41)
INPUTS=PRIVATE/"shared/inputs.sqlite"
def seed_dir(s):
    assert s in SEEDS
    path=HERE/f"seed-{s}"
    path.mkdir(exist_ok=True)
    return path
def private(s):
    path=PRIVATE/f"seed-{s}"
    path.mkdir(exist_ok=True)
    return path
def key(s):return hashlib.sha256(s.encode("utf8")).digest()
def check_space(required,where):
    free=shutil.disk_usage(PRIVATE).free
    if free<required:
        raise OSError(f"{where}: {free} free bytes on D, {required} bytes needed for outstanding writes")
    return free
def db_ro(path):return sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=120)
def as_path(obj):return PRIVATE/obj["relative_model"]


def plan():
    s=load(R19/"split.json.gz");group=load(R20/"residual_graph/cpu_fallback/cohorts.json")["hash64"]
    assert [len(s[k]) for k in ("train","dev","test")]==[3894,500,2000]
    assert len(group["q"])==101 and len(group["t"])==64
    assert not {r["t"] for r in s["test"]}&{r["t"] for r in s["train"]+s["dev"]}
    inputs=[HERE/"PROTOCOL_RU.md",R19/"split.json.gz",R19/"trained-checkpoint.json",R20/"factor_reader/prior.json",R20/"factor_reader/hash64-weights.json",
            R20/"factor_reader/hash64-seal.json",R20/"factor_reader/metrics-test.json",R20/"residual_graph/cpu_fallback/cohorts.json",
            R18/"isetrace_official/source-lock.json",R18/"isetrace_e5/inventory.json",R19/"training-lock.json"]
    up=f.gmod.UP
    cf=up/"configs/stage/dense_ft.yaml"
    assert cf.read_text(encoding="utf8").count("random_seed: ${seed}")==2
    work_files={p.relative_to(WORK).as_posix():sha(p) for p in inputs}
    historical=load(R19/"trained-checkpoint.json")
    assert sha(base.RUN/"model/model.safetensors")==historical["files"]["model.safetensors"]
    save(HERE/"plan.json",{"protocol":sha(HERE/"PROTOCOL_RU.md"),"files":work_files,"seeds":list(SEEDS),"primary":"factor-minus-seed-matched-dense/full_support_2048","upstream":"df29287116fa1565b3fd6b485022cd6090dc0b27",
           "native_configs":{p.relative_to(up).as_posix():sha(p) for p in (cf,up/"configs/profile/full.yaml",up/"docs/40-operations/paper-reproduction.md")},
           "reused_model_s13":historical["files"]["model.safetensors"],"code":{"study":sha(HERE/"study.py"),"score":sha(HERE/"score.py")},"trajectories":1207})


def setup_inputs():
    INPUTS.parent.mkdir(parents=True,exist_ok=True)
    source=CACHE/"vectors.sqlite3"
    orig=db_ro(source)
    expected=load(R18/"isetrace_e5/inventory.json")["unique_prefixed_strings"]
    assert orig.execute("select count(*) from corpus").fetchone()[0]==expected
    con=sqlite3.connect(INPUTS,timeout=120)
    con.execute("create table if not exists corpus(k blob primary key,text text not null,nchar int not null) without rowid")
    con.execute("pragma journal_mode=WAL")
    con.commit()
    # One immutable shared corpus for all four new seeds. Corpus inputs never depend on test gold.
    cur=orig.execute("select k,text,nchar from corpus")
    while batch:=cur.fetchmany(1024):
        assert all(k==key(v) and n==len(v) for k,v,n in batch)
        con.executemany("insert or ignore into corpus values(?,?,?)",batch)
    con.commit();after_test=con.execute("select count(*) from corpus").fetchone()[0]
    calibration=load(R20/"residual_graph/cpu_fallback/cohorts.json")["hash64"];extra={}
    for t in calibration["t"]:
        raw=load(base.RUN/"projection/train"/(t+".json.gz"))
        candidates=tuple(base.TextCandidate.model_validate(x) for x in raw["pool"])
        ss=[format_dense_passage(v,passage_prefix="passage: ") for v in candidates]
        for q in raw["qs"]:
            req=pilot.TextRankingRequest(task_id=q["q"],query_text=q["text"],candidates=candidates)
            ss.append(format_dense_query(req,query_prefix="query: "))
        for v in ss:extra[key(v)]=v
    con.executemany("insert or ignore into corpus values(?,?,?)",[(k,v,len(v)) for k,v in extra.items()])
    con.execute("create index if not exists corpus_by_length on corpus(nchar,k)")
    con.commit();count=con.execute("select count(*) from corpus").fetchone()[0]
    cursor=con.execute("select k from corpus order by k");hashes=hashlib.sha256()
    for (k,) in cursor:hashes.update(k)
    assert expected<=after_test<=count<=expected+len(extra)
    con.close();orig.close()
    save(HERE/"inputs.json",{"keys_sha":hashes.hexdigest(),"total":count,"test_unique":expected,"calibration_unique":len(extra),"plan":sha(HERE/"plan.json")})


def mine(s):
    out=seed_dir(s); cfg=base.NegativeSamplingConfig(random_seed=s,easy_random_per_positive=2,hard_bm25_per_positive=2,hard_dense_per_positive=0,hard_graph_neighbor_per_positive=0,hard_pool_size=30)
    req,lab,_=base.pools("train")
    tasks=[base.TrainPairBuildTask(text_request=q,label=l) for q,l in zip(req,lab,strict=True)]
    start=time.perf_counter(); result=base.build_train_pairs(tasks,cfg)
    path=out/"train-pairs.json.gz";save(path,[r.model_dump() for r in result.pairs])
    save(out/"pairs.json",{"pairs":sha(path),"n":len(result.pairs),"train_questions":len(req),"summary":result.summary.model_dump(),"config":cfg.model_dump(),"seconds":time.perf_counter()-start,"split":sha(R19/"split.json.gz")})


def pin(s):
    import torch
    torch.set_num_threads(3);torch.set_num_interop_threads(1)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    torch.manual_seed(s)
    return torch


def fit(s):
    assert s!=13
    out=seed_dir(s);priv=private(s)
    if (out/"model.json").exists():
        m=load(out/"model.json");mp=as_path(m)
        assert all(sha(mp/n)==h for n,h in m["files"].items());return
    torch=pin(s);assert torch.cuda.is_available()
    free=check_space(3*1024**3,"training")
    pairs=out/"train-pairs.json.gz";assert sha(pairs)==load(out/"pairs.json")["pairs"]
    settings=base.SET.model_copy(update={"trainer":base.SET.trainer.model_copy(update={"random_seed":s})})
    req,_,group=base.pools("train");dev,lab,_=base.pools("dev")
    ps=[base.TrainPairRecord.model_validate(q) for q in load(pairs)]
    idx=1
    while (priv/f"attempt-{idx:03d}").exists():idx+=1
    attempt=priv/f"attempt-{idx:03d}";attempt.mkdir()
    checkpoint=attempt/"model"
    start=time.perf_counter()
    res=base.train_dense_finetune(config=settings,train_requests=req,train_pairs=ps,train_group_ids=group,dev_requests=dev,dev_labels=lab,task_local_dev=True,
                                  output_dir=attempt/"fit",model_dir=checkpoint)
    files={p.relative_to(checkpoint).as_posix():sha(p) for p in sorted(checkpoint.rglob("*")) if p.is_file()}
    assert "model.safetensors" in files and res.selected_metric_name=="dev_recall_at_5"
    save(out/"model.json",{"seed":s,"relative_model":checkpoint.relative_to(PRIVATE).as_posix(),"files":files,"train":len(req),"dev":len(dev),"metric":res.selected_metric_name,"selected":res.selected_metric_value,"log":list(res.metric_records),"seconds":time.perf_counter()-start,"peak_cuda_bytes":torch.cuda.max_memory_allocated(),"free_bytes_start":free,"device":torch.cuda.get_device_name(),"input_pairs":sha(pairs),"settings":settings.model_dump(mode="json")})


def encode(s):
    assert s!=13
    from graph_memory.embeddings import load_sentence_transformer
    torch=pin(s)
    src=load(HERE/"inputs.json");out=seed_dir(s);model_receipt=load(out/"model.json");cp=as_path(model_receipt);weight=sha(cp/"model.safetensors")
    assert weight==model_receipt["files"]["model.safetensors"]
    vector=private(s)/"vectors.sqlite";con=sqlite3.connect(vector,uri=True,timeout=120)
    con.execute("pragma journal_mode=WAL");con.execute("create table if not exists vectors(k blob,prec text,v blob,primary key(k,prec)) without rowid")
    con.execute("create table if not exists identity(w text primary key)");con.execute("insert or ignore into identity values(?)",(weight,));con.commit()
    assert con.execute("select w from identity").fetchall()==[(weight,)]
    con.execute("attach database ? as src",(INPUTS.as_uri()+"?mode=ro",))
    n0=con.execute("select count(*) from vectors").fetchone()[0]
    check_space((src["total"]-n0)*7000+64*1024**2,"encoding")
    start=time.perf_counter();m=load_sentence_transformer(str(cp),device="cuda").eval()
    cur=con.execute("select k,text from src.corpus c where not exists(select 1 from vectors v where v.k=c.k and v.prec='ft') order by c.nchar,c.k")
    n=0
    with torch.inference_mode():
        while batch:=cur.fetchmany(128):
            texts=[v for _,v in batch]
            arr=m.encode(texts,batch_size=64,normalize_embeddings=True,show_progress_bar=False)
            assert arr.dtype==np.float32 and arr.shape==(len(batch),768) and np.isfinite(arr).all()
            con.executemany("insert into vectors values(?,'ft',?)",[(k,v.astype("<f4",copy=False).tobytes()) for (k,_),v in zip(batch,arr,strict=True)]);con.commit();n+=len(batch)
            if n%2048==0:print(s,"encoded",n+n0,"/",src["total"],round(time.perf_counter()-start,1),flush=True)
    assert con.execute("select count(*) from vectors").fetchone()[0]==src["total"]
    assert not con.execute("select 1 from src.corpus c where not exists(select 1 from vectors v where v.k=c.k and v.prec='ft') limit 1").fetchone()
    con.close()
    save(out/"embeddings.json",{"seed":s,"total":src["total"],"new":n,"prior_checkpointed":n0,"seconds_this_pass":time.perf_counter()-start,"checkpoint":weight,"inputs":sha(HERE/"inputs.json"),"dtype":"float32","tf32":False,"microbatch":64})


def calibrate(s):
    out=seed_dir(s)
    cohort=load(R20/"residual_graph/cpu_fallback/cohorts.json")["hash64"]
    con=db_ro(private(s)/"vectors.sqlite")
    ret=f.DenseTaskRetriever(encoder=f.Lookup(con,"ft"),device="cpu")
    xs=[];ys=[];ws=[];ids=[]
    for t in sorted(cohort["t"]):
        p=load(base.RUN/"projection/train"/(t+".json.gz"));pool=tuple(base.TextCandidate.model_validate(v) for v in p["pool"])
        for q in p["qs"]:
            req=pilot.TextRankingRequest(task_id=q["q"],query_text=q["text"],candidates=pool)
            rank=[r.node_id for r in ret.rank(req)]
            pair=f.labels(rank,set(q["positive"]))
            if pair:
                y,w=pair;xs.append(f.rank_x(len(y)));ys.append(y);ws.append(w);ids.append(q["q"])
    assert set(ids)==set(cohort["q"]) and len(ids)==101
    x=np.vstack(xs);y=np.concatenate(ys);w=np.concatenate(ws)
    save(out/"calibration.json",{"seed":s,"rank":f.lr(x,y,w),"queries":ids,"rows":len(y),"trajectories":64,"source":sha(R20/"residual_graph/cpu_fallback/cohorts.json"),"weights":sha(out/"model.json"),"prior":sha(R20/"factor_reader/prior.json")})
    con.close()


if __name__=="__main__":
    task=sys.argv[1]
    if task=="plan":plan()
    elif task=="inputs":setup_inputs()
    else:{"pairs":mine,"fit":fit,"encode":encode,"calibrate":calibrate}[task](int(sys.argv[2]))

