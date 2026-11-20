"""Check seals, hashes of rendered stimuli, and query/candidate permutation equivariance of the frozen ranker."""
from collections import Counter
import pickle
from data_io import *
from memory import encode,features
import numpy as np
def signature(code,docs,k):
    q="\n".join(code.splitlines()[-k:])
    return hashstr(q+"\0"+"\0".join(sorted(hashstr(x) for x in docs)))
def main():
    for k,h in read("method_lock.json")["files"].items():assert sha(D/k)==h
    for k,h in read("prediction_lock.json")["files"].items():assert sha(D/k)==h
    assert read("fit.json")["sha256"]==sha(D/"models.pkl")
    with (D/"models.pkl").open("rb") as f:m=pickle.load(f)
    allsrc=read("sources.json")
    for v in allsrc:assert sha(D/"inputs"/v["path"])==v["sha256"]
    chosen=read("roster.json");ext=read("strict_roster.json");sections={};checks=0;trimmed={}
    for stage,paths,ids in [("train",files("java","train"),chosen),("test_java",files("java","test"),chosen),("test_python",files("python","test"),chosen),("strict",files("java","test"),ext)]:
        recs=[];repos=set();hashes=set();stim={3:set(),10:set()};ids_=[]
        for p in paths:
            wanted=dict(ids[p.stem]);mark=set(sorted(wanted,key=lambda i:hashstr(p.stem+str(i)))[:3])
            for j,row in enumerate(rows(p,["code","context","repo_name"])):
                if j not in wanted:continue
                code=row["code"];docs=row["context"];repos.add(row["repo_name"]);hashes.add(hashstr(code));ids_.append((panel_name(p.stem),wanted[j]))
                for k in (3,10):stim[k].add(signature(code,docs,k))
                if j not in mark or stage=="train":continue
                perm=np.random.default_rng(j+99).permutation(len(docs))
                v=features(code,encode(docs),3);u=features(code,encode([docs[x] for x in perm]),3)
                assert np.allclose(v[perm],u,rtol=1e-6,atol=1e-6)
                assert np.allclose(m[3,"graph"].predict_proba(v)[:,1][perm],m[3,"graph"].predict_proba(u)[:,1])
                checks+=1
        sections[stage]=dict(sets=stim,repos=repos,codes=hashes,ids=set(ids_))
    stats={s:dict(n=len(v["ids"]),projects=len(v["repos"]),unique_codes=len(v["codes"]),unique_stimuli={k:len(x) for k,x in v["sets"].items()}) for s,v in sections.items()}
    for a,b in [("train","test_java"),("train","test_python"),("train","strict"),("strict","test_java")]:
        v=sections[a];w=sections[b];stats[a+"_"+b]={"project_overlap":len(v["repos"]&w["repos"]),"whole_code_overlap":len(v["codes"]&w["codes"]),"prompt_overlap":{k:len(v["sets"][k]&w["sets"][k]) for k in (3,10)}}
        assert not v["repos"]&w["repos"]
    write("verification.json",{"samples_reordered":checks,"source_sha256s_checked":len(allsrc),"panels":stats,"public_numeric_BM25_cells_matched":2*sum(x["match"] for x in read("comparison_audit.json").values())})
if __name__=="__main__":main()
