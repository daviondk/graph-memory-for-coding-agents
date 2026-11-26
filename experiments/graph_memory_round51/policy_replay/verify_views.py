"""Validate the databases distributed to reviewers against the sealed full-question evidence."""
from contextlib import closing
from pathlib import Path
import sqlite3
import rank_view
import replay

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/"baseline"

def rank_records():
    groups=replay.read(BASE/"decisions.json.gz")
    groups["hotpot"]=replay.read(BASE/"hotpot-decisions.json.gz")
    groups["confirm"]=replay.read(BASE/"confirm/choices.json.gz")
    scores=replay.read(BASE/"complete-records.json.gz")
    scores["confirm"]=replay.read(BASE/"confirm/records.json.gz")
    contexts=replay.read(BASE/"matched-contexts.json.gz")
    contexts["confirm"]=replay.read(BASE/"confirm/contexts.json.gz")
    with closing(sqlite3.connect((ROOT/"rank.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        db.row_factory=sqlite3.Row
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        checked=0; canary=None
        for panel,qs in groups.items():
            source={"hotpot":ROOT.parent/"transfer","confirm":ROOT.parent/"routing"}.get(panel,replay.R50/panel)
            receipt=replay.read(source/"catalog-receipts.json.gz")
            for q,row in qs.items():
                question=db.execute("SELECT question,fragment,first_title FROM question WHERE panel=? AND q=?",(panel,q)).fetchone()
                assert question["first_title"]
                assert all(replay.digest(question[k].encode())==receipt[q][f] for k,f in (("question","question"),("fragment","snippet")))
                for method in ("graph","hybrid"):
                    result=list(db.execute(rank_view.RANK_SQL,dict(panel=panel,q=q,method=method,suppress=-1)))
                    assert all(replay.digest(r["title"].encode())==receipt[q]["titles"][str(r["cid"])] for r in result)
                    winner=result[0]["cid"]
                    assert winner==row[method]
                    obs=db.execute("SELECT * FROM response WHERE panel=? AND q=? AND cid=?",(panel,q,winner)).fetchone()
                    cid,key,n=contexts[panel][q]["refs"][method]
                    assert (obs["cid"],obs["prompt"],obs["input_tokens"])==(cid,key,n)
                    assert (obs["f1"],obs["full"])==(scores[panel][q][method]["f1"],scores[panel][q][method]["full"])
                    checked+=1
                    if method=="graph" and not canary and result[0]["edge"]:
                        flipped=db.execute(rank_view.RANK_SQL,dict(panel=panel,q=q,method=method,suppress=winner)).fetchone()
                        if not db.execute("SELECT 1 FROM response WHERE panel=? AND q=? AND cid=?",(panel,q,flipped["cid"])).fetchone():
                            canary=dict(panel=panel,q=q,suppress=winner)
        assert canary
        example=rank_view.get_result("/api/rank/query",canary)
        assert example["recorded"] is None and example["certificate"]["agrees"]
    return checked

def replay_records():
    archived=replay.read(ROOT/"results.json")["panels"]
    with closing(sqlite3.connect((ROOT/"replay.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        for panel,group in archived.items():
            for pair,expected in group.items():
                a,b=pair.split("-to-")
                result,_=replay.evaluate(db,panel,a,b)
                assert result==expected
    return len(archived)

if __name__=="__main__":
    print(f"Verified {rank_records()} learned selections, matched response keys and recorded scores; {replay_records()} cost panels and an actually unobserved intervention.")

