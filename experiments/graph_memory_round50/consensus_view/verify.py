"""Independent budget and coverage audit, including leave-one-reader-out configurations."""
from serve import *
def main():
    matches=interventions=0
    with closing(connect()) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()==("ok",)
        for case in range(1,33):
            for method in METHODS:
                x=inspect(db,case,SEEDS,method,2048,True)
                assert x["archive_matches"]
                assert "evaluation" not in inspect(db,case,SEEDS,method,2048,False)
                matches+=1
            for jj,remaining in enumerate([SEEDS[:j]+SEEDS[j+1:] for j in range(len(SEEDS))]):
                for b in (512,1024,1536):
                    method=METHODS[jj%len(METHODS)]
                    v=inspect(db,case,remaining,method,b,True)
                    assert sum(u["cost"] for u in v["units"] if u["selected"])==v["used"]<=b
                    assert all(u["votes"]==len(set(u["voters"]))<=len(remaining) for u in v["units"])
                    ids=set(v["packet"])
                    fields=db.execute("SELECT atom,width FROM official_span WHERE q=?",(case,)).fetchall()
                    covered=0
                    for atom,width in fields:
                        members={i for i, in db.execute("SELECT u FROM official_member WHERE q=? AND atom=?",(case,atom))}
                        if members&ids:covered+=width
                    assert covered==v["evaluation"]["covered"]
                    interventions+=1
    print("Matched",matches,"archived packets and audited",interventions,"interactive interventions.")
if __name__=="__main__":main()

