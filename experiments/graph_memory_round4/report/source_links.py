"""Check external references in the manuscript without downloading or running code."""
import concurrent.futures
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

here = Path(__file__).resolve().parent
sources = {}
for md in sorted((here / "pages").glob("*.md")):
    for label,url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)",md.read_text("utf8")):
        sources.setdefault(url,[]).append({"label":label,"page":md.stem})

def verify(url):
    for method in ("HEAD", "GET"):
        try:
            req=urllib.request.Request(url,method=method,headers={"User-Agent":"Mozilla/5.0 (public academic research report source verification)"})
            with urllib.request.urlopen(req,timeout=10) as response:
                status=response.status
                return {"references":sources[url],"status":status,"final":response.geturl(),"method":method}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            failure=str(e)
    return {"references":sources[url],"error":failure}

ordered=sorted(sources)
with concurrent.futures.ThreadPoolExecutor(6) as pool:
    results=dict(zip(ordered,pool.map(verify,ordered)))
(here/"final/source_links.json").write_text(json.dumps(results,ensure_ascii=False,indent=1),encoding="utf8")
print(len(results),"sources;",sum(x.get("status")==200 for x in results.values()),"HTTP 200")
for url,details in results.items():
    if "error" in details:
        print(url,details["error"])
