from inspect_shapes import *
from collections import Counter
from hashlib import sha256
def main():
    hal=json.loads((P/"halumem-medium.jsonl").open(encoding="utf8").readline())
    mp=next(x for s in hal["sessions"] for x in s["memory_points"] if x["original_memories"]);qu=next(x for s in hal["sessions"] for x in s["questions"] if x["evidence"])
    print("Halu origin",schema(mp["original_memories"],3),"is_update",Counter(x["is_update"] for s in hal["sessions"] for x in s["memory_points"]),"question evidence",schema(qu["evidence"],3))
    for a in [mp["original_memories"][0],qu["evidence"][0]]:print("join token",list(a) if isinstance(a,dict) else str(a)[:120])
    case=json.loads((P/"stale.json").read_bytes())
    for s in case[:2]:
        print("STALE redacted",s["uid"][:30],s["type"],s["relevant_session_index"],s["timestamps"][0],s["M_old"][:160],s["M_new"][:160],s["probing_queries"]["dim1_query"][:100])
    print("types",Counter(x["type"] for x in case));print("n session",Counter(len(r['haystack_session']) for r in case))
    data=pq.read_table(P/"fact.parquet").to_pylist();r=data[4]
    print("MAB head",repr(r["context"][:340]),"q",r["questions"][0][:150],"example-id",r["metadata"]["qa_pair_ids"][0],"answer",r["answers"][0])
    m=json.loads(LM.read_bytes());up=[r for r in m if r["question_type"]=="knowledge-update"];print("updates",len(up),sum(r["question_id"].endswith('_abs') for r in up))
    sample=next(r for r in up if not r["question_id"].endswith('_abs'))
    print("sample",sample["question_id"],sample["answer_session_ids"],sample["question"][:140],sample["answer"][:85],[(i,s[:35],sample["haystack_dates"][i],sum(t.get('has_answer',False) for t in sample["haystack_sessions"][i])) for i,s in enumerate(sample["haystack_session_ids"]) if s in sample["answer_session_ids"]])
if __name__=="__main__":main()

