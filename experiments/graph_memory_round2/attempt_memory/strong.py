from prepare import HERE,read,save,sha
from policy import candidates,design
from llm import model_call
import re,sys,time
def main():
    for panel in ("old","fresh"):
        src=HERE/("observed_"+panel+".json")
        for _ in range(1800):
            if src.exists():break
            time.sleep(1)
        out=[]
        for r in read(src):
            gs,available,sel=design(r)
            static=min(gs,key=lambda g:(-g[2],g[1][0]))[1][0]
            legal=[a for a in r["arms"] if a["public"]==max(t["public"] for t in r["arms"])]
            def agree(a):
                return sum(x is not None and x==y for other in legal if other["j"]!=a["j"] for x,y in zip(a["vec"],other["vec"]))
            mbr=min(legal,key=lambda a:(-agree(a),a["j"]))["j"]
            key=None;choice=static;usage={}
            if available:
                ls=sorted(legal,key=lambda a:sha(f"ordering|{r['id']}|{a['j']}"))
                variants="\n\n".join(chr(65+k)+".\n"+(HERE/"programs"/str(r["id"])/f"{a['j']}.py").read_text(encoding="utf8")[:1450] for k,a in enumerate(ls))
                user=f"Task: {r['spec']}\nInterface: {r['sig']}\nAll listed candidates have the same outcome on the first public test: {legal[0]['public']}. Choose the best implementation.\n\n"+variants
                sysmsg="Select the implementation most likely to pass all tests for the given specification. Choose among the listed letters. Answer only with a single letter; U is allowed for unknown."
                rec=model_call(sysmsg,user,8,int(sha("direct|"+str(r["id"]))[:7],16),0)
                raw=rec["reply"]["choices"][0]["message"].get("content") or ""
                m=re.fullmatch(r"\s*([A-C])[.)]?\s*",raw,re.I)
                if m and ord(m.group(1).upper())-65<len(ls):choice=ls[ord(m.group(1).upper())-65]["j"]
                key=rec["key"];usage=rec["reply"]["usage"]
            out.append(dict(id=r["id"],mbr=mbr,direct=choice,call=key,usage=usage))
        path=HERE/f"strong_{panel}.json";save(path,out)
        print("strong",panel,len(out),sha(path.read_bytes()),flush=True)
if __name__=="__main__":main()

