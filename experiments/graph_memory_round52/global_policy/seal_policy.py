"""Frozen addresses, portably keyed by question ID. Never opens support/answer files."""
from collections import Counter
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "global_titles"
sys.path.insert(0,str(BASE))
from corpus import WORK, read, save, hashfile
from lexicon import tokens, STOP

GATES = ["two_words", "primary", "loose"]
OUTPUTS = ["free", "parent_text", "parent_href", "text_first", "href_first",
           *[gate+"_"+branch for gate in GATES for branch in ("href","text","free")]]
def rows(name):
    return {k:[int(x) for x in rest] for k,*rest in
            (line.split("\t") for line in (WORK/name).read_text(encoding="ascii").splitlines())}

def main():
    first, second, directs = (rows(n) for n in ("seed.tsv", "second.tsv", "policy52-direct.tsv"))
    queries = read(WORK/"questions.json.gz")
    assert len(queries)==12576 and set(first)==set(second)==set(directs)==set(queries)
    targets=set()
    data={}
    branches=Counter()
    for q in sorted(queries):
        seed, free, _, parent_text, parent_href, _, text_first, href_first, *_ = second[q]
        header,*raw_gates = directs[q][1:]
        assert seed==first[q][0]==directs[q][0] and len(raw_gates)==18
        pred=[free,parent_text,parent_href,text_first,href_first]
        gates=[]
        for j,name in enumerate(GATES):
            addr,n,a,b,terms,df = raw_gates[6*j:6*j+6]
            assert (addr>=0)==(n>0) and addr!=seed
            if n:
                assert a<b and terms and header>0
                branches[name]+=1
            gates.append([addr,n,a,b,terms,df])
            for fallback in (href_first,text_first,free):
                pred.append(addr if n else fallback)
        assert seed not in pred and min(pred)>=0
        assert gates[0][1]<=gates[1][1]<=gates[2][1]
        data[q]={"seed":seed,"seed_mentions":header,"gates":gates,"choices":pred}
        targets.update([seed,*pred])
    names={}
    with (WORK/"titles.txt").open(encoding="utf8") as f:
        for row,line in enumerate(f):
            if row in targets:
                wiki,title=line.rstrip("\n").split("\t",1)
                names[row]=[int(wiki),title]
    assert set(names)==targets
    checks=Counter()
    for q,row in data.items():
        question=tokens(queries[q]);seed=tokens(names[row["seed"]][1]);n=len(seed)
        matches=[(i,i+n) for i in range(len(question)) if n>0 and question[i:i+n]==seed]
        # Ineligible abbreviated parenthetical titles are excluded by the common index.
        if row["seed_mentions"] or any(g[1] for g in row["gates"]):
            assert len(matches)==row["seed_mentions"]
        occupied={j for a,b in matches for j in range(a,b)}
        for j,(dest,k,a,b,words,df) in enumerate(row["gates"]):
            picked=row["choices"][5+j*3:8+j*3]
            if not k:
                assert picked==[row["choices"][4],row["choices"][3],row["choices"][0]]
                checks["fallback_triplets"]+=1
                continue
            assert picked==[dest]*3 and matches
            assert not occupied.intersection(range(a,b))
            title=tokens(names[dest][1]);extract=question[a:b]
            assert extract==title
            content=set(title)-STOP
            assert content-set(seed) and len(content)==words
            assert words>=2 or (j in (1,2) and 0<df<=[0,59,5989][j])
            checks["independent_span_triplets"]+=1
    save(HERE/"predictions.json.gz", data)
    save(HERE/"chosen-titles.json.gz",names)
    save(HERE/"routes.json",{"n":len(data),"direct_branches":branches,"guard":checks,
         "modes":GATES,"arms":OUTPUTS,"independent_lookup_names":len(names)})
    upstream=read(BASE/"opening.json")
    for key,filename in (("second_inputs","second.in"),("seed","seed.tsv"),("opened","opened.json.gz")):
        assert upstream[key]==hashfile(WORK/filename)
    files=["PROTOCOL_RU.md","policy.cpp","seal_policy.py","predictions.json.gz","chosen-titles.json.gz","routes.json"]
    inputs=["lex.bin","stop.bin","questions.in","second.in","seed.tsv","second.tsv","policy52-direct.tsv"]
    save(HERE/"prediction-seal.json",{"local":{k:hashfile(HERE/k) for k in files},"upstream_cache":{k:hashfile(WORK/k) for k in inputs},
          "upstream_code":{k:hashfile(BASE/k) for k in ("retrieval.cpp","lexicon.py","corpus.py","PROTOCOL_RU.md","opening.json","source.json")},
          "n":len(data),"arms":OUTPUTS,"modes":GATES,"first_address":"same frozen seed as global_titles"})
    print("SEALED",len(data),len(names),dict(branches),dict(checks),hashfile(HERE/"prediction-seal.json"))

if __name__=="__main__":
    main()

