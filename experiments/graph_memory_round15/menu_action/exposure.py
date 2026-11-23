"""Input-only readout of the specific additional memory records available in the chosen experiments."""
from menu import D,F,LOCK,h,lock,read,put

def main():
    assert h((F/"forecast.lock.json").read_bytes())==LOCK
    lock(F/"forecast.lock.json");lock(D/"assignment.json")
    by_id={u["id"]:u for seq in read(F/"frontier_inputs.json.gz").values() for u in seq}
    rows=[]
    for q in read(D/"menus.json.gz"):
        f=by_id[q["id"]];unread=set(f["frontier"])-set(f["viewed"])
        rows.append(dict(id=q["id"],iid=q["iid"],panel=q["panel"],unread_pool=len(unread),
                         unread_offered=sorted(unread&set(q["menus"]["flat_union"])),frontier_bytes=f["frontier_bytes"],
                         opened_guard_bytes=f["opened_bytes"]))
    put(D/"exposure.json",dict(rows=rows,any_unread_pool=sum(bool(r["unread_pool"]) for r in rows),
            any_unread_offered=sum(bool(r["unread_offered"]) for r in rows),frontier_bytes=sum(r["frontier_bytes"] for r in rows),
            opened_guard_bytes=sum(r["opened_guard_bytes"] for r in rows)))

if __name__=="__main__":main()
