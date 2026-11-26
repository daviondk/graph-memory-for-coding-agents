from study import *
from analyze import panels,summarize

def test_ties():
    rng=np.random.default_rng(50090)
    for n in range(1,100):
        group=rng.integers(0,12,size=n)
        cosine=rng.integers(-2,5,size=n)/8
        priority=rng.permutation(np.arange(1,n+1))
        sem=np.column_stack((priority,1/priority,priority,cosine))
        value=witnesses(sem,group,12)
        for i,g in enumerate(group):
            own=[j for j in range(n) if j!=i and group[j]==g]
            opposite=[j for j in range(n) if group[j]==(g^1)]
            row=[]
            for candidates in (own,opposite):
                if candidates:
                    j=max(candidates,key=lambda j:(cosine[j],sem[j,1],-j))
                    row.extend([cosine[j],sem[j,1]])
                else:row.extend([-2.,0.])
            assert np.array_equal(value[i],row)

if __name__=="__main__":
    test_ties()
    for stage in ("mid","trigger"):
        observations,missing=panels(stage)
        assert observations==read(HERE/f"{stage}-outcomes.json.gz")
        report=summarize(observations,stage)
        report["no_trigger_trajectories"]=missing
        assert report==read(HERE/f"{stage}-results.json")
    print("Regraded both panels and reproduced paired intervals; independent top-two tie tests passed.")

