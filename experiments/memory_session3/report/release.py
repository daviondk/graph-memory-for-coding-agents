"""Publish only the exact assets visually approved after the independent layout and source checks."""
from pathlib import Path
import csv
import hashlib
import json
import shutil
import sys
import zipfile
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parent
FINAL=ROOT/"final"
OUTPUT=ROOT.parents[2]/"outputs"
NAME="agent-memory-session3-results"
def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def commit():
    checks=read(FINAL/"qa.json")
    assert len(checks["pages"])==len(checks["paragraph_titles"])==12
    for row,title in zip(checks["pages"],checks["paragraph_titles"]):
        assert row["bounds_ok"] and title in row["matches"] and row["words"]>130,row
        assert row["body_end_pt"]<796 and row["links"]>=0,row
        assert (FINAL/f"page-{row['n']}.png").stat().st_size>9000
    assert len(checks["docx_hyperlinks"])>=18
    alf=read(ROOT.parent/"alfworld/results.json")
    assert sum(v["n"] for v in alf["all"].values())==1340
    transfer=read(ROOT.parent/"alfworld/transfer_results.json")
    assert transfer["valid_seen"]["all"]["full"]["n"]==140 and transfer["valid_unseen"]["all"]["full"]["n"]==134
    run=read(ROOT.parent/"runtime/verified.json")["actual_by_experiment"]
    assert sum(x["calls"] for x in run.values())==200
    assert sum(x["prompt_tokens"] for x in run.values())==62327
    assert sum(x["completion_tokens"] for x in run.values())==19665
    with zipfile.ZipFile(FINAL/(NAME+".docx")) as zipped:
        xml=zipped.read("word/document.xml").decode("utf8")
        assert "будут внесены" not in xml and "будут доступны" not in xml
    pdf=PdfReader(FINAL/(NAME+".pdf"))
    assert len(pdf.pages)==12
    n_annot=sum(len(pg.get("/Annots",[])) for pg in pdf.pages)
    assert n_annot>=len(checks["docx_hyperlinks"])
    signatures={}
    for suffix in [".docx",".pdf"]:
        source=FINAL/(NAME+suffix)
        expected=sha(source)
        dest=OUTPUT/(NAME+suffix)
        tmp=OUTPUT/(NAME+".partial"+suffix)
        shutil.copyfile(source,tmp)
        assert sha(tmp)==expected
        tmp.replace(dest)
        assert sha(dest)==expected
        signatures[dest.name]=expected
    (FINAL/"published.json").write_text(json.dumps({"files":signatures,"pdf_page_count":len(pdf.pages),"pdf_link_annotations":n_annot},indent=2),encoding="utf8")
    print(signatures)
if __name__=="__main__":
    commit()

