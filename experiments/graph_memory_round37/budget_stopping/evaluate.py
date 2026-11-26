"""Score sealed cutoffs, check nested source coverage, and resample complete trajectories."""
from policy import ALPHAS, ATOMS, CAL, D, atomic_trace, load, np, save, sha
from scipy.stats import beta

def binomial_interval(k, n):
    return [float(beta.ppf(.025,k,n-k+1)) if k else 0.,
            float(beta.ppf(.975,k+1,n-k)) if k < n else 1.]

def evaluate(stage):
    seal = load(D/"seal.json")
    assert sha(D/(stage+"-forecast.json.gz")) == seal[stage] and sha(D/"selection.json") == seal["selection"]
    rows = load(D/(stage+"-forecast.json.gz"))
    truth = load(ATOMS/(stage+"-atoms.json.gz"))
    reference = load(CAL/(stage+"-outcomes.json.gz"))
    outcomes = {}
    for q,item in rows.items():
        target, cum, denominator = atomic_trace(item,truth[q])
        arms = {}
        for arm,k in item["arms"].items():
            assert 0 <= k <= item["arms"]["full"]
            mass = int(cum[k])
            arms[arm] = [int(mass == denominator),mass/denominator,item["spent"][k],k,int(k < target)]
            assert (k < target) == (mass < cum[-1])
        ref = reference[q]["arms"]["oof_3894"]
        assert np.allclose([ref[0],ref[4]],arms["full"][:2],atol=1e-12,rtol=0)
        outcomes[q] = dict(t=item["t"],arms=arms,oracle=item["spent"][target])
    name = stage+"-outcomes.json.gz"
    save(name,outcomes)
    qids = sorted(rows)
    ts, ix = np.unique([rows[q]["t"] for q in qids],return_inverse=True)
    arms = sorted(outcomes[qids[0]]["arms"])
    obs = np.array([[outcomes[q]["arms"][a] for a in arms] for q in qids])
    hurt = np.zeros((len(ts),len(arms)),dtype=int)
    np.maximum.at(hurt,ix,obs[:,:,4].astype(int))
    means = {}
    full = arms.index("full")
    for j,arm in enumerate(arms):
        count = int(hurt[:,j].sum())
        means[arm] = dict(fs=obs[:,j,0].mean(),coverage=obs[:,j,1].mean(),tokens=obs[:,j,2].mean(),
                          nodes=obs[:,j,3].mean(),questions_hurt=int(obs[:,j,4].sum()),
                          trajectories_hurt=count,risk=count/len(ts),risk_ci95=binomial_interval(count,len(ts)),
                          shortened=int((obs[:,j,3]<obs[:,full,3]).sum()))
    pairs = [("learned_5","tokens_5"),("learned_5","matched"),("learned_5","full"),("tokens_5","full")]
    diff = np.stack([obs[:,arms.index(a),:3]-obs[:,arms.index(b),:3] for a,b in pairs],axis=1)
    group = np.zeros((len(ts),len(pairs)*3))
    np.add.at(group,ix,diff.reshape(len(ix),-1))
    sizes = np.bincount(ix)
    rng = np.random.default_rng(37012)
    means_boot = []
    for _ in range(100):
        samp = rng.integers(len(ts),size=(100,len(ts)))
        weights = np.stack([np.bincount(row,minlength=len(ts)) for row in samp])
        means_boot.append((weights@group)/(weights@sizes)[:,None])
    interval = np.quantile(np.concatenate(means_boot),[.025,.975],axis=0).reshape(2,len(pairs),3)
    comparison = {a+" minus "+b:dict(delta=diff[:,j].mean(axis=0).tolist(),ci95=interval[:,j].tolist())
                  for j,(a,b) in enumerate(pairs)}
    res = dict(questions=len(rows),trajectories=len(ts),means=means,paired=comparison,bootstrap=10000,
               mean_oracle_cost=np.mean([x["oracle"] for x in outcomes.values()]),
               outcome_columns=["full_support","coverage","delivered_tokens","delivered_nodes","lost_any_covered_span"],
               seal=sha(D/"seal.json"),outcomes=sha(D/name),atoms=sha(ATOMS/(stage+"-atoms.json.gz")))
    save(stage+"-results.json",res)
    print(stage,len(rows),len(ts),{a:[round(means[a][k],4) for k in ("tokens","fs","risk")] for a in ("full","learned_5","tokens_5","matched")})
    print(comparison["learned_5 minus tokens_5"])
if __name__ == "__main__":
    for stage in ("dev","test"):
        evaluate(stage)

