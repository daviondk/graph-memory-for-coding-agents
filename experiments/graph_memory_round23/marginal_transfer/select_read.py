"""Apply the ISETrace read chooser to fixed MultiDoc2Dial memories before consulting labels."""
from collections import defaultdict
from pathlib import Path
import sqlite3
import sys
D=Path(__file__).resolve().parent
U=D.parent/"open_transfer";sys.path.insert(0,str(U))
from run import c,merged,paid_open
M=D.parent/"marginal_open";sys.path.insert(0,str(M))
from novelty import choose,lexical_order,make_windows

def main():
    assert c.checksum(M/"novelty.py")=="b2a4d6a4d87ef609e93f1f0625a2fbdfb732f0f28dc56c52c18de8d8f9e8bbdc"
    T=D.parent/"transfer";pred=T/"predictions.json.gz"
    assert c.checksum(pred)==c.read(T/"forecast-seal.json")["forecasts"]
    oldfile=U/"opens.json.gz";assert c.checksum(oldfile)==c.read(U/"open-lock.json")["opens"]
    controls={r["q"]:r for r in c.read(oldfile)}
    v=c.get_views();tok=c.tok();docs={i:r[2] for i,r in enumerate(v["documents"])}
    lengths={i:len(s) for i,s in docs.items()};texts={r[0]:r[2] for r in v["q"]}
    db=sqlite3.connect((c.CACHE/"source-lookup.sqlite").resolve().as_uri()+"?mode=ro&immutable=1",uri=True)
    out={}
    for row in c.read(pred):
        q=row["q"];arm=row["arms"]["two_ratio"];blocks=[v["blocks"][i] for i in arm["chosen"]]
        assert c.sha("\n".join(c.render(b,v["documents"]) for b in blocks).encode())==arm["text_sha"]
        parts=merged([(b["doc"],b["a"],b["b"]) for b in blocks])
        shown=defaultdict(list)
        for e,l,h in parts:shown[e].append((l,h))
        windows=make_windows([(e,l,docs[e][l:h]) for e,l,h in parts],tok)
        order=lexical_order(texts[q],windows)
        headers=[len(tok.encode(f"[{w.field}:{w.start}] ",add_special_tokens=False).ids) for w in windows]
        picks,geom=choose(windows,order,shown,lengths,headers)
        for name in ("first_positive","max_novelty","rank_novelty"):
            picks[name+"_forced"]=picks[name] if picks[name] is not None else picks["bm25"]
        actions={};cache={}
        for name,j in picks.items():
            if j is None:
                actions[name]=None
                continue
            if j not in cache:
                w=windows[j];e,l=w.field,w.start
                (source,)=db.execute("SELECT body FROM source WHERE d=?",(e,)).fetchone()
                result=paid_open(tok,source,e,l)
                assert result[3]<=256
                cache[j]=[j,result,geom[j]]
            actions[name]=cache[j]
        for a,old in (("first","anchor/first"),("bm25","lex/lex")):
            assert actions[a][1]==controls[q]["arms"]["merged/"+old][:4]
        assert q not in out
        out[q]={"base":parts,"actions":actions,"source_tokens":arm["tokens"]}
    db.close();assert len(out)==661
    forecasts=c.save(D/"actions.json.gz",out)
    c.save(D/"forecast-seal.json",{"predictions":forecasts,"plan":c.checksum(D/"PROTOCOL_RU.md"),"clarification":c.checksum(D/"OPERATOR_RU.md"),
             "shared":c.checksum(M/"novelty.py"),"script":c.checksum(Path(__file__)),"old_opens":c.checksum(oldfile),"memories":c.checksum(pred)})
if __name__=="__main__":main()
