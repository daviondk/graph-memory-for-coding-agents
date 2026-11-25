from collections import defaultdict
from statistics import median,mean
from time import perf_counter_ns
import random
from cfg import *
from bench import connect,ONE,TWO,WHOLE
from online import serve,c,Tokenizer,TOK
from results import ci_ratio
class Reply:
    def __init__(self,data):self.data=data
    def fetchone(self):return self.data
class ClientField:
    def __init__(self,body,rid):self.body=body;self.rid=rid
    def execute(self,sql,params):
        if sql not in (ONE,TWO) or params[-1]!=self.rid:raise AssertionError("unexpected interval request")
        text=self.body
        return Reply(tuple(text[st-1:st-1+n].encode() for st,n in zip(params[:-1:2],params[1:-1:2])))
def main():
    rng=random.Random(26099);db=connect();list(db.execute("select length(body) from field"))
    src=load(D/"cases.json.gz");toks={"ise":Tokenizer.from_file(str(TOK)),"mdd":c.tok(),"squad":Tokenizer.from_file(str(TOK))}
    runs=[];med=defaultdict(list);traffic={}
    for i in range(9):
        indices=list(range(len(src)));rng.shuffle(indices)
        for j in indices:
            r=src[j];a,b=r["both"];get=lambda z:tuple(map(int,z["header"][1:-2].split(":")));e,left=get(a);_,right=get(b)
            key=r["rid"],e,left,right,r["field_chars"];arms=["slice_sql","slice_client"];rng.shuffle(arms)
            for k in arms:
                tic=perf_counter_ns()
                if k=="slice_client":
                    body=db.execute(WHOLE,(key[0],)).fetchone()[0];adapter=ClientField(body.decode(),key[0])
                else:adapter=db
                ops,wire,fromdb,calls=serve(adapter,toks[r["n"]],key,"local_pair")
                paid=len(body) if k=="slice_client" else fromdb
                ns=perf_counter_ns()-tic
                assert sha(wire.encode())==r["wire"]
                runs.append([i,j,k,ns,paid]);med[j,k].append(ns);traffic[j,k]=paid
    db.close();data={("warm",j,k):[median(v)] for (j,k),v in med.items()}
    ids=list(range(len(src)));rat=ci_ratio(data,src,ids,"warm","slice_sql","slice_client",0)
    summary={k:{"warm_us":median(data["warm",j,k][0] for j in ids)/1000,"avg_db_bytes":mean(traffic[j,k] for j in ids)} for k in ("slice_sql","slice_client")}
    h=save(D/"matched-times.json.gz",runs);result={"summary":summary,"pairs":rat,"runs":len(runs),"raw":h,"protocol":sha_file(D/"MATCHED_RU.md"),"code":sha_file(Path(__file__)),"online_code":sha_file(D/"online.py")}
    save(D/"matched-results.json",result);print(result)
if __name__=="__main__":main()
