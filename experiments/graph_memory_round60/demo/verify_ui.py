"""Exercise the offline UI and check its arbitrary eviction sequences in Chromium."""
from hashlib import sha256
import json
import random
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright
from build import HERE,registry

d=registry();p=HERE/"index.html";errors=[];net=[];views=ops=0
with sync_playwright() as pw:
    b=pw.chromium.launch(channel="msedge",headless=True)
    pg=b.new_page(viewport={"width":1280,"height":900},offline=True)
    pg.on("pageerror",lambda e:errors.append(str(e)))
    pg.on("request",lambda r:net.append(r.url) if r.url.startswith(("http:","https:")) else None)
    pg.goto(p.as_uri())
    for mode in ("notify","quiet"):
        pg.select_option("#rule",mode)
        rng=random.Random(60111)
        bits=[[1,1] for _ in d["ids"]];exc=set()
        for i,t in [(0,0),(0,1),(1,0),(1,1)]+[(rng.randrange(8),rng.randrange(2)) for _ in range(15)]:
            pg.click(f"#copy-{i}-{t}");bits[i][t]^=1
            if not any(bits[i]) and mode=="notify":
                exc.add(i)
            live={j for j,v in enumerate(bits) if any(v)}
            fallback=len(live|exc)<8
            assert ("Fallback" if fallback else "Certified") in pg.locator("#status").inner_text()
            pg.click("#ask")
            assert pg.locator("#access").inner_text()==f"{int(fallback)} posting request"+("s" if not fallback else "")+f" · {8-len(live)} fresh bodies"
            got=[r.locator("td").all_inner_texts() for r in pg.locator("#answer tr").all()]
            assert got==[["test_reader.py","5"],["store.py","4"],["test_cache.py","4"],["schema.py","4"]]
            gothex=pg.locator("#packets .packet code").last.inner_text()
            mask=sum(1<<i for i in exc);assert gothex==d["packets"][str(mask)]["hex"]
            ops+=1
    pg.select_option("#rule","notify");pg.click("#two");assert "2 missing" in pg.locator("#status").inner_text()
    pg.click("#undo");assert "0 missing" in pg.locator("#status").inner_text()
    pg.click("#goData")
    for g in ("old12","r59","new"):
        pg.select_option("#cohort",g)
        for schedule in ("B","long"):
            pg.select_option("#density",schedule)
            for c in ("1024","4096"):
                pg.select_option("#cap",c);block=d["cases"][g+"/"+schedule][c]
                for repo in ("all",*block["projects"].keys()):
                    pg.select_option("#project",repo)
                    val=block["all"]["notify"]["charged"] if repo=="all" else block["projects"][repo]["notify"]
                    assert pg.locator("#rows tr").last.locator("td").nth(1).inner_text()==f"{val:,}";views+=1
    pg.click("#goLimits")
    for k,t in (("1024","71.06"),("4096","67.99")):
        pg.select_option("#tc",k);assert t in pg.locator("#timeRows").inner_text()
    pg.select_option("#span","4");assert "7,798 / 7,650 / 7,636" in pg.locator("#short").inner_text()
    pg.set_viewport_size({"width":390,"height":844})
    for nav in ("goLab","goData","goLimits"):
        pg.click("#"+nav);assert pg.evaluate("document.documentElement.scrollWidth-innerWidth")<=1
    b.close()
assert not errors and not net,(errors,net)
proof=dict(arbitrary_evictions=ops,ledger_views=views,mobile_width=390,javascript_errors=0,
           external_requests=0,html_sha256=sha256(p.read_bytes()).hexdigest())
dest=HERE/"ui-check.json"
if "--record" in sys.argv:dest.write_text(json.dumps(proof,indent=2)+"\n",encoding="utf8")
else:assert json.loads(dest.read_bytes())==proof
print(proof)
