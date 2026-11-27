"""Check both the offline view and the live SQLite route with Chromium."""
from contextlib import closing
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect
from demo import HERE, build, connect, handler, html, snapshot


def exercise(browser, url, offline, width):
    context = browser.new_context(offline=offline, viewport={"width": width,"height": 880})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    expect(page.locator("#caseInfo h2")).to_have_text("dask/dask")
    assert page.locator(".card .hit").count() == 5
    page.locator("#judgment").uncheck()
    expect(page.locator(".card .hit")).to_have_count(0)
    page.locator("#caseSelect").select_option("loss")
    expect(page.locator("#caseInfo h2")).to_have_text("pydata/xarray")
    page.locator("#witnesses summary").first.click()
    assert page.locator("#witnesses details[open]").count() == 1
    page.locator("#worldButton").click()
    page.locator("#a").select_option("4")
    page.locator("#b").select_option("13")
    page.locator("#shift").select_option("7")
    expect(page.locator("#third")).to_contain_text("C8.")
    expect(page.locator(".cell.found")).to_contain_text("C8")
    assert len(page.locator(".cell").all()) == 16
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    context.close()
    assert not errors, errors
    return {"offline":offline,"width":width,"real_cases":2,"known_files":[4,13],"history":7,"third":8}


def main():
    result = []
    with TemporaryDirectory(dir=HERE) as tmp:
        database = Path(tmp) / "demo.sqlite"
        build(database)
        with closing(connect(database)) as db:
            page = html(snapshot(db))
        with ThreadingHTTPServer(("127.0.0.1",0), handler(database,page)) as server:
            thread = Thread(target=server.serve_forever,daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base+"/case/gain", timeout=5) as response:
                    assert json.load(response)["repo"] == "dask/dask"
                try:
                    urlopen(base+"/world/16/0/0",timeout=5)
                except HTTPError as error:
                    assert error.code == 404
                else:
                    raise AssertionError("Invalid history accepted")
                with sync_playwright() as pw:
                    with closing(pw.chromium.launch()) as browser:
                        for width in (390, 1280):
                            result.append(exercise(browser, (HERE/"demo.html").as_uri(), True, width))
                            result.append(exercise(browser, base+"/?source=sqlite", False, width))
            finally:
                server.shutdown()
                thread.join()
    (HERE/"browser-check.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf8")
    print("Live SQLite and offline Chromium checks passed at both widths.")


if __name__ == "__main__":
    main()
