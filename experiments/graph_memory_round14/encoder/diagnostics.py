"""Prespecified paired mechanism and coverage diagnostics."""
from collections import Counter,defaultdict
import statistics
from forecast import D,read,save

def band(n):
    if n==0:return '0'
    if n==1:return '1'
    if n<=3:return '2-3'
    if n<=8:return '4-8'
    return '9+'
def main():
    pred=read(D/'predictions.json.gz');obs=read(D/'evaluation_rows.json.gz')
    result={}
    for panel,rows in pred.items():
        menu=defaultdict(Counter)
        for r in rows:
            ranks=r['ranks'];base=ranks['dense'];bucket=menu[band(len(base))];bucket['n']+=1
            if not base:continue
            bucket['graph_changes_top1_vs_strong']+=ranks['graph'][0]!=ranks['strong'][0]
            bucket['rrf_graph_changes_top1_vs_rrf_strong']+=ranks['rrf_graph'][0]!=ranks['rrf_strong'][0]
            for m in ('graph','strong','uniform','shuffled'):
                scores={p:1/(60+a)+1/(61+ranks[m].index(p)) for a,p in enumerate(base,1)}
                tied=sum(v==max(scores.values()) for v in scores.values())
                bucket['rrf_'+m+'_tied_first']+=int(tied>1)
        epi={}
        for ep,observations in obs[panel].items():
            groups=defaultdict(list);sub=defaultdict(Counter)
            for r in observations:
                dense=r['ranks']['dense'];graph=r['ranks']['rrf_graph'];strong=r['ranks']['rrf_strong']
                delta=int(graph==1)-int(strong==1)
                groups[r['iid']].append(delta)
                v=sub[band(r['candidates'])];v['n']+=1
                v['reach']+=r['reachable'];v['dense_h1']+=dense==1;v['rrf_graph_h1']+=graph==1;v['rrf_strong_h1']+=strong==1
            avg=[sum(a)/len(a) for a in groups.values()]
            epi[ep]={'task_mean_h1_difference':statistics.mean(avg),'task_n':len(avg),
                     'task_win_tie_loss':[sum(z>0 for z in avg),sum(z==0 for z in avg),sum(z<0 for z in avg)],
                     'menu_size':sub}
        result[panel]={'menus':menu,'endpoints':epi}
    save(D/'diagnostics.json',result)
if __name__=='__main__':main()
