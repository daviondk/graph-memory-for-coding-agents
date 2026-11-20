"""Visible-only census of alternative call/type-use witnesses at fixed top-1 address and candidate pool."""
from collections import Counter, defaultdict
from pathlib import Path
import datetime
import json
import re
import sys
import pyarrow.parquet as pq
from audit_reader import HERE, SOURCE, digest, load_inputs, read
from audit_ast import PARSER, rightmost_name, declaration_name, classify
sys.path.insert(0,str(SOURCE))
from memory import record


def uses(text, wanted):
    binary=text.encode(); tree=PARSER.parse(binary)
    work=[tree.root_node]; found={}
    while work:
        n=work.pop()
        name=None
        if n.type=="object_creation_expression":
            name=rightmost_name(n.child_by_field_name("type"))
        elif n.type=="method_invocation":
            direct=n.child_by_field_name("object")
            if direct is not None and direct.type=="identifier": name=direct
        if name is not None and name.text.decode()==wanted:
            role=classify(name,wanted,wanted)
            if role in {"method_direct_receiver","new_object_type"}:
                found[(name.start_point.row,role)] = True
        work.extend(n.named_children)
    return sorted(found)


def main():
    panels={s:load_inputs(s) for s in ("A","B")}
    old=read(HERE/"ast_roles.json")["records"]
    grouped=defaultdict(list)
    for s,rows in panels.items():
        for x in rows: grouped[x["file"]].append((s,x))
    out=defaultdict(dict)
    for f, group in grouped.items():
        needed={r["local_index"] for s,r in group}; texts={}; offset=0
        for batch in pq.ParquetFile(SOURCE/"archive_inputs"/f).iter_batches(columns=["context"],batch_size=64):
            for idx in needed:
                if offset<=idx<offset+len(batch): texts[idx]=batch.column(0)[idx-offset].as_py()
            offset+=len(batch)
        for s,r in group:
            candidates=texts[r["local_index"]]; rank=r["rank"]; target=candidates[rank[0]]
            key=record(target)["root"]; name,kind=declaration_name(target,key)
            prior=r["edge_event"]; originals = old[s].get(r["id"],{})
            assert prior is None or name==originals["target_spelling"]
            previous=originals.get("strong",False)
            found={}
            if kind=="type":
                valid=re.compile(r"(?<![A-Za-z0-9_$])"+re.escape(name)+r"(?![A-Za-z0-9_$])")
                for order, idx in enumerate(rank[1:],1):
                    text=candidates[idx]
                    if valid.search(text):
                        examples=uses(text,name)
                        if examples: found[idx]={"graph_rank":order+1,"uses":examples}
            previous_visible=prior is not None and prior["source"] in found and any(
                line==prior["line"] for line,role in found[prior["source"]]["uses"])
            assert previous==previous_visible
            out[s][r["id"]]={"had_lexical_edge":prior is not None,"previous_direct":previous,
                 "semantically_typed_target":kind=="type","candidate_count":len(candidates),"available":found,
                 "in_source_already_picked":bool(prior and prior["source"] in found)}
    summary={}
    for s,group in out.items():
        vals=list(group.values())
        summary[s]={"n":len(vals),"typed_targets":sum(z["semantically_typed_target"] for z in vals),
                    "rows_with_any_strong":sum(bool(z["available"]) for z in vals),"rows_selected_strong":sum(z["previous_direct"] for z in vals),
                    "additional_via_search":sum(bool(z["available"]) and not z["previous_direct"] for z in vals),
                    "additional_inside_already_chosen_source":sum(z["in_source_already_picked"] and not z["previous_direct"] for z in vals),
                    "additional_from_previously_no_lexical_edge":sum(bool(z["available"]) and not z["had_lexical_edge"] for z in vals),
                    "rows_with_any_strong_top4":sum(any(i["graph_rank"]<=4 for i in z["available"].values()) for z in vals),
                    "distinct_row_local_sources_with_strong":sum(len(z["available"]) for z in vals),"other_candidates_examined":sum(z["candidate_count"]-1 for z in vals)}
    doc={"summary":summary,"items":out,"utc":datetime.datetime.now(datetime.UTC).isoformat(),"script_sha256":digest(Path(__file__)),
         "protocol_sha256":digest(HERE/"WITNESS_SUPPLY_PROTOCOL_RU.md")}
    (HERE/"witness_supply.json").write_text(json.dumps(doc,indent=1),encoding="utf8")
    print(summary)
if __name__=="__main__":main()
