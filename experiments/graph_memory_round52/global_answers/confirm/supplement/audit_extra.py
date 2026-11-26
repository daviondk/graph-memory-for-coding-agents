"""Cross-check exact prompt reuse, branch interventions and dF1 denominators."""
from prepare_extra import *
import math,struct
def main():
    parent=read(PARENT/"prediction-seal.json");src=read(PARENT/"predictions.json.gz");order=parent["arms"]
    reg=get("registration.json");inp=get("input-seal.json");out=get("answer-seal.json");grade=get("grade-seal.json")
    assert hashfile(PARENT/"prediction-seal.json")==reg["parent"]
    for seal,k,n in [(reg,"protocol","PROTOCOL_RU.md"),(reg,"code","prepare_extra.py"),(reg,"choices","choices.json.gz"),
          (inp,"code","answer_extra.py"),(inp,"prompts","prompts.json.gz"),(inp,"contexts","contexts.json.gz"),
          (out,"inputs","input-seal.json"),(out,"answers","answers.json.gz"),
          (grade,"code","grade_extra.py"),(grade,"answers","answer-seal.json"),(grade,"results","results.json"),(grade,"records","records.json.gz")]:
        assert hashfile(D/n)==seal[k],n
    ctx=get("contexts.json.gz");prompts=get("prompts.json.gz");answers=get("answers.json.gz")
    prior=read(D.parent/"prompts.json.gz");prior_answers=read(D.parent/"answers.json.gz");choices=get("choices.json.gz")
    assert set(prompts)==set(answers)
    for k,v in prompts.items():
        assert hashlib.sha256(struct.pack("<"+"I"*len(v),*v)).hexdigest()==k
    overlap=prompts.keys() & prior.keys()
    assert all(prior[k]==prompts[k] and answers[k]==prior_answers[k] for k in overlap)
    assert len(overlap)==out["reused"] and len(prompts)-len(overlap)==out["generated"]
    novel=read(PARENT/"novelty.json")["ever_unseen_ids"];sample=read(D.parent/"sample.json.gz");census=[]
    for q in novel:
        p=src[q];cd=lambda x:p["choices"][order.index(x)]
        if cd("coord_cautious")!=cd("learned_dev"):
            census.append(q)
            for arm in c.ARMS:assert choices["census|"+q]["arms"][arm]==cd(arm)
        if q in sample:
            h=choices["fallback|"+q]["arms"]
            assert h["learned_href"]==cd("learned_dev")
            assert h["learned_literal"]==(p["direct_gate"][0] if p["learned_direct"] else cd("text_first"))
    assert sorted(census)==reg["discordant"] and len(census)==10
    records=get("records.json.gz");result=get("results.json")
    for name,keys,left,right in [("census",census,"learned_dev","coord_cautious"),("fallback",sample,"learned_href","learned_literal")]:
        denominator=len(novel) if name=="census" else len(sample)
        tally=[]
        for q in keys:
            row=ctx[name+"|"+q];rec=records[name+"|"+q]
            assert set(row["refs"])=={left,right} and len({v[2] for v in row["refs"].values()})==1
            for idx,h,n in row["refs"].values():assert len(prompts[h])==n and idx!=row["first"]
            tally.append(rec[left][0]-rec[right][0])
        assert abs(100*math.fsum(tally)/denominator-result[name]["paired"]["f1"]["delta_pp"])<1e-10
    print(f"Passed. {len(sample)} fallback pairs, {len(census)} measured differences among {len(novel)} clean questions; {len(overlap)} exact prompt reuses.")
if __name__=="__main__":main()
