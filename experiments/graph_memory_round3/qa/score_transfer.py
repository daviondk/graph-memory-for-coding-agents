from prepare import P,read,write,sha
from evaluate import aggregate,contrast,normalized,official
def compare(rows,a,b,metric):
    return contrast({i:{'graph':v[a],b:v[b]} for i,v in rows.items()},b,metric) if b!='graph' else contrast({i:{'graph':v[a],'old':v[b]} for i,v in rows.items()},'old',metric)
def main():
    g=read("gold.json");out=read("transfer_output.json");rc=read("transfer_receipt.json");assert rc['sha256']==sha((P/'transfer_output.json').read_bytes())
    lock=read("transfer_lock.json");assert not set(lock['items'])&set(read('reader_lock.json')['questions'])
    rows={i:{a:dict(f1=official(x['answer'],g[i]['answer'],g[i]['cat']),em=int(normalized(x['answer'])==normalized(g[i]['answer'])),tokens=x['tokens'],truncated=int(x['truncated'])) for a,x in arms.items()} for i,arms in out.items()}
    write("transfer_scores.json",rows);meta=read("transfer_features.json")
    total=dict(n=len(rows),means=aggregate(rows),joint_minus={b:compare(rows,'joint',b,'f1') for b in ('flat','graph','owner','date','wrong_date','previous','directed')},
               each_vs_graph={a:compare(rows,a,'graph','f1') for a in ('flat','owner','date','joint','wrong_date','previous','directed')},subsets={})
    for name,pred in [("relative_phrase_in_top5",lambda i:meta[i]["explicit_relative_date_in_top5"]),("temporal_questions",lambda i:g[i]['cat']==2)]:
        sub={i:v for i,v in rows.items() if pred(i)};total["subsets"][name]=dict(n=len(sub),means=aggregate(sub),joint_vs_graph=compare(sub,'joint','graph','f1'),date_vs_graph=compare(sub,'date','graph','f1'))
    write("transfer_results.json",total)
if __name__=='__main__':main()