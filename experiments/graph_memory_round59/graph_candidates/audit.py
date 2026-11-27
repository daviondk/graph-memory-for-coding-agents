"""Offline token audit and post-outcome diagnostics of the fixed candidate ranker."""
from collections import Counter
import csv
import hashlib
import math
import struct
from select_slates import HERE,FIRST,OLD,get,lex,put,sha,tokens


def main():
    seal=get(HERE/"selection-seal.json")
    assert sha(HERE/"PROTOCOL_RU.md")==seal["protocol"] and sha(HERE/"select_slates.py")==seal["source"]
    assert all(sha(HERE/n)==h for n,h in seal["hashes"].items())
    assert all(sha(HERE/n)==h for n,h in get(HERE/"prompt-seal.json")["hashes"].items())
    assert all(sha(HERE/n)==h for n,h in get(HERE/"answer-seal.json").items())
    ans=get(HERE/"answers.json.gz");inp=get(HERE/"inputs.json.gz");maps=get(HERE/"assignments.json.gz")
    assert set(ans)==set(inp)
    assert all(hashlib.sha256(struct.pack(f"<{len(seq)}I",*seq)).hexdigest()==h for h,seq in inp.items())
    sc=get(HERE/"scored.json.gz");roster=get(HERE/"roster.json.gz");short=get(HERE/"decisions.json.gz")
    graphs={**get(FIRST/"graph.json.gz"),**get(HERE/"new-graphs.json.gz")}
    for g in graphs.values():
        edges=g["edges"]
        ends=[b for a,b in edges]
        rotated=[(a,ends[(j+1)%len(ends)]) for j,(a,b) in enumerate(edges)]
        assert Counter(a for a,b in edges)==Counter(a for a,b in rotated)
        assert Counter(b for a,b in edges)==Counter(b for a,b in rotated)
    original=OLD/"evaluation_library.csv"
    if original.is_file():
        assert sha(original)==get(FIRST/"graph-seal.json")["library"]
        raw={r["trace_key"]:r["instance_id"] for r in csv.DictReader(original.open(encoding="utf8"))}
        lib={k:raw[k] for k in graphs}
        if (HERE/"library-projection.json.gz").is_file():
            assert lib==get(HERE/"library-projection.json.gz")
        else:
            put("library-projection.json.gz",lib)
    else:
        lib=get(HERE/"library-projection.json.gz")
    assert set(lib)==set(graphs)
    bags={k:lex(v) for k,v in graphs.items()}
    df=Counter(w for _,_,terms in bags.values() for w in terms)
    weights={w:1+math.log((len(bags)+1)/(v+1)) for w,v in df.items() if v<=max(2,len(bags)//5)}
    study={};detailed={}
    for num,r in sc.items():
        assert all(len(set(v))==5 for v in r["slates"].values())
        for arm,row in maps[num].items():
            h=row["hash"];assert set(row["order"])==set(r["slates"][arm])
            s=ans[h]["text"].strip()
            picked=row["order"][int(s)-1] if s in ("1","2","3","4","5") else r["slates"][arm][0]
            assert picked==r["choices"][arm]
        assert len({len(inp[row["hash"]]) for row in maps[num].values()})==1
        overlap=tokens(roster["tasks"][num]["query"])&weights.keys()
        gold=set(r["gold"]);head=r["slates"]["fusion"][:4];fifth=r["slates"]["fusion"][4]
        eligible={};changing=0
        for k,(left,right,words) in bags.items():
            if k in head or len(overlap&words)<2:continue
            flat=sum(weights[t] for t in sorted(overlap&words))
            edges=graphs[k]["edges"]
            for i,arm in enumerate(("true","rotation")):
                boost=0
                for j,(a,_) in enumerate(edges):
                    b=edges[(j+i)%len(edges)][1]
                    allowed=[min(weights[x],weights[y]) for x in left[a-1]&overlap for y in right[b-1]&overlap if x!=y]
                    boost=max([boost]+allowed)
                eligible.setdefault(k,{"vertex":flat})[arm]=flat+boost
            changing+=eligible[k]["true"]!=eligible[k]["rotation"]
        ranks={}
        for arm in ("vertex","true","rotation"):
            order=sorted(eligible,key=lambda k:(-eligible[k][arm],k!=fifth,k))
            assert [k for k,_ in short[num][arm]["first_ten"]]==order[:10]
            ranks[arm]=next((i for i,k in enumerate(order,1) if lib[k] in gold),None)
        detailed[num]=dict(id=r["id"],common_four=r["covered_by_common_four"],old_fifth=r["outcome"]["fusion"]["hit5"],
                           any_searchable_gold=any(lib[k] in gold for k in graphs),rank_after_four=ranks,
                           score_changed_true_vs_rotation=changing)
    hard=[v for v in detailed.values() if not v["common_four"]]
    study=dict(questions=len(sc),hard=len(hard),hard_with_searchable_trajectory=sum(v["any_searchable_gold"] for v in hard),
               hard_with_eligible_trajectory=sum(v["rank_after_four"]["true"] is not None for v in hard),
               hard_with_gold_in_top10=sum((v["rank_after_four"]["true"] or 10**8)<=10 for v in hard),
               questions_changing_any_candidate_score=sum(v["score_changed_true_vs_rotation"]>0 for v in detailed.values()),
               records=detailed)
    put("audit.json",study)
    print({k:v for k,v in study.items() if k!="records"})

if __name__=="__main__":main()
