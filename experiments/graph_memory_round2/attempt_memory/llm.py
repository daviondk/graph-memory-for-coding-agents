import datetime, gzip, json, time, urllib.request, urllib.error
from prepare import HERE,sha

def model_call(system,user,limit,seed,temp):
    req={"model":"qwen38-27b-ud-q4km","messages":[{"role":"system","content":system},{"role":"user","content":user}],
         "max_tokens":limit,"seed":seed,"temperature":temp,"top_k":20,"top_p":.95,"min_p":0,
         "repeat_penalty":1,"cache_prompt":False,"stream":False,"chat_template_kwargs":{"enable_thinking":False}}
    raw=json.dumps(req,sort_keys=True,ensure_ascii=True).encode()
    key=sha(raw)
    d=HERE/"calls";d.mkdir(exist_ok=True)
    cache=d/(key+".json.gz")
    if cache.exists():return json.loads(gzip.decompress(cache.read_bytes()))
    start=time.monotonic()
    for attempt in range(3):
        try:
            q=urllib.request.Request("http://127.0.0.1:18887/v1/chat/completions",data=raw,headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(q,timeout=110) as f:result=json.load(f)
            break
        except (TimeoutError,urllib.error.URLError):
            if attempt==2:raise
            time.sleep(1)
    rec={"key":key,"request":req,"reply":result,"elapsed":time.monotonic()-start,"end_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
    tmp=cache.with_suffix(".tmp")
    tmp.write_bytes(gzip.compress(json.dumps(rec,ensure_ascii=True,separators=(",",":")).encode(),mtime=0));tmp.replace(cache)
    return rec

