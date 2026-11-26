from transfer import *
def main():
    check_source();summary=load(D/"results.json");report=summary["groups"];series=load(D/"outcomes.json.gz")
    atoms=load(W/"graph_memory_round34/interval_witness/test-atoms.json.gz");data={r["q"]:r for r in load(b.PRIVATE/"test.json.gz")};summary_checks=0
    fs={str(s):[0,0,0,0] for s in SEEDS};grid=np.array([256,512,1024,2048,4096,8192])
    for i in range(8):
        o=load(D/f"orders-{i}.json.gz")
        for q,seeds in o.items():
            aa=atoms[q];length=np.array([end-start for _,start,end,_ in aa]);cost=np.asarray(data[q]["c"])
            for sk,arms in seeds.items():
                for name,order in arms.items():
                    ix=np.asarray(order);back=np.argsort(ix);first=np.array([min(back[j] for j in g) for *_,g in aa]);fc=np.cumsum(cost[ix])[first]
                    cov=(length[:,None]*(fc[:,None]<=grid[None,:])).sum(axis=0)/length.sum();bs=(fc.max()<=grid).astype(float)
                    auc=lambda v:(v[0]/2+v[-1]/2+v[1:-1].sum())/5
                    m=[bs[3],auc(cov),auc(bs),1/(first.min()+1),cov[3]]
                    assert np.allclose(m,series[q]["seeds"][sk][name],rtol=0,atol=1e-12);summary_checks+=1
                a=series[q]["seeds"][sk];x,y=a[NAMES[1]][0],a[NAMES[0]][0];f=fs[sk];f[0]+=int(x);f[1]+=int(y);f[2]+=int(x>y);f[3]+=int(y>x)
    for sk,counts in fs.items():
        g=report[sk];assert counts==[round(g["means"][name][0]*2000) for name in (NAMES[1],NAMES[0])]+[g["win_question"][0],g["loss_question"][0]]
    assert np.allclose(report["transfer4"]["delta_pp"],np.mean([report[str(s)]["delta_pp"] for s in SEEDS],axis=0),atol=1e-11)
    assert np.allclose(report["13"]["means"]["oof_3894"],load(S/"test-results.json")["means"]["oof_3894"],atol=1e-12)
    save(D/"audit.json",dict(query_seed_methods=summary_checks,numeric_entries=5*summary_checks,counts_new_old_wins_losses=fs,source_manifest=SOURCE,outcomes=sha(D/"outcomes.json.gz")))
    print("verified",summary_checks,fs)
if __name__=="__main__":main()