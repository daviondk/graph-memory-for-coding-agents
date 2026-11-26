"""Interactive exact knapsack-core replay over four learned Q32 states. Python standard library."""
import argparse,json,sqlite3
from contextlib import closing
from fractions import Fraction
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

BASE=Path(__file__).resolve().parent
CAP=2048
HEAD=1024
Q=2**32
def connect():
    return sqlite3.connect((BASE/'core.sqlite').as_uri()+'?mode=ro&immutable=1',uri=True)

def dynamic(items,room):
    scores=[0]*(room+1)
    traceback=[]
    cells=0
    for i,c,v in items:
        mask=bytearray(room+1)
        if c<=room:
            cells+=room-c+1
            for b in range(room,c-1,-1):
                choice=scores[b-c]+v
                if choice>scores[b]:
                    scores[b]=choice;mask[b]=1
        traceback.append(mask)
    picks=[]
    for (i,c,_),mask in zip(reversed(items),reversed(traceback)):
        if mask[room]:picks.append(i);room-=c
    return picks[::-1],cells

def prefix(items):
    used=0;count=0
    for _,c,_ in items:
        if used+c>HEAD:break
        used+=c;count+=1
    return items[:count],items[count:],CAP-used

def greedy(order,room,initial=()):
    picks=set();value=0
    for i,c,v in [*initial,*order]:
        if i not in picks and c<=room:
            picks.add(i);room-=c;value+=v
    return value

def reduce(items,prior,warm):
    head,tail,room=prefix(items)
    heavy=[i for i,c,v in tail if c>room]
    rows=[r for r in tail if r[1]<=room]
    value_head=sum(v for _,_,v in head)
    zero=[i for i,c,v in rows if v==0]
    free=[i for i,c,v in rows if c==0 and v>0]
    must=set(free);out=set(zero);positive=[r for r in rows if r[1]>0 and r[2]>0]
    fixed_value=sum(v for _,c,v in rows if c==0)
    ordered=sorted(positive,key=lambda r:Fraction(r[2],r[1]),reverse=True)
    used=0;break_item=None
    for r in ordered:
        used+=r[1]
        if used>room:break_item=r;break
    greedy_value=greedy(ordered,room)
    previous_value=greedy(ordered,room,(r for r in positive if r[0] in prior)) if warm else greedy_value
    lower=max(greedy_value,previous_value)
    if break_item is None:
        upper=Fraction(sum(v for _,_,v in positive))
        must.update(i for i,_,_ in positive)
    else:
        _,den,num=break_item
        reduced={i:v*den-c*num for i,c,v in positive}
        upper_num=num*room+sum(max(0,r) for r in reduced.values())
        upper=Fraction(upper_num,den)
        gap=upper_num-den*lower
        assert gap>=0
        for i,r in reduced.items():
            if r>gap:must.add(i)
            elif -r>gap:out.add(i)
    core=[r for r in rows if r[0] not in (must | out)]
    residual=room-sum(c for i,c,v in rows if i in must)
    picked,cells=dynamic(core,residual) if core else ([],0)
    take=must|set(picked)
    packet=[i for i,c,v in head]+[i for i,c,v in rows if i in take]
    vmap={i:v for i,c,v in items}; cmap={i:c for i,c,v in items}
    base=value_head+fixed_value
    total_ub=upper+base
    result=dict(packet=packet,prefix=[i for i,c,v in head],forced=[i for i,c,v in rows if i in must],
                rejected=[i for i,c,v in rows if i in out],over_budget=heavy,core=[i for i,c,v in core],
                candidates=len(items),eligible_tail=len(rows),budget=CAP,cost=sum(cmap[i] for i in packet),
                work_cells=cells,residual_capacity=residual,lower_q32=lower+base,
                greedy_lower_q32=greedy_value+base,upper_num=total_ub.numerator,upper_den=total_ub.denominator,
                lambda_num=break_item[2] if break_item else 0,lambda_den=break_item[1] if break_item else 1,
                previous_bound_strictly_better=warm and previous_value>greedy_value,
                objective_q32=sum(vmap[i] for i in packet))
    assert sum(len(result[k]) for k in ('forced','rejected','core'))==len(rows)
    assert result['lower_q32']<=result['objective_q32']<=total_ub and result['cost']<=CAP
    return result

def evaluate(case,step,policy,audit=False):
    if case not in ('short','medium','long') or step not in (25,50,75,100) or policy not in ('greedy','previous'):
        raise ValueError('Choose a listed case, cut and bound.')
    with closing(connect()) as conn:
        q,t,total,c=conn.execute('SELECT query,trajectory,total,costs FROM example WHERE name=?',(case,)).fetchone()
        cost=json.loads(c)
        records=conn.execute('SELECT pct,event,ordered,utility FROM state WHERE name=? AND pct<=? ORDER BY pct',(case,step)).fetchall()
    previous=set()
    for pct,evt,o,v in records:
        earlier=previous
        order=json.loads(o);values=json.loads(v)
        items=[(i,cost[i],u) for i,u in zip(order,values)]
        result=reduce(items,previous,policy=='previous')
        previous=set(result['packet'])
        result['added']=sorted(previous-earlier);result['removed']=sorted(earlier-previous)
    result.update(case=case,step=step,policy=policy,event=evt,query=q,trajectory=t,total=total)
    if audit:
        h,t,room=prefix(items);eligible=[r for r in t if r[1]<=room]
        if sum(r[1] for r in eligible)<=room:
            ids=[r[0] for r in eligible if r[2]>0];cells=0
        else:ids,cells=dynamic(eligible,room)
        full=[r[0] for r in h]+ids
        result['audit']=dict(equal=(full==result['packet']),full_order=full,full_cells=cells)
    return result

class Handler(BaseHTTPRequestHandler):
    def reply(self,code,kind,body):
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
    def data(self,obj,code=200):self.reply(code,'application/json; charset=utf-8',json.dumps(obj).encode())
    def handle_route(self,post=False):
        u=urlsplit(self.path)
        if u.path=='/' and not post:
            self.send_response(302);self.send_header('Location','/core');self.end_headers();return
        if u.path=='/core' and not post:
            self.reply(200,'text/html; charset=utf-8',(BASE/'core.html').read_bytes());return
        if u.path=='/core/catalog' and not post:
            with closing(connect()) as db:
                cols=db.execute('SELECT name,total,query FROM example ORDER BY total').fetchall()
            self.data(dict(cases=[dict(name=a,total=b,query=c) for a,b,c in cols],steps=[25,50,75,100],policies=['greedy','previous']));return
        if u.path not in ('/core/api','/core/audit'):
            self.data({'error':'Unknown route'},404);return
        try:
            if post:
                n=int(self.headers.get('Content-Length','0'));assert 0<n<=4096
                p=json.loads(self.rfile.read(n));assert isinstance(p,dict)
            else:p={k:v[-1] for k,v in parse_qs(u.query).items()}
            self.data(evaluate(p.get('case','medium'),int(p.get('step',50)),p.get('policy','previous'),audit=u.path.endswith('/audit')))
        except (ValueError,TypeError,KeyError,AssertionError):
            self.data(dict(error='Invalid request parameters.'),400)
    def do_GET(self):self.handle_route()
    def do_POST(self):self.handle_route(True)
    def log_message(self,*args):pass

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=0);a=p.parse_args()
    with ThreadingHTTPServer(('127.0.0.1',a.port),Handler) as server:
        print(f'http://127.0.0.1:{server.server_port}',flush=True);server.serve_forever()
