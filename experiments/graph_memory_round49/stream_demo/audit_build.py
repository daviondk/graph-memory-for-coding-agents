"""Render the manuscript and exercise the example and its narrow screen layout."""
from pathlib import Path
from hashlib import sha256
import argparse,json,sqlite3,subprocess
import fitz
from PIL import Image
from playwright.sync_api import sync_playwright
from demo import child
D=Path(__file__).resolve().parent
def main(out):
    with fitz.open(D/"paper.pdf") as doc:
        assert len(doc)==4 and all(p.rect.width==612 and p.rect.height==792 for p in doc)
        words=' '.join(p.get_text() for p in doc)
        values=['1,072','17/54','8/54','106,134','51,849','64.90','75.15','40,000','131.11','Pisinger','Ganguly','Crema']
        assert all(w in words for w in values)
        if out:
            im=Image.new("RGB",(1228,400),"#aaa")
            for i,p in enumerate(doc):
                pix=p.get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False)
                im.paste(Image.frombytes("RGB",(pix.width,pix.height),pix.samples),(i*307,2))
            im.save(out/'r49-paper.png')
    checked=[]
    with child(D/'apps/trace/launcher.py') as addr, sync_playwright() as pw:
        chrome=next(p for p in ("C:/Program Files/Google/Chrome/Application/chrome.exe","C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe") if Path(p).is_file())
        browser=pw.chromium.launch(executable_path=chrome,headless=True)
        for width in (1040,390):
            page=browser.new_page(viewport={"width":width,"height":844});errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(addr+'/observed');page.wait_for_function("document.body.dataset.ready==='q25/9/4/all'")
            assert page.locator("#rows").inner_text().count("Same packet")==6
            page.locator("#subset").select_option("5");page.wait_for_function("document.body.dataset.ready==='q25/9/4/5'");assert "stays the same" in page.locator("#delta").inner_text()
            page.locator("#subset").select_option("");page.wait_for_function("document.body.dataset.ready==='q25/9/4/'")
            page.locator("#subset").select_option("5,18");page.wait_for_function("document.querySelector('#delta').textContent.includes('19 to 15')")
            page.locator("#policy").select_option("1");page.wait_for_function("document.body.dataset.ready==='q25/9/1/5,18'");assert "same" in page.locator("#delta").inner_text()
            page.locator("#reset").click();page.wait_for_function("document.body.dataset.ready==='q25/9/4/all'")
            page.locator("#verify").click();page.wait_for_function("document.querySelector('#proof').textContent.startsWith('Exact match')")
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth") and not errors
            assert page.request.get(addr+'/api/observed/show?q=q25&step=9&cap=1&set=999').status==400
            if out:page.screenshot(path=out/f'r49-observed-{width}.png',full_page=True)
            checked.append(width);page.close()
        with child(D/'apps/stream/server.py') as stream:
            for width in (1040,390):
                page=browser.new_page(viewport={"width":width,"height":844})
                page.goto(stream);page.wait_for_function("document.body.dataset.ready==='Medium/16/1'")
                page.locator('[data-distance="4"]').click();page.wait_for_function("document.body.dataset.ready==='Medium/16/5'")
                page.locator('[data-distance="4"]').click();page.wait_for_function("document.body.dataset.ready==='Medium/16/9'")
                page.click('#audit');page.wait_for_function("document.querySelector('#status').textContent.startsWith('Exact match')")
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                if out:page.screenshot(path=out/f'r49-stream-{width}.png',full_page=True)
                page.close()
        with child(D/'apps/core/core_view.py') as core:
            for width in (1040,390):
                page=browser.new_page(viewport={"width":width,"height":844})
                page.goto(core);page.locator("#case").select_option("long");page.locator("#step").select_option("100")
                page.wait_for_function("document.querySelector('#remain').textContent==='61'")
                page.locator("#audit").click();page.wait_for_function("document.querySelector('#status').textContent.startsWith('All ordered packet IDs match')")
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                if out:page.screenshot(path=out/f'r49-core-{width}.png',full_page=True)
                page.close()
        browser.close()
    streams=json.loads(subprocess.check_output(["ffprobe","-v","quiet","-count_frames","-show_entries","stream=codec_name,codec_type,nb_read_frames","-of","json",str(D/"walkthrough.mp4")]))["streams"]
    assert {s["codec_name"] for s in streams}=={"h264","aac"} and all(int(s["nb_read_frames"])>0 for s in streams)
    result=dict(pages=4,page_dimensions_points=[612,792],widths=checked,text_values=values,streams=streams,
                pdf_sha256=sha256((D/"paper.pdf").read_bytes()).hexdigest(),zip_sha256=sha256((D/"candidate.zip").read_bytes()).hexdigest())
    print(json.dumps(result));(D/"build-check.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--screens",type=Path);main(parser.parse_args().screens)
