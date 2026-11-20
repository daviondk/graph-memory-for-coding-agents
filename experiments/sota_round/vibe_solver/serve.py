"""Local, inference-only Qwen Chat Completions endpoint for the pinned mini-SWE-agent."""
import argparse
import collections
import hashlib
import json
import queue
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessor, StoppingCriteria


MODEL = "Qwen/Qwen3-8B"
INSTANCE = uuid.uuid4().hex
TOOL = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>",re.S)
ROUTE = re.compile(r"(?:/replicate/(\d+))?/v1/chat/completions")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_tools(raw, tools):
    if not tools:
        return raw, []
    calls=[]
    remainder=[]
    pos=0
    for match in TOOL.finditer(raw):
        try:
            obj=json.loads(match.group(1))
            if not isinstance(obj["name"],str) or not isinstance(obj["arguments"],dict):
                continue
        except (KeyError,TypeError,json.JSONDecodeError):
            continue
        remainder.append(raw[pos:match.start()])
        pos=match.end()
        calls.append(dict(id="call_"+uuid.uuid4().hex[:20],type="function",
                          function=dict(name=obj["name"],arguments=json.dumps(obj["arguments"],ensure_ascii=False))))
    remainder.append(raw[pos:])
    return "".join(remainder).strip(),calls


class SampleRows(LogitsProcessor):
    """Independent, seeded categorical draws for each concurrent agent trajectory."""
    def __init__(self, items):
        self.items=items
        self.generators=[torch.Generator(device="cuda").manual_seed(i.seed) for i in items]

    def __call__(self, ids, logits):
        chosen=[]
        for score,j,gen in zip(logits,self.items,self.generators):
            if j.temperature==0:
                chosen.append(score.argmax().view(1))
                continue
            score=score.float()/j.temperature
            if j.top_k:
                values,idx=torch.topk(score,min(j.top_k,len(score)))
            else:
                values,idx=score.sort(descending=True)
            probs=values.softmax(0)
            if j.top_p<1:
                discard=(probs.cumsum(0)-probs)>=j.top_p
                probs=probs.masked_fill(discard,0.)
            chosen.append(idx[torch.multinomial(probs,1,generator=gen)])
        return torch.full_like(logits,-float("inf")).scatter_(1,torch.stack(chosen),0.)


class StopRows(StoppingCriteria):
    def __init__(self, items, width, tokenizer):
        self.items,self.width,self.tokenizer=items,width,tokenizer
    def __call__(self, ids, scores, **kwargs):
        n=ids.shape[-1]-self.width
        ends=[n>=j.limit for j in self.items]
        for k,j in enumerate(self.items):
            if j.stops and not ends[k]:
                text=self.tokenizer.decode(ids[k,self.width:],skip_special_tokens=True)
                ends[k]=any(s in text for s in j.stops)
        return torch.tensor(ends,dtype=torch.bool,device=ids.device)


class Job:
    def __init__(self, obj, replicate, seq, tokenizer, max_context, default_max):
        self.obj=obj
        if obj.get("model") not in (MODEL,"openai/"+MODEL):
            raise ValueError("unknown model")
        if obj.get("stream") or obj.get("n",1)!=1:
            raise ValueError("use non-streaming chat completions with n=1")
        if obj.get("tool_choice") not in (None,"auto"):
            raise ValueError("this evaluator endpoint uses automatic tool selection")
        messages=obj["messages"]
        if not isinstance(messages,list) or not messages:
            raise ValueError("messages must be nonempty")
        self.tools=obj.get("tools") or []
        text=tokenizer.apply_chat_template(messages,tools=self.tools or None,tokenize=False,
                                           add_generation_prompt=True,enable_thinking=False)
        self.tokens=tokenizer(text,add_special_tokens=False)["input_ids"]
        self.prompt_sha=digest(text)
        self.rep=replicate
        self.turn=sum(m.get("role")=="assistant" for m in messages)
        if obj.get("seed") is not None:
            self.seed=int(obj["seed"])%(2**63-1)
        else:
            # Matched replicate routes share random draws by assistant turn across
            # memory conditions. Plain /v1 substitutes a serial request ID so independent
            # trials do not accidentally reuse one deterministic sample.
            material=f"20261116|{replicate}|{self.turn}" if replicate is not None else f"20261116|request|{seq}"
            self.seed=int(digest(material)[:15],16)
        self.temperature=float(obj.get("temperature",.5))
        self.top_p=float(obj.get("top_p",.95))
        self.top_k=int(obj.get("top_k",20))
        requested=int(obj.get("max_completion_tokens") or obj.get("max_tokens") or default_max)
        if requested<1 or self.temperature<0 or not 0<self.top_p<=1 or self.top_k<0:
            raise ValueError("invalid sampling controls")
        self.limit=min(requested,max_context-len(self.tokens))
        if self.limit<=0:
            raise ValueError(f"context_length_exceeded: {len(self.tokens)} input tokens, maximum {max_context}")
        self.stops=obj.get("stop") or []
        if isinstance(self.stops,str):
            self.stops=[self.stops]
        if not all(isinstance(x,str) and x for x in self.stops):
            raise ValueError("invalid stop string")
        self.id="chatcmpl-"+uuid.uuid4().hex
        self.done=threading.Event()
        self.result=None
        self.error=None
        self.started=time.monotonic()


class Engine:
    def __init__(self,args):
        self.args=args
        self.tokenizer=AutoTokenizer.from_pretrained(args.model,local_files_only=True,padding_side="left")
        self.model=AutoModelForCausalLM.from_pretrained(args.model,local_files_only=True,
                        torch_dtype=torch.bfloat16,device_map={"":"cuda:0"},attn_implementation="sdpa").eval()
        self.model.generation_config.temperature=None
        self.model.generation_config.top_k=None
        self.model.generation_config.top_p=None
        self.max_context=self.model.config.max_position_embeddings
        self.queue=queue.Queue()
        self.lock=threading.Lock()
        self.sequence=0
        self.log=args.runtime/"requests.jsonl"
        self.state=dict(instance=INSTANCE,model=MODEL,revision=args.model.name,port=args.port,bind="127.0.0.1",
           max_context=self.max_context,default_max_output=args.max_output,batch=args.batch,batch_token_budget=args.batch_budget,
           temperature=.5,top_k=20,top_p=.95,thinking=False,dtype="bfloat16",torch=torch.__version__,
           transformers=transformers.__version__,gpu=torch.cuda.get_device_name(),started_epoch=time.time())
        (args.runtime/"state.json").write_text(json.dumps(self.state,indent=2),encoding="utf-8")
        threading.Thread(target=self.worker,daemon=True).start()

    def submit(self,obj,replicate):
        with self.lock:
            self.sequence+=1
            j=Job(obj,replicate,self.sequence,self.tokenizer,self.max_context,self.args.max_output)
        self.queue.put(j)
        j.done.wait()
        if j.error:
            raise RuntimeError(j.error)
        return j.result

    def worker(self):
        pending=collections.deque()
        while True:
            batch=[pending.popleft() if pending else self.queue.get()]
            until=time.monotonic()+.06
            while len(batch)<self.args.batch:
                try:
                    item=pending.popleft() if pending else self.queue.get(timeout=max(0.,until-time.monotonic()))
                except queue.Empty:
                    break
                proposed=batch+[item]
                if len(proposed)*max(len(j.tokens)+j.limit for j in proposed)>self.args.batch_budget:
                    pending.appendleft(item)
                    break
                batch=proposed
            self.execute(batch)

    def execute(self,batch):
        try:
            self.generate(batch)
        except torch.OutOfMemoryError:
            torch.cuda.empty_cache()
            if len(batch)>1:
                for j in batch:
                    self.execute([j])
                return
            batch[0].error="CUDA allocation insufficient for the requested context"
        except Exception as exc:
            for j in batch:
                j.error=repr(exc)
        for j in batch:
            if j.error:
                print(j.id,j.error,flush=True)
            j.done.set()

    @torch.inference_mode()
    def generate(self,batch):
        t=time.monotonic()
        encoded=self.tokenizer.pad([{"input_ids":j.tokens} for j in batch],padding=True,return_tensors="pt").to("cuda")
        width=encoded.input_ids.shape[1]
        out=self.model.generate(**encoded,do_sample=False,max_new_tokens=max(j.limit for j in batch),
                logits_processor=[SampleRows(batch)],stopping_criteria=[StopRows(batch,width,self.tokenizer)],
                use_cache=True,pad_token_id=self.tokenizer.pad_token_id)
        toks=out[:,width:].tolist()
        elapsed=time.monotonic()-t
        eos=self.model.generation_config.eos_token_id
        eos=set(eos if isinstance(eos,list) else [eos])
        for j,ids in zip(batch,toks):
            ids=ids[:j.limit]
            eos_pos=next((i for i,tok in enumerate(ids) if tok in eos),None)
            if eos_pos is not None:
                ids=ids[:eos_pos+1]
            raw=self.tokenizer.decode(ids,skip_special_tokens=True,clean_up_tokenization_spaces=False)
            end=min((raw.index(s) for s in j.stops if s in raw),default=None)
            if end is not None:
                raw=raw[:end]
            content,calls=parse_tools(raw,j.tools)
            reason="stop" if eos_pos is not None or end is not None else "length"
            if calls and reason!="length":
                reason="tool_calls"
            message=dict(role="assistant",content=content or None)
            if calls:
                message["tool_calls"]=calls
            usage=dict(prompt_tokens=len(j.tokens),completion_tokens=len(ids),total_tokens=len(j.tokens)+len(ids))
            j.result=dict(id=j.id,object="chat.completion",created=int(time.time()),model=MODEL,
                          choices=[dict(index=0,message=message,finish_reason=reason)],usage=usage)
            record=dict(id=j.id,replicate=j.rep,turn=j.turn,prompt_sha256=j.prompt_sha,seed=j.seed,
                        temperature=j.temperature,top_p=j.top_p,top_k=j.top_k,limit=j.limit,
                        finish_reason=reason,tool_count=len(calls),tool_names=[c["function"]["name"] for c in calls],
                        usage=usage,batch=len(batch),generation_s=round(elapsed,3),wall_s=round(time.monotonic()-j.started,3),
                        output_sha256=digest(raw),cuda_peak_bytes=torch.cuda.max_memory_allocated(),epoch=time.time())
            with self.log.open("a",encoding="utf-8") as f:
                f.write(json.dumps(record)+"\n")


class Handler(BaseHTTPRequestHandler):
    def reply(self,status,obj):
        data=json.dumps(obj,ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.path=="/health":
            return self.reply(200,self.server.engine.state)
        if self.path.endswith("/v1/models"):
            return self.reply(200,dict(object="list",data=[dict(id=MODEL,object="model",owned_by="local")]))
        self.reply(404,{"error":{"message":"unknown path"}})
    def do_POST(self):
        match=ROUTE.fullmatch(self.path)
        if not match:
            return self.reply(404,{"error":{"message":"unknown path"}})
        try:
            size=int(self.headers.get("Content-Length","0"))
            if not 0<size<8_000_000:
                raise ValueError("invalid request size")
            obj=json.loads(self.rfile.read(size))
            result=self.server.engine.submit(obj,int(match[1]) if match[1] is not None else None)
            self.reply(200,result)
        except (KeyError,TypeError,ValueError) as exc:
            self.reply(400,{"error":{"message":str(exc),"type":"invalid_request_error","code":"context_length_exceeded" if "context_length_exceeded" in str(exc) else "invalid_request"}})
        except RuntimeError as exc:
            self.reply(500,{"error":{"message":str(exc),"type":"server_error"}})
    def log_message(self,*args):
        return


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--model",type=Path,required=True)
    cli.add_argument("--runtime",type=Path,required=True)
    cli.add_argument("--port",type=int,default=18991)
    cli.add_argument("--max-output",type=int,default=2048)
    cli.add_argument("--batch",type=int,default=4)
    cli.add_argument("--batch-budget",type=int,default=18000)
    args=cli.parse_args()
    args.runtime.mkdir(parents=True,exist_ok=True)
    engine=Engine(args)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    server.engine=engine
    print("Ready",engine.state,flush=True)
    server.serve_forever()


if __name__=="__main__":
    main()
