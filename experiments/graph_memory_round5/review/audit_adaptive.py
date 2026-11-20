"""Validate both stages of adaptive reads with the original gold, only after final C is sealed."""
from collections import Counter
import datetime
import gzip
import json
from pathlib import Path

from audit_reader import HERE, READER, SOURCE, check, check_files, digest, exact_discordants, idf1, overlap, read, read_responses, similarity_float, source_rows


def main():
    check((READER / "C_decisions.json").is_file(), "final C not sealed")
    groups = {}
    for k in ("A","B","C0","C"):
        groups[k] = read(READER / f"{k}_packets.json.gz")
        lock = read(READER / f"{k}_data_lock.json")
        check_files(READER,lock["sha"])
        check(dict(Counter(x["panel"] for x in groups[k])) == lock["strata"], "strata")
        check(len({x["id"] for x in groups[k]}) == len(groups[k]) == len({x["repo"] for x in groups[k]}), "unique cases")
    check_files(SOURCE / "archive_inputs", read(READER / "A_data_lock.json")["source"])
    sets = {k:{p["repo"] for p in v} for k,v in groups.items()}
    check(sets["C0"] == sets["C"] and sets["C"].isdisjoint(sets["A"] | sets["B"]), "project split")
    plans0,responses0 = read_responses("C0")
    plans,responses = read_responses("C")
    check(set(plans0) == set(plans), "adaptive panel ids")
    cases0 = {p["id"]:p for p in groups["C0"]}
    check(set(cases0) == set(plans0), "draft assignment")
    labels = source_rows(groups["C"])
    rows = []
    for case in groups["C"]:
        k = case["id"]; ref = labels[k]["next_line"].strip(); meta = labels[k]["gold_snippet_index"]
        draft = cases0[k]
        for field in ("rank","repo","ctx","id","file","local_index"):
            check(draft[field]==case[field],f"adaptive identity [{field}]")
        check(case["draft_sha"] == plans0[k]["empty"], "draft-to-case assignment")
        arms = {}
        for arm in ("empty","head","static_focus","draft_lex","verified"):
            use_draft = arm not in {"empty","head"}
            plan,out,packet = (plans0,responses0,draft) if arm=="empty" else (plans,responses,case)
            actual, answer, tokens, finish, _, out_tokens = out[plan[k][arm]]
            snip, sniplen = packet["snippets"][arm]
            check(actual=="External Java fragment:\n"+snip+"\n\nLast lines of current file:\n"+case["ctx"]+"\n\nNext source line:","rebuild stimulus")
            check(0<=sniplen<=256,"external token ceiling")
            earlier = responses0[plans0[k]["empty"]]
            correct_addr = None if arm=="empty" else meta==case["addresses"][arm]
            arms[arm]={"em":answer==ref,"es":round(similarity_float(answer,ref)),"id_f1":idf1(answer,ref),"address_hit":correct_addr,
                       "final_input":tokens,"total_input":tokens+int(use_draft)*earlier[2],"total_output":out_tokens+int(use_draft)*earlier[5],
                       "external":overlap(snip,ref),"cid":plan[k][arm],"finish":finish}
        rows.append({"id":k,"arms":arms,"reason":case["reason"],"address_changed":case["addresses"]["draft_lex"]!=case["addresses"]["verified"]})
    summary={}
    for a in rows[0]["arms"]:
        vs=[r["arms"][a] for r in rows]
        summary[a]={"em_count":sum(v["em"] for v in vs),"address_hits":sum(v["address_hit"] for v in vs) if a!="empty" else None,
                    **{f:sum(v[f] for v in vs)/len(vs) for f in ("es","id_f1","final_input","total_input","total_output")}}
    w=sum(r["arms"]["verified"]["em"]>r["arms"]["draft_lex"]["em"] for r in rows)
    l=sum(r["arms"]["verified"]["em"]<r["arms"]["draft_lex"]["em"] for r in rows)
    per = HERE/"C_audit_items.json.gz"
    per.write_bytes(gzip.compress(json.dumps(rows,ensure_ascii=True,separators=(",",":")).encode(),mtime=0))
    result={"n":len(rows),"a_b_overlap_with_c":0,"outcome_sha":digest(per),"script_sha":digest(Path(__file__)),
            "utc":datetime.datetime.now(datetime.UTC).isoformat(),"calls_C0":len(responses0),"calls_C":len(responses),
            "reasons":dict(Counter(r["reason"] for r in rows)),"methods":summary,"verified_vs_draft_lex":{"wins":w,"losses":l,"exact_p":exact_discordants(w,l),
            "different_address":sum(r["address_changed"] for r in rows),"different_request":sum(r["arms"]["verified"]["cid"]!=r["arms"]["draft_lex"]["cid"] for r in rows)}}
    (HERE/"C_audit.json").write_text(json.dumps(result,indent=1),encoding="utf8")
    print(result)
if __name__=="__main__":
    main()
