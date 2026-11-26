"""Count sqlite3_stmt_status VM steps on the actual sorted query while verifying every packet."""
import argparse
import ctypes as ct
from ctypes.util import find_library
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import _sqlite3

from bench import HERE, PLANS, Controller, Rows, initialize, read_json, workload, write_json

COUNTERS = {"fullscan_steps":1, "sort_ops":2, "vm_steps":4, "reprepare":5, "executions":6}

class Native:
    """Read-only SQLite C connection on the same committed WAL index as the writer."""
    def __init__(self, path):
        windows = Path(_sqlite3.__file__).with_name("sqlite3.dll")
        self.lib = ct.CDLL(str(windows) if windows.exists() else find_library("sqlite3"))
        ptr, outptr, integer, string = ct.c_void_p, ct.POINTER(ct.c_void_p), ct.c_int, ct.c_char_p
        specs = {
            "open_v2":([string,outptr,integer,string],integer),
            "libversion":([],string), "errmsg":([ptr],string), "close":([ptr],integer),
            "prepare_v2":([ptr,string,integer,outptr,outptr],integer),
            "bind_text":([ptr,integer,string,integer,ptr],integer),
            "bind_int":([ptr,integer,integer],integer),
            "step":([ptr],integer), "column_int":([ptr,integer],integer),
            "stmt_status":([ptr,integer,integer],integer), "reset":([ptr],integer),
            "finalize":([ptr],integer)}
        for name,(args,result) in specs.items():
            fn=getattr(self.lib,"sqlite3_"+name)
            fn.argtypes=args
            fn.restype=result
        assert self.lib.sqlite3_libversion().decode()==sqlite3.sqlite_version
        self.handle=ptr()
        self.check(self.lib.sqlite3_open_v2(str(path).encode("utf8"),ct.byref(self.handle),1,None))
        self.stmts={}
        self.counts={k:0 for k in (*COUNTERS,"returned_rows")}

    def check(self, rc):
        if rc:
            raise RuntimeError((rc,self.lib.sqlite3_errmsg(self.handle).decode()))

    def execute(self, sql, params):
        if sql not in self.stmts:
            stmt=ct.c_void_p()
            self.check(self.lib.sqlite3_prepare_v2(self.handle,sql.encode(),-1,ct.byref(stmt),None))
            self.stmts[sql]=stmt
        stmt=self.stmts[sql]
        for j,param in enumerate(params,1):
            if isinstance(param,str):
                self.check(self.lib.sqlite3_bind_text(stmt,j,param.encode(),-1,ct.c_void_p(-1)))
            else:
                self.check(self.lib.sqlite3_bind_int(stmt,j,param))
        rows=Rows()
        while True:
            rc=self.lib.sqlite3_step(stmt)
            if rc==101:
                break
            if rc!=100:
                self.check(rc)
            rows.append((self.lib.sqlite3_column_int(stmt,0),self.lib.sqlite3_column_int(stmt,1)))
        for k,code in COUNTERS.items():
            self.counts[k] += self.lib.sqlite3_stmt_status(stmt,code,1)
        self.counts["returned_rows"] += len(rows)
        self.check(self.lib.sqlite3_reset(stmt))
        return rows

    def close(self):
        for stmt in self.stmts.values():
            self.check(self.lib.sqlite3_finalize(stmt))
        self.check(self.lib.sqlite3_close(self.handle))

def main(scratch,check):
    work=workload(read_json(HERE.parent/"commits.json.gz"))
    reference=read_json(HERE.parent/"results.json")["results"]["32"]["projects"]
    groups={}
    with TemporaryDirectory(dir=scratch) as tmp:
        for q,(paths,oracle) in work.items():
            filename=Path(tmp)/(q.replace("/","_")+".sqlite")
            db,graph=initialize(str(filename),"wal",paths)
            runs={}
            for plan in PLANS:
                mode="classic" if plan.startswith("classic") else "partial"
                native=Native(filename)
                controller=Controller(native,int(plan[len(mode):]),mode)
                assert controller.state[0][:8]==oracle[0]
                cold=dict(native.counts)
                runs[plan]=(controller,native,cold)
            for t in range(64,len(paths)):
                dirty,_=graph.apply(paths[t],paths[t-32],t)
                db.commit()
                for controller,native,cold in runs.values():
                    assert controller.step(dirty)==oracle[t-63]
            groups[q]={}
            for plan,(_,native,cold) in runs.items():
                warm={k:v-cold[k] for k,v in native.counts.items()}
                for phase,value in (("warm",warm),("cold",cold)):
                    assert [value["executions"],value["returned_rows"]]==reference[q]["costs"][plan][phase]
                    assert value["sort_ops"]==0 and value["fullscan_steps"]==0
                groups[q][plan]={"cold":cold,"warm":warm}
                native.close()
            db.close()
    sums={}
    for plan in PLANS:
        sums[plan]={phase:{k:sum(s[plan][phase][k] for s in groups.values())
                    for k in next(iter(groups.values()))[plan][phase]} for phase in ("warm","cold")}
    result={"sqlite":sqlite3.sqlite_version,"projects":groups,"total":sums,"counter_codes":COUNTERS}
    write_json(HERE/"vm-steps.json",result,check)
    print({p:v["warm"] for p,v in sums.items()})

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--scratch",type=Path,required=True)
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    main(args.scratch,args.verify)
