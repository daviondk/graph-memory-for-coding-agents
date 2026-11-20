"""Read author-reported merged PR IDs from public HTML. Cache only paired references and timing."""
import concurrent.futures,collections,html,json,re,time,urllib.request
from pathlib import Path
from extract import D,get,save,h
def read(row):
    iid=row["iid"];repo=row["repo"];num=iid.rsplit("-",1)[1]
    url=f"https://github.com/{repo}/pull/{num}";out=D/"pr_metadata"/(iid+".json")
    if out.exists():return get(out)
    r={"iid":iid,"repo":repo,"url":url,"number":int(num)}
    for k in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 research Git revision reader"})
            with urllib.request.urlopen(req,timeout=30) as f:content=f.read();r['canonical']=f.geturl()
            page=content.decode();ids=set(re.findall(r'"mergeCommitSha"\s*:\s*"([a-f0-9]{40})"',page))
            explicit=re.findall(r'merged commit\s*<a[^>]+href="[^"]*/commit/([a-f0-9]{40})"',page)
            if len(ids)!=1 or (explicit and set(explicit)!=ids):raise ValueError("merge ID missing or ambiguous")
            r['merge']=ids.pop();r['html_sha']=h(content);r['merged_badge']='State--merged' in page or '>Merged</' in page or bool(explicit)
            if not r['merged_badge']:raise ValueError('missing merged state')
            r['status']='ok';break
        except (OSError,ValueError) as e:
            r['status']='unavailable';r['error']=str(e)[:200]
            if k<2:time.sleep(0.8*(k+1))
    out.write_text(json.dumps(r,ensure_ascii=True),encoding="utf8");return r
if __name__=="__main__":
    (D/'pr_metadata').mkdir(exist_ok=True);rows=list({r["iid"]:r for r in get(D/"keys.json")}.values())
    with concurrent.futures.ThreadPoolExecutor(6) as pool:result=list(pool.map(read,rows))
    save("pr_metadata.json",result);print(collections.Counter(r['status'] for r in result))
