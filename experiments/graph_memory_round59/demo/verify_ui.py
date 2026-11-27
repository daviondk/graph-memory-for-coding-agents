"""Open the standalone document offline and exercise each research workflow."""
import json
from hashlib import sha256
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright
from build import HERE, make

raw=make()
assets=HERE/"index.html"
errors=[]; network=[]; checked=0
with sync_playwright() as pw:
    b=pw.chromium.launch(channel="msedge",headless=True)
    page=b.new_page(viewport={"width":1280,"height":880},offline=True)
    page.on("pageerror",lambda err:errors.append(str(err)))
    page.on("request",lambda req:network.append(req.url) if req.url.startswith(("http:","https:")) else None)
    page.goto(assets.as_uri())
    assert page.get_by_role("heading",name="What crosses the restart boundary?").is_visible()
    for scope,(g,w) in raw["scopes"].items():
        page.select_option("#scope",scope)
        cases={k:v for k,v in raw["rows"].items() if v["w"]==w and (v["g"]!="original" if g=="external" else v["g"]=="original")}
        for key in ("all",*list(cases)):
            page.select_option("#repo",key)
            for h,selection in [("0","full"),("full","demand1024")]:
                page.select_option("#h",h);page.select_option("#selection",selection)
                expected=sum(sum(v["metrics"][h][selection]["lazy"][:6]) for v in (cases.values() if key=="all" else [cases[key]]))
                assert page.locator("#ledgerRows tr").nth(3).locator("td").nth(7).inner_text()==f"{expected:,}"
                checked+=1
    page.click("#showCounter");assert "4,484" in page.locator("#counter").inner_text()
    page.click("#goEvent")
    page.select_option("#scope","Original · sparse")
    page.select_option("#repo","original/long/sphinx-doc/sphinx")
    page.select_option("#query","1")
    case=raw["rows"]["original/long/sphinx-doc/sphinx"]["examples"][1]
    page.click("#step")
    assert page.locator("#eventList li").count()==len(case["source"])
    page.click("#step");assert page.locator("#answer tr").count()==len(case["rank"])
    assert page.locator("#answer tr").first.locator("td").first.inner_text()==case["rank"][0][0]
    page.click("#reset");assert not page.locator("#answer tr").count()
    page.click("#goCache");page.select_option("#scope","Transfer · sparse");page.select_option("#repo","all");page.select_option("#h","full")
    assert page.locator("#cacheRows tr").nth(1).locator("td").nth(3).inner_text()=="11,600"
    page.click("#reversal");assert page.locator("#cacheRows tr").nth(1).locator("td").nth(3).inner_text()=="17,698"
    page.click("#goSketch")
    for layout in ("B","long"):
        page.select_option("#hs",layout)
        for cap in ("1024","4096"):
            page.select_option("#hb",cap)
            for counts in ("all",*[k for k in raw["holdout"]["projects"] if k.startswith(layout+"/")]):
                page.select_option("#hp",counts)
                expected=raw["holdout"]["groups"][layout][cap+"/xor"]["charged"] if counts=="all" else raw["holdout"]["projects"][counts][cap+"/xor"]
                assert page.locator("#holdRows tr").nth(3).locator("td").nth(1).inner_text()==f"{expected:,}"
                checked+=1
    page.select_option("#missing","2");assert "Fetch the exact posting list" in page.locator("#equation").inner_text()
    page.select_option("#missing","0");assert "already known" in page.locator("#equation").inner_text()
    page.set_viewport_size({"width":390,"height":844})
    for nav in ("goLedger","goCache","goEvent","goSketch"):
        page.click("#"+nav)
        assert page.evaluate("document.documentElement.scrollWidth-innerWidth")<=1
    b.close()
assert not errors and not network
out=dict(numerical_views_checked=checked,mobile_width=390,javascript_errors=len(errors),
         network_requests=len(network),offline_sha256=sha256(assets.read_bytes()).hexdigest())
print(out)
if "--record" in sys.argv:
    (HERE/"ui-check.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf8")
else:
    assert out==json.loads((HERE/"ui-check.json").read_bytes())
