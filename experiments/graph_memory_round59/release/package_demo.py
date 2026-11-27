"""Build a deterministic portable release and verify the actual extracted result."""
import argparse
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import build_opener, ProxyHandler
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

HERE=Path(__file__).resolve().parent
ROUND=HERE.parent
EXP=ROUND.parent
TWO=EXP/"graph_memory_round57/seed_pair"
FILES={"start.html":HERE/"start.html","README.md":HERE/"README.md",
       "graph-memory.html":ROUND/"demo/index.html","restart.html":EXP/"graph_memory_round58/demo/index.html",
       "paper.pdf":ROUND/"manuscript/paper.pdf","walkthrough.mp4":ROUND/"walkthrough/walkthrough.mp4",
       "captions.srt":ROUND/"walkthrough/captions.srt","one-file.html":EXP/"graph_memory_round56/manuscript/replay.html",
       **{k:HERE/k for k in ("live_query.py","query.json","source.sqlite")},
       **{"two-files/"+k:TWO/k for k in ("demo.py","demo_store.py","demo.html","replay.sqlite","view.html")}}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__();self.href=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":self.href.append(dict(attrs)["href"])


def build(dest):
    with ZipFile(dest,"w",compression=ZIP_DEFLATED,compresslevel=6) as z:
        for k,p in sorted(FILES.items()):
            meta=ZipInfo(k,(1980,1,1,0,0,0))
            meta.create_system=3;meta.external_attr=0o100644<<16;meta.compress_type=ZIP_DEFLATED
            z.writestr(meta,p.read_bytes(),compresslevel=6)


def sqlite_cases(root):
    cmd=[sys.executable,"-I","-B","-S"]
    def case(extra):
        return json.loads(subprocess.check_output([*cmd,"live_query.py","--json",*extra],cwd=root,text=True,timeout=15))
    basic=case([]);lost=case(["--hide-one"])
    assert (basic["known"],basic["count"],basic["query_reads"])==(39,40,["body(177)"])
    assert basic["recovered"][0]["commit"]=="79234f8909ce103792e646ed79c429046353ba58"
    assert lost["query_reads"]==["posting(file)","body(2)","body(177)"]
    assert basic["ranking"]==lost["ranking"] and basic["ranking"][0]==["rich/console.py",37]
    assert basic["full_index_verified"] and lost["full_index_verified"]
    two=root/"two-files"
    cli=[*cmd,"-u","-c","import sys,runpy;sys.path.insert(0,'.');sys.argv=['demo.py',*sys.argv[1:]];runpy.run_path('demo.py',run_name='__main__')"]
    subprocess.run([*cli,"check-snapshot"],cwd=two,check=True,capture_output=True,timeout=20)
    proc=subprocess.Popen([*cli,"open-snapshot","--port","0"],cwd=two,stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT,text=True,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    try:
        host=re.search(r"http://127\.0\.0\.1:\d+",proc.stdout.readline()).group()
        opener=build_opener(ProxyHandler({}))
        results={}
        for name,expected in (("gain",[0,2,3]),("loss",[1,0,0])):
            with opener.open(host+"/case/"+name,timeout=5) as f:r=json.load(f)
            actual=[len(set(r["ranks"][k])&set(r["gold"])) for k in ("sum","joint","placebo")]
            assert actual==expected;results[name]=actual
        with opener.open(host+"/world/7/4/13",timeout=5) as f:assert json.load(f)["third"]==8
    finally:
        proc.terminate();proc.wait(timeout=10)
    return dict(one_missing=basic["query_reads"],two_missing=lost["query_reads"],rank_count=len(basic["ranking"]),
                source=basic["recovered"][0]["commit"],interactive_two_file_cases=results,world_third=8)


def browser_views(root):
    from playwright.sync_api import sync_playwright
    errors=[];requests=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel="chrome",headless=True)
        page=browser.new_page(offline=True,viewport={"width":1170,"height":850})
        page.on("pageerror",lambda err:errors.append(str(err)))
        page.on("request",lambda req:requests.append(req.url) if req.url.startswith(("https:","http:")) else None)
        start=(root/"start.html").as_uri();page.goto(start)
        page.get_by_role("link",name="Open the graph memory demo").click()
        assert page.get_by_role("heading",name="What crosses the restart boundary?").is_visible()
        page.click("#showCounter");assert "4,484" in page.locator("#counter").inner_text()
        page.click("#goSketch");page.select_option("#hs","B");page.select_option("#hp","all")
        for cap,amount in (("1024","20,055"),("4096","7,725")):
            page.select_option("#hb",cap)
            assert page.locator("#holdRows tr").nth(3).locator("td").nth(1).inner_text()==amount
        page.select_option("#missing","2");assert "Fetch the exact posting list" in page.locator("#equation").inner_text()
        page.goto(start);page.get_by_role("link",name="Checkpoint budgets").click()
        assert page.locator("#total").inner_text()=="82,907 B"
        page.goto(start);page.get_by_role("link",name="One-file NetworkX queries").click()
        assert "NetworkX" in page.locator("body").inner_text() or "networkx" in page.locator("body").inner_text()
        page.goto(start);page.get_by_role("link",name="Two-file Dask and xarray queries").click()
        assert page.locator("#caseInfo h2").inner_text()=="dask/dask"
        page.set_viewport_size({"width":390,"height":844});page.goto(start)
        assert page.evaluate("document.documentElement.scrollWidth-innerWidth")<=1
        browser.close()
    assert not requests and not errors,(requests,errors)
    return dict(offline_browser_views=5,screen_widths=[1170,390],network_requests=0,page_errors=0)


def media(root):
    import fitz
    with fitz.open(root/"paper.pdf") as pdf:
        assert len(pdf)==4 and all(tuple(p.rect)==(0,0,612,792) for p in pdf)
        assert "REFERENCES" in pdf[-1].get_text()
    manuscript=json.loads((ROUND/"manuscript/verification.json").read_bytes())
    assert digest(root/"paper.pdf")==manuscript["pdf_sha256"]
    release=json.loads((ROUND/"walkthrough/verification.json").read_bytes())
    raw=subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_name",
                                "-of","json",str(root/"walkthrough.mp4")],text=True,timeout=15)
    video=json.loads(raw)
    secs=float(video["format"]["duration"])
    assert 0<secs<=300 and (root/"walkthrough.mp4").stat().st_size<50000000
    assert {s["codec_name"] for s in video["streams"]}=={"h264","aac"}
    assert digest(root/"walkthrough.mp4")==release["file_sha256"]
    assert digest(root/"captions.srt")==release["captions_sha256"]
    caps=(root/"captions.srt").read_text("utf8")
    times=re.findall(r"(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})",caps)
    assert times and ((int(times[-1][4])*60+int(times[-1][5]))*60+int(times[-1][6])+int(times[-1][7])/1000)<=secs+0.2
    return dict(pages=4,video_seconds=secs,video_codecs=["h264","aac"],caption_cues=len(times))


def inspect(archive,out):
    with ZipFile(archive) as z:
        assert z.namelist()==sorted(FILES) and z.testzip() is None
        for name,p in FILES.items():assert z.read(name)==p.read_bytes()
        z.extractall(out)
    links=Anchors();links.feed((out/"start.html").read_text("utf8"))
    assert links.href[0]=="graph-memory.html" and all((out/k).is_file() for k in links.href)
    return dict(sha256=digest(archive),size_bytes=archive.stat().st_size,source_sha256={k:digest(p) for k,p in sorted(FILES.items())},
                start_links=links.href,isolated_sqlite=sqlite_cases(out),offline_browser=browser_views(out),media=media(out))


def main():
    p=argparse.ArgumentParser();p.add_argument("--verify",action="store_true");opt=p.parse_args()
    archive=HERE/"candidate.zip";record=HERE/"verification.json"
    with TemporaryDirectory(dir=HERE) as tmp:
        base=Path(tmp);candidate=base/"candidate.zip";build(candidate)
        receipt=inspect(candidate,base/"extracted")
        if opt.verify:
            assert archive.read_bytes()==candidate.read_bytes() and json.loads(record.read_bytes())==receipt
        else:
            shutil.copyfile(candidate,archive)
            record.write_bytes((json.dumps(receipt,sort_keys=True,indent=2)+"\n").encode())
    print("Verified",len(FILES),"files,",receipt["size_bytes"],"bytes,",receipt["sha256"])

if __name__=="__main__":main()
