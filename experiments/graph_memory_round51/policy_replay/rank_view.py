"""Execute title ranking on visible features; attach recorded outcomes only after selecting a title."""
from contextlib import closing
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parent
NAMES=("gate_confirmation","adaptive_address","hotpot","confirm")
RANK_SQL="""
SELECT c.cid,c.title,c.cos,c.qr,c.sr,c.dr,c.edge,
       w0*c.cos+w1/(1.+c.qr)+w2/(1.+c.sr)+w3/(1.+c.dr)+
       w4*(CASE WHEN c.cid=:suppress THEN 0 ELSE c.edge END) AS score
FROM candidate AS c JOIN coef ON coef.policy=:method
WHERE panel=:panel AND q=:q ORDER BY score DESC,dr
"""

def revised_score(row,w,edge):
    return (w["w0"]*row["cos"] + w["w1"]/(1.0+row["qr"]) +
            w["w2"]/(1.0+row["sr"]) + w["w3"]/(1.0+row["dr"]) + w["w4"]*edge)

def certified(rows,candidate,w,edge):
    head=rows[0]
    if candidate["cid"]==head["cid"]:
        if len(rows)==1 or edge>=candidate["edge"]:
            return head["cid"]
        other=rows[1]
    else:
        if edge<=candidate["edge"]:
            return head["cid"]
        other=head
    old=(other["score"],-other["dr"])
    new=(revised_score(candidate,w,edge),-candidate["dr"])
    return candidate["cid"] if new>old else other["cid"]

def get_result(route,params):
    panel=params.get("panel","gate_confirmation")
    if panel not in NAMES:
        raise ValueError("Unknown question panel")
    uri=(ROOT/"rank.sqlite").as_uri()+"?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri,uri=True)) as db:
        db.row_factory=sqlite3.Row
        if route=="/api/rank/cases":
            category=params.get("category","gain")
            if category not in ("gain","loss","tie"):
                raise ValueError("Unknown effect")
            cases=db.execute("SELECT q,question FROM question WHERE panel=? AND label=? ORDER BY q LIMIT 100",(panel,category))
            return {"cases":[dict(row) for row in cases],
                    "summary":[dict(r) for r in db.execute("SELECT arm,f1,full FROM summary WHERE panel=?",(panel,))]}
        method=params.get("method","graph")
        if method not in ("graph","hybrid"):
            raise ValueError("Unknown method")
        q=params.get("q","")
        context=db.execute("SELECT question,fragment,first_title FROM question WHERE panel=? AND q=?",(panel,q)).fetchone()
        if context is None:
            raise ValueError("Unknown question")
        removed=int(params.get("suppress","-1"))
        options=dict(panel=panel,q=q,method=method,suppress=removed)
        ordered=[dict(row) for row in db.execute(RANK_SQL,options)]
        if removed!=-1 and not any(r["cid"]==removed and r["edge"] for r in ordered):
            raise ValueError("Select one of the observed mentions")
        winner=ordered[0]
        answer=db.execute("SELECT prompt,input_tokens,answer,f1,full FROM response WHERE panel=? AND q=? AND cid=?",(panel,q,winner["cid"])).fetchone()
        coefs=dict(db.execute("SELECT * FROM coef WHERE policy=?",(method,)).fetchone())
        certificate=None
        if removed!=-1:
            reference=list(db.execute(RANK_SQL,dict(options,suppress=-1)))
            target=next(r for r in reference if r["cid"]==removed)
            predicted=certified(reference,target,coefs,0)
            assert predicted==winner["cid"]
            certificate=dict(agrees=True,original=reference[0]["cid"],predicted=predicted)
        return dict(certificate=certificate,context=dict(context),winner=winner["cid"],ordered=ordered,coefficients=coefs,
                    recorded=dict(answer) if answer else None,removed=removed)

