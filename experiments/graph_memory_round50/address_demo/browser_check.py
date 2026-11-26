"""Optional Chromium smoke test for the interaction and two viewport widths."""
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright
from address_server import Handler,ThreadingHTTPServer
def main():
    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
        worker=Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            with sync_playwright() as pw:
                path=next(p for p in [Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")] if p.exists())
                browser=pw.chromium.launch(executable_path=str(path),headless=True)
                for width in [1040,390]:
                    tab=browser.new_page(viewport=dict(width=width,height=900));errors=[]
                    tab.on("pageerror",lambda e:errors.append(str(e)))
                    tab.goto(f"http://127.0.0.1:{server.server_port}/")
                    tab.wait_for_selector("tr.pick");assert tab.locator("tbody tr").count()==9
                    tab.locator("#filter").select_option("loss");tab.wait_for_function("document.querySelector('#count').textContent.startsWith('4 of')")
                    tab.wait_for_function("current?.changed===true && current.selected_answer.f1<current.baseline_answer.f1")
                    tab.locator("#zero").click();tab.wait_for_function("current?.mode==='custom' && current.threshold===0 && !current.changed")
                    tab.locator("#always").click();tab.wait_for_function("current?.mode==='always' && current.changed")
                    tab.locator("#custom").fill("0.2");tab.locator("#custom").press("Tab");tab.wait_for_function("current?.threshold===0.2")
                    tab.locator("#registered").click();tab.wait_for_function("current?.mode==='registered'")
                    tab.locator("#reveal").click();tab.wait_for_function("document.querySelector('#gold').childElementCount===2")
                    tab.locator("#next").click();tab.wait_for_function("document.querySelector('#gold').childElementCount===0")
                    tab.wait_for_function("current?.episode.id===document.querySelector('#case').value")
                    assert tab.evaluate("document.documentElement.scrollWidth<=innerWidth"),tab.evaluate("[document.documentElement.scrollWidth,innerWidth]")
                    assert not errors;tab.close();print(width,"OK")
                browser.close()
        finally:server.shutdown();worker.join()
if __name__=="__main__":main()

