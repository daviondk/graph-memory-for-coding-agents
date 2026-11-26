from paths_href import *
def main():
    check();signed=get(H/"handoff.json")["subsets"];all_={}
    for split,meta in signed.items():
        hand=get(H/meta["file"]);file=H/f"forecast-{split}.json.gz";cl=H/f"clip-{split}.json.gz"
        assert sha(file)==meta["frozen_numeric_rows"] and sha(cl)==meta["visible_clip"]
        src=get(file);clip=get(cl);old=get(PRIOR[split]/"orders.json.gz")
        assert set(src)==set(clip)==set(hand)==set(old) and len(hand)==meta["rows"]
        for q,v in hand.items():
            assert q not in all_;r=src[q];order=r["sort"];text=set(r["text_edges"]);good,href,chosen=clip[q]
            pick=lambda edges:next((j for j in order if j in edges),order[0])
            assert pick(set(href))==v["href"]==chosen and pick(text)==v["text"]==old[q]["true"]
            assert pick(text|set(href))==v["union"] and v["lex"]==order[0] and v["seed"]==old[q]["seed"]
            all_[q]=dict(split=split,seed=v["seed"],true=v["text"],href=v["href"],union=v["union"],order=order,
                         href_edges=href,text_edges=sorted(text),verified_visible=good)
    put(D/"orders.json.gz",all_);put(D/"retrieval-seal.json",dict(orders=sha(D/"orders.json.gz"),code=sha(Path(__file__)),
        registration=sha(D/"registration.json"),dev=signed["dev"]["sha256"],train=signed["train"]["sha256"]))
if __name__=="__main__":main()
