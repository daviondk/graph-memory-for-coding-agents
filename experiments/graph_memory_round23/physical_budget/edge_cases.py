"""Property tests for ties, overlapping intervals, empty residual budgets and updates."""
import collections
import random
import sqlite3
import greedy_sql as g
from bench import D,save

def main():
    rng=random.Random(37);counts=collections.Counter();cases=0
    c=sqlite3.connect(":memory:")
    c.execute("create table blocks(q integer,j integer,neg real,c integer,e integer,l integer,h integer,unique(q,j))")
    c.execute("create index idx_priority on blocks(q,neg,j,c,e,l,h)")
    for jtrial in range(768):
        c.execute("delete from blocks")
        n=5+rng.randrange(40)
        core=[["f",4,0,1,3],["s",3,1,0,3]]
        start=[];new_rows=[]
        for j in range(n):
            l=rng.randrange(10);e=rng.randrange(4);h=l+1+rng.randrange(6)
            start.append((-rng.randint(1,6)/6,j,rng.randrange(1,12),e,l,h))
        budget=rng.choice((7,8,12,20,29,43,90))
        old=g.greedy(start,core,budget)
        c.executemany("insert into blocks values(?,?,?,?,?,?,?)",[(0,v[1],v[0],*v[2:]) for v in start])
        k=rng.choice((0,1,3,min(n,9),n))
        for v in rng.sample(start,k):
            new_rows.append((v,(-rng.randint(1,7)/7,*v[1:])))
        if jtrial%2:new_rows.append((None,(-rng.randint(1,6)/6,n,2,rng.randrange(4),1,4)))
        g.write(c,0,new_rows);after={v[1]:v for v in start}
        for _,v in new_rows:after[v[1]]=v
        expected=g.greedy(after.values(),core,budget)
        result,_,branch=g.repair(c,0,core,budget,old,new_rows)
        assert result==expected==g.rebuild(c,0,core,budget)[0]
        counts[branch]+=1;cases+=1
    c.close();save(D/"adversarial.json",{"cases":cases,"branch_counts":counts,"seed":37,"mismatches":0})
if __name__=="__main__":main()

