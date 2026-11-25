"""Diagnose the loss of tokenizer state when the visible fragment begins/ends mid-statement."""
import io,keyword,token,tokenize
from collections import Counter
from common28 import *
from operators import observations
from predict28 import text_of
def run():
    summary={}
    for p in ("swe","loc"):
        rows=read(D/(p+"-forecasts.json.gz"));x=Counter()
        for f in rows:
            txt=text_of(f["file"]);lines=txt.split("\n");lo,hi=f["first"]
            obs,calls,bad=observations("\n".join(lines[lo-1:hi]));x["rows"]+=1;x["incomplete_flag"]+=bad
            privileged=[v for v in tokenize.generate_tokens(io.StringIO(txt).readline) if lo<=v.start[0] and v.end[0]<=hi and v.type in (token.NAME,token.OP,token.STRING,token.NUMBER)]
            ideal=[v.string for i,v in enumerate(privileged) if v.type==token.NAME and not keyword.iskeyword(v.string) and v.string not in {"self","cls"} and (i==0 or privileged[i-1].string not in {"def","class"}) and i+1<len(privileged) and privileged[i+1].string=="("]
            x["same_sequence"]+=calls==ideal
            x["same_names"]+=set(calls)==set(ideal)
            x["flag_and_same"]+=bool(bad and set(calls)==set(ideal))
            x["flag_and_different"]+=bool(bad and set(calls)!=set(ideal))
            x["unflagged_different"]+=bool(not bad and set(calls)!=set(ideal))
        summary[p]=x
    save(D/"lexer-audit.json",summary);print(summary)
if __name__=="__main__":run()

