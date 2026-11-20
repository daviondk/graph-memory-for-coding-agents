"""Read-only interpretation of observed bash actions and ephemeral prompt construction."""
import copy
import hashlib
import json
import re
import shlex


def digest(obj):
    return hashlib.sha256(json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def read_segments(command):
    if not isinstance(command,str) or any(c in command for c in "\r\n$`<>"):
        return None
    try:
        lexer=shlex.shlex(command,posix=True,punctuation_chars=";&|")
        lexer.whitespace_split=True
        lexer.commenters="#"
        tokens=list(lexer)
    except ValueError:
        return None
    parts=[[]]
    operators=[]
    for token in tokens:
        if re.fullmatch(r"[;&|]+",token):
            if token not in {"&&","||",";","|"} or not parts[-1]:return None
            parts.append([]); operators.append(token)
        else:
            parts[-1].append(token)
    if not parts[-1]:return None
    reads=[]
    for part in parts:
        op,*args=part
        if op in {"pwd","cd","wc","uniq","cut"}:
            continue
        if op=="sort" and not any(x=="-o" or (x.startswith("-o") and not x.startswith("--")) or x.startswith("--output") for x in args):
            continue
        if op in {"cat","head","tail","nl","ls","grep"}:
            reads.append(part);continue
        if op=="rg" and not any(x.startswith("--pre") or x.startswith("--hostname-bin") for x in args):
            reads.append(part);continue
        if op=="find" and not any(x in {"-exec","-execdir","-ok","-okdir","-delete","-fprint","-fprint0","-fprintf","-fls"} for x in args):
            reads.append(part);continue
        if op=="git" and args and args[0] in {"grep","ls-files","status"}:
            reads.append(part);continue
        if op=="sed" and len(args)>=2 and args[0]=="-n" and re.fullmatch(r"(?:\d+|\$)(?:,(?:\d+|\$))?p",args[1]) and all(not x.startswith("-") for x in args[2:]):
            reads.append(part);continue
        return None
    if not reads:return None
    return reads,operators


def contains_path(text,paths,repo):
    # Match complete components, including the optional verified checkout prefix.
    optional_prefix=r"(?:\./|/testbed/|/"+re.escape(repo)+r"/)?"
    for path in paths:
        pattern=r"(?<![\w./-])"+optional_prefix+re.escape(path)+r"(?![\w./-])"
        if re.search(pattern,text):
            return path
    return None


def observation_text(message):
    c=message.get("content","")
    if isinstance(c,str):return c
    if isinstance(c,list):return "\n".join(v.get("text","") for v in c if isinstance(v,dict) and v.get("type")=="text")
    return ""


def link_events(messages):
    actions={}
    for msg in messages:
        if msg.get("role")=="assistant":
            for call in msg.get("tool_calls") or []:
                if not isinstance(call,dict) or not call.get("id"):continue
                fn=call.get("function") or {}
                try:
                    obj=json.loads(fn.get("arguments","{}"))
                except (TypeError,ValueError):
                    obj={}
                if isinstance(obj,dict) and fn.get("name")=="bash" and isinstance(obj.get("command"),str):
                    actions[call["id"]]=obj["command"]
        elif msg.get("role")=="tool" and msg.get("tool_call_id") in actions:
            call=msg["tool_call_id"]
            yield call,actions[call],observation_text(msg)


def match_read(command,observation,card):
    segments=read_segments(command)
    if segments is None:return None,None
    reads,operators=segments
    # The observed tool output is attributable to the complete allowlisted shell invocation.
    path=contains_path(observation,card["paths"],card["repo_directory"])
    if path:return path,"observation"
    # A successful all-&& chain, simple pipeline or unconditional sequence executed its
    # positive read segment; ignore potentially skipped textual branches, cd and filters.
    if "||" in operators or ("&&" in operators and not re.search(r"<returncode>\s*0\s*</returncode>",observation)):
        return None,None
    for read in reads:
        path=contains_path(" ".join(read),card["paths"],card["repo_directory"])
        if path:return path,"command"
    return None,None


class Delivery:
    def __init__(self,arm,card):
        self.arm=arm
        self.card=card
        self.seen=set()
        self.fired=False
        self.request_count=0
        self.delivered_at=None

    def apply(self,body):
        self.request_count+=1
        messages=body["messages"]
        new=[]
        trigger=None
        for cid,command,observation in link_events(messages):
            if cid in self.seen:continue
            self.seen.add(cid)
            index=len(self.seen)
            path,where=match_read(command,observation,self.card)
            event={"tool_call_id":cid,"index":index,"command_sha256":digest(command),"observation_sha256":digest(observation),"path":path,"match_source":where}
            new.append(event)
            if self.fired or trigger is not None:continue
            if self.arm=="path_trigger" and path:trigger=event
            elif self.arm=="fixed_third" and index==3:trigger=event
        copied=copy.deepcopy(body)
        injected=False
        if trigger is not None:
            copied["messages"].append({"role":"user","content":"<relevant_experiences>\n"+self.card["card"]+"\n</relevant_experiences>"})
            self.fired=True
            self.delivered_at=self.request_count
            injected=True
        record={"request":self.request_count,"observed_total":len(self.seen),"new_events":new,"injected":injected,
                "evicted":self.delivered_at is not None and self.request_count>self.delivered_at,"trigger":trigger,
                "incoming_sha256":digest(messages),"forwarded_sha256":digest(copied["messages"]),
                "card_sha256":self.card["card_sha256"],"source":self.card["source_session_id"]}
        return copied,record
