"""Read a retained interval using a backward map, with a global-capacity fallback."""
import sys
from pathlib import Path
D=Path(__file__).resolve().parent
STORE=D.parent/"code_store"
sys.path.insert(0,str(STORE))
import storage

# Each disjoint branch exposes a primary-key range to SQLite. A globally crowded case
# must first select winners using the same priority as when reading the complete graph.
SQL="""
SELECT 0,k,z,d,overflow,NULL FROM v WHERE e=?1
UNION ALL
SELECT 1,f.n,NULL,NULL,NULL,f.s FROM v CROSS JOIN f
 WHERE v.e=?1 AND f.e=?1 AND v.overflow=0 AND v.k IS NOT NULL
   AND f.n BETWEEN ?2 AND min(?3,v.k-1)
UNION ALL
SELECT 1,f.n+v.d,NULL,NULL,NULL,f.s FROM v CROSS JOIN f
 WHERE v.e=?1 AND f.e=?1 AND v.overflow=0 AND v.k IS NOT NULL
   AND f.n BETWEEN max(v.z+1,?2-v.d) AND ?3-v.d
UNION ALL
SELECT 2,r.n,NULL,NULL,NULL,r.s FROM v CROSS JOIN r
 WHERE v.e=?1 AND r.e=?1 AND v.overflow=0 AND r.n BETWEEN ?2 AND ?3
UNION ALL
SELECT 3,f.n,NULL,NULL,NULL,f.s FROM v CROSS JOIN f
 WHERE v.e=?1 AND f.e=?1 AND v.overflow=1
UNION ALL
SELECT 4,r.n,NULL,NULL,NULL,r.s FROM v CROSS JOIN r
 WHERE v.e=?1 AND r.e=?1 AND v.overflow=1
"""
ARMS=("lazy_full","inverse","eager_full","eager_index")
def build(paths,inputs):
    eager=storage.initialize(paths[0],"A",inputs)
    lazy=storage.initialize(paths[1],"L",inputs)
    lazy.execute("ALTER TABLE v ADD COLUMN overflow INTEGER NOT NULL DEFAULT 0")
    for e,item in inputs.items():
        storage.transition(eager,"A",e,item)
        storage.transition(lazy,"L",e,item)
        crowded=item["start"] is not None and len(item["base"])+len(item["receipt"])>128
        if crowded:
            lazy.execute("UPDATE v SET overflow=1 WHERE e=?",(e,))
    return eager,lazy

def filtered(pairs,lo,hi):
    return [(n,s) for n,s in pairs if lo<=n<=hi]

def read(dbs,arm,e,item,lo,hi):
    eager,lazy=dbs
    if arm=="eager_index":
        ans=eager.execute("SELECT n,s FROM f WHERE e=? AND n BETWEEN ? AND ? ORDER BY n",(e,lo,hi)).fetchall()
        return ans,len(ans)
    if arm=="lazy_full" or arm=="eager_full":
        db,kind=(lazy,"L") if arm=="lazy_full" else (eager,"A")
        pairs,raw=storage.lookup(db,kind,e,item)
        return filtered(pairs,lo,hi),raw
    assert arm=="inverse"
    raw=lazy.execute(SQL,(e,lo,hi)).fetchall()
    tag,start,end,delta,crowded,_=raw[0]
    assert tag==0
    if crowded:
        base=[(n,s) for kind,n,_,_,_,s in raw[1:] if kind==3]
        seen={n:s for kind,n,_,_,_,s in raw[1:] if kind==4}
        goal=storage.material(item["path"],base,seen,start,end,delta)
        return sorted(filtered(goal.items(),lo,hi)),len(raw)
    # Three index ranges return ordered rows in each branch. Receipts take precedence.
    pairs={n:s for _,n,_,_,_,s in raw[1:]}
    return sorted(pairs.items()),len(raw)

