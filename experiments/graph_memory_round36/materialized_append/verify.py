"""Independent scoring from per-question character atoms and branch-observation checks."""
from materialize import *
def main():
    hx=load(D/"forecast-seal.json");report=load(D/"results.json");assert report["seal"]==sha(D/"forecast-seal.json")
    a=W/"graph_memory_round34/interval_witness";p=a/"test-atoms.json.gz";assert sha(p)==load(a/"test-geometry.json")["atoms"];atoms=load(p)
    r={(r["q"],r["cut"]):r for r in load(D/"outcomes.json.gz")};matches=0;methods=0;table=defaultdict(int)
    for sh in range(8):
        old={(v["q"],v["cut"]):v for v in load(R34/f"forecast-{sh}.json.gz")}
        ps=D/f"orders-{sh}.json.gz";assert sha(ps)==hx["files"][ps.name]
        c={row["q"]:[n["token_count"] for n in row["rr"]] for row in load(l.ref.TR/f"forecasts-main-{sh}.json.gz")}
        for q,t,cut,ords in load(ps):
            for m,prev in (("E","exact"),("L","append")):
                assert ords[m]==old[q,cut]["selected"][prev];matches+=3
            row=r[q,cut];aa=atoms[q];lng=np.array([b-a for _,a,b,g in aa])
            for m in MODES:
                ix=ords[m][-1];chosen=set(ix);hit=np.array([any(i in chosen for i in g) for *_,g in aa])
                measure=[int(hit.all()),lng[hit].sum()/lng.sum(),sum(c[q][i] for i in ix),len(ix)];assert np.allclose(measure,row["arms"][m],atol=1e-12,rtol=0);methods+=1
            if cut==50 and row["eligible"] and not row["pilot"]:table["".join(str(row["arms"][m][0]) for m in MODES)]+=1
    native=load(D/"native-audit.json");assert native["source"]==sha(D/"native-raw-states.json.gz") and native["trajectories"]==12
    assert matches==48000 and methods==24000 and sum(table.values())==901
    put(D/"audit.json",dict(root_equality_selections=matches,atomic_candidate_case_methods=methods,field_values=methods*4,
        full_support_patterns_E_M_L=table,native_checked=native["pairset_digests_checked"],report=sha(D/"results.json")))
    print(table)
if __name__=="__main__":main()