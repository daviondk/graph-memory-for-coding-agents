"""Compare new single-query features and compiled ensembles with the signed batch implementation."""
from inputs import D,R39,SEEDS,pool_source,cases,arrays,save,read,sha
from runtime import Reader,np
import sys
sys.path.insert(0,str(R39/"global_packet"))
import packet


def main():
    raw=pool_source()
    engine=Reader()
    model=read(R39/"global_packet/models.json")["models"]["graph"]
    feature_error=utility_error=0.
    facts=0
    for seed in SEEDS:
        ref,matrix=packet.projections("test",seed)
        expected=np.logaddexp(0,packet.portable(model,matrix[:,model["cols"]]))
        for q,t,record in cases(seed,raw):
            a=arrays(record)
            p=engine.features(a)
            sl=ref[q][-1]
            feature_error=max(feature_error,float(np.max(np.abs(p-matrix[sl]))))
            utility_error=max(utility_error,float(np.max(np.abs(engine.utility(p)-expected[sl]))))
            facts+=len(p)
    assert feature_error<1e-10 and utility_error<1e-12
    save(D/"model-check.json",dict(candidate_rows=facts,queries=10000,max_feature_error=feature_error,
        max_utility_error=utility_error,source=sha(R39/"global_packet/packet.py")))
    print(facts,feature_error,utility_error)


if __name__=="__main__":
    main()
