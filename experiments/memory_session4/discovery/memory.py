"""Teacher-forced online state. observe runs only AFTER all arms select from present candidates."""
from collections import Counter,defaultdict
import gzip,hashlib,json
from fetch import ROOT
TARGETS={'click','text_input','submit','change'}
def load_rows(s):
    demos=defaultdict(list)
    with gzip.open(ROOT/'rows'/(s+'.json.gz'),'rt',encoding='utf8') as f:
        for line in f:
            row=json.loads(line);demos[row['demo']].append(row)
    for rows in demos.values():
        rows.sort(key=lambda r:r['turn'])
        assert len(rows)==len({r['turn'] for r in rows})
    return demos
def shard(demo):return int(hashlib.sha256(('20261117'+demo).encode()).hexdigest(),16)%3
def keycell(parts):return '|'.join(map(str,parts))
class State:
    def __init__(self):self.clear()
    def clear(self):
        self.last=None;self.focus=None;self.persistent=None;self.prev='none'
    def observe(self,turn,candidates,kind,y):
        if kind=='load':
            self.clear()
        elif kind in TARGETS:
            by_uid={u:b for u,t,b in candidates}
            self.last=(y,turn,kind,by_uid.get(y,False)) if y else None
            if kind=='click':
                self.focus=self.last if self.last and self.last[-1] else None
                self.persistent=self.focus
            elif kind in ('text_input','change','submit'):
                self.focus=None
        self.prev=kind
    def available(self,turn,candidates):
        ranks={e[0]:i+1 for i,e in enumerate(candidates)};first=candidates[0][0] if candidates else None
        def one(rec):
            if rec is None:return None
            uid,old,kind,editable=rec
            if uid not in ranks:return None
            rank=ranks[uid];gap=turn-old;assert gap>0
            return (uid,keycell([kind,'2' if rank==2 else '3-5' if 3<=rank<=5 else '6+' if rank>5 else '1','1' if gap==1 else '2-3' if gap<=3 else '4+']),editable,old)
        return first,one(self.last),one(self.focus),one(self.persistent)
def choose(rec,base,table,tag=False):
    if rec is None or rec[0]==base:return base
    label=rec[1]+('|'+str(rec[2]) if tag else '')
    data=table.get(label,[0,0,0])
    return rec[0] if data[0]>=20 and data[1]-data[2]>2 else base
def learn(table,rec,base,y,tag=False):
    if rec is None or rec[0]==base:return
    label=rec[1]+('|'+str(rec[2]) if tag else '')
    h=table.setdefault(label,[0,0,0]);h[0]+=1;h[1]+=int(rec[0]==y);h[2]+=int(base==y)
def suggest(state,turn,c,lex,tables):
    a,l,f,p=state.available(turn,c);b=choose(l,a,tables['last']);strong=choose(l,a,tables['tagged'],True)
    return {'released':a,'lexical':lex,'last_always':l[0] if l else a,'last_click_editable':l[0] if l and l[2] and l[1].startswith('click|') else a,
       'last_cal':b,'last_cal_tagged':strong,'focus_always':f[0] if f else a,'focus_cal':choose(f,b,tables['focus']),
       'persistent_cal':choose(p,b,tables['persistent']),'focus_on_tagged':choose(f,strong,tables['focus_tagged'])}
def train(demos):
    table={k:{} for k in ('last','tagged','focus','persistent','focus_tagged')}
    for stage in (0,1):
        for demo,rows in demos.items():
            if (shard(demo)==0)!=bool(stage):continue
            st=State()
            for r in rows:
                c=r['c'];y=r['y'];kind=r['k'];turn=r['turn']
                if y and kind in TARGETS:
                    first,last,f,p=st.available(turn,c)
                    if stage==0:
                        learn(table['last'],last,first,y);learn(table['tagged'],last,first,y,True)
                    else:
                        b=choose(last,first,table['last']);t=choose(last,first,table['tagged'],True)
                        learn(table['focus'],f,b,y);learn(table['persistent'],p,b,y);learn(table['focus_tagged'],f,t,y)
                st.observe(turn,c,kind,y)
    return table

