"""Unpack the R55 archive and check the complete offline demonstration."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from zipfile import ZipFile

import fitz
import package


def command(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                            encoding="utf8", errors="replace", timeout=360)
    if result.returncode:
        raise AssertionError((args, result.stdout[-1200:], result.stderr[-1500:]))
    return result.stdout


def check_pdf(root):
    external = set()
    internal = 0
    page_images = []
    with fitz.open(root / "paper.pdf") as doc:
        assert len(doc) == 4
        text = "\n".join(page.get_text() for page in doc)
        compact_text = " ".join(text.replace("-\n", "-").split())
        for phrase in ("archived per-commit index counters", "atomic batches of signed updates", "omit adaptive sizing"):
            assert phrase in compact_text, phrase
        for marker in ("9.94", "714", "10.08", "533", "1,112", "1,072", "33.49%", "48.92%", "41/61", "43/61", "20 hits",
                       "3,023", "338", "904", "848", "888", "308", "214", "72-byte", "14,482", "12,253", "880",
                       "34.75%", "48.83%", "29.58%", "50.46%", "41.20%", "43.36%", "28 additional", "OpenAI Codex"):
            assert marker in text, marker
        for page in doc:
            assert tuple(page.rect) == (0., 0., 612., 792.)
            assert len(page.get_text().split()) > 450
            for item in page.get_links():
                if item["kind"] == fitz.LINK_URI:
                    uri = item["uri"]
                    assert urlsplit(uri).scheme in ("https", "http") and urlsplit(uri).hostname
                    external.add(uri)
                else:
                    assert 0 <= item["page"] < len(doc), item
                    internal += 1
            pixels = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
            page_images.append(sha256(pixels.samples).hexdigest())
    assert {"https://arxiv.org/abs/2607.24882", "https://arxiv.org/abs/2308.01861"} <= external
    assert internal >= 10
    md = [root / "README.md", root / "DATA_SOURCES.md", root / "apps/session/README.md"]
    for document in md:
        for link in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf8")):
            if link.startswith(("http://", "https://", "#")):
                continue
            assert (document.parent / link).is_file(), (document, link)
    return dict(internal_pdf_links=internal, external_pdf_targets=sorted(external),
                raster_rgb_sha256=page_images, raster_dpi=90, updated_markdown_checked=len(md))


def check_git_scene(root):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runner:
        browser = runner.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 900, "height": 750})
            page.goto((root / "tox-replay.html").as_uri())
            table = []
            for version, cap, score, classic, partial in (("after", 8, 29, 1, 0), ("before", 8, 30, 0, 0),
                                                        ("after", 12, 29, 0, 0)):
                page.locator("#" + version).click()
                page.locator("#l" + str(cap)).click()
                values = {name: int(page.locator("#" + name).inner_text().strip())
                          for name in ("eighthScore", "classicWarm", "partialWarm", "classicRows", "partialRows",
                                       "coldProbes", "coldRows")}
                assert (values["eighthScore"], values["classicWarm"], values["partialWarm"]) == (score, classic, partial)
                assert (values["classicRows"], values["partialRows"]) == (classic, partial)
                assert (values["coldProbes"], values["coldRows"]) == (1, cap)
                table.append(dict(version=version, cap=cap, **values))
            return table
        finally:
            browser.close()

def check_coedit_scene(root):
    from playwright.sync_api import sync_playwright
    import importlib.util
    with sync_playwright() as pw:
        with pw.chromium.launch(headless=True) as browser:
            page=browser.new_page(viewport={"width":1280,"height":760})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto((root/"coedit-replay.html").as_uri())
            page.wait_for_selector("#task option",state="attached")
            assert page.locator("#task option").count()==54
            page.click("#lexical")
            page.click("#reveal")
            assert page.locator("#reveal").get_attribute("aria-expanded")=="true"
            page.click("#graph")
            # Compare all three objective primary aggregate states in the actual new SQL console.
            spec=importlib.util.spec_from_file_location("archive_loopback",root/"demo.py")
            launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
            observed=[]
            with launcher.child(root/"apps/cochange/serve.py") as url:
                page.goto(url)
                for cap,basis,w,probes,rows,vm in [(8,"bytes",32,214,888,"12253"),(8,"slots",32,338,904,"15664"),(8,"bytes",16,274,1240,"—")]:
                    page.select_option("#cap",str(cap));page.select_option("#basis",basis);page.select_option("#w",str(w))
                    page.wait_for_function("x=>document.querySelector('#costs tr td:nth-child(4)')?.textContent===x",arg=str(probes))
                    row=page.locator("#costs tr").first.locator("td").all_text_contents()
                    assert int(row[4])==rows and row[5]==vm
                    observed.append(dict(cap=cap,basis=basis,window=w,warm_probes=probes,warm_rows=rows,vm_steps=vm))
            assert not errors, errors
            return dict(retrieval_tasks=54,sql_browser_states=observed)


def main():
    d = package.D
    archive_sha = package.digest((d / "candidate.zip").read_bytes())
    previous = package.predecessor()
    new = package.extension()
    with TemporaryDirectory(dir=d.parent) as temp:
        root = Path(temp)
        with ZipFile(d / "candidate.zip") as archive:
            names = archive.namelist()
            assert len(names) == len(set(names)) and archive.testzip() is None
            assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts for n in names)
            payload = {n: archive.read(n) for n in names if n != "CONTENT_SHA256.json"}
            assert json.loads(archive.read("CONTENT_SHA256.json")) == {n: package.digest(v) for n, v in payload.items()}
            assert set(payload) == set(previous) | set(package.DOCS) | set(new)
            assert all(payload[n] == (d / n).read_bytes() for n in package.DOCS)
            assert all(payload[n] == data for n, data in new.items())
            retained = [n for n in previous if n not in set(package.DOCS) | set(new) | {"app-inputs.json"}]
            assert all(payload[n] == previous[n] for n in retained)
            archive.extractall(root)
        session_sha = {"trace.sqlite": "d1a6cf8100c605c7c40f86a59fea7f7f23ba9e2f6ca28d14bd79b5efd9bf9cea",
                       "audit.sqlite": "18172ad97ddbeeecc831da535eb81a19a3f8b2fa345c2416b3459f8119cb484a"}
        for name, digest in session_sha.items():
            assert package.digest((root / "apps/session" / name).read_bytes()) == digest
        checks = {}
        for name in ["verify_candidate.py", "replay_topk.py", "apps/session/test_console.py", "apps/churn/demo/verify_http.py",
                     "apps/directory/test_console.py", "apps/history/test_console.py", "apps/history/test_extension.py"]:
            checks[name] = command([sys.executable, "-B", "-X", "utf8", name], root).strip()[-600:]
        # Reproduce the paper's two live console states from the extracted applications.
        # Pixel hashes are recorded separately because OS fonts and browser builds can vary.
        checks["capture.py"] = command([sys.executable, "-B", "capture.py"], root).strip()
        from PIL import Image
        recaptured = {}
        for name in ("session-read.png", "withdrawal.png"):
            original = Image.open(root / name)
            replay = Image.open(root / "captures" / name)
            assert original.size == replay.size and original.size[0] > 300 and original.size[1] > 100
            recaptured[name] = dict(size=list(replay.size), same_pixels=original.convert("RGB").tobytes() == replay.convert("RGB").tobytes())
        assert package.digest((root / "tox-replay.html").read_bytes()) == "0fa340c0a36fbb419282148eece7d12699d8f788f0ae39122c167b9532fa9774"
        git_scene = check_git_scene(root)
        coedit = check_coedit_scene(root)
        pdf = check_pdf(root)
        pdf["figure_replay"] = recaptured
        video = root / "walkthrough.mp4"
        v = json.loads((root / "browser-video.json").read_bytes())
        probe = json.loads(command(["ffprobe", "-v", "error", "-show_entries",
                                    "stream=codec_name:format=duration,size", "-of", "json", str(video)], root))
        assert [s["codec_name"] for s in probe["streams"]] == ["h264", "aac"]
        seconds=float(probe["format"]["duration"]); size=int(probe["format"]["size"])
        assert seconds==193.16 and size==5661457 and v["file_sha256"]==package.digest(video.read_bytes())
        assert (package.FILM/"walkthrough.mp4").read_bytes()==video.read_bytes()
        assert v["captions_sha256"]==package.digest((root/"captions.srt").read_bytes())
        assert len(v["verified_scenes"])==20 and v["decoded_full_file"]
        command(["ffmpeg", "-loglevel", "error", "-xerror", "-i", str(video), "-map", "0:v", "-map", "0:a",
                 "-f", "null", "-"], root)
        assert package.digest((d / "candidate.zip").read_bytes()) == archive_sha, "Candidate changed during verify"
        assert (d / "paper.pdf").read_bytes() == (root / "paper.pdf").read_bytes()
        result = dict(files=len(names), sha256=archive_sha,
                      zip_bytes=(d / "candidate.zip").stat().st_size, previous_archive=package.PIN,
                      previous_payload_files_unchanged=len(retained), video_sha256=v["file_sha256"],
                      seconds=seconds, video_bytes=size, pages=4, session_databases=session_sha, git_scene=git_scene, coedit=coedit,
                      paper_sha256=package.digest((d / "paper.pdf").read_bytes()),
                      output_pdf="Letter 612 x 792 pt, each page", pdf=pdf, checks=checks)
        (d / "verification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
