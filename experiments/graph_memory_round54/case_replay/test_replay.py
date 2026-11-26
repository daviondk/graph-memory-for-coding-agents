"""Independent embedded-data test. Pass --browser to also exercise the browser controls with Playwright."""
import argparse
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

HERE=Path(__file__).resolve().parent
class Parsed(HTMLParser):
    def __init__(self):
        super().__init__();self.ids=set();self.data="";self.record=False
    def handle_starttag(self,tag,items):
        attrs=dict(items)
        if "id" in attrs:
            assert attrs["id"] not in self.ids
            self.ids.add(attrs["id"])
        if tag=="script" and attrs.get("id")=="data":
            self.record=True
    def handle_endtag(self,tag):
        if tag=="script":
            self.record=False
    def handle_data(self,txt):
        if self.record:
            self.data+=txt


def sql_check(html):
    parser=Parsed()
    parser.feed(html)
    assert {"before","after","l8","l12","ranking","priorScore","eighthScore","boundScore","valid","classicWarm",
            "partialWarm","classicRows","partialRows","coldProbes","coldRows","localCold"}<=parser.ids
    data=json.loads(parser.data)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE source(id INTEGER PRIMARY KEY,n INTEGER NOT NULL)")
        db.executemany("INSERT INTO source VALUES(?,?)",[(i,v) for i,v in enumerate(data["baseline"],1) if v is not None])
        for i,snap in enumerate(data["commits"]):
            if i:
                db.executemany("INSERT INTO source VALUES(?,0)",[(v,) for v in data["born"]])
                for src,dst,delta in data["edges"]:
                    assert db.execute("UPDATE source SET n=n+? WHERE id=?", (delta,src)).rowcount==1
            assert db.execute("SELECT COUNT(*) FROM source").fetchone()[0]==292+i
            top=db.execute("SELECT id,n FROM source ORDER BY n DESC,id ASC LIMIT 8").fetchall()
            assert [list(x) for x in top]==snap["top"]
            assert top[-1]==(11,30-i)
            for l in (8,12):
                part,classic=(snap["policies"][p+str(l)] for p in ("partial","classic"))
                assert (part["warm"],part["rows"])==(0,0)
                expected=int(i==1 and l==8)
                assert (classic["warm"],classic["rows"])==(expected,expected)
                assert part["earlierCold"]==classic["earlierCold"]==1
                assert part["earlierColdRows"]==classic["earlierColdRows"]==l
                assert (top[-1][1],-top[-1][0])>=tuple(part["upper"])
        assert data["commits"][1]["policies"]["classic8"]["priorTail"]==[11,30]
        assert data["commits"][1]["policies"]["partial8"]["upper"]==[29,-11]
    return data


def check_browser(page_path,data,screenshot):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=pw.chromium.executable_path)
        with browser.new_context(viewport={"width":1170,"height":890},offline=True) as context:
            page=context.new_page()
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(page_path.as_uri())
            for idx,control in enumerate(("before","after")):
                page.locator("#"+control).click()
                for l in (8,12):
                    page.locator("#l"+str(l)).click()
                    s=data["commits"][idx]
                    p,c=s["policies"]["partial"+str(l)],s["policies"]["classic"+str(l)]
                    wanted=dict(eighthScore=s["top"][-1][1],priorScore=p["oldEighth"][1],boundScore=p["upper"][0],classicWarm=c["warm"],
                                partialWarm=p["warm"],classicRows=c["rows"],partialRows=p["rows"],coldRows=l,coldProbes=1,localCold=0)
                    for k,v in wanted.items():
                        assert page.locator("#"+k).inner_text()==str(v),(idx,l,k,v)
                    assert page.locator("#ranking tr").count()==8
                    assert page.locator("#ranking tr").last.locator("td").nth(1).inner_text()==data["files"][10]
                    assert page.locator("#source").get_attribute("href").endswith(s["rev"])
                    assert page.locator("#valid").inner_text().startswith(str(292+idx))
            page.locator("#l8").click()
            if screenshot:
                page.screenshot(path=screenshot,full_page=True)
            page.set_viewport_size({"width":360,"height":780})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#before").click()
            assert page.locator("#eighthScore").inner_text()=="30"
            assert not errors,errors
        browser.close()


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--browser",action="store_true")
    ap.add_argument("--screenshot")
    a=ap.parse_args()
    file=HERE/"index.html"
    data=sql_check(file.read_text(encoding="utf-8"))
    if a.browser:
        check_browser(file,data,a.screenshot)
    print("Verified both full SQL ranks, four receipt pairs, controls and bounds.",
          "Offline UI verified at 1170 and 360 px." if a.browser else "")

