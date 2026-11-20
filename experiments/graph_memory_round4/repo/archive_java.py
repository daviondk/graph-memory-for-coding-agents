"""Fix official crop/Jaccard source and frozen ranker, predict every Java v0 Parquet retrieval candidate set."""
from experiment import *
import ast
import pyarrow.parquet as pq
from typing import Union,Any
from data_io import panel_name
class Adapter:
    @staticmethod
    @lru_cache(550)
    def tokenize(raw):return TOK.encode(raw,add_special_tokens=False).tokens
def author_function(file,name):
    mod=ast.parse((D/file).read_text("utf8"))
    node=next(x for x in mod.body if isinstance(x,ast.FunctionDef) and x.name==name)
    ns={"Union":Union,"AutoTokenizer":Any}
    exec(compile(ast.Module(body=[node],type_ignores=[]),file,"exec"),ns)
    return ns[name]
def one(task):
    file,start,end,base=task;p=D/"archive_inputs"/file
    with (D/"models.pkl").open("rb") as f:models=pickle.load(f)
    crop=author_function("repo_author_utils.py","crop_code_lines")
    jacc=author_function("repo_author_similarity.py","jaccard_similarity")
    adapter=Adapter();prefix=D/"archive_full";prefix.mkdir(exist_ok=True)
    dest=prefix/f"{p.stem}.{start}.jsonl.gz";t=time.monotonic();rows_done=0;diff=0
    pf=pq.ParquetFile(p);rg_index=0
    with gzip.open(dest,"wt",encoding="utf8") as out:
        for rg in range(pf.num_row_groups):
            n=pf.metadata.row_group(rg).num_rows
            if rg_index+n<=start:rg_index+=n;continue
            if rg_index>=end:break
            i=rg_index
            for batch in pf.iter_batches(row_groups=[rg],batch_size=48,columns=["repo_name","context","code"]):
                feature_blocks=[];info=[]
                for row in batch.to_pylist():
                    idx=i;i+=1
                    if idx<start or idx>=end:continue
                    code=row["code"];docs=row["context"];q=crop(code,3)
                    diff+=int(q!="\n".join(code.splitlines()[-3:]))
                    m=features(q,encode(docs),3)
                    lexical=sorted(range(len(docs)),key=lambda j:jacc(q,docs[j],adapter),reverse=True)
                    feature_blocks.append(m);info.append((base+idx,row["repo_name"],hashstr(q),lexical,len(docs)))
                if not info:continue
                matrix=np.vstack(feature_blocks);pred={arm:models[3,arm].predict_proba(matrix[:,ARMS[arm]])[:,1] for arm in ("graph","owner")}
                lo=0
                for idx,project,h,lex,nc in info:
                    ranks={arm:np.argsort(-vec[lo:lo+nc],kind="stable").tolist() for arm,vec in pred.items()}
                    ranks["jaccard"]=lex
                    out.write(json.dumps([panel_name(p.stem),idx,project,h,ranks],separators=(",",":"))+"\n")
                    lo+=nc;rows_done+=1
            rg_index+=n
    assert rows_done==end-start
    print(file,start,end,round(time.monotonic()-t,1),flush=True)
    return {"file":dest.name,"hash":sha(dest),"rows":rows_done,"changed_crop":diff,"seconds":time.monotonic()-t}
def main():
    start=time.monotonic();paths=sorted((D/"archive_inputs").glob("*.parquet"));todo=[];offset={}
    for p in paths:
        panel=panel_name(p.stem);n=pq.ParquetFile(p).metadata.num_rows;base=offset.get(panel,0);offset[panel]=base+n
        for k in range(0,n,1000):todo.append((p.name,k,min(k+1000,n),base))
    write("archive_method_lock.json",{"sha256":{n:sha(D/n) for n in ["ARCHIVE_PROTOCOL_RU.md","archive_java.py","archive_convert.py","archive_probe.py","memory.py","models.pkl","repo_author_similarity.py","repo_author_utils.py","repo_author_retriever.py","repo_author_run_repobench_r.py"]},"counts":offset})
    with ProcessPoolExecutor(5) as pool:receipt=list(pool.map(one,todo))
    write("archive_decision_lock.json",{"utc":datetime.now(timezone.utc).isoformat(),"shards":receipt,"seconds":time.monotonic()-start})
if __name__=="__main__":main()
