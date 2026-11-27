"""Small loopback interface carrying indexed lookups, with independent endpoint ledgers."""
from collections import Counter
from contextlib import contextmanager, closing
import hashlib
import socket
import sqlite3
import struct
import threading
from time import sleep, perf_counter_ns

MAX_FRAME=2**20
POSTING=1
BODIES=2
POST_SQL="SELECT js FROM posting WHERE f=?"
BODY_START="SELECT members FROM event WHERE j IN ("
BODY_END=") ORDER BY j"


def vint(value):
    if not isinstance(value,int) or value<0:raise ValueError("expected a nonnegative integer")
    out=bytearray()
    while value>=128:
        out.append(128|(value&127));value>>=7
    out.append(value)
    return bytes(out)


class Cursor:
    def __init__(self,b):
        self.b=b
        self.at=0
    def number(self):
        v=0
        for shift in range(0,35,7):
            if self.at>=len(self.b):raise ValueError("incomplete integer")
            x=self.b[self.at];self.at+=1;v|=(x&127)<<shift
            if x<128:return v
        raise ValueError("oversized integer")
    def blob(self):
        size=self.number();end=self.at+size
        if end>len(self.b):raise ValueError("incomplete blob")
        b=self.b[self.at:end];self.at=end;return b
    def done(self):
        if self.at!=len(self.b):raise ValueError("unexpected trailing data")


class Ledger:
    def __init__(self):
        self.req=hashlib.sha256();self.res=hashlib.sha256()
        self.counts=Counter()
    def record(self,req,res):
        self.req.update(req);self.res.update(res)
        op="posting" if req[4]==POSTING else "bodies"
        for k,n in ((op+"_req_bytes",len(req)),(op+"_resp_bytes",len(res)),(op+"_calls",1)):
            self.counts[k]+=n
    def seal(self):
        return dict(counts=dict(self.counts),request_sha=self.req.hexdigest(),response_sha=self.res.hexdigest())


def read_exact(sock,length,eof=False):
    buf=bytearray()
    while len(buf)<length:
        chunk=sock.recv(length-len(buf))
        if not chunk:
            if eof and not buf:return None
            raise EOFError("incomplete TCP frame")
        buf.extend(chunk)
    return bytes(buf)


def receive(sock,eof=False):
    header=read_exact(sock,4,eof)
    if header is None:return None
    n=struct.unpack("!I",header)[0]
    if not 0<n<=MAX_FRAME:raise ValueError("invalid frame length")
    return header+read_exact(sock,n)


def frame(payload):
    if not 0<len(payload)<=MAX_FRAME:raise ValueError("invalid payload length")
    return struct.pack("!I",len(payload))+payload


def lookup(db,req):
    op=req[4];cursor=Cursor(req[5:])
    if op==POSTING:
        k=cursor.number()-1;cursor.done()
        rows=db.execute(POST_SQL,(k,)).fetchall()
    elif op==BODIES:
        n=cursor.number()
        if not 1<=n<=400:raise ValueError("invalid body count")
        keys=[cursor.number() for _ in range(n)];cursor.done()
        if any(a>=b for a,b in zip(keys,keys[1:])):raise ValueError("unsorted body IDs")
        sql=BODY_START+",".join("?" for _ in keys)+BODY_END
        rows=db.execute(sql,keys).fetchall()
        if len(rows)!=n:raise LookupError("source row not found")
    else:raise ValueError("unknown operation")
    return frame(b"\0"+vint(len(rows))+b"".join(vint(len(v))+v for v, in rows))


class Result:
    def __init__(self,rows):self.rows=rows
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows


class Remote:
    def __init__(self,sock):
        self.sock=sock;self.ledger=Ledger()
    def execute(self,sql,params):
        if sql==POST_SQL and len(params)==1:
            payload=bytes([POSTING])+vint(params[0]+1)
        elif 0<len(params)<=400 and sql==BODY_START+",".join("?" for _ in params)+BODY_END:
            payload=bytes([BODIES])+vint(len(params))+b"".join(vint(k) for k in params)
        else:raise ValueError("unsupported local adapter operation")
        req=frame(payload);self.sock.sendall(req)
        res=receive(self.sock)
        if res[4]!=0:raise RuntimeError("fixed-operation service returned an error")
        cursor=Cursor(res[5:]);n=cursor.number()
        if n>400:raise ValueError("invalid output count")
        rows=[(cursor.blob(),) for _ in range(n)];cursor.done()
        self.ledger.record(req,res)
        return Result(rows)


@contextmanager
def service(path,delay_ms):
    ready=threading.Event();errors=[];server_log=Ledger();server_timing=Counter()
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    listener.bind(("127.0.0.1",0));listener.listen(1);listener.settimeout(20)
    def serve():
        try:
            with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,isolation_level=None)) as db:
                db.execute("PRAGMA query_only=ON")
                ready.set()
                with closing(listener.accept()[0]) as conn:
                    conn.settimeout(20);conn.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    while True:
                        req=receive(conn,eof=True)
                        if req is None:break
                        res=lookup(db,req)
                        if delay_ms:
                            start=perf_counter_ns();sleep(delay_ms/1000)
                            server_timing["actual_emulated_sleep_ns"]+=perf_counter_ns()-start
                        conn.sendall(res);server_log.record(req,res)
        except BaseException as err:errors.append(repr(err))
        finally:ready.set()
    t=threading.Thread(target=serve);t.start()
    try:
        if not ready.wait(20) or errors:raise RuntimeError(errors)
        with closing(socket.create_connection(listener.getsockname(),timeout=20)) as client:
            client.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
            rpc=Remote(client)
            yield rpc,server_log,server_timing
    finally:
        t.join(21);listener.close()
        if t.is_alive() or errors:raise RuntimeError((t.is_alive(),errors))
