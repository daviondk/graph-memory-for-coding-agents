"""Physical offline Chrome checks against independent source-SDK prefix results."""
from pathlib import Path
import os,hashlib,json
from playwright.sync_api import sync_playwright
D=Path(__file__).resolve().parent
def write(p,x):p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n",encoding="utf8")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    oracle=json.loads((D/"oracle.json").read_bytes());file=D/"index.html"
    options=[os.getenv("CHROME_PATH"),"C:/Program Files/Google/Chrome/Application/chrome.exe","C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"];exe=next((s for s in options if s and Path(s).exists()),None);qa=D/"qa";qa.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=exe,headless=True,args=["--disable-background-networking","--disable-extensions"]);context=browser.new_context(offline=True,viewport={"width":1360,"height":955},device_scale_factor=1);page=context.new_page();errors=[];requests=[];page.on("pageerror",lambda e:errors.append(str(e)));page.on("request",lambda r:requests.append(r.url));page.goto(file.as_uri(),wait_until="load")
        checks=page.evaluate("""oracle=>{let checks=0;for(const cs of CASES){const evs=oracle[String(cs.id)];const bd=new Set([0,1,512,1024,1700,1701,2048,2127,2128,6144,8192,16384]);for(const arr of evs)for(const v of arr)for(const d of [-1,0,1])if(v.spent+d>=0&&v.spent+d<=16384)bd.add(v.spent+d);for(const b of bd)for(let k=1;k<=20;k++)for(let m=0;m<2;m++){const exp=evs[m];let depth=0;for(let i=1;i<=k&&exp[i].spent<=b;i++)depth=i;const s=measure(cs,m,b,k);const t=exp[depth];if(s.cost!==t.spent||s.num!==depth||s.complete!==t.complete||JSON.stringify(s.hit)!==JSON.stringify(t.groups))throw Error('Oracle mismatch '+[cs.id,m,b,k]);checks++}}return checks}""",oracle)
        def view(b,k,complete):
            actual=page.evaluate("""()=>({b:Number(document.querySelector('#budget').value),k:Number(document.querySelector('#depth').value),ok:[...document.querySelectorAll('.badge')].map(x=>x.textContent==='Complete'), metrics:[...document.querySelectorAll('.metrics')].map(x=>x.innerText)})""")
            assert [actual["b"],actual["k"],actual["ok"]]==[b,k,complete],actual
            return actual
        snapshots=[view(2048,8,[False,True])];page.screenshot(path=str(qa/"budget-desktop.png"),full_page=True)
        page.locator("#pFirst").click();snapshots.append(view(1701,8,[False,True]));page.locator("#budget").fill("1700");page.locator("#budget").press("Tab");snapshots.append(view(1700,8,[False,False]));page.locator("#pSecond").click();snapshots.append(view(2128,8,[True,True]))
        page.locator("#depth").fill("7");page.locator("#depth").press("Tab");snapshots.append(view(2128,7,[False,False]));page.locator("#reset").click()
        page.locator("[data-case='2']").click();snapshots.append(view(6144,8,[False,True]));page.screenshot(path=str(qa/"depth-desktop.png"),full_page=True);page.locator("#pSecond").click();snapshots.append(view(6144,16,[True,True]));page.locator("#budgetSlider").fill("6105");snapshots.append(view(6105,16,[False,True]));page.locator("#pFirst").click();snapshots.append(view(6105,8,[False,True]));page.locator("#reset").click();snapshots.append(view(6144,8,[False,True]))
        page.locator("header a").click();assert page.locator("#method").evaluate("e=>e.open");page.locator("#method summary").click()
        page.set_viewport_size({"width":390,"height":844});page.locator("[data-case='1']").click();page.evaluate("window.scrollTo(0,0)");snapshots.append(view(2048,8,[False,True]));assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth");page.screenshot(path=str(qa/"budget-mobile.png"),full_page=True);page.set_viewport_size({"width":320,"height":760});assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")
        version=browser.version;context.close();browser.close()
    remote=[s for s in requests if not s.startswith("file:")];assert not errors and not remote,(errors,remote);write(D/"browser-receipt.json",{"html":sha(file),"oracle":sha(D/"oracle.json"),"browser":version,"offline":True,"remote_requests":len(remote),"page_errors":errors,"threshold_depth_combinations":checks,"ui_states":snapshots,"mobile_widths_checked":[390,320],"screenshots":{p.name:sha(p) for p in sorted(qa.glob("*.png"))},"program":sha(Path(__file__))});print(checks,"states,",len(snapshots),"UI transitions,",version)
if __name__=="__main__":main()
