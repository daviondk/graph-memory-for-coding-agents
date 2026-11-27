"""Offline check of sealed inputs, greedy deduplication and counts in the report."""
import hashlib
import struct
from solve import ARMS, HERE, OLD, common, read, study
from evaluate import LABELS, summary


def main():
    selection=read("selection.json.gz")
    old=study.read("selections.json.gz")
    assert not (set(selection) & set(old))
    reg=read("selection-seal.json")
    assert reg["protocol"] == common.sha(HERE/"PROTOCOL_RU.md")
    assert reg["selected_sha"] == common.sha(HERE/"selection.json.gz")
    assert all(common.sha(OLD/n)==h for n,h in reg["prior"].items())
    assert all(common.sha(HERE/n)==v for n,v in read("generation-seal.json")["hashes"].items())
    assert all(common.sha(HERE/n)==v for n,v in read("answer-seal.json").items())
    inp=read("inputs.json.gz");ans=read("answers.json.gz");assign=read("assignments.json.gz")
    assert set(inp)==set(ans)
    assert all(hashlib.sha256(struct.pack(f"<{len(ids)}I",*ids)).hexdigest()==h for h,ids in inp.items())
    for q,c in assign.items():
        arms=c["arms"];index=next((i for i,v in enumerate(c["status"]) if v=="FAIL"),0)
        assert arms["adaptive"]["index"] == index == arms["masked"]["index"]
        assert arms["static"]["index"]==0 and arms["review"]["index"] is None
        assert arms["adaptive"]["hash"]==arms["static"]["hash"] if index==0 else arms["adaptive"]["hash"]!=arms["static"]["hash"]
        assert len({len(inp[v["hash"]]) for v in arms.values()})==1
    rows=read("records.json.gz");results=read("results.json")
    assert set(selection)==set(assign)==set(rows)
    assert results["arms"]==summary(list(rows.values()))
    for a in LABELS:
        assert all(v[a]["good"]<=v[a]["total"] and v[a]["total"]>=2 for v in rows.values())
    p=results["paired"]["adaptive_vs_static"]
    assert p["wins"]+p["losses"]+p["ties"]==len(rows)
    assert len(inp)==sum(v["unique"] for v in results["computed_cost"].values())
    print("Verified",len(inp),"distinct input/answer pairs,",len(rows),"calibrated tasks,",len(old),"disjoint previous targets")


if __name__=="__main__":
    main()
