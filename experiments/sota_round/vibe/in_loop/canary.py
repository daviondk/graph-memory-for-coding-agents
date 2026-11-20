"""Synthetic policy and full HTTP transport canaries. No benchmark result or model generation is used."""
import json
import tempfile
from threading import Thread
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from policy import Delivery,digest,match_read
from transport import post,server

HERE=Path(__file__).resolve().parent
card={"card":"HISTORICAL_CANARY_TOKEN","card_sha256":"a"*64,"source_session_id":"earlier-9","paths":["pkg/file.py"],"repo_directory":"example"}
def add(messages,cid,cmd,obs):
    return messages+[{"role":"assistant","content":None,"tool_calls":[{"id":cid,"type":"function","function":{"name":"bash","arguments":json.dumps({"command":cmd})}}]},
        {"role":"tool","tool_call_id":cid,"content":"<returncode>0</returncode>\n<output>"+obs+"</output>"}]

def main():
    checked={}
    for cmd,obs,expected in [
        ("cat pkg/file.py","content",True),("ls -R","pkg/file.py:12",True),("cat ./pkg/file.py","",True),
        ("head /testbed/pkg/file.py","",True),("head /example/pkg/file.py","",True),("cd /testbed && cat pkg/file.py","<returncode>0</returncode>",True),
        ("cat other/pkg/file.py","",False),("cat file.py","",False),("rg needle","pkg/file.py.bak",False),
        ("echo pkg/file.py","pkg/file.py",False),("cat README && echo pkg/file.py","pkg/file.py",False),
        ("sed -i s/a/b/ pkg/file.py","pkg/file.py",False),("find . -exec bash '{}' +","pkg/file.py",False),
        ("cat pkg/file.py > a","",False),("cat $(echo pkg/file.py)","",False),
        ("ls || cat pkg/file.py","",False),("cd pkg/file.py && ls","<returncode>0</returncode>",False),
        ("rg -n needle","./pkg/file.py",True),("sed -n 2,8p pkg/file.py","",True),
        ("sort pkg/file.py","pkg/file.py",False)]:
        assert bool(match_read(cmd,obs,card)[0])==expected,(cmd,obs)
    checked["path_cases"]=20
    base=[{"role":"user","content":"The target or a user's text could mention pkg/file.py"}]
    d=Delivery("path_trigger",card)
    ordered=[base,add(base,"a","echo pkg/file.py","pkg/file.py")]
    ordered.append(add(ordered[-1],"b","grep -n token .","pkg/file.py:42"))
    ordered.append(add(ordered[-1],"c","cat pkg/file.py","value"))
    for i,msgs in enumerate(ordered):
        body={"messages":msgs,"tools":[{"type":"function"}],"temperature":.5}
        source_hash=digest(body)
        forwarded,event=d.apply(body)
        assert event["injected"]==(i==2) and source_hash==digest(body)
        assert len(forwarded["messages"])==len(msgs)+int(i==2)
        if i==2:assert forwarded["messages"][-1]["content"].count("HISTORICAL_CANARY_TOKEN")==1
        if i==3:assert event["evicted"] and digest(body)==digest(forwarded)
    repeat=d.apply({"messages":ordered[-1]})[1]
    assert not repeat["injected"] and not repeat["new_events"]
    orphan=Delivery("fixed_third",card).apply({"messages":base+[{"role":"tool","tool_call_id":"fake","content":"pkg/file.py"}]})[1]
    assert orphan["observed_total"]==0
    checked.update(immutable_copy=True,one_shot=True,stale_excluded=True,orphan_excluded=True)

    seen=[]
    class Fake(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            obj=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path=="/apply-template":data={"prompt":json.dumps(obj["messages"],sort_keys=True)}
            elif self.path=="/tokenize":data={"tokens":list(range(len(obj["content"])))}
            else:
                assert self.path=="/replicate/1/v1/chat/completions"
                seen.append(obj)
                data={"id":f"fake-{len(seen)}","usage":{"prompt_tokens":len(json.dumps(obj["messages"],sort_keys=True)),"completion_tokens":2}}
            raw=json.dumps(data).encode()
            self.send_response(200);self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
    backend=ThreadingHTTPServer(("127.0.0.1",0),Fake)
    Thread(target=backend.serve_forever,daemon=True).start()
    dest="http://127.0.0.1:"+str(backend.server_port)
    with tempfile.TemporaryDirectory() as tmp:
        prot={"methods":["path_trigger","fixed_third"],"planned_seeds":[0,1],"solver":"openai/fake"}
        relay=server({"example-10":card},prot,Path(tmp),dest,dest,0)
        Thread(target=relay.serve_forever,daemon=True).start()
        before=base
        url="http://127.0.0.1:"+str(relay.server_port)+"/episode/example-10/fixed_third/1/"+("b"*32)+"/v1/chat/completions"
        for i in range(5):
            if i:before=add(before,f"id-{i}","echo anything","nothing")
            status,reply=post(url,{"model":"fake","messages":before,"tools":[]})
            assert status==200 and json.loads(reply)["id"]==f"fake-{i+1}"
            assert any("HISTORICAL_CANARY_TOKEN" in (m.get("content") or "") for m in seen[-1]["messages"])==(i==3)
        events=[json.loads(s) for s in (Path(tmp)/"intervention_events.jsonl").read_text().splitlines()]
        assert [e["observed_total"] for e in events]==list(range(5))
        assert [e["injected"] for e in events]==[False,False,False,True,False]
        assert events[-2]["native_count_difference"]==0 and events[-2]["template_delta_tokens"]>0 and events[-1]["evicted"]
        relay.shutdown();relay.server_close()
    backend.shutdown();backend.server_close()
    checked.update(mock_http_events=5,fixed_exact_third=True,raw_reply_transparent=True,token_delta_crosscheck=True)
    (HERE/"canary_results.json").write_text(json.dumps(checked,indent=2)+"\n",encoding="utf8")
    print(checked)
if __name__=="__main__":main()
