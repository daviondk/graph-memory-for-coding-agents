"""Illustrative, post-primary synthetic workload that forces a populated cold start and fallback."""
from collections import Counter
from pathlib import Path
import tempfile

from run import HERE, connect, make, save
from source import sig


def event(t,born,delta):
    return dict(t=t,born=born,delta=delta,sha=sig(born,delta))


def main():
    with tempfile.TemporaryDirectory(dir=HERE) as scratch:
        db=connect(Path(scratch)/"stress.sqlite")
        try:
            store=make(db,"lazy",12)
            population=list(range(20))
            changed=[[i,i,20-i] for i in population]
            assert store.update("stress",event(1,population,changed))
            initial=dict(store.event)
            store.last.clear()
            withdrawals=[[i,i,-(20-i)] for i in range(8)]
            row=event(2,[],withdrawals)
            assert store.update("stress",row)
            fall=dict(store.event)
            result=store.get("stress",2,8)
            assert result==[(i,20-i) for i in range(8,16)]
            assert store._history("stress",1,8)==[(i,20-i) for i in range(8)]
            assert store._history("stress",2,8)==result
            assert fall["cold_probes"]==fall["warm_probes"]==1
            assert fall["cold_rows"]==fall["warm_rows"]==12
            assert not store.update("stress",row)
            report=dict(synthetic=True,n=20,k=8,l=12,edits_after_restart=8,
                        first_event=initial,second_event=fall,new_top=result,
                        previous_version_verified=True,idempotent_retry_verified=True)
            save("stress.json",report)
            print(report)
        finally:
            db.close()


if __name__=="__main__":
    main()

