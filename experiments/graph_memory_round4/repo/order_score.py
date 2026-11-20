from data_io import *
from score import metric
from secondary_score import duo,goldcols
def main():
    gs=goldcols();p=read("order_prediction_lock.json");alt={};base={};lex={}
    for run in p:
        name="order_"+run["config"]+".json";assert sha(D/name)==run["hash"]
        for panel,i,sz,ranking in read(name):alt[panel,i]=ranking
        for panel,i,k,returned,ranking in read("paired_"+run["config"]+".json"):base[panel,i,k]=ranking
    data={}
    for panel,i,k,repo,cost,h,e,arms in gz(D/"strict_java.pred.jsonl.gz"):
        if (panel,i) not in alt:continue
        row=data.setdefault((panel,i),(repo,cost,{}))
        row[2][f"base{k}_binary"]=base[panel,i,k];row[2][f"base{k}_bm25"]=arms["publisher_bm25"]
    scores=[]
    for (panel,i),(repo,cost,ranks) in data.items():
        ranks.update(alt[panel,i]);scores.append([panel,i,3,repo,{a:metric(d,cost,gs[panel][i]) for a,d in ranks.items()}])
    stats={a:[sum(z[-1][a][j] for z in scores) for j in range(3)] for a in scores[0][-1]}
    pairs={}
    for tool in ("binary","bm25"):
        for name in ("base3","rotate","repeat"):
            pairs[tool+"_"+name+"_versus_base10"]=duo(scores,name+"_"+tool,"base10_"+tool)
    write("order_results.json",{"n":len(scores),"hits_at_1_3_5":stats,"contrasts":pairs})
if __name__=="__main__":main()
