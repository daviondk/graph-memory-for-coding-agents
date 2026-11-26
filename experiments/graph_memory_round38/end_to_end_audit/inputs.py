from pathlib import Path
from hashlib import sha256
from urllib.request import urlopen,Request
from urllib.parse import urlencode
import io,json,os,shutil,subprocess,sys,tarfile
D=Path(__file__).resolve().parent;R=D/"runtime"; R.mkdir(exist_ok=True)
V=Path(os.environ.get("VIBE_CHECKOUT","D:/CodexResearch/x20-official-vibe/VibeMemBench"))
KEY="ipython__traitlets-670";COMMIT="191ff75e93d56446b2c051f4dbb33e2f0e7be71d"
HF="11164976b4f920cdb0d0cd570ca572e49acea1e8";GIT="7152cf96809b45343ccc1caf7115a7d3fa43f956"
def sha(p):return sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
def fetch(url,h=None):
    if h:
        raise ValueError("Use only anonymous incoming public artifacts")
    return subprocess.run(["curl.exe","--fail","--silent","--show-error","--location","--max-time","40",url],
                          check=True,stdout=subprocess.PIPE).stdout
def row():
    import pyarrow.parquet as pq
    path=V/"benchmark/test.parquet"
    assert sha(path)=="22238743ca143276e3ff4616f569b3921c42945bfee1a6aa8fa376a02feebb98"
    return next(x for x in pq.read_table(path).to_pylist() if x["instance_id"]==KEY)
def main():
    case=row();assert case["base_commit"]==COMMIT and case["license"]=="BSD-3-Clause"
    image=json.loads((D/"image.json").read_text(encoding="utf-8-sig"))
    url=f"https://codeload.github.com/ipython/traitlets/tar.gz/{COMMIT}"
    cache=R/"base.tar.gz"
    if not cache.exists():cache.write_bytes(fetch(url))
    archive=tarfile.open(cache,"r:gz");members=archive.getmembers()
    expanded=sum(m.size for m in members);assert expanded<30_000_000
    for arm in ("base","reference"):
        dest=R/arm;dest.mkdir(exist_ok=True)
        for member in members:
            if not member.isfile():continue
            rel=Path(member.name).relative_to("traitlets-"+COMMIT)
            assert not rel.is_absolute() and ".." not in rel.parts
            p=dest/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.extractfile(member).read())
    archive.close()
    vendor=V/"scripts/vendor"; code={p:sha(vendor/p) for p in ("eval.py","log_parsers.py","swe_constants.py")}
    upstream=f"https://raw.githubusercontent.com/AlibabaResearch/DAMO-ConvAI/{GIT}/VibeMemBench/scripts/vendor/"
    assert all(sha256(fetch(upstream+name)).hexdigest()==sig for name,sig in code.items())
    patches={}
    for field,good in (("patch","traitlets/traitlets.py"),("test_patch","traitlets/config/tests/test_loader.py")):
        content=case[field]; paths=[l for l in content.splitlines() if l.startswith("diff --git ")]
        assert paths==[f"diff --git a/{good} b/{good}"]
        file=R/(field+".diff");file.write_bytes(content.encode());patches[field]=sha(file)
    history=V/"benchmark/history/python/ipython__traitlets"
    hist=sorted(history.glob("*/*.traj.json"))
    license_path=next(p for p in (R/"base").glob("COPYING*") if p.is_file())
    save(D/"inputs.json",dict(instance=KEY,hf=HF,upstream=GIT,base=COMMIT,dataset_sha=sha(V/"benchmark/test.parquet"),
        repo_license=case["license"],license_file=license_path.name,license_sha=sha(license_path),
        benchmark_license_sha=sha(V/"LICENSE"),archive_url=url,archive_sha=sha(cache),archive_bytes=cache.stat().st_size,
        source_expanded=expanded,regular_files=sum(m.isfile() for m in members),
        image=case["image_name"],image_metadata=image,source_code=code,patches=patches,
        benchmark_test_command=case["install_config"]["test_cmd"],parser=case["install_config"]["log_parser"],
        historical_trajectory_count=len(hist),historical_trajectories=[p.parent.name for p in hist],
        f2p_count=len(case["FAIL_TO_PASS"]),p2p_count=len(case["PASS_TO_PASS"])))
    print("image compressed",image["compressed_bytes"],"archive",cache.stat().st_size,"histories",len(hist))
if __name__=="__main__":main()
