from predict_density import *
def main():
    gold=load(l.ref.OFF/"gold-spans.json.gz");mid=load(MID/"outcomes.json.gz");seal=load(D/"forecast-seal.json");assert sha(MID/"outcomes.json.gz")==load(D/"plan.json")["mid_outcomes_sha"] and sha(D/"plan.json")==seal["plan"]
    out={};checked=0;projection=0
    for sh in range(8):
        p=D/f"forecast-{sh}.json.gz";assert sha(p)==seal["files"][p.name];pred=load(p)
        pools={r["q"]:tuple(l.RankedNodeRecord.model_validate(v) for v in r["rr"]) for r in load(l.ref.TR/f"forecasts-main-{sh}.json.gz")}
        for q,r in pred.items():
            truths=tuple(l.SourceSpan.model_validate(s) for s in gold[q]);nd=pools[q];score=[]
            for ix in r["choices"]:
                s=tuple(nd[j] for j in ix);tok=sum(v.token_count for v in s);assert tok<=2048;v=l.span_metrics_under_token_budget(s,truths,2048);score.append([int(v.full_support),v.coverage,tok]);projection+=1
            mr=mid[q];assert mr["t"]==r["t"]
            for sd in SEEDS:
                for i,k in enumerate(ARMS[:3]):
                    assert score[r["seeds"][str(sd)][i]][:2]==mr["seeds"][str(sd)][k];checked+=1
            out[q]={"t":r["t"],"eligible":mr["eligible"],"pilot":mr["pilot"],"seeds":r["seeds"],"values":score}
    assert set(out)==set(mid) and checked==24000;put(D/"outcomes.json.gz",out);put(D/"outcome-audit.json",{"anchors":checked,"unique_selections_scored":projection,"questions":len(out),"values":"FS2048, Coverage2048, selected token count","outcomes":sha(D/"outcomes.json.gz"),"forecast":sha(D/"forecast-seal.json"),"code":sha(D/"score_density.py")})
if __name__=="__main__":main()
