from artifacts import *
def main():
    url="https://api.github.com/repos/iroiro147/dreambench-swe/releases/tags/v2.1.0"
    assets=json.loads(fetch(url))["assets"]
    name="dreambench-swe-v2.1.0-artifact.tar.gz"
    def asset(s):return next(x for x in assets if x["name"]==s)
    info=asset(name);checksum=asset("dreambench-swe-v2.1.0-RELEASE-CHECKSUMS.sha256")
    data=fetch(info["browser_download_url"]);ledger=fetch(checksum["browser_download_url"])
    assert sha(data)==next(row.split()[0] for row in ledger.decode().splitlines() if row.split()[-1].endswith(name))
    public=ROOT/"successor-public"
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as z:
        listing=[]
        for entry in z:
            if not entry.isfile():continue
            f=public/entry.name;assert f.resolve().is_relative_to(public)
            f.parent.mkdir(exist_ok=True,parents=True);f.write_bytes(z.extractfile(entry).read());listing.append(entry.name)
    put(ROOT/"release-verification.json",dict(url=info["browser_download_url"],sha256=sha(data),ledger_url=checksum["browser_download_url"],ledger_sha=sha(ledger),
                                             listing=listing))
    print([f for f in listing if "verif" in f or f.endswith("README.md")][:15])
if __name__=="__main__":main()
