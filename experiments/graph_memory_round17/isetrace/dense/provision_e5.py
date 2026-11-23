from pathlib import Path
import sys,concurrent.futures,json
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import provision as p
p.CACHE=p.CACHE.parent/"e5-base-v2"
names=("config.json","model.safetensors","1_Pooling/config.json","modules.json","sentence_bert_config.json","special_tokens_map.json","tokenizer.json","tokenizer_config.json","vocab.txt")
if __name__=="__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        rows=list(ex.map(p.fetch,[(p.E5,"models",name) for name in names]))
    (Path(__file__).resolve().parent/"weights-lock.json").write_text(json.dumps(rows,indent=2)+"\n",encoding="utf8")
