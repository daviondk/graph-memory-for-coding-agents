"""Recompute content/coverage counts from complete, real rendered responses using only standard Python."""
import argparse
import gzip
import json
import statistics
from collections import Counter
from pathlib import Path

from certificate import canonical,digest,exhaustive
from synthetic import fixture,POSITIVE,NEGATIVE

D=Path(__file__).resolve().parent
MODES=("native_only","derived_bound","certified","asserted_certified","unchecked")


def read(name):
    p=D/name;r=p.read_bytes()
    return json.loads(gzip.decompress(r) if p.suffix==".gz" else r)


def decode(raw):
    lines=raw.splitlines();assert any("UNTRUSTED_RECOVERED_DATA" in x for x in lines[:2])
    return json.loads("\n".join(lines[2:-1]))


def unit(raw,rev):
    doc=decode(raw);matches=[f for f in doc.get("restored_code_changes",[]) if
        f.get("key",{}).get("semantic_role")=="read_block" and f["key"]["canonical_entity_id"]=="file:sample" and
        f["key"]["revision_constraint"]=="revision:"+rev]
    assert len(matches)<=1
    return (matches[0] if matches else None),doc


def grade():
    data=read("native-output.json.gz");raw=read("rendered-blocks.json.gz");run=read("run.json")
    for group in ("program","outputs"):
        for path,sha in run[group].items():assert digest((D/path).read_bytes())==sha,path
    assert run["lemma"]==exhaustive()
    assert set(data)==set(raw) and len(raw)==150
    assert len(POSITIVE)==5 and len(NEGATIVE)==10
    rows={};summary={};cost={}
    for mode in MODES:
        tally=Counter();pages=[];tokens=[];seconds=[]
        for name in sorted(POSITIVE+NEGATIVE):
            for size in (48,128):
                key=f"{name}/{size}/{mode}";r=data[key];b=raw[key];fc=fixture(name,size)
                initial,_=unit(b[0],"old")
                assert initial["content"]["body"]==fc["observed"].decode()
                assert initial["content"]["read_receipt"]==fc["read"]
                tally["trials"]+=1;seconds.append(r["elapsed_s"])
                if "rejected" in r:
                    assert mode=="derived_bound" and name in POSITIVE and len(b)==1 and r["new_sql_units"]==0
                    tally["rejected_publication"]+=1
                    rows[key]={"verdict":"sql_rejected","error":r["rejected"]}
                    continue
                assert len(b)==3
                rec,doc=unit(b[1],"new");reopened,restored=unit(b[2],"new")
                assert (rec or {}).get("content")==r["result"]["record"]==r["reopened"]["record"]==(reopened or {}).get("content")
                assert digest(b[1].encode())==r["result"]["rendered_sha256"] and digest(b[2].encode())==r["reopened"]["rendered_sha256"]
                assert (r["result"]["state"]=="COMPLETE")==bool(rec) and r["reopened"]["state"]==r["result"]["state"]
                tally["durable_replays"]+=1
                ok=False;coords=None
                if rec:
                    assert doc["temporal_semantics"]["source_revision_state"]=="CURRENT"
                    tally["complete"]+=1
                    result=rec["content"];ok=result["body"].encode()==fc["oracle_bytes"]
                    tally["byte_match"]+=int(ok);tally["byte_mismatch"]+=int(not ok)
                    tally["unsupported_accept"]+=int(name in NEGATIVE)
                    tally["accepted_positive"]+=int(name in POSITIVE)
                    if mode in ("certified","asserted_certified"):
                        coords=(result["lo"],result["hi"])
                        assert coords==(fc["oracle_start"],fc["oracle_start"]+size)
                        assert result["for_root"]==fc["target"][2] and result["digest"]==digest(fc["oracle_bytes"])
                        assert (result["source_event"],result["edit_event"])==("source-observation","edit")
                        assert result["prior_receipt"]==digest(canonical(fc["read"])) and result["edit_receipt"]==digest(canonical(fc["edit"]))
                        assert rec["authority"]==("ASSERTED" if mode=="asserted_certified" else "DERIVED")
                        assert r["result"]["record"]==r["reopened"]["record"]
                        tally["certificate_verified_in_returned_body"]+=1
                else:
                    tally["empty"]+=1;tally["refused_negative"]+=int(name in NEGATIVE)
                pages.append(r["result"]["page_bytes"]);tokens.append(r["result"]["recovered_tokens"])
                rows[key]={"verdict":r["result"]["state"],"byte_match":ok if rec else None,
                           "coordinates":list(coords) if coords else None,"reason":r["cert_decision"]}
        summary[mode]=dict(tally)
        cost[mode]=dict(median_page_bytes=statistics.median(pages),median_recovered_tokens=statistics.median(tokens),
                        median_s=statistics.median(seconds))
    assert summary["certified"]["complete"]==summary["asserted_certified"]["complete"]==10
    for mode in ("certified","asserted_certified"):
        assert summary[mode]["byte_mismatch"]==summary[mode]["unsupported_accept"]==0
        assert summary[mode]["refused_negative"]==20 and summary[mode]["certificate_verified_in_returned_body"]==10
    assert summary["native_only"]["empty"]==30 and summary["derived_bound"]["rejected_publication"]==10
    assert summary["unchecked"]["complete"]==30 and summary["unchecked"]["unsupported_accept"]==20
    return dict(summary=summary,cost=cost,conditions=rows,requests=run["requests"],lemma=run["lemma"])


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--write",action="store_true");args=parser.parse_args()
    result=grade()
    if args.write:(D/"results.json").write_bytes(canonical(result)+b"\n")
    else:assert read("results.json")==result
    if (D/"manifest.json").exists():
        for fn,sha in read("manifest.json")["files"].items():assert digest((D/fn).read_bytes())==sha
    print("Verified",result["requests"],"real RecallService calls;",result["lemma"])
    print({k: [v.get("complete",0),v.get("refused_negative",0),v.get("byte_mismatch",0)] for k,v in result["summary"].items()})


if __name__=="__main__":main()

