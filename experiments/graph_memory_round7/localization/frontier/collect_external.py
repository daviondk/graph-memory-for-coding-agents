"""Select a public cross-project cohort before scoring, and fetch immutable base snapshots."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import re
import shutil
import time
import urllib.request
import duckdb
import truststore

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[1]
BENCH=Path("D:/CodexResearch/x20-round4-verified.parquet")
EXCLUDED=re.compile(r"\b(?:security|cve|malware|exploit\w*|vulnerab\w*|injection|cross.site|denial.of.service|path.traversal|unsafe deserializ\w*|remote code execution|dos attack|xss|ssrf|rce)\b",re.I)
def digest(data):
    return hashlib.sha256(data).hexdigest()
def save(path, data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n","utf8")
def main():
    truststore.inject_into_ssl()
    folder=HERE/"inputs";folder.mkdir(exist_ok=True)
    db=duckdb.connect()
    rows=db.execute("select instance_id,base_commit,problem_statement from read_parquet(?) where repo='sphinx-doc/sphinx'",[str(BENCH)]).fetchall()
    eligible=[{"id":i,"rev":c,"issue":s,"project":"sphinx"} for i,c,s in rows if not EXCLUDED.search(s)]
    eligible.sort(key=lambda x:digest(("r7-local-doc-transfer-v1|"+x["id"]).encode()))
    selected=eligible[24:]
    assert not ({x["id"] for x in selected} & set(json.loads((HERE.parent/"cohort_sphinx.json").read_bytes())["ids"]))
    save(HERE/"cohort_sphinx.json",{"data_sha":digest(BENCH.read_bytes()),"available":len(rows),"filtered":len(rows)-len(eligible),"ids":[x["id"] for x in selected],"notes":"Public-fields-only selection, SHA-256 ordering."})
    def fetch(x):
        public=folder/x["id"];public.mkdir(exist_ok=True)
        save(public/"public.json",x)
        tar=public/"base.tar.gz"
        url="https://codeload.github.com/sphinx-doc/sphinx/tar.gz/"+x["rev"]
        if not tar.exists():
            for attempt in range(3):
                try:
                    req=urllib.request.Request(url,headers={"User-Agent":"academic-research-snapshot/1"})
                    with urllib.request.urlopen(req,timeout=28) as resp, (public/"tmp").open("wb") as dest:
                        shutil.copyfileobj(resp,dest)
                    (public/"tmp").replace(tar)
                    break
                except OSError:
                    if attempt==2:raise
                    time.sleep(1+attempt)
        save(public/"source.json",{"url":url,"sha256":digest(tar.read_bytes())})
        print(x["id"],tar.stat().st_size,flush=True)
    with ThreadPoolExecutor(5) as ex:
        list(ex.map(fetch,selected))
if __name__=="__main__":
    main()
