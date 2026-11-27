"""Create a reproducible visitor ZIP and exercise the unpacked pages, media and SQLite console."""
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
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent
FILES = {"start.html":HERE/"start.html", "graph-memory.html":ROUND/"demo/index.html",
         "paper.pdf":ROUND/"manuscript/paper.pdf", "walkthrough.mp4":ROUND/"walkthrough/walkthrough.mp4",
         "captions.srt":ROUND/"walkthrough/captions.srt",
         **{k:HERE/k for k in ("live_query.py","snapshot.html","query.json","source.sqlite")}}


def load(path):
    return json.loads(path.read_bytes())


def digest(p):
    return sha256(p.read_bytes()).hexdigest()


def build(zip_path):
    with ZipFile(zip_path, "w") as z:
        for name,p in sorted(FILES.items()):
            meta = ZipInfo(name, (1980,1,1,0,0,0))
            meta.create_system = 3
            meta.external_attr = 0o100644 << 16
            meta.compress_type = ZIP_DEFLATED
            z.writestr(meta, p.read_bytes(), compresslevel=6)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href.append(dict(attrs)["href"])


def isolated(root, *args):
    return [sys.executable, "-I", "-S", "-B", "-u", str(root/"live_query.py"), *args]


def queries(root):
    result = {}
    for mode, flags, size in (("notify", [], 0), ("quiet", ["--quiet"], 49)):
        q = json.loads(subprocess.check_output(isolated(root, "--json", *flags), cwd=root, timeout=12))
        assert q["read"] == dict(posting_calls=int(bool(size)), posting_bytes=size, body_calls=1, body_bytes=8)
        assert q["certified"] == (mode=="notify")
        assert q["full_history_verified"] and q["source_commits"] == {
            "94":"78b483d39e5d5e26814eeed5f4417c4bcbd15c97","117":"6d097c0214f9d581a2c41e4c701cfaca3796f874"}
        assert q["request"] == 50 and q["file"] == "tests/test_tablib.py"
        assert q["missing"] == [94,117] and q["resident"] == 38 and q["count"] == 40
        assert q["exceptions"] == ([94,116,117] if mode=="notify" else [])
        result[mode] = q
    assert result["notify"]["ranking"] == result["quiet"]["ranking"]
    return result


def browser(root, sql):
    from playwright.sync_api import sync_playwright, expect
    errors, external = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        offline = browser.new_context(offline=True, viewport={"width":1220, "height":860})
        page = offline.new_page()
        def observe(pg):
            pg.on("pageerror", lambda e:errors.append(str(e)))
            pg.on("request", lambda req:external.append(req.url) if req.url.startswith(("http:","https:"))
                  and not req.url.startswith("http://127.0.0.1:") else None)
        observe(page)
        start = (root/"start.html").as_uri()
        page.goto(start)
        page.get_by_role("link", name="Open the eviction lab").click()
        page.click("#first"); page.click("#last"); page.click("#two")
        expect(page.locator("#union")).to_contain_text("E = {13, 45}")
        page.click("#ask")
        expect(page.locator("#access")).to_have_text("0 posting requests · 2 fresh bodies")
        ranks = page.locator("#answer tr").all_text_contents()
        page.select_option("#rule", "quiet"); page.click("#two"); page.click("#ask")
        expect(page.locator("#access")).to_have_text("1 posting request · 2 fresh bodies")
        assert ranks == page.locator("#answer tr").all_text_contents()
        page.click("#goData")
        expect(page.locator("#rows tr").last.locator("td").nth(1)).to_have_text("9,213")
        page.click("#large")
        expect(page.locator("#rows tr").last.locator("td").nth(1)).to_have_text("4,322")
        page.click("#goLimits"); page.select_option("#span","4")
        expect(page.locator("#short")).to_contain_text("5,468")
        page.set_viewport_size({"width":390,"height":844}); page.goto(start)
        assert page.evaluate("document.documentElement.scrollWidth-innerWidth") <= 1
        offline.close()
        with subprocess.Popen(isolated(root,"--serve"), cwd=root, stdout=subprocess.PIPE,
                   stderr=subprocess.DEVNULL, text=True, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0)) as proc:
            try:
                host = proc.stdout.readline().strip()
                assert re.fullmatch(r"http://127\.0\.0\.1:\d+/", host)
                local = browser.new_context()
                local.route("**/*", lambda route:route.continue_() if route.request.url.startswith(host) else route.abort())
                pg = local.new_page(); observe(pg); pg.goto(host)
                for mode in ("notify","quiet"):
                    pg.click("#"+mode)
                    expect(pg.locator("#cost")).to_contain_text(f"= {8 if mode=='notify' else 57} SQLite payload bytes")
                    expect(pg.locator("#statements")).to_have_text("\n".join(sql[mode]["statements"]))
                    assert [[r.locator("td").first.inner_text(), int(r.locator("td").last.inner_text())]
                            for r in pg.locator("#scores tr").all()] == sql[mode]["ranking"]
                local.close()
            finally:
                proc.terminate();proc.wait(timeout=10)
        browser.close()
    assert not errors and not external
    return dict(workshop_ranks=ranks, sqlite_console_modes=["notify","quiet"], panel_costs=[9213,4322],
                observed_four_line_cost=5468, mobile_width=390, javascript_errors=0, external_requests=0)


def media(root):
    import fitz
    manuscript = load(ROUND/"manuscript/verification.json")
    assert digest(root/"paper.pdf") == manuscript["sha256"]["paper.pdf"]
    with fitz.open(root/"paper.pdf") as pdf:
        assert len(pdf)==4 and all(tuple(p.rect)==(0,0,612,792) and len(p.get_text())>500 for p in pdf)
        assert "When the Last Copy Leaves" in pdf[0].get_text()
        assert "REFERENCES" in pdf[-1].get_text().upper()
    recorded = load(ROUND/"walkthrough/verification.json")
    assert digest(root/"walkthrough.mp4") == recorded["file_sha256"]
    assert digest(root/"captions.srt") == recorded["captions_sha256"]
    info = json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_name,nb_frames",
                      "-of","json",str(root/"walkthrough.mp4")], text=True, timeout=15))
    assert [a["codec_name"] for a in info["streams"]]==["h264","aac"]
    assert int(info["streams"][0]["nb_frames"])==2742 and float(info["format"]["duration"])==109.68
    caps = (root/"captions.srt").read_text("utf8")
    assert caps.count(" --> ")==9 and "00:01:49,680" in caps
    subprocess.run(["ffmpeg","-v","error","-xerror","-i",str(root/"walkthrough.mp4"),"-f","null","-"],
                   check=True, capture_output=True, timeout=30)
    return dict(pages=4, paper_title="When the Last Copy Leaves", seconds=109.68, video_frames=2742,
                audio="AAC", video="H.264", decoded=True, caption_cues=9)


def inspect(archive, root):
    with ZipFile(archive) as z:
        assert z.namelist()==sorted(FILES) and z.testzip() is None
        assert all(z.read(k)==p.read_bytes() for k,p in FILES.items())
        z.extractall(root)
    links = Links()
    ui = load(ROUND/"demo/ui-check.json")
    assert digest(root/"graph-memory.html") == ui["html_sha256"]
    links.feed((root/"start.html").read_text("utf8"))
    assert set(links.href)=={"graph-memory.html","paper.pdf","walkthrough.mp4","captions.srt"}
    assert all((root/name).is_file() for name in links.href)
    sql = queries(root)
    return dict(sha256=digest(archive), bytes=archive.stat().st_size,
                sources={n:digest(root/n) for n in sorted(FILES)}, links=links.href,
                sqlite=sql, browser=browser(root,sql), media=media(root))


def rebuild_or_verify(verify):
    from capture_query import capture
    with TemporaryDirectory(dir=HERE, prefix="pack-") as td:
        temp = Path(td)
        capture(temp)
        assert all((temp/k).read_bytes()==(HERE/k).read_bytes() for k in ("source.sqlite","query.json"))
        packed = temp/"candidate.zip"
        build(packed)
        check = inspect(packed, temp/"extracted")
        where = HERE/"candidate.zip"
        audit = HERE/"verification.json"
        if verify:
            assert where.read_bytes()==packed.read_bytes() and load(audit)==check
        else:
            shutil.copyfile(packed,where)
            audit.write_bytes((json.dumps(check,sort_keys=True,indent=2)+"\n").encode())
    print("Verified",len(FILES),"files,",check["bytes"],"bytes,",check["sha256"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    rebuild_or_verify(parser.parse_args().verify)
