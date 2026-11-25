"""Conservative finite-sample sensitivity when there is a single discordant pair."""
from collections import Counter
from scipy.stats import beta
from prepare import D,read,sha,write
def main():
    summary=read(D/"results.json")
    n=summary["n"];x=summary["primary"]["wins"];y=summary["primary"]["losses"]
    def bounds(k):
        # Bonferroni for two 97.5% marginal Clopper-Pearson intervals.
        return (float(beta.ppf(.0125,k,n-k+1)) if k else 0.,
                float(beta.ppf(.9875,k+1,n-k)) if k<n else 1.)
    a,b=bounds(x);c,d=bounds(y)
    decisions=read(D/"choices.json.gz")
    write(D/"sparse-sensitivity.json",dict(n=n,observed_positive=x,observed_negative=y,
        paired_difference_conservative_95=[a-d,b-c],family_alpha=.05,endpoint_alpha=.0125,
        method="Two exact marginal binomial intervals for positive and negative discordance at 97.5% each; project their jointly 95%-covered rectangle onto p_plus-p_minus.",
        distribution=Counter(z["letter"] for z in decisions.values() if z["ok"]),
        sealed_choices=sha(D/"choices.json.gz"),source=sha(D/"results.json")))
if __name__=="__main__":main()
