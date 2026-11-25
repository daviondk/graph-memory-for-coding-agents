"""Cross-check standalone full dev ranks against the chosen seed encoder's native dev report."""
from setup_graph import ROOT,TR,TRAINED,pilot,load,put
from statistics import mean
def main():
    ids={r['q']:r['t'] for r in load(TR/'split.json.gz')['dev']}
    labels={}
    for t in set(ids.values()):
        rec=load(TRAINED/'projection/dev'/f'{t}.json.gz');labels.update({q['q']:set(q['positive']) for q in rec['qs']})
    rows=load(ROOT/'dev500-pu-dense-ranks.json.gz');metrics=[]
    for row in rows:
        q=row['q'];order=[n['node_id'] for n in row['rr']];gold=labels[q]
        assert ids[q]==row['t'] and gold<=set(order)
        recall=len(set(order[:5])&gold)/len(gold);mrr=next(1/i for i,k in enumerate(order,1) if k in gold)
        metrics.append((recall,mrr))
    mu=[mean(v[i] for v in metrics) for i in (0,1)];assert len(metrics)==len(labels)==500
    old=load(TR/'trained-checkpoint.json')
    put(ROOT/'dev500-calibration.json',dict(n=len(rows),node_recall5_recalculated=mu[0],mrr_full_ranking=mu[1],R19_checkpoint_selection_node_recall5=old['value'],difference_node_recall5=mu[0]-old['value'],
        ranks_sha=pilot.sha(ROOT/'dev500-pu-dense-ranks.json.gz'),checkpoint_sha=pilot.sha(TR/'trained-checkpoint.json')))
if __name__=='__main__':main()

