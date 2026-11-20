"""Plain JSON-RPC client for released octofs' native stdio service."""
import gzip
import json
from pathlib import Path
import subprocess
import time
from acquire import D, V, h

def wire(message):
    return (json.dumps(message,ensure_ascii=False,separators=(",",":"))+"\n").encode()
class Client:
    def __init__(self, root, session, epoch=0):
        self.root=root
        self.id=0
        self.rows=[]
        self.stderr=open(root/("stderr-"+session+".log"),"wb")
        self.proc=subprocess.Popen([str(V/"octofs.exe"),"mcp","--path",str(root)],
                    cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr)
        capabilities={} if epoch is None else {"experimental":{"session":{"session_id":session,"context_epoch":epoch,"workdir":str(root)}}}
        self.ask("initialize",{"protocolVersion":"2025-11-25","capabilities":capabilities,"clientInfo":{"name":"local-observation-test","version":"1"}})
        self.proc.stdin.write(wire({"jsonrpc":"2.0","method":"notifications/initialized"}));self.proc.stdin.flush()
    def ask(self,method,params):
        self.id+=1;req={"jsonrpc":"2.0","id":self.id,"method":method,"params":params}
        payload=wire(req);start=time.perf_counter_ns()
        self.proc.stdin.write(payload);self.proc.stdin.flush()
        while True:
            raw=self.proc.stdout.readline()
            if not raw:raise RuntimeError("EOF "+str(self.proc.poll()))
            response=json.loads(raw)
            if response.get("id")==self.id:break
        row={"request":req,"response":response,"request_bytes":len(payload),"response_bytes":len(raw),"elapsed_ns":time.perf_counter_ns()-start}
        self.rows.append(row)
        if "error" in response:raise ValueError(response)
        return response["result"],row
    def view(self,name,**params):
        res,row=self.ask("tools/call",{"name":"view","arguments":{"path":name,**params}})
        if res.get("isError"):raise ValueError(res)
        txt="\n".join(x["text"] for x in res["content"] if x["type"]=="text")
        return txt,row
    def close(self):
        self.proc.stdin.close();self.proc.wait(timeout=7);self.stderr.close()
def dumpgz(path,rows):
    path.write_bytes(gzip.compress(json.dumps(rows,ensure_ascii=False,separators=(",",":")).encode(),mtime=0))
if __name__=="__main__":
    s=D/"scratch";s.mkdir(exist_ok=True)
    p=s/"calibration.txt";p.write_bytes("".join(f"l{i}\n" for i in range(1,21)).encode())
    c=Client(s,"sanity")
    a,_=c.view(p.name);b,_=c.view(p.name)
    ranged,_=c.view(p.name,start=3,end=4)
    p.write_bytes(p.read_bytes().replace(b"l10\n",b"L10\n"))
    d,_=c.view(p.name);f,_=c.view(p.name,full=True)
    print(repr(a[:80]),repr(b[:140]),repr(ranged),repr(d),repr(f[:35]))
    assert len(a.splitlines())==20 and b.startswith("[unchanged since") and ranged.startswith("3:74|l3\n4:87|l4")
    assert d.startswith("[changed since your last view: 1 hunk(s), 20 lines now]") and len(d.splitlines())==9
    assert any(x.startswith("-") and "(1 line)" in x for x in d.splitlines()) and any(x.startswith("+") and "|L10" in x for x in d.splitlines())
    assert len(f.splitlines())==20 and "|L10" in f
    dumpgz(D/"upstream_example.json.gz",c.rows);c.close()
