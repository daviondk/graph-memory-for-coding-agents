"""Public, inference-visible state features and train-only sufficient-set distances."""
from pathlib import Path
import gzip,hashlib,itertools,json,math,os,re,sys
from collections import Counter
for name in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMEXPR_NUM_THREADS"):os.environ[name]="1"
import numpy as np
from scipy.sparse import csr_matrix
D=Path(__file__).resolve().parent
W=D.parents[1];R34=W/"graph_memory_round34/external_transfer";STRONG=R34/"strong";R37=W/"graph_memory_round37/serbench_reference"
UP=W/"memory_session5/serbench";PUB=UP/"upstream/data/cal500";sys.path.insert(0,str(UP/"upstream/src"))
from serbench import _reference_scorer as native
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def stable(s):return hashlib.sha256(s.encode()).digest()
def get(p):
    b=p.read_bytes();return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)
def save(name,data):
    b=(json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()
    (D/name).write_bytes(gzip.compress(b,mtime=0) if name.endswith(".gz") else b)
def stream(p):
    with gzip.open(p,"rt",encoding="utf8") as f:
        for line in f:yield json.loads(line)
def norm(p):return str(p).replace(chr(92),"/").strip("./").lower()
def tokens(value):
    s=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
    return set(re.findall(r"[a-z_][a-z_0-9]{2,}",s.lower()))
def splitwords(words):
    return {piece for tok in words for piece in tok.split("_") if len(piece)>=3}
def order(score):return np.argsort(-np.asarray(score),kind="stable")
def rank(score):return np.argsort(order(score))+1
def sets_native(ids,label):
    index={v:i for i,v in enumerate(ids)};groups=[]
    for group in label["required_evidence_groups"]:
        options=sorted({index[k] for k in group["acceptable_evidence_ids"] if k in index})
        groups.append(list(itertools.combinations(options,group["minimum_required"])))
    alternatives={frozenset(index[k] for k in a) for a in label["alternative_minimal_sets"] if a and all(k in index for k in a)}
    for combo in itertools.product(*groups):
        alternatives.add(frozenset(i for subset in combo for i in subset))
    return sorted([a for a in alternatives if not any(other<a for other in alternatives)],key=lambda a:(len(a),tuple(sorted(a))))
def target(routes,selected,n):
    if not routes:return None
    chosen=frozenset(selected);missing=[a-chosen for a in routes];dist=min(map(len,missing))
    if dist==0:return None
    positive=set().union(*(m for m in missing if len(m)==dist))
    y=np.zeros(n,dtype=bool);y[list(positive)]=True
    return y
def labels(qs):return {r["state_id"]:r for r in stream(PUB/"labels.jsonl.gz") if r["state_id"] in qs}
PATH=re.compile(r"[\w@.+/\\-]+\.[A-Za-z][A-Za-z0-9_]*")
def inference():
    path=STRONG/"features.json.gz";assert sha(path)==get(STRONG/"input.json")["features"]
    data=get(path)
    model_entry=get(STRONG/"selection.json")["modes"]["union_cost"]
    model=get(STRONG/"models.json")[model_entry]
    assert sha(UP/"dense_vectors.npy")==get(UP/"dense_runtime.json")["vectors_sha256"]
    mat=np.load(UP/"dense_vectors.npy",mmap_mode="r")
    layouts={r["state_id"]:r for r in stream(UP/"dense_inputs.jsonl.gz") if r["state_id"] in data}
    out={}
    for obj in stream(PUB/"items.jsonl.gz"):
        q=obj["state_id"]
        if q not in data:continue
        r=data[q];ids=r["ids"];n=len(ids);cd={c["evidence_id"]:c for c in obj["candidate_evidence"]};cs=[cd[k] for k in ids]
        layout=layouts[q];mapping=dict(layout["candidates"])
        em=mat[[mapping[i] for i in ids]].astype(np.float32);em/=np.linalg.norm(em,axis=1,keepdims=True)
        qv=mat[layout["queries"]["state"]].astype(np.float32);qv/=np.linalg.norm(qv)
        cosine=em@qv;pair_cos=em@em.T
        x=np.array(r["x"]);u=np.array(r["off"])+(x-model["center"])/model["scale"]@model["weights"]
        base=np.column_stack([np.log1p(r["ranks"][name]) for name in ("dense_state","dense_addresses","bm25")]+
            [np.log1p(rank(u)),u,cosine,cosine.max()-cosine,x[:,1],x[:,2],x[:,3],np.log1p(r["qw"])])
        paths=[norm(c["source_path"]) for c in cs];dirs=[p.rpartition("/")[0] for p in paths]
        words=[tokens(c["content_excerpt"]) for c in cs];docs=[z|splitwords(z) for z in words]
        pathwords=[set(re.findall(r"[a-z0-9]{2,}",p)) for p in paths];testpath=np.array([bool(re.search(r"(^|[/_.-])tests?([/_.-]|$)",p)) for p in paths],float)
        observed=np.array([c["observed_by_state"] for c in cs],float)
        feats=[observed,testpath,np.log1p([p.count("/") for p in paths]),np.log1p([len(z) for z in words])]
        vocab=Counter(t for w in docs for t in w);idf={t:math.log1p(n/(1+freq)) for t,freq in vocab.items()}
        for field in ("issue","information_need","current_subgoal","current_hypothesis","current_observation","latest_test_output","search_queries","opened_files","current_diff"):
            s=obj.get(field) or "";literal=(s if isinstance(s,str) else json.dumps(s,ensure_ascii=False)).lower();qw=tokens(s);qw|=splitwords(qw)
            weighted=np.array([sum(idf[t] for t in sorted(z&qw)) for z in docs]);testq=bool(re.search(r"\b(test|tests|verify|failure|assertion)\b",literal))
            feats.extend([weighted/(1+sum(idf.get(t,0.) for t in sorted(qw))),np.log1p(rank(weighted)),
                np.array([len(z&qw)/(1+len(z)) for z in pathwords]),np.array([p in literal and bool(p) for p in paths],float),
                np.array([bool(p) and p.rsplit("/",1)[-1] in literal for p in paths],float),
                testpath*testq])
        xx=np.column_stack([base,*feats]).astype(np.float32)
        # Intra-pool graph matrices: same file, same directory, source proximity, identifier cosine, dense cosine, historical co-access.
        file=np.equal.outer(paths,paths);directory=np.equal.outer(dirs,dirs)
        starts=np.array([int(c.get("line_start") or 0) for c in cs]);ends=np.array([int(c.get("line_end") or 0) for c in cs])
        gap=np.maximum(0,np.maximum(starts[:,None]-ends[None,:],starts[None,:]-ends[:,None]))
        proximity=file/(1+np.log1p(gap))
        reverse={v:i for i,v in enumerate(vocab)};sparse_rows=[];cols=[];vals=[]
        for i,z in enumerate(docs):
            for v in sorted(z):
                sparse_rows.append(i);cols.append(reverse[v]);vals.append(idf[v])
        lex=csr_matrix((vals,(sparse_rows,cols)),shape=(n,len(vocab)),dtype=np.float32)
        norms=np.sqrt(np.asarray(lex.multiply(lex).sum(axis=1)).ravel());lex=lex.multiply(1/np.maximum(1e-8,norms)[:,None]).tocsr()
        pair_lex=(lex@lex.T).toarray()
        path_events=[{norm(k.group()) for k in PATH.finditer(json.dumps([ev.get("action_input"),ev.get("tool_output"),ev.get("opened_files")],ensure_ascii=False))} for ev in obj["trajectory_prefix"]]
        hits=np.array([[p in ev for ev in path_events] for p in paths],dtype=np.float32);over=hits@hits.T;total=np.diag(over);coact=over/np.maximum(1,total[:,None]+total[None,:]-over)
        G=np.stack((pair_cos,file,directory,proximity,pair_lex,coact),axis=2).astype(np.float32)
        out[q]=dict(x=xx,g=G,u=u,seen=observed,ids=ids,repo=r["repo"],task=r["task"],split=r["split"],qw=np.array(r["qw"]),bge=np.argsort(r["ranks"]["dense_state"]))
    assert Counter(r["split"] for r in out.values())=={"train":179,"dev":101,"test":214}
    return out

def pool(r,s,perm=None):
    n=len(r["ids"])
    if not len(s):return np.zeros((n,13),dtype=np.float32)
    ix=np.asarray(s,dtype=int);subset=r["g"][:,ix,:] if perm is None else r["g"][perm[:,None],perm[ix][None,:],:]
    return np.column_stack((np.full(n,len(s)/8),subset.max(axis=1),subset.mean(axis=1))).astype(np.float32)

