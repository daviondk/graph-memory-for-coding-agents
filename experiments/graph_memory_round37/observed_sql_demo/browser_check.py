"""Physical browser exercise of live API, with only loopback requests permitted."""
import os,json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from selftest import D,running,write,sha
def main():
    oracle=json.loads((D/"checks.json").read_bytes())["cases"]
    options=[os.environ.get("CHROME_PATH"),"C:/Program Files/Google/Chrome/Application/chrome.exe",
             "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"]
    exe=next((x for x in options if x and Path(x).is_file()),None)
    dbs=[D/"eager.db",D/"inverse.db"];before=[sha(p) for p in dbs]
    with running() as base,sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=exe,headless=True,args=["--disable-background-networking"])
        ctx=browser.new_context(viewport={"width":1280,"height":950},device_scale_factor=1)
        page=ctx.new_page();errors=[];remote=[];calls=[];paths=[]
        page.on("pageerror",lambda err:errors.append(str(err)))
        def route(req):
            if req.request.url.startswith(base+"/"):
                path=urlsplit(req.request.url).path;paths.append(path)
                if path=="/api/read":calls.append(req.request.url.split("?",1)[1])
                req.continue_()
            else:
                remote.append(req.request.url);req.abort()
        ctx.route("**/*",route)
        page.goto(base+"/",wait_until="load")
        def wait(case,ab):
            page.wait_for_function("s=>document.documentElement.dataset.window===s",arg="/".join(map(str,[case,*ab])))
            assert page.locator("#status").inner_text()=="Signatures match"
        checks=[]
        for label in ("growth","contraction","capacity"):
            case=oracle[label]
            if label!="growth":page.locator(f"[data-key={label}]").click()
            wait(label,case["range"])
            assert page.locator("#rows tr").count()==case["retained"]
            assert [int(x) for x in page.locator("#comparison tr td:nth-child(2)").all_text_contents()]==list(case["rows"][n] for n in ("eager_index","inverse"))
            page.locator("#signature summary").click();assert page.locator("#digests").inner_text().count(case["digest"])==2;page.locator("#signature summary").click()
            checks.append([label,"recorded",case["retained"]])
            if label=="growth":
                page.locator("#base-detail summary").click()
                page.screenshot(path=str(D/"qa/desktop.png"),full_page=True)
                page.locator("#base-detail summary").click()
            page.locator("#special").click();wait(label,case["special"]);checks.append([label,"special",page.locator("#rows tr").count()])
            if label=="capacity":
                assert page.locator("#rows tr").count()==0 and "omitted by the global" in page.locator("#gaps").inner_text()
                page.screenshot(path=str(D/"qa/capacity.png"),full_page=True)
            page.locator("#actual").click();wait(label,case["range"])
        page.locator("#lo").fill("1");page.locator("#hi").fill("513");page.locator(".action").click()
        page.wait_for_function("()=>document.getElementById('error').textContent.includes('512')")
        page.locator("#lo").fill("99999");page.locator("#hi").fill("100000");page.locator(".action").click();wait("capacity",[99999,100000]);assert page.locator("#rows tr").count()==0
        page.locator("[data-key=growth]").click();wait("growth",oracle["growth"]["range"])
        for width in (390,320):
            page.set_viewport_size({"width":width,"height":844});assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            if width==390:page.screenshot(path=str(D/"qa/mobile.png"),full_page=True)
        assert not errors and not remote and len(calls)>=12 and set(paths)>={"/api/source","/api/read","/api/cases","/style.css","/app.js"}
        version=browser.version;ctx.close();browser.close()
    assert before==[sha(p) for p in dbs] and not any(D.glob("*.db-*"))
    write(D/"browser.json",dict(browser=version,states=checks,live_http_reads=len(calls),blocked_external_requests=remote,
         js_errors=errors,invalid_input=True,mobile_widths=[390,320],screenshot_sha={p.name:sha(p) for p in (D/"qa").glob("*.png")}))
    print(version,len(calls),"reads; service closed")
if __name__=="__main__":main()
