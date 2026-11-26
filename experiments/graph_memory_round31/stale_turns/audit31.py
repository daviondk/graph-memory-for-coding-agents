"""Rerun ordinary-address ranking without access to other questions or gold addresses, and directly replay all source receipts."""
from base31 import D,P,Path,h,sha,save,read,data,DATA
from predict31 import run_case,METHODS,QWT,Tokenizer,E5,e5_session,END
import collections
def main():
    sig=read(D/"forecast-seal.json");qs=data();a=read(D/"access.json.gz");f=read(D/"forecast.json.gz");tok=Tokenizer.from_file(str(QWT))
    et=Tokenizer.from_file(str(E5/"tokenizer.json"));engine=e5_session();by=collections.defaultdict(list)
    for c,qv in qs.items():
        for q in qv:
            for k in set(a[q].values()):by[c].append(k)
    # Eight different test scenarios; one isolated question per case; the synthetic diagnostic pair is deliberately unrelated.
    split=read(D/"case-split.json");ids=sorted((c for c,s in split.items() if s=="test"),key=lambda c:h("r31-blind-audit/"+c))[:8]
    isolated={}
    for c in ids:
        hist=read(DATA/"history"/(c+".json.gz"))["sources"];q=min(qs[c],key=lambda k:h("r31-isolated-question/"+k));others=[s["id"] for s in hist][11:13]
        pred=run_case(c,{q:qs[c][q]},hist,{q:others},tok,et,engine);orig=a[q]["actual"];fresh=pred["access"][q]["actual"]
        assert orig==fresh and pred["out"][fresh]==f[orig]
        isolated[c]={"question":q,"pair":fresh,"n_methods":len(pred["out"][fresh])}
    pos=read(D/"position-forecast.json.gz");assert sha(D/"position-forecast.json.gz")==read(D/"position-seal.json")["output"]
    for k,vv in pos.items():f[k].update(vv)
    costs=collections.Counter();sums=collections.Counter();checked=0;unique=0;seen=set()
    for c in sorted(qs):
        hist=read(DATA/"history"/(c+".json.gz"))["sources"]
        texts={s["id"]:(s["time"],"\n".join(v["text"] for v in s["turns"] if v["role"].lower()=="user" and v["text"])) for s in hist}
        for k in sorted(set(by[c])):
            groups=f[k];length=[]
            for mn,frames in groups.items():
                strings=[]
                for z in frames:
                    sid=z["source"];ts,alltext=texts[sid];body=alltext[z["start"]:z["end"]];st="["+ts+" "+sid+"]\n"+body+END
                    key=(sid,z["start"],z["end"])
                    if key not in seen:
                        assert h(st)==z["frame_hash"] and len(st.encode())==z["utf8_bytes"] and len(tok.encode(st,add_special_tokens=False).ids)==z["native"]
                        seen.add(key)
                    strings.append(st)
                actual=len(tok.encode("".join(strings),add_special_tokens=False).ids);assert actual==sum(z["native"] for z in frames)
                length.append(actual);checked+=1
            assert len(set(length))==1;costs[str(length[0])]+=1
    save(D/"blind-audit.json",dict(forecast=sha(D/"forecast-seal.json"),code=sha(Path(__file__)),isolated_checks=isolated,
           all_qwen_pair_receipts=checked,unique_frames=len(seen),pair_token_hist=costs,n_questions=len(a)))
if __name__=="__main__":main()
