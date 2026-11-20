"""Local-only transport for an ephemeral historical card; the native agent and model are unchanged."""
from __future__ import annotations

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from policy import Delivery,digest

HERE=Path(__file__).resolve().parent
ROUTE=re.compile(r"^/episode/([a-z0-9_-]+)/([a-z_]+)/([01])/([a-f0-9]{32})/v1/chat/completions$")


def post(url,obj,timeout=1500):
    raw=json.dumps(obj,ensure_ascii=False).encode()
    req=Request(url,data=raw,headers={"Content-Type":"application/json","Authorization":"Bearer local"})
    try:
        with urlopen(req,timeout=timeout) as res:
            return res.status,res.read()
    except HTTPError as exc:
        return exc.code,exc.read()


def count_tokens(native,body):
    template=dict(body)
    template["chat_template_kwargs"]={**body.get("chat_template_kwargs",{}),"enable_thinking":False}
    code,raw=post(native+"/apply-template",template,20)
    if code!=200:raise RuntimeError("apply-template HTTP "+str(code))
    prompt=json.loads(raw)["prompt"]
    return tokenize(native,prompt,True)


def tokenize(native,string,parse_special):
    status,raw=post(native+"/tokenize",{"content":string,"add_special":False,"parse_special":parse_special},20)
    if status!=200:raise RuntimeError("tokenize HTTP "+str(status))
    return len(json.loads(raw)["tokens"])


def server(cards,protocol,store,destination,native,port):
    states={}
    lock=threading.Lock()
    events=store/"intervention_events.jsonl"
    store.mkdir(parents=True,exist_ok=True)
    def append(record):
        with lock,events.open("a",encoding="utf8") as f:
            f.write(json.dumps(record,ensure_ascii=False)+"\n")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):return
        def emit(self,status,raw):
            self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            self.emit(200 if self.path=="/health" else 404,b'{"ready":true}' if self.path=="/health" else b"{}")
        def do_POST(self):
            match=ROUTE.fullmatch(self.path)
            if not match:return self.emit(404,b"{}")
            iid,arm,seed,attempt=match.groups()
            if iid not in cards or arm not in protocol["methods"] or int(seed) not in protocol["planned_seeds"]:
                return self.emit(403,b"{}")
            try:
                started=time.time()
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if body.get("model")!=protocol["solver"].removeprefix("openai/") or not isinstance(body.get("messages"),list) or body.get("stream"):
                    return self.emit(400,b'{"error":"unexpected model, messages or streaming"}')
                session=(iid,arm,seed,attempt)
                with lock:
                    if session not in states:states[session]=Delivery(arm,cards[iid])
                    forwarded,event=states[session].apply(body)
                event.update(iid=iid,arm=arm,seed=int(seed),attempt=attempt,epoch=started)
                if event["injected"]:
                    # Save the exact paired native inputs for independent token/eviction audits.
                    folder=store/"payloads";folder.mkdir(exist_ok=True)
                    name=f"{iid}-{arm}-{seed}-{attempt}-r{event['request']}.json"
                    (folder/name).write_text(json.dumps({"incoming":body,"forwarded":forwarded},ensure_ascii=False),encoding="utf8")
                    event["payload_file"]=name
                    try:
                        event["baseline_template_tokens"]=count_tokens(native,body)
                        event["forwarded_template_tokens"]=count_tokens(native,forwarded)
                        event["template_delta_tokens"]=event["forwarded_template_tokens"]-event["baseline_template_tokens"]
                        event["card_content_tokens"]=tokenize(native,cards[iid]["card"],False)
                    except Exception as exc:
                        event["tokenization_error"]=repr(exc)
                assert digest(body["messages"])==event["incoming_sha256"]
                code,raw=post(destination+f"/replicate/{seed}/v1/chat/completions",forwarded)
                event.update(http_status=code,seconds=time.time()-started)
                if code==200:
                    result=json.loads(raw)
                    event["response_id"]=result["id"]
                    event["usage"]=result["usage"]
                    if event["injected"] and "forwarded_template_tokens" in event:
                        event["native_count_difference"]=result["usage"]["prompt_tokens"]-event["forwarded_template_tokens"]
                append(event);self.emit(code,raw)
            except Exception as exc:
                append(dict(iid=iid,arm=arm,seed=seed,attempt=attempt,error=repr(exc),epoch=time.time()))
                self.emit(502,json.dumps({"error":str(exc)}).encode())
    return ThreadingHTTPServer(("127.0.0.1",port),Handler)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--store",type=Path,required=True)
    a=p.parse_args()
    cards=json.loads((HERE/"cards.json").read_text(encoding="utf8"))
    protocol=json.loads((HERE/"protocol.json").read_text(encoding="utf8"))
    server(cards,protocol,a.store,"http://127.0.0.1:18839","http://127.0.0.1:18840",18841).serve_forever()
