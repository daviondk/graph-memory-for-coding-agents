"""Normalize recorded PROV. Input producer presence and versioned read endpoints are constructed separately."""
from collections import Counter,defaultdict
from decimal import Decimal,InvalidOperation
import csv
import hashlib
from pathlib import Path
import json
import re
from sources import D,C,read,dump,sha

NUM=r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?'
VAR=r'(?:[A-Za-z_]|\.(?!\d))[A-Za-z0-9_.]*'
TOKEN=re.compile(r'#[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`[^`]*`|<<-|<-|->>|->|==|<=|>=|!=|:::+|'+NUM+r'L?|'+VAR+r'|[^\s]')
BASIC_VAR=re.compile(VAR+r'(?:\$'+VAR+r')*\Z')
NUMVAL=re.compile('[+-]?'+NUM+r'[lL]?\Z')


def tag(kind,v):return sha((kind+'\0'+v).encode())[:24]
def order(act):
    m=re.fullmatch(r'(?:\w+:)?p(\d+)',act)
    return int(m.group(1)) if m else None
def variable(s):
    return tag('var',s) if isinstance(s,str) and BASIC_VAR.fullmatch(s) else None
def numeric(s):
    if not NUMVAL.fullmatch(s):return None
    try:
        v=Decimal(s.rstrip('Ll'))
        return tag('num',str(v.normalize()) if v else '0') if v.is_finite() else None
    except InvalidOperation:return None


def entity(z):
    if z.get('rdt:type')!='Data':return None
    x=z.get('rdt:value');typ=z.get('rdt:valType')
    if not isinstance(x,str) or len(x)>4096:return None
    kind=None
    if isinstance(typ,str) and typ.startswith('{'):
        try:m=json.loads(typ)
        except ValueError:return None
        if m.get('container')!='vector' or m.get('dimension')!=[1] or len(m.get('type',[]))!=1:return None
        kind=m['type'][0]
    elif typ in ('int','float','str','bool','numeric','integer','character','logical','double'):kind=typ
    elif typ in (None,'') and NUMVAL.fullmatch(x):kind='numeric' # older recorder without scalar type metadata
    if kind in ('numeric','integer','double','int','float'):val=numeric(x)
    elif kind in ('logical','bool') and x.upper() in ('TRUE','FALSE'):val=tag('bool',x.upper())
    elif kind in ('character','str') and x not in ('<NA>','NA') and not x.startswith('File : '):val=tag('str',x)
    else:return None
    if val is None:return None
    name=variable(z.get('rdt:name'))
    sc=z.get('rdt:scope')
    scope=tag('qualified',(str(sc)+'|'+str(name))) if name and isinstance(sc,str) and sc.strip() else None
    return [val,name,scope]


def tokens(text):
    # A lightweight observable interface. No commands are evaluated. Strings/comments cannot create identifiers.
    lex=[x for x in TOKEN.findall(text) if not x.startswith('#')]
    vals=set();names=set()
    for i,item in enumerate(lex):
        left=lex[i-1] if i else ''
        right=lex[i+1] if i+1<len(lex) else ''
        if item[0] in ('"',"'") and len(item)>=2 and item[-1]==item[0]:
            # Preserve exact strings; only unescape the delimiter and the backslash itself.
            v=item[1:-1].replace(chr(92)+item[0],item[0]).replace(chr(92)*2,chr(92))
            vals.add(tag('str',v));continue
        if NUMVAL.fullmatch(item):
            sign='-' if left=='-' and (i<2 or lex[i-2] in ('(','=',',','<-','<<-','[','+','-','*','/')) else ''
            vals.add(numeric(sign+item));continue
        if item in ('TRUE','FALSE','True','False'):
            vals.add(tag('bool',item.upper()));continue
        name=item.strip('`')
        if variable(name) and right not in ('<-','<<-','=') and left not in ('->','->>','$','::',':::'):
            names.add(variable(name))
            j=i
            while j+2<len(lex) and lex[j+1]=='$' and variable(lex[j+2]):
                name+='$'+lex[j+2];j+=2
                after=lex[j+1] if j+1<len(lex) else ''
                if after not in ('<-','<<-','='):names.add(variable(name))
    return sorted(vals),sorted(names)


def family(repo,path):
    if repo in ('RDataTracker','rdtLite'):return 'regression/'+path.split('/')[1].lower()
    if repo=='eep-usecases':
        lab=path.split('/')[1].lower()
        if lab.startswith('coerce'):lab='coerce'
        return 'case/'+lab
    if repo=='provExplainR':
        label=path.split('/')[2].split('_20')[0].lower()
        return 'explain/'+label
    return 'python/'+path.split('/')[1].lower()


def main():
    entries=read(D/'source-lock.json');packs=[];gold=[];ledger=[]
    fingerprints=set()
    for ix,rec in enumerate(entries):
        key=f't{ix:03}'
        audit=dict(trace=key,repo=rec['repo'],family=family(rec['repo'],rec['path']),blob=rec['git_blob'],status='eligible')
        ledger.append(audit)
        if not rec['bytes']:audit['status']='empty';continue
        p=C/(rec['git_blob']+'.json')
        assert sha(p.read_bytes())==rec['sha256']
        try:obj=read(p)
        except (UnicodeError,ValueError):audit['status']='invalid_json';continue
        if rec['sha256'] in fingerprints:audit['status']='exact_duplicate';continue
        fingerprints.add(rec['sha256'])
        if not all(isinstance(obj.get(k),dict) for k in ('entity','activity','used','wasGeneratedBy')):
            audit['status']='missing_required_sections';continue
        acts={}
        for name,z in obj['activity'].items():
            j=order(name)
            if j is None:continue
            assert j not in acts
            vals,syms=tokens(str(z.get('rdt:name','')))
            acts[j]=dict(id=j,literals=vals,symbols=syms,write=[])
        producers=defaultdict(set)
        for edge in obj['wasGeneratedBy'].values():
            n=order(edge.get('prov:activity',''))
            if n in acts:producers[edge.get('prov:entity')].add(n)
        entities={k:v for k,z in obj['entity'].items() if (v:=entity(z)) is not None}
        for e,meta in entities.items():
            if len(producers[e])==1:
                n=next(iter(producers[e]));acts[n]['write'].append(meta)
        excluded=Counter();native=[];cards=[];seen=set();pairs=set()
        for edge in obj['used'].values():
            e=edge.get('prov:entity');consumer=order(edge.get('prov:activity',''))
            if e not in entities:excluded['non_scalar_or_not_data']+=1;continue
            if consumer not in acts:excluded['unknown_consumer']+=1;continue
            if len(producers[e])!=1:excluded['no_unique_recorded_generator']+=1;continue
            prod=next(iter(producers[e]))
            if prod>=consumer:excluded['generator_not_prior']+=1;continue
            if (e,consumer) in seen:excluded['repeated_read_arc']+=1;continue
            seen.add((e,consumer));pairs.add((prod,consumer))
            card=f'r{len(cards):05}'
            cards.append(dict(id=card,consumer=consumer,base=entities[e]))
            native.append(dict(card=card,producer=prod,entity=tag('entity',key+e),consumer=consumer))
        flow_bad=0;flow=0
        for v in obj.get('wasInformedBy',{}).values():
            a,b=order(v.get('prov:informant','')),order(v.get('prov:informed',''))
            if a in acts and b in acts:
                flow+=1;flow_bad+=int(a>=b)
        audit.update(activities=len(acts),typed_scalar_entities=len(entities),writes=sum(map(lambda x:len(x['write']),acts.values())),used_all=len(obj['used']),eligible_cards=len(cards),eligible_pairs=len(pairs),excluded=dict(excluded),native_control_arcs=flow,nonmonotone_control_arcs=flow_bad)
        packs.append(dict(trace=key,events=[acts[j] for j in sorted(acts)],cards=cards))
        gold.append(dict(trace=key,reads=native))
    dump(C/'flow-packets.json',packs);dump(C/'flow-gold.json',gold)
    dump(D/'corpus-audit.json',ledger)
    dump(D/'input-lock.json',dict(gold=sha((C/'flow-gold.json').read_bytes()),packets=sha((C/'flow-packets.json').read_bytes()),protocol=sha((D/'protocol.json').read_bytes()),source_lock=sha((D/'source-lock.json').read_bytes()),builder=sha(Path(__file__).read_bytes()),ledger=sha((D/'corpus-audit.json').read_bytes())))
    print(Counter(r['status'] for r in ledger),sum(r.get('eligible_cards',0) for r in ledger),sum(r.get('eligible_pairs',0) for r in ledger),flush=True)

if __name__=='__main__': main()

