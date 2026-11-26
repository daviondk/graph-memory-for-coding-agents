from support import *
def main():
    raw,hashes,inputs=original();path=D/"source.sqlite3"
    if not path.exists():
        db=sqlite3.connect(path);db.execute("PRAGMA synchronous=FULL");db.execute("CREATE TABLE events(hid INTEGER, seq INTEGER, step INTEGER NOT NULL, cut INTEGER NOT NULL, added TEXT NOT NULL, removed TEXT NOT NULL, PRIMARY KEY(hid,seq)) WITHOUT ROWID")
        with db:
            for h,evs in enumerate(raw):
                db.executemany("INSERT INTO events VALUES(?,?,?,?,?,?)",[(h,i,n,int(bool(c)),json.dumps(a,separators=(",",":")),json.dumps(r,separators=(",",":"))) for i,(n,b,c,a,r) in enumerate(evs,1)])
        db.close()
    cases=[];db=source()
    for h,evs in enumerate(raw):
        chk=list(fetch(db,h,0,len(evs)));assert chk==[(i,bool(c),a,r) for i,(_,_,c,a,r) in enumerate(evs,1)]
        cuts=[i for i,(_,_,cut,_,_) in enumerate(evs,1) if cut]
        for label,idx in [("first",0),("third",min(len(cuts)-1,2))]+([("uncommitted_first",0)] if h<16 else []):
            p=cuts[idx];cases.append({"case":len(cases),"history":h,"n":len(evs),"type":label,"received":p-1,"next":p,"barrier":max([i for i in cuts if i<p],default=0)})
    n=db.execute("SELECT COUNT(*) FROM events").fetchone()[0];assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok";db.close()
    save(D/"plan.json",{"source":sha(path),"source_bytes":path.stat().st_size,"n_events":n,"id_hashes":hashes,"operations":inputs,"cases":cases,"protocol":sha(D/"PROTOCOL_RU.md"),"engine":{f:sha(D/f) for f in ["support.py","prepare.py","worker.py","run.py"]}})
if __name__=="__main__":main()
