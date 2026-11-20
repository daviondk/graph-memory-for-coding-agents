"""Positive-control smoke test of the author's distinct MCP read_file API over stdio."""
from exercise import *
import io,zipfile,urllib.request
def main():
    api="https://api.github.com/repos/ojuschugh1/sqz/releases/tags/v2.2.0"
    rel=json.load(urllib.request.urlopen(api))
    asset=next(a for a in rel["assets"] if a["name"]=="sqz-mcp-v2.2.0-x86_64-pc-windows-msvc.zip")
    b=urllib.request.urlopen(asset["browser_download_url"]).read();assert "sha256:"+sha(b)==asset["digest"]
    with zipfile.ZipFile(io.BytesIO(b)) as z:exe=z.read(next(n for n in z.namelist() if n.endswith("sqz-mcp.exe")))
    binary=ROOT/"vendor/sqz-mcp.exe";binary.write_bytes(exe)
    src=load(ROOT/"control.json")["source"];full,_,excerpt=src
    with tempfile.TemporaryDirectory(dir=ROOT/"scratch") as directory:
        dd=Path(directory);f=dd/"observation.py";f.write_bytes(full.encode())
        env={**os.environ,"SQZ_DB_PATH":str(dd/"session.db"),"SQZ_QUIET":"1"}
        r=subprocess.Popen([str(binary),"--transport","stdio","--preset-dir",str(dd)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=dd,env=env)
        trace=[]
        def rpc(i,method,params):
            q=dict(jsonrpc="2.0",id=i,method=method,params=params)
            r.stdin.write(json.dumps(q).encode()+b"\n");r.stdin.flush()
            out=json.loads(r.stdout.readline());trace.append(dict(request=q,response=out));assert "error" not in out,out
            return out["result"]
        rpc(1,"initialize",dict(protocolVersion="2024-11-05",capabilities={},clientInfo=dict(name="offline-check",version="1")))
        def call(i,name,args):
            res=rpc(i,"tools/call",dict(name=name,arguments=args));assert not res.get("isError"),res
            return res["content"][0]["text"]
        first=call(2,"sqz_read_file",dict(path=str(f)));second=call(3,"sqz_read_file",dict(path=str(f)))
        third=call(4,"sqz_read_file",dict(path=str(f),offset=11,limit=22))
        verifier=[]
        for i,(label,text,expected) in enumerate([("whole",second,full),("slice",third,excerpt)]):
            ref=re.search(r"§ref:[^§]+§",text)
            if ref:
                expanded=call(5+i,"expand",dict(prefix=ref[0]))
                verifier.append(dict(case=label,ref=ref[0],exact_body=expanded.partition("\n")[2]==expected,contains=expected in expanded,tail=expanded[-40:]))
            else:verifier.append(dict(case=label,ref=None,repeats_literal=expected in text))
        r.stdin.close();exitcode=r.wait(timeout=5)
        put(ROOT/"mcp-control.json",dict(executable_sha=sha(exe),release_sha=sha(b),url=asset["browser_download_url"],trace=trace,
                checks=verifier,first_contains=full in first,stderr=r.stderr.read().decode(),exit=exitcode))
        print(json.dumps(verifier,ensure_ascii=True))
if __name__=="__main__":main()
