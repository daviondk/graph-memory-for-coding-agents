"""Exercise the offline file in Chromium and compare the displayed data with the measured registry."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from build import HERE,METHODS,data,traffic

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--channel",default="msedge",help="Playwright channel (msedge, chrome or chromium)")
    ap.add_argument("--capture",action="store_true",help="Write optional local screenshot for visual review.")
    args=ap.parse_args()
    trusted=data();dest=HERE/"index.html"
    errors=[];network=[];checks=0;views=0
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel=args.channel,headless=True,
                    args=["--disable-background-networking","--disable-component-update","--no-first-run"])
        context=browser.new_context(viewport={"width":1240,"height":910},offline=True)
        page=context.new_page()
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("request",lambda r:network.append(r.url) if r.url.startswith(("http:","https:")) else None)
        page.goto(dest.as_uri())
        assert page.locator("#total").inner_text()=="82,907 B"
        if args.capture:page.screenshot(path=str(HERE/"preview.png"))
        for panel,scopes in trusted["restart"].items():
            page.select_option("#panel",panel)
            for project,rows in scopes.items():
                page.select_option("#project",project)
                for m in METHODS:
                    optional=m not in ("cold","full")
                    budget=("1024" if m.endswith("1024") else "4096") if optional else m
                    page.select_option("#budget",budget)
                    if optional:page.select_option("#selector",m.removesuffix(budget))
                    assert page.locator("#selector").is_disabled()!=optional
                    r=rows[m];assert page.locator("#total").inner_text()==f"{traffic(r):,} B"
                    assert page.locator("#nreads").inner_text()==f"{r['n']:,}"
                    b=page.locator("#breakdown tr td:last-child").all_inner_texts()
                    assert b==[f"{r[k]:,}" for k in ("write","load","receipt","posting","body")]
                    assert page.locator("#arms tr.sel").count()==1
                    assert f"{r['db']:,}" in page.locator("#disk").inner_text()
                    checks+=1
        page.click("#negative");assert page.input_value("#panel")=="B" and page.input_value("#budget")=="4096"
        assert page.locator("#total").inner_text()=="53,808 B" and page.locator("#difference").inner_text().startswith("+")
        page.click("#goCache")
        assert page.locator("#cache").is_visible() and page.locator("#restart").is_hidden()
        for cap in ("4096","16384","65536"):
            page.select_option("#capacity",cap)
            for encoding in ("fixed","packed"):
                page.select_option("#layout",encoding)
                keys=["global","global_intern","file","file_intern","segmented","segmented_intern"] if encoding=="fixed" else ["packed_none","packed_file","packed_all"]
                rows=page.locator("#cacheRows tr")
                assert rows.count()==len(keys)
                for idx,k in enumerate(keys):
                    _,amount,full=rows.nth(idx).locator("td").all_inner_texts()
                    assert [int(amount.replace(",","")),int(full)]==trusted["cache"][cap][k]
                views+=1
        page.select_option("#windowProject","all")
        assert page.locator("#windowChoice option").count()==822
        for x in (0,48,148,821):
            page.select_option("#windowChoice",str(x))
            r=trusted["windows"][x];display=page.locator("#windowOut").inner_text()
            assert f"Requested {r[2]:,} bytes" in display and f"Separate copies served {r[3]:,}" in display and f"Shared contents served {r[4]:,}" in display
        page.click("#prev");page.click("#next");assert page.input_value("#windowChoice")=="821"
        page.click("#gain");r=trusted["windows"][int(page.input_value("#windowChoice"))];assert r[4]>r[3]
        for i in range(len(trusted["projects"])):
            page.select_option("#windowProject",str(i));opts=page.locator("#windowChoice option").count()
            assert opts==sum(r[0]==i for r in trusted["windows"])
        page.click("#goRestart")
        page.set_viewport_size({"width":390,"height":844})
        for id_ in ("goRestart","goCache"):
            page.click("#"+id_)
            overflow=page.evaluate("document.documentElement.scrollWidth - innerWidth")
            assert overflow<=1,(id_,overflow)
        browser.close()
    assert not network and not errors, (network,errors)
    receipt=dict(restart_scope_method_states=checks,cache_views=views,available_trace_windows=822,public_trace_projects=len(trusted["projects"]),
                 checked_mobile_width=390,network_requests=len(network),javascript_errors=len(errors),html_bytes=dest.stat().st_size,
                 html_sha256=sha256(dest.read_bytes()).hexdigest())
    (HERE/"ui-check.json").write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(receipt)
if __name__=="__main__":main()
