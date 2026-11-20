"""Pure online cue selection. Original tool outputs and currently valid rendered blocks only."""
import difflib
import hashlib
import re

WORDS = re.compile(r"[\w]+(?:['’][\w]+)*", re.UNICODE)
HITS = re.compile(r"\n\n(?=path: [^\n]+\nline: \d+\n)")
HEADER = re.compile(r"^path: ([^\n]+)\nline: (\d+)\n")


def signature(s):
    return hashlib.sha256(s.encode()).hexdigest()


def changed_phrase(old, current):
    if old == current:
        return None
    a = [m.group().casefold() for m in WORDS.finditer(old)]
    b = list(WORDS.finditer(current))
    words = [m.group().casefold() for m in b]
    ops = difflib.SequenceMatcher(None, a, words, autojunk=False).get_opcodes()
    changes = [(i,j) for op,_,_,i,j in ops if op in ('replace','insert') and j>i]
    if not changes:
        return None
    i,j = changes[0]
    def span(start, end):
        return current[b[start].start():b[end-1].end()]
    j = min(i+16,j)
    while j>i and len(span(i,j).encode())>120:
        j-=1
    if j==i:
        return None
    focal = span(i,j)
    k = j-i
    length=len(focal.encode())
    options=[]
    for op,_,_,lo,hi in ops:
        if op!='equal':
            continue
        width = min(hi-lo,k)
        for start in range(lo,hi-width+1):
            if not width:
                continue
            val=span(start,start+width)
            if len(val.encode())>120:
                continue
            overlap=len(set(words[start:start+width]) & set(words[i:j]))
            rank=(k-width, overlap, abs(len(val.encode())-length), abs(i-start), start)
            options.append((rank,val))
    neighbor=min(options)[1] if options else 'Source record refreshed'
    return focal,neighbor


class Tracker:
    def __init__(self, mode):
        self.mode=mode
        self.previous={}
        self.served=set()
        self.events=[]
        self.snapshots=[]
        self.request=0

    def inspect(self,messages,out,runtime,tool_evidence):
        from block_context.types import BlockState,TransformType
        self.request+=1
        candidates=[]
        valid=invalid=0
        for pos,m in enumerate(messages):
            if m.get('role')!='tool' or m.get('name') not in ('grep','read_file'):
                continue
            tid=str(m['tool_call_id'])
            ids=tool_evidence.get(tid,())
            if not ids:
                continue
            raw=m['content']
            parts=HITS.split(raw) if m['name']=='grep' else [raw]
            assert len(parts)==len(ids), (raw[:50],len(parts),len(ids))
            for k,(bid,original) in enumerate(zip(ids,parts)):
                block=runtime.get_block(bid)
                if block.transform_type!=TransformType.VERBATIM:
                    continue
                if block.state!=BlockState.VALID:
                    invalid+=1
                    continue
                valid+=1
                current=block.content
                assert current in out[pos]['content']
                key=(tid,k)
                before=self.previous.get(key)
                self.previous[key]=current
                base=before if self.mode=='previous' else original
                if base is None or base==current:
                    continue
                event_key=(tid,k,signature(current))
                if event_key in self.served:
                    continue
                # Exclude grep metadata from both matched passages.
                oldtext=HEADER.sub('',base,count=1)
                newtext=HEADER.sub('',current,count=1)
                spans=changed_phrase(oldtext,newtext)
                if not spans:
                    continue
                path=block.source_set[0].object_id if block.source_set else m['name']
                head=HEADER.match(current)
                loc=path+(f" line {head[2]}" if head else '')
                candidates.append((event_key,dict(request=self.request,tool_id=tid,part=k,locator=loc,revision=signature(current),prior_exposed=before is not None and before!=current,correction=spans[0],control=spans[1])))
        notice=len(out)>len(messages)
        self.snapshots.append(dict(request=self.request,visible_verbatim=valid,omitted_verbatim=invalid,notice=notice))
        if not candidates:
            return None
        self.served.update(key for key,_ in candidates)
        selected=candidates[-1][1]
        selected['eligible']=[dict(tool_id=e['tool_id'],part=e['part'],revision=e['revision']) for _,e in candidates]
        self.events.append(selected)
        return selected


def present(out,original_messages,event,arm):
    cue='Current source detail ('+event['locator']+'): '+event[arm]
    if len(out)>len(original_messages) and out[-1]['role']=='system':
        out[-1]={**out[-1],'content':out[-1]['content']+'\n'+cue}
    else:
        out.append({'role':'user','content':cue})
    return cue
