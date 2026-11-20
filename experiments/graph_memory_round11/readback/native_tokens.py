"""Cross-check all primary serialized packets against the tokenizer in the serving GGUF."""
import collections,gzip,json,urllib.request
from replay import ROOT,sha,packet,literal,write
from functools import lru_cache
@lru_cache(maxsize=4096)
def length(text):
    req=urllib.request.Request("http://127.0.0.1:18950/tokenize",
        json.dumps(dict(content=text,add_special=False,parse_special=False)).encode(),
        {"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as f:return len(json.load(f)["tokens"])
def main():
    data=json.loads(gzip.decompress((ROOT/"views.gz").read_bytes()))
    wr=json.loads(gzip.decompress((ROOT/"wires-primary.gz").read_bytes()))
    counts=collections.defaultdict(collections.Counter);rows=[]
    for task,entry in data.items():
        for m in ("raw","whole","single","union"):
            comp={x["turn"]:x["wire"] for x in wr.get(task+"|"+m,[])}
            for v in entry["views"]:
                body=comp.get(v["turn"]) or "".join(literal(n,s) for n,s in v["lines"])
                s=packet(v["turn"],body);n=length(s)
                counts[entry["panel"]][m]+=n
                rows.append((task,v["turn"],m,sha(s.encode()),n))
    write("native-token-rows.gz",rows);write("native-token-counts.json",dict(counts=counts,distinct=length.cache_info().misses,
           rows=len(rows),add_special=False,model="Qwen3.8-27B UD-Q4_K_M"))
if __name__=="__main__":main()
