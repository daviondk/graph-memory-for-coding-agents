"""Freeze diagnostic candidate pools using only blind case histories and queries, preserving the batch shape used in the primary current-time panel."""
import sys
from retrieve29 import chunks,encode,choose,rank_all,Tokenizer,QWT,E5,e5_session,words
from setup29 import D,P,h,sha,read,save,Path
def predict():
    hist=read(P/"reader-histories.json.gz");qs=read(P/"reader-questions.json");qq=Tokenizer.from_file(str(QWT))
    et=Tokenizer.from_file(str(E5/"tokenizer.json"));mod=e5_session();out={};chosen=read(D/"effective-retrieval.json.gz")
    for c,hs in hist.items():
        qids=[q for q,d in qs.items() if d["case"]==c];subjects=sorted({qs[q]["query"] for q in qids})
        rows=chunks(hs,qq);bow=[words(r["chunk"]) for r in rows]
        vv=encode(["query: "+s for s in subjects]+["passage: "+r["chunk"] for r in rows],et,mod)
        for q in qids:
            s=qs[q]
            if s["asof"] is not None:continue
            args=(s["query"],bow,rows,vv[len(subjects):],vv[subjects.index(s["query"])],s["available_until"],None)
            ranking,bm=rank_all(*args);top=ranking[:8];starts={rows[i]["source"]:rows[i]["start"] for i in top}
            o=choose(s,rows,bow,vv[len(subjects):],vv[subjects.index(s["query"])])
            assert all({rows[i]["source"] for i in o[a]}=={v["source"] for v in chosen[q][a]} for a in ("H","G","T"))
            a=top[0];later=[i for i in top[1:] if rows[i]["seq"]>rows[a]["seq"]]
            out[q]={"candidate_order":[rows[i]["source"] for i in top],"origins":starts,"allowed_second_G":[rows[i]["source"] for i in later or top[1:]]}
    save(D/"current-candidates.json.gz",out);save(D/"candidate-seal.json",dict(inputs=sha(D/"input-seal.json"),
          code=sha(Path(__file__)),predictions=sha(D/"current-candidates.json.gz"),n=len(out),phase="exploratory; locked before answer/evidence scoring"))
def evaluate():
    cs=read(D/"current-candidates.json.gz");ky=read(P/"eval-keys.json.gz");rows=[]
    for q,p in cs.items():
        e=ky[q];old=e["old_source"];new=e["new_source"];ids=p["candidate_order"];second=p["allowed_second_G"];anchor=ids[0]
        target={old,new};both=set(ids).issuperset(target)
        z={"q":q,"mode":e["mode"],"case":e["case"],"old_in_pool":old in ids,"new_in_pool":new in ids,"both_in_pool":both,
           "anchor_old":anchor==old,"anchor_new":anchor==new,
           "both_possible_given_anchor":both and anchor in target,"both_possible_after_direction":any({anchor,s}==target for s in second),
           "new_possible_after_direction":anchor==new or new in second}
        rows.append(z)
    summary={k:sum(v[k] for v in rows) for k in rows[0] if k not in ("q","mode","case")}
    save(D/"candidate-score.json",dict(seal=sha(D/"candidate-seal.json"),summary=summary,rows=rows))
    print(summary)
if __name__=="__main__":(evaluate if sys.argv[1:]==["score"] else predict)()
