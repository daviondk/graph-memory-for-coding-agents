"""A state-synchronized exact top-eight API with one binary request and response per query."""
from collections import Counter
from contextlib import contextmanager,closing
from hashlib import sha256
import socket
import sqlite3
from threading import Event,Thread
from time import sleep,perf_counter_ns

from wire import Cursor,vint,frame,receive
from lazy_reader import best,unpack

TOP=3


def mapping(entries):
    result=bytearray(vint(len(entries)))
    prev=-1
    for i,n in sorted(entries.items()):
        result.extend(vint(i-prev-1));result.extend(vint(n));prev=i
    return bytes(result)


def payload(f,tie,last):
    # File IDs are allocated densely. The graph omits single-file commits.
    n=len(tie)
    assert not tie or (min(tie)==0 and max(tie)==n-1)
    present={i:v for i,v in tie.items() if v}
    changes={i:present.get(i,0) for i in set(present)|set(last) if present.get(i,0)!=last.get(i,0)}
    full=b"\x00"+mapping(present);delta=b"\x01"+mapping(changes)
    chosen=full if len(full)<=len(delta) else delta
    return frame(bytes((TOP,))+vint(f+1)+vint(n)+chosen),present


class Seal:
    def __init__(self):
        self.tx=sha256();self.rx=sha256()
        self.counts=Counter()
    def register(self,req,res):
        self.tx.update(req);self.rx.update(res)
        self.counts.update(req=len(req),reply=len(res),calls=1)
    def seal(self):
        return self.tx.hexdigest(),self.rx.hexdigest(),dict(self.counts)


class RankClient:
    def __init__(self,sock):
        self.socket=sock;self.ledger=Seal();self.last={}
    def rank(self,f,tie):
        req,present=payload(f,tie,self.last)
        self.socket.sendall(req)
        res=receive(self.socket)
        assert res[4]==0
        cur=Cursor(res[5:]);n=cur.number()
        assert n<=8
        rows=[(cur.number(),cur.number()) for _ in range(n)]
        cur.done()
        self.ledger.register(req,res)
        self.last=present
        return rows,(len(req),len(res),len(frame(bytes((TOP,))+vint(f+1))))


def answer(db,req,old):
    assert req[4]==TOP
    c=Cursor(req[5:]);f=c.number()-1;files=c.number()
    mode=c.b[c.at];c.at+=1
    assert mode in (0,1)
    recent=old.copy() if mode else Counter()
    previous=-1
    for _ in range(c.number()):
        i=previous+c.number()+1;n=c.number()
        assert previous<i<files and n<=32
        if n:recent[i]=n
        else:recent.pop(i,None)
        previous=i
    c.done()
    assert all(0<=i<files for i in recent)
    prior=sorted(range(files),key=lambda i:(-recent[i],i))[:9]
    result=db.execute("SELECT js FROM posting WHERE f=?",(f,)).fetchone()
    counts=Counter();source=Counter()
    if result:
        js=unpack(result[0]);source["posting_bytes"]=len(result[0])
        for start in range(0,len(js),400):
            batch=js[start:start+400]
            stmt="SELECT members FROM event WHERE j IN ("+",".join("?" for _ in batch)+")"
            for b, in db.execute(stmt,batch):
                source["body_bytes"]+=len(b);counts.update(unpack(b))
    rank=best(counts,f,recent,prior)
    res=frame(b"\0"+vint(len(rank))+b"".join(vint(i)+vint(v) for i,v in rank))
    return res,recent,source


@contextmanager
def rank_service(path,lag):
    server=Seal();wait=Counter();errors=[];ready=Event();source=Counter()
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listener.bind(("127.0.0.1",0));listener.listen(1);listener.settimeout(20)
    def serve():
        try:
            with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,isolation_level=None)) as db:
                db.execute("PRAGMA query_only=ON");ready.set();state=Counter()
                with closing(listener.accept()[0]) as conn:
                    conn.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1);conn.settimeout(20)
                    while True:
                        req=receive(conn,eof=True)
                        if req is None:break
                        res,state,local=answer(db,req,state);source.update(local)
                        if lag:
                            start=perf_counter_ns();sleep(lag/1000)
                            wait["actual_emulated_sleep_ns"]+=perf_counter_ns()-start
                        conn.sendall(res);server.register(req,res)
        except BaseException as e:errors.append(repr(e))
        finally:ready.set()
    thread=Thread(target=serve);thread.start()
    try:
        assert ready.wait(20) and not errors
        with closing(socket.create_connection(listener.getsockname(),timeout=20)) as client:
            client.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            yield RankClient(client),server,wait,source
    finally:
        thread.join(21);listener.close()
        if thread.is_alive() or errors:raise RuntimeError((thread.is_alive(),errors))
