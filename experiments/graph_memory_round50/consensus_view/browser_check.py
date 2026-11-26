"""Exercise the shipped page and its layout against the actual local HTTP service."""
import json
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright
from serve import Handler,ThreadingHTTPServer,D

def run():
    checks=[]
    with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
        worker=Thread(target=server.serve_forever,daemon=True);worker.start()
        with sync_playwright() as pw:
            exe=next(p for p in (Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")) if p.is_file())
            browser=pw.chromium.launch(executable_path=str(exe),headless=True)
            for size in (1040,390):
                page=browser.new_page(viewport={"width":size,"height":844})
                errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                page.wait_for_function("document.body.dataset.ready==='votes_greedy/2048/5'")
                assert "matches" in page.locator("#archive").inner_text()
                page.locator("#evaluate").click();page.wait_for_function("document.querySelector('#gold').textContent.includes('characters')")
                page.locator("#method").select_option("hamming_dp")
                page.wait_for_function("document.body.dataset.ready==='hamming_dp/2048/5'")
                page.locator("#budget").fill("1024");page.locator("#budget").press("Tab")
                page.locator("#seeds input").first.uncheck()
                page.wait_for_function("document.body.dataset.ready==='hamming_dp/1024/4'")
                page.locator("#case").select_option("17")
                page.wait_for_function("document.querySelector('#case').value==='17' && !document.querySelector('#error').textContent")
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                assert not errors
                checks.append([size,page.locator("tbody tr").count(),page.locator("#used").inner_text()])
                page.close()
            browser.close()
        server.shutdown();worker.join()
    print(checks)
if __name__=="__main__":run()

