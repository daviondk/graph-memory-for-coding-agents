"""Interleave matched warm point lookups on the same persisted SQLite catalogs."""
from itertools import permutations
import math
import platform
from pathlib import Path
import shutil
import sqlite3
import statistics
import sys
import tempfile
from time import perf_counter_ns
import numpy as np
from study import HERE,SOURCE,raw,save
from sql_check import DB_SCHEMA

FORMULA="{0}*cosine + {1}/(1.0+question_rank) + {2}/(1.0+snippet_rank) + {3}/(1.0+dense_rank) + {4}*mention"
NAMES=["DENSE","GRAPH","INDEXED_GRAPH"]
SEED=510927


def start(path):
    db=sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA cache_size=-32768")
    return db


def main():
    root=Path("D:/CodexResearch/x20-r51-pairwise-completion")
    root.mkdir(exist_ok=True)
    model=raw(HERE/"model.json")
    coef=[v/s for v,s in zip(model["graph"]["coef"],model["scale"])]
    expression=FORMULA.format(*(repr(x) for x in coef))
    parameters={f"c{i}":x for i,x in enumerate(coef)}
    bound_expression=FORMULA.format(*[":c"+str(i) for i in range(5)])
    create="CREATE INDEX graph_score ON candidates(qid,("+expression+") DESC,dense_rank,candidate)"
    dense_query="SELECT candidate FROM candidates INDEXED BY dense_order WHERE qid=:q ORDER BY dense_rank LIMIT 1"
    graph_query="SELECT candidate FROM candidates INDEXED BY dense_order WHERE qid=:q ORDER BY ("+bound_expression+") DESC,dense_rank LIMIT 1"
    indexed_query="SELECT candidate FROM candidates INDEXED BY graph_score WHERE qid=:q ORDER BY ("+expression+") DESC,dense_rank LIMIT 1"
    sqls=[dense_query,graph_query,indexed_query]
    base_labels=raw(HERE/"decisions.json.gz")
    base_labels["hotpot"]=raw(HERE/"hotpot-decisions.json.gz")
    ground={}
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        prefix=Path(tmp)
        base=prefix/"base.sqlite"
        con=start(base)
        con.execute("PRAGMA page_size=4096")
        con.execute(DB_SCHEMA)
        count=0
        for p,rows in base_labels.items():
            path=HERE.parent/"transfer" if p=="hotpot" else SOURCE/p
            lex=raw(path/"lex-orders.json.gz");ranks=raw(path/"orders.json.gz")
            batch=[]
            for q,r in ranks.items():
                key=p+"/"+q
                ground[key]=(rows[q]["dense"],rows[q]["graph"])
                for j,i in enumerate(r["order"]):
                    k=str(i)
                    batch.append((key,i,j,r["scores"][k],lex[q]["question_rank"][k],
                                  lex[q]["snippet_rank"][k],int(i in r["edges"])))
            count+=len(batch)
            con.executemany("INSERT INTO candidates VALUES(?,?,?,?,?,?,?)",batch)
        con.execute("CREATE INDEX dense_order ON candidates(qid,dense_rank,candidate)")
        con.commit()
        con.close()
        base_bytes=base.stat().st_size
        build=[]
        for i in range(3):
            path=prefix/f"build{i}.sqlite"
            shutil.copyfile(base,path)
            db=start(path)
            t0=perf_counter_ns()
            db.execute(create)
            db.commit()
            build.append(perf_counter_ns()-t0)
            db.close()
        both_bytes=path.stat().st_size
        db=start(path)
        qs=sorted(ground); n=len(qs)
        plans=[]
        for j,query in enumerate(sqls):
            plans.append(db.execute("EXPLAIN QUERY PLAN "+query,{**parameters,"q":qs[0]}).fetchall())
            for q in qs:
                assert db.execute(query,{**parameters,"q":q}).fetchone()[0]==ground[q][int(j!=0)]
        weights={**parameters}
        orders=list(permutations(range(3)))
        rng=np.random.default_rng(SEED); timing={}
        rankset=np.arange(n);rng.shuffle(rankset)
        # A query gets every ordering once; shuffle across queries and rounds to distribute position effects.
        for round_index in range(6):
            q_order=rng.permutation(n)
            for ix in q_order:
                q=qs[ix];bind={**weights,"q":q}
                elapsed=[0,0,0]
                for j in orders[(int(rankset[ix])+round_index)%6]:
                    t0=perf_counter_ns()
                    got=db.execute(sqls[j],bind).fetchone()
                    elapsed[j]=perf_counter_ns()-t0
                    assert got[0]==ground[q][int(j!=0)]
                timing.setdefault(q,[]).append(elapsed)
        try:
            stat=db.execute("SELECT name,SUM(pgsize) FROM dbstat GROUP BY name ORDER BY name").fetchall()
        except sqlite3.OperationalError:
            stat=None
        db.close()
    arr=np.asarray([timing[q] for q in qs],dtype=float)
    means=arr.mean(axis=(0,1));meds=np.median(arr,axis=(0,1));perq=arr.mean(1)
    samples=np.random.default_rng(SEED+1)
    dist=[]
    for _ in range(100):
        block=perq[samples.integers(n,size=(100,n))].mean(1)
        dist.extend(block[:,1]-block[:,2])
    saved=float(means[1]-means[2])
    save("sql-timings.json.gz",timing)
    save("sql-cost.json",{"engine":sqlite3.sqlite_version,"platform":platform.platform(),"python":sys.version,
          "seed":SEED,"repetitions":6,"n_queries":n,"n_candidates":count,"n_timed":int(arr.size),
          "queries":dict(zip(NAMES,sqls)),"index":create,"plans":dict(zip(NAMES,plans)),
          "raw_weights":coef,"scores_additive_constant_omitted":-sum(a*b for a,b in zip(coef,model["mean"])),
          "index_build_ns":build,"database_bytes_before":base_bytes,"database_bytes_after":both_bytes,
          "extra_bytes":both_bytes-base_bytes,"dbstat":stat,
          "mean_us":dict(zip(NAMES,(means/1e3).tolist())),"median_us":dict(zip(NAMES,(meds/1e3).tolist())),
          "saving_per_read_us":saved/1e3,"ci95_saving_us":(np.quantile(dist,[.025,.975])/1e3).tolist(),
          "amortization_read_count":math.ceil(statistics.mean(build)/saved) if saved>0 else None})
    print("Measured",arr.size,"matched lookups. Mean us",means/1e3,"incremental bytes",both_bytes-base_bytes)


if __name__=="__main__":
    main()
