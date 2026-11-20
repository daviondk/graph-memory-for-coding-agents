"""Characterize modern/archival API drift without tuning retrieval on outcomes."""
from pathlib import Path
import hashlib,json,os,sys,urllib.request,gzip,collections
D=Path(__file__).resolve().parent
R3=D.parents[1]/"graph_memory_round3/repo"
BASE="https://huggingface.co/Salesforce/codegen-350M-multi/resolve/b25de779e2044ed5e7707505dea0e5a9bb08556a/"
def setup():
    from data_io import pq,rows,panel_name
    home=D/"tokenizer_snapshot";home.mkdir(exist_ok=True)
    for file in ("tokenizer_config.json","special_tokens_map.json","config.json","tokenizer.json","vocab.json","merges.txt","added_tokens.json"):
        try:data=urllib.request.urlopen(BASE+file,timeout=15).read()
        except urllib.error.HTTPError as e:
            if e.code==404:continue
            raise
        (home/file).write_bytes(data)
    sys.path.insert(0,str(R3/"lib"));from tokenizers import Tokenizer
    tok=Tokenizer.from_file(str(home/"tokenizer.json"));samples=[]
    for p in sorted((D/"archive_inputs").glob("*.parquet")):
        ids=set(sorted(range(pq.ParquetFile(p).metadata.num_rows),key=lambda n:hashlib.sha256(f"tokenizer-check|{p.stem}|{n}".encode()).digest())[:32])
        for i,r in enumerate(rows(p,["context","code"])):
            if i not in ids:continue
            for name,val in [("query","\n".join(r["code"].split("\n")[-3:]))]+[("doc",x) for x in r["context"]]:
                h=hashlib.sha256(json.dumps(tok.encode(val,add_special_tokens=False).tokens,ensure_ascii=True).encode()).hexdigest()
                samples.append([name,val,h])
    with gzip.open(home/"sample.json.gz","wt",encoding="utf8") as f:json.dump(samples,f)
def check():
    sys.path.insert(0,str(D/"legacy_check"))
    os.environ.update(USE_TORCH="0",USE_TF="0",USE_FLAX="0",HF_HUB_OFFLINE="1")
    import tokenizers,transformers
    home=D/"tokenizer_snapshot";tok=transformers.AutoTokenizer.from_pretrained(str(home),local_files_only=True)
    rows=json.load(gzip.open(home/"sample.json.gz","rt",encoding="utf8"));cnt=collections.Counter();same=collections.Counter()
    for name,val,expected in rows:
        observed=hashlib.sha256(json.dumps(tok.tokenize(val),ensure_ascii=True).encode()).hexdigest();cnt[name]+=1;same[name]+=int(expected==observed)
    (D/"tokenizer_audit.json").write_text(json.dumps({"transformers":transformers.__version__,"tokenizers":tokenizers.__version__,"class":type(tok).__name__,"sample":dict(cnt),"identical":dict(same)},indent=2),encoding="utf8")
if __name__=="__main__":(setup if sys.argv[1]=="setup" else check)()
