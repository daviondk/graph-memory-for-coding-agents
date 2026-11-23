"""Final read-only reconciliation of official grades with captured bytes and tests."""
import collections,gzip,hashlib,json,math
from pathlib import Path
D=Path(__file__).resolve().parent;T=D.parent
def read(p):return json.loads(p.read_bytes())
def h(b):return hashlib.sha256(b).hexdigest()
def main():
    idx=read(D/"index.json");env=read(D/"environment.json");cohort=read(T/"cohort.json")
    rows=[]
    for target in cohort["targets"]:
        i=target["instance_id"];m=idx[i];assert set(m)=={"gold","marker","official","fallback"}
        s=read(D/"selection"/(i+".json"));seed=T/"episodes/python"/i/"base/seed1"
        assert h((seed/"seal.json").read_bytes())==s["seed_seal"]
        for p,sig in read(seed/"seal.json").items():assert h((seed/p).read_bytes())==sig
        assert s["official_patch"]==m["official"] and s["fallback_patch"]==m["fallback"]
        c=s["capture"];tr=read(seed/(i+".traj.json"))
        results={};by_role={}
        for mode,sig in m.items():
            p=D/"grades"/i/sig
            g=read(p/"grade.json");blob=gzip.decompress((p/"patch.gz").read_bytes());assert len(blob)==g["bytes"] and h(blob)==sig
            for fname,sha in g["outputs"].items():assert h((p/fname).read_bytes())==sha
            compact={key:g[key] for key in ("sha","bytes","status","score","expected_f2p","expected_p2p","unit_exit","passed_match","unit_log","vendor_error")}
            compact["resolved"]=g["native"]["resolved"]
            results[mode]=compact;by_role[mode]=blob
        raw=tr["info"].get("submission") or ""
        assert by_role["official"]==raw.encode() or s["official_origin"]=="preds.json"
        candidate=(gzip.decompress((seed/"terminal.patch.gz").read_bytes()) if c["rc"]==0 else None)
        if candidate is not None:assert h(candidate)==s["terminal_patch"] and len(candidate)==c["bytes"]
        expected=by_role["official"] if by_role["official"].strip() else candidate or b""
        assert expected==by_role["fallback"]
        # Retained inputs and native reports make exact same-task byte dedup auditable.
        assert results["gold"]["resolved"] and not results["marker"]["resolved"]
        assert results["gold"]["score"]["f2p_passed"]==results["gold"]["expected_f2p"]
        assert results["marker"]["score"]["f2p_passed"]<results["marker"]["expected_f2p"]
        calls=sum(len(x.get("tool_calls") or []) for x in tr.get("messages",[]) if x.get("role")=="assistant")
        rows.append({"iid":i,"image":env["images"][i]["image"],"repo_digest":env["images"][i]["registry"],"base":target["base_commit"],
            "seed":s["seed"],"exit":s["exit_status"],"model_stats":tr["info"].get("model_stats"),"n_tool_calls":calls,"native_run_s":c["result"]["duration_s"],"capture_s":c["seconds"],"start_after_return_s":c["after_native_s"],
            "capture_rc":c["rc"],"cleanup_rc":s["cleanup"]["rc"],"capture_stderr":c["stderr"],"native_bytes":len(by_role["official"]),"captured_bytes":None if candidate is None else len(candidate),
            "terminal_equals_official":None if candidate is None else candidate==by_role["official"],"policy_equal":by_role["official"]==by_role["fallback"],"fallback_reason":s["fallback_policy"],"outcomes":results})
    wins=sum(v["outcomes"]["fallback"]["resolved"] and not v["outcomes"]["official"]["resolved"] for v in rows)
    losses=sum(v["outcomes"]["official"]["resolved"] and not v["outcomes"]["fallback"]["resolved"] for v in rows)
    out={"episodes":rows,"paired":{"n":len(rows),"base":sum(r["outcomes"]["official"]["resolved"] for r in rows),"fallback":sum(r["outcomes"]["fallback"]["resolved"] for r in rows),"wins":wins,"losses":losses,"ties":len(rows)-wins-losses},
         "unique_fresh_evaluations":len(list((D/"grades").rglob("grade.json"))),"zero_grade_reuse_from_prior_project_runs":True}
    (D/"results.json").write_text(json.dumps(out,indent=1,ensure_ascii=False)+"\n",encoding="utf8")
    print(out["paired"],out["unique_fresh_evaluations"])
if __name__=="__main__":main()
