"""Attach registered per-turn seeds to the unchanged native OpenAI messages/tools."""
import hashlib
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
DEST="http://127.0.0.1:18840"
NAME="qwen38-27b-ud-q4km"
ROUTE=re.compile(r"(?:(?:/replicate/([01])))?/v1/chat/completions")
LOCK=threading.Lock()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass

    def emit(self,status,data):
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path=re.sub(r"^/replicate/[01]","",self.path)
        if path not in ("/v1/models","/health"):
            self.emit(404,b"{}")
            return
        try:
            with urlopen(DEST+path,timeout=10) as response:
                self.emit(response.status,response.read())
        except (HTTPError,URLError,OSError):
            self.emit(503,b'{"error":"native server unavailable"}')

    def do_POST(self):
        match=ROUTE.fullmatch(self.path)
        if not match:
            self.emit(404,b"{}")
            return
        started=time.time()
        rep=int(match[1]) if match[1] is not None else 0
        try:
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["model"] in (NAME,"openai/"+NAME) and not body.get("stream"),"Unknown model or streaming"
            messages=body["messages"]
            turn=sum(m["role"]=="assistant" for m in messages)
            seed=(int(body["seed"]) if body.get("seed") is not None else
                  int(digest(f"20261116|{rep}|{turn}".encode())[:15],16)) % (2**31-1)
            cap=int(body.pop("max_completion_tokens",None) or body.get("max_tokens") or 1024)
            assert cap>0
            body.update(model=NAME,seed=seed,max_tokens=min(1024,cap),
                        cache_prompt=False,temperature=float(body.get("temperature",.5)),
                        top_p=float(body.get("top_p",.95)),top_k=int(body.get("top_k",20)),
                        min_p=0.0,repeat_penalty=1.0)
            body["chat_template_kwargs"]={**(body.get("chat_template_kwargs") or {}),"enable_thinking":False}
            raw=json.dumps(body,ensure_ascii=False).encode()
            request=Request(DEST+"/v1/chat/completions",data=raw,headers={"Content-Type":"application/json"})
            event={"replicate":rep,"turn":turn,"seed":seed,"epoch":started,"max_output":body["max_tokens"],
                   "temperature":body["temperature"],"chat_template_thinking":False,
                   "top_p":body["top_p"],"top_k":body["top_k"],"min_p":0.0,"repeat_penalty":1.0,
                   "message_sha256":digest(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()),
                   "payload_sha256":digest(raw),"tool_names":[x.get("function",{}).get("name") for x in body.get("tools",[])]}
            try:
                with urlopen(request,timeout=1500) as response:
                    status,data=response.status,response.read()
            except HTTPError as exc:
                status,data=exc.code,exc.read()
            event.update(http_status=status,seconds=time.time()-started,response_sha256=digest(data))
            if status==200:
                result=json.loads(data)
                ch=result["choices"][0]
                msg=ch["message"]
                event.update(id=result.get("id"),usage=result.get("usage"),timings=result.get("timings"),
                             finish=ch.get("finish_reason"),tool_calls=len(msg.get("tool_calls") or []),
                             native_tool_names=[x.get("function",{}).get("name") for x in msg.get("tool_calls",[])],
                             reason_chars=len(msg.get("reasoning_content") or ""))
            else:
                event["error"]=data.decode(errors="replace")[:1200]
            with LOCK, (ROOT/"requests.jsonl").open("a",encoding="utf8") as f:
                f.write(json.dumps(event)+"\n")
            self.emit(status,data)
        except (ValueError,KeyError,AssertionError,URLError,OSError) as exc:
            self.emit(502,json.dumps({"error":str(exc)}).encode())


if __name__=="__main__":
    ThreadingHTTPServer(("127.0.0.1",18839),Handler).serve_forever()
