"""Archive material required to inspect every observation, including source and metric receipts."""
import hashlib,json,os,zipfile
from pathlib import Path
R=Path(__file__).resolve().parent;root=R.parents[1];out=root/"outputs"
def collect():
    files=set()
    def take(p):
        if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts and p.suffix not in {".pyc",".tmp"}:files.add(p)
    def flat(p):
        for f in p.glob("*"):take(f)
    def tree(p):
        for f in p.rglob("*"):take(f)
    take(out/"graph-memory-research-round2.docx")  # layout source for rebuilding the current report
    for ext in ("pdf","docx"):
        published=out/("graph-memory-research-round3."+ext)
        if not published.is_file():raise FileNotFoundError(published)
        take(published)
    for p in R.glob("*"):
        if p.name!="plot_install.log":take(p)
    for key in ("writer","demand","context","class_memory"):tree(R/key)
    flat(R/"serialized_writer")
    for p in (R/"serialized_writer/curve").glob("*"):
        if p.is_file() and not p.name.startswith(("cuts_","events_")):take(p)
    for p in (R/"repo").glob("*"):take(p)
    for p in (R/"qa").glob("*"):
        if not p.name.startswith("tree_"):take(p)
    for p in (R/"qa/upstream").glob("*"):
        if p.name in ("LICENSE.txt","sources.json","extra_sources.json") or ("score" in p.name and p.stat().st_size<3_000_000):take(p)
    flat(R/"report");flat(R/"report/pages")
    for p in (R/"report/final").glob("*.json"):take(p)
    # Public raw trajectories may be large. Retain safe projected inputs, scoring scripts and per-item predictions.
    # Skip re-fetchable source tarballs and unfiltered raw command histories.
    for sub in ("real_swe", "real_swe_followup"):
        path=R/sub
        if path.exists():
            flat(path)
            for folder in ("projected","source","predictions","scores"):
                if (path/folder).is_dir():tree(path/folder)
    P=root/"work/memory_session5/packets"
    for n in ("common.py","policy.py","pipeline.py","extract5.py","parent_extract.py","qwen_tokenizer.json","shards.json","selection.json","transfer/selection.json"):take(P/n)
    tree(P/"source/train");tree(P/"source/test");tree(P/"transfer/source")
    old=root/"work/graph_memory_round2"
    for n in ("edit_memory/experiment.py","edit_memory/model.json","edit_memory/split.json","span_memory/run.py","span_memory/budget.py","span_memory/width_model.json","span_memory/offset.json","span_memory/selection.json"):take(old/n)
    return sorted(files)
def main():
    dest=out/"graph-memory-round3-records.zip";tmp=dest.with_suffix(".partial.zip");manifest={}
    with zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for p in collect():
            n=p.relative_to(root).as_posix();data=p.read_bytes();manifest[n]={"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()};z.writestr(n,data)
        z.writestr("MANIFEST.json",json.dumps({"format":1,"files":manifest},indent=1))
    with zipfile.ZipFile(tmp) as z:
        assert z.testzip() is None and set(z.namelist())==set(manifest)|{"MANIFEST.json"}
        for n,v in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==v["sha256"]
    os.replace(tmp,dest)
    print(len(manifest),dest.stat().st_size,hashlib.sha256(dest.read_bytes()).hexdigest())
if __name__=="__main__":main()
