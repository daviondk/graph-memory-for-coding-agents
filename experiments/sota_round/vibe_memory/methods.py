"""Synchronous offline VibeMemBench methods under a shared reader cap."""
import math
import re
from collections import Counter
from memory_interface import MemorySystem, RetrievedMemory
from memory_systems.demo import EchoMemorySystem

MAX_WORDS, MAX_CHARS = 240, 6000
TEST_COMMAND = re.compile(r"(?:\bpytest\b|\bunittest\b|\b(?:go|cargo|swift|npm|pnpm|yarn|gradle|mvn|dotnet|make)\s+(?:run\s+)?test\b|\b(?:jest|vitest|phpunit|tox)\b|gradlew\s+test\b)",re.I)
TEST_PASS = re.compile(r"(?:\b[1-9]\d*\s+(?:tests?\s+)?pass(?:ed|ing)\b|^\s*OK\s*$|^ok\s+\S|\bBUILD SUCCESS(?:FUL)?\b|\btest result:\s*ok\b|\bTests run:\s*[1-9]\d*.*Failures:\s*0)",re.I|re.M)
READ = re.compile(r"(?:^|&&\s*|\n)\s*(?:cat|rg|grep|head|tail|sed\s+-n|find|ls)\b")
WORD = re.compile(r"[A-Za-z]+[A-Za-z0-9]*|[0-9]+")
CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")


def clip(text, words=MAX_WORDS, chars=MAX_CHARS):
    text = text.strip()[:chars]
    spans = list(re.finditer(r"\S+",text))
    return text[:spans[words-1].end()].rstrip() if len(spans)>words else text.rstrip()


def tokens(text):
    result=[]
    for raw in WORD.findall(text):
        result.append(raw.lower())
        pieces=CAMEL.findall(raw)
        if len(pieces)>1:
            result.extend(p.lower() for p in pieces)
    return result


class BM25Memory(MemorySystem):
    def __init__(self):
        self.documents=[]
        self.user=None
        self.stored_bytes=0
        self.source_steps=0
        self.kinds=Counter()
        self.df=Counter()
        self.sum_length=0
        self.parser=EchoMemorySystem()

    def store(self,scope,session,index,text,kind):
        text=clip(text)
        if not text:
            return
        if self.user is None:
            self.user=scope.user_id
        assert scope.user_id==self.user
        freq=Counter(tokens(text))
        length=freq.total()
        self.df.update(freq.keys())
        self.sum_length+=length
        self.stored_bytes+=len(text.encode("utf8",errors="replace"))
        self.kinds[kind]+=1
        self.documents.append((session.session_id,index,text,kind,freq,length))

    def search(self,query,*,scope,top_k):
        if not self.documents or not top_k:
            return []
        assert self.user==scope.user_id
        q=set(tokens(query))
        n=len(self.documents)
        avg=max(1,self.sum_length/n)
        idfs={w:math.log(1+(n-self.df[w]+.5)/(self.df[w]+.5)) for w in sorted(q) if self.df[w]}
        ranked=[]
        for sid,i,content,kind,freq,length in self.documents:
            norm=1.2*(.25+.75*length/avg)
            score=sum(idf*freq[w]*2.2/(freq[w]+norm) for w,idf in idfs.items() if freq[w])
            if score>0:
                ranked.append(RetrievedMemory(id=f"{sid}::step{i}",content=content,score=score,
                                              source_session_id=sid,metadata={"evidence_kind":kind}))
        ranked.sort(key=lambda x:x.score,reverse=True)
        return ranked[:top_k]

    def count(self):
        return len(self.documents)


class RawBM25(BM25Memory):
    def add(self,session,*,scope):
        for i,step in enumerate(self.parser._iter_steps(session.messages)):
            self.source_steps+=1
            parts=[step["reasoning"][:800],step["command"],step["output"][:2000]]
            self.store(scope,session,i,"\n".join(p for p in parts if p),step["kind"])


class ActionReceipt(BM25Memory):
    def add(self,session,*,scope):
        steps=self.parser._iter_steps(session.messages)
        self.source_steps+=len(steps)
        paths=[]
        tests={}
        last_read=None
        for i,s in enumerate(steps):
            cmd=s["command"].strip()
            out=s["output"].strip()
            if s["kind"]=="final_patch":
                paths += re.findall(r"^\+\+\+ b/([^\n\r]+)",out,re.M)
                continue
            if str(s["returncode"])!="0" or not cmd or not out:
                continue
            # A shell pipe/alternative or unconditional separator may hide a failing command.
            if TEST_COMMAND.search(cmd) and not re.search(r"[|;]",cmd) and TEST_PASS.search(out):
                positive=[ln.strip() for ln in out.splitlines() if TEST_PASS.search(ln)]
                tests.pop(cmd,None)
                tests[cmd]=(i,cmd,positive[-1] if positive else out[-270:])
            elif READ.search(cmd):
                last_read=(i,cmd,out[:550])
        chosen=list(tests.values())[-3:][::-1] if tests else ([last_read] if last_read else [])
        if not chosen:
            return
        kind="observed_test" if tests else "observed_read"
        text=["Earlier issue. "+("The following test command(s) returned 0." if tests else "This code inspection returned 0.")]
        if paths:
            text.append("Paths in the prior submission: "+clip(", ".join(dict.fromkeys(paths)),38,420))
        for _,cmd,out in chosen:
            text.append("Command: "+clip(cmd,32,380)+"\nObserved output: "+clip(out,34,340))
        self.store(scope,session,chosen[0][0],"\n".join(text),kind)


class CappedEcho(EchoMemorySystem):
    def search(self,query,*,scope,top_k):
        selected=super().search(query,scope=scope,top_k=top_k)
        for item in selected:
            item.content=clip(item.content)
        return selected

    @property
    def stored_bytes(self):
        return sum(len(x["content"].encode("utf8",errors="replace")) for x in self._store)


METHODS={"action_receipt":ActionReceipt,"raw_bm25":RawBM25,"echo_capped":CappedEcho}
