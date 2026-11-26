"""Evaluate the explicit suggested_unread_files channel of the archived agent."""
import argparse
import json
import tarfile
from decide import DEFAULT_CACHE, HERE, TRACES, choose, file_hash, first_chunks, original_runs, read_file, save
from grade import analyze

def propose(cache):
    orig=read_file(HERE/"decision-seal.json")
    assert all(file_hash(cache/name)==digest for name,digest in orig["sources"].items())
    traces,_,_=original_runs(cache)
    schema={"checked":0,"equal_last_action":0,"without_field":0,"different":[]}
    with tarfile.open(cache/TRACES) as arc:
        for member in arc:
            if "/traces_" not in member.name or not member.isfile():continue
            row=json.load(arc.extractfile(member));q=row["sample_id"]
            if q not in traces:continue
            supplied=row["suggested_unread_files"]
            assert isinstance(supplied,list)
            action=next((a["parsed"] for a in reversed(row["actions"]) if isinstance(a.get("parsed"),dict)
                         and "suggested_unread_files" in a["parsed"]),None)
            schema["checked"]+=1
            if action is None:schema["without_field"]+=1
            elif action["suggested_unread_files"]==supplied:schema["equal_last_action"]+=1
            else:schema["different"].append(q)
            traces[q]["raw"]=supplied
    receipts=first_chunks(cache,traces)
    decisions={}
    for q,t in sorted(traces.items()):
        valid=receipts[(t["repo"].replace("/", "__"),t["commit"])]
        dec=choose(t,valid)
        blocked=set(t["given"])|set(t["reads"])
        proposed=list(dict.fromkeys(p for p in t["raw"] if p not in blocked))
        dec["missing_first"]=bool(proposed and proposed[0] not in valid)
        decisions[q]=dec
    save("explicit-decisions.json.gz",decisions)
    save("explicit-seal.json",dict(code=file_hash(HERE/"suggestions.py"),original_seal=file_hash(HERE/"decision-seal.json"),
        prereg=file_hash(HERE/"ADDENDUM_RU.md"),decisions=file_hash(HERE/"explicit-decisions.json.gz"),schema=schema))
    print("Sealed explicit suggestions",len(decisions),{k:len(v) if isinstance(v,list) else v for k,v in schema.items()})

def grade(verify):
    seal=read_file(HERE/"explicit-seal.json")
    assert seal["decisions"]==file_hash(HERE/"explicit-decisions.json.gz") and seal["prereg"]==file_hash(HERE/"ADDENDUM_RU.md")
    assert seal["code"]==file_hash(HERE/"suggestions.py") and seal["original_seal"]==file_hash(HERE/"decision-seal.json")
    dec=read_file(HERE/"explicit-decisions.json.gz");labels=read_file(HERE/"labels.json.gz")
    out=analyze(dec,labels)
    out["unavailable_first"]=sum(d["missing_first"] for d in dec.values())
    out["gold_in_some_proposal"]=sum(bool(set(d["new_suggestions"])&set(labels[q])) for q,d in dec.items())
    out["first_valid_correct"]=sum(bool(d["new_suggestions"]) and d["new_suggestions"][0] in labels[q] for q,d in dec.items())
    if verify:assert read_file(HERE/"explicit-results.json")==out
    else:save("explicit-results.json",out)
    print("Explicit",out["n"],out["proposed"],out["valid"],out["changed"],out["paired"]["memory-fusion"])

if __name__=="__main__":
    cli=argparse.ArgumentParser();cli.add_argument("operation",choices=["decide","grade","verify"])
    cli.add_argument("--cache",default=DEFAULT_CACHE,type=type(DEFAULT_CACHE))
    a=cli.parse_args()
    if a.operation=="decide":propose(a.cache)
    else:grade(a.operation=="verify")
