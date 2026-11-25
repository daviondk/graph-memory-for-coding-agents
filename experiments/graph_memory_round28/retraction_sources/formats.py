"""Full official public schema audit; no model inference. Keep raw user histories in a local cache."""
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
import json,gzip,re
import pyarrow.parquet as pq
from inspect_shapes import P,LM
D=Path(__file__).resolve().parent
def hashed(s):return sha256(s.encode()).hexdigest()
def sha(p):return sha256(p.read_bytes()).hexdigest()
def write(p,o):
    b=(json.dumps(o,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    p.write_bytes(gzip.compress(b,mtime=0) if p.suffix==".gz" else b);return sha(p)
def norm(text):return " ".join(text.casefold().split())
PINS={LM:"d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442",P/"fact.parquet":"24d5c3f09ce0ce15625cb9f8a98f44f0d864ca6c94d7b4ad04eb697ca3a5ff45",P/"stale.json":"5f3ec375179e20e2e94469e018189188f34e2e7e5f21cbecbd99fcfa648c1876",P/"halumem-medium.jsonl":"486fbc130a5c8781a2af27ffa508a1d7855245137aa449c193ac4d29c45634e7"}
def halumem():
    counts=Counter();typ=Counter();msource=Counter();qmode=defaultdict(Counter);ex=None
    for line in (P/"halumem-medium.jsonl").open(encoding="utf8"):
        user=json.loads(line);counts["users"]+=1;hist=defaultdict(list);allidx=[]
        for si,s in enumerate(user["sessions"]):
            counts["sessions"]+=1;counts["turns"]+=len(s["dialogue"]);points=s["memory_points"];keys=[norm(m["memory_content"]) for m in points]
            for mi,m in enumerate(points):
                counts["points"]+=1;allidx.append(m["index"]);msource[m["memory_source"][:70]]+=1
                if str(m["is_update"]).casefold()=="true":counts["update_points"]+=1
                if m["original_memories"]:counts["with_prior_text"]+=1
                for prior in m["original_memories"]:
                    assert isinstance(prior,str)
                    k=norm(prior);counts["prior_refs"]+=1
                    if k in hist:counts["prior_resolved_earlier_session"]+=1
                    elif k in keys[:mi]:counts["prior_only_same_session_preceding"]+=1
                    else:counts["prior_without_normalized_prior_points"]+=1
                    if k in hist and len(hist[k])>1:counts["prior_ambiguous_prior"]+=1
                    if ex is None and k in hist:ex={"user":user["uuid"],"current_session":si,"current_point":mi,"prior_addresses":hist[k][:3],"current_record_keys":sorted(m),"original_type":"str"}
            for mi,k in enumerate(keys):hist[k].append([si,mi])
            if "questions" not in s:counts["sessions_without_questions_key"]+=1
            for q in s.get("questions",[]):
                ty=q["question_type"];typ[ty]+=1;counts["questions"]+=1
                qmode[ty]["questions"]+=1
                if q["evidence"]:qmode[ty]["has_evidence"]+=1
                for e in q["evidence"]:
                    k=norm(e["memory_content"]);qmode[ty]["references"]+=1
                    if k in hist:qmode[ty]["resolved_to_point_by_text_at_query"]+=1
                    if len(hist.get(k,()))>1:qmode[ty]["ambiguous_text_join"]+=1
        counts["users_unique_index"]+=len(allidx)==len(set(allidx))
    return dict(counts=counts,question_types=typ,evidence_by_type=qmode,example_structural=ex,showing_raw_prior_text=False)
def longmem():
    data=json.loads(LM.read_bytes());counts=Counter();eqlens=Counter();example=None
    for r in data:
        if r["question_type"]!="knowledge-update":continue
        counts["questions"]+=1;absent=r["question_id"].endswith("_abs")
        counts["abstention_suffix"]+=absent
        hs,ds,ss=r["haystack_session_ids"],r["haystack_dates"],r["haystack_sessions"]
        ev=r["answer_session_ids"];assert len(hs)==len(ss)==len(ds);eqlens[len(ev)]+=1
        counts["contains_answer_prefixed_source_ids"]+=any(str(i).startswith("answer_") for i in hs)
        counts["dates_nondecreasing"]+=ds==sorted(ds)
        counts["all_references_present"]+=all(i in hs for i in ev)
        counts["all_refs_have_turn_marker"]+=bool(ev) and all(any(t.get("has_answer") is True for t in ss[hs.index(i)]) for i in ev)
        counts["with_answer_prefixed_negative"]+=any(i.startswith("answer_") and i not in ev for i in hs)
        counts["latest_reference_after_question"]+=any(ds[hs.index(i)]>r["question_date"] for i in ev if i in hs)
        if not absent and example is None:example={"id":r["question_id"],"source_ids":ev,"positions":[hs.index(i) for i in ev],"canonical_answer_nonempty":bool(r["answer"]),"reference_types":sorted(next(iter(ss))[0]),"old_new_role_fields":[]}
    return dict(total=len(data),counts=counts,target_ref_counts=eqlens,example_structural=example)
def fact():
    ds=pq.read_table(P/"fact.parquet").to_pylist();rows=[];distinct={}
    for r in ds:
        c=r["context"];pairs=re.findall(r"(?m)^(\d+)\.\s+(.+)$",c)
        ids=[int(x[0]) for x in pairs];name=r["metadata"]["source"];h=hashed(c);distinct.setdefault(h,[]).append(name)
        assert len(r["questions"])==len(r["answers"])==len(r["metadata"]["qa_pair_ids"])
        rows.append(dict(name=name,questions=len(r["questions"]),numbered_statements=len(ids),contiguous_from_zero=ids==list(range(len(ids))),session_dates=r["metadata"]["question_dates"],q_references="no relation columns",source_index=h))
    return dict(rows=rows,shared_context_groups=list(distinct.values()),num_contexts=len(distinct),example_case_id=ds[4]["metadata"]["qa_pair_ids"][0])
def stale():
    rows=json.loads((P/"stale.json").read_bytes());cnt=Counter();props=defaultdict(Counter);uids=set();old_counts=Counter();qns=Counter();example=None
    for r in rows:
        uid=r["uid"];assert uid not in uids;uids.add(uid)
        ss=r["haystack_session"];ts=r["timestamps"];a,b=r["relevant_session_index"];p=props[r["type"]]
        assert len(ss)==len(ts) and 0<=a<b<len(ss);cnt["stories"]+=1;p["stories"]+=1;cnt["queries"]+=len(r["probing_queries"]);assert set(r["probing_queries"])=={"dim1_query","dim2_query","dim3_query"}
        cnt["timestamps_nondecreasing"]+=ts==sorted(ts);cnt["relevant_times_in_order"]+=ts[a]<=ts[b];cnt["events"]+=len(ss);cnt["turns"]+=sum(map(len,ss));old_counts[norm(r["M_old"])]+=1
        for i,key in ((a,"M_old"),(b,"M_new")):
            h=norm(r[key]);matches=[j for j,t in enumerate(ss[i]) if h and h in norm(t["content"])];p[key+"_substring_in_expected_session"]+=bool(matches)
            if len(matches)>1:p[key+"_multi_turn_match"]+=1
        for v in r["probing_queries"].values():qns[norm(v)]+=1
        if example is None:example={"uid":uid,"session_indices":[a,b],"input_sessions":len(ss),"source_role_fields":sorted(ss[0][0]),"question_count":3,"explicit_old_new_fields":True}
    return dict(counts=cnt,by_type=props,repeated_old_fact_exact_groups=sum(x>1 for x in old_counts.values()),unique_query_strings=len(qns),example_structural=example)
def rollback():
    files=sorted(P.glob("rollback-*.jsonl"))
    res={}
    for path in files:
        if path.stat().st_size<100:continue
        rows=[json.loads(s) for s in path.open(encoding="utf8") if s.strip()]
        r=rows[0];res[path.name]=dict(n=len(rows),keys=sorted(r),example_id=r.get("task_id"),supersedes_nonempty=sum(bool(x.get("supersedes")) for x in rows),derived_from_nonempty=sum(bool(x.get("derived_from")) for x in rows),sha=sha(path))
        if "memory_ground_truth" in r:res[path.name]["gold_fields"]=list(r["memory_ground_truth"])[:24]
    return res
if __name__=="__main__":
    for p,s in PINS.items():assert sha(p)==s,p
    readout={"halumem_medium":halumem(),"longmemeval_s":longmem(),"factconsolidation":fact(),"stale":stale(),"rollback_customer_support":rollback()}
    write(D/"formats.json",readout)
    print(json.dumps({k:(x.get("counts") or x.get("num_contexts") or len(x)) for k,x in readout.items()}))
