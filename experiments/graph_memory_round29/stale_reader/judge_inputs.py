"""Privileged, condition-blinded scoring preparation after the actor forecast has been sealed."""
from collections import defaultdict
from itertools import product
import ast,json
from setup29 import D,P,Path,h,sha,read,save
ARMS=("H","T","G","O")
HIST=("past_prefix","past_full")
DIMS=("dim1_query","dim2_query","dim3_query")
REF=Path("D:/CodexResearch/x20-r28-retraction/judge_prompts.py.txt")
def rubrics():
    tree=ast.parse(REF.read_text(encoding="utf8"))
    prompt=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=="SYSTEM_PROMPT_ALL_IN_ONE_JUDGE")
    return prompt.split("### Output Format")[0].strip()
NATIVE_DETAIL={"dim1_query":"Pass only if the answer recognizes that the old information is possibly no longer valid. Assuming the old state still holds or merely claiming ignorance fails.",
 "dim2_query":"Pass only if it detects the outdated premise or acknowledges the new state; agreeing with the stale premise fails.",
 "dim3_query":"Pass only if the action/recommendation actually fits the new state. Generic advice and an action premised on the old state fail."}
HIST_SYSTEM=("You are an independent evaluator of answers about what a person previously reported. The question asks what was last reported "
    "before its stated cutoff, not whether that state actually persisted until then. The old note is authentic historical evidence. "
    "A later state may supersede it for current use. Grade one answer. V = correctly identifies the substance of the earlier report; "
    "appropriate caveats about persistence or the later change are allowed. R = retroactively rejects that earlier report, or substitutes "
    "the later state as if it had been reported before the cutoff. U = says evidence is insufficient or remains equivocal on what was reported. "
    "X = other incorrect/unrelated answer. Return exactly one of V, R, U or X.")
def main():
    f=read(D/"effective-actor-forecast-seal.json");assert sha(P/"effective-actor-outputs.json.gz")==f["raw"]
    lock=read(D/"input-seal.json");assert sha(P/"eval-keys.json.gz")==lock["eval_keys"]
    ass=read(D/"effective-actor-assignment.json.gz");outputs=read(P/"effective-actor-outputs.json.gz");keys=read(P/"eval-keys.json.gz");qs=read(P/"reader-questions.json")
    groups=defaultdict(dict);blind=[];req={};refs={}
    for q,r in keys.items():groups[r["case"]][r["mode"]]=q
    sys1=rubrics()+"\nOutput only three digits in order, 1 if pass and 0 otherwise. No explanation."
    def job(s,u,grammar,allow):
        k=h(s+"\0"+u+"\0"+grammar);req[k]=dict(system=s,user=u,grammar=grammar,allow=allow);return k
    for c,mm in groups.items():
        for arm in ARMS:
            r=keys[mm[DIMS[0]]];facts="Old report: "+r["old"]+"\nNew information: "+r["new"]+"\nUpdate logic: "+r["rubric"]
            seq=[]
            for i,mode in enumerate(DIMS,1):
                q=mm[mode];ans=outputs[ass[q][arm]].get("answer","")
                seq.append(f"\nDimension {i}. Question: "+qs[q]["ask"]+"\nCandidate response: "+ans)
            k=job(sys1,facts+"\n"+"\n".join(seq),'root ::= [01] [01] [01]',["".join(z) for z in product("01",repeat=3)])
            for i,mode in enumerate(DIMS):
                q=mm[mode];refs[q+"/"+arm]=[k,i]
            for mode in HIST:
                q=mm[mode];ans=outputs[ass[q][arm]].get("answer","")
                u=facts+"\nHistorical question: "+qs[q]["ask"]+"\nCandidate response: "+ans
                k=job(HIST_SYSTEM,u,'root ::= [VRUX]',list("VRUX"))
                refs[q+"/"+arm]=[k,0]
            for mode in (*DIMS,*HIST):
                q=mm[mode];tok=h("r29-audit-mask/"+q+arm)[:16];ans=outputs[ass[q][arm]].get("answer","")
                blind.append((mode,tok,dict(token=tok,kind=mode,question=qs[q]["ask"],old=r["old"],new=r["new"],update=r["rubric"],
                          answer=ans,instructions=NATIVE_DETAIL.get(mode,HIST_SYSTEM)),q,arm))
    # One item per method per dimension, 20 total. Selection uses only fixed IDs and a method-balancing stratum, never the outputs or grades.
    packet=[];link={}
    for mode in (*DIMS,*HIST):
        for arm in ARMS:
            pool=[s for s in blind if s[0]==mode and s[4]==arm]
            z=min(pool,key=lambda t:h("r29-blind-audit-choice/"+t[1]));packet.append(z[2]);link[z[1]]=[z[3],z[4]]
    packet.sort(key=lambda r:h("r29-shuffle/"+r["token"]))
    save(P/"audit-packet.json",packet);save(P/"audit-map.json",link);save(P/"judge-requests.json.gz",req);save(D/"judge-assignment.json.gz",refs)
    save(D/"judge-input-seal.json",dict(actor=sha(D/"effective-actor-forecast-seal.json"),requests=sha(P/"judge-requests.json.gz"),
          judge_assignment=sha(D/"judge-assignment.json.gz"),official_prompt=sha(REF),code=sha(Path(__file__)),unique=len(req),max_tokens=6,
          review_packet=sha(P/"audit-packet.json"),review_mapping=sha(P/"audit-map.json"),review_n=20))
    print(len(req),len(packet))
if __name__=="__main__":main()
