"""Post-hoc full enumeration of early subsets at the original size. Trials remain nested within programs."""
import itertools
import math
import collections
import run as r
def main():
    rows=[]
    for n in r.answers():
        task=r.ts(n)
        traces=r.get(task/"base/testdata/trace.json.gz")["records"]
        pre=r.get(task/"preflight.json");k=len(pre["early"]);sites=set(pre["gold_lines"])
        total=collections.Counter();blocks=[]
        for subset in itertools.combinations(sorted(traces),k):
            pref={k:traces[k] for k in subset}
            lt,et=r.rank(pref,"lines"),r.rank(pref,"edges")
            ls=lt[0][2][0] if lt else None;es=et[0][2][0] if et else None
            a={"with_failure":any(x["status"]=="failed" for x in pref.values()),"line_exact":ls in sites,"edge_exact":es in sites,"disagree":ls!=es}
            total.update(a);blocks.append({"ids":list(subset),"line":ls,"edge":es,**a})
        rows.append({"id":n,"n_subsets":len(blocks),"counts":total,"subsets":blocks})
    counts={k:sum(v["counts"][k]/v["n_subsets"] for v in rows)/len(rows) for k in ["with_failure","line_exact","edge_exact","disagree"]}
    r.dump(r.D/"split_sensitivity.json",{"tasks":len(rows),"sum_nested_subsets":sum(v["n_subsets"] for v in rows),"macro_probability":counts,"observations_reused_from_original_native_order":True,"rows":rows})
if __name__=="__main__":main()
