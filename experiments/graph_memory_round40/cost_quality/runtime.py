"""Portable CPU packet reader. Requires NumPy, kernels.dll and model.json.gz for learned modes."""
import os
for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"):
    os.environ[key]="1"
import ctypes
import gzip
import json
from pathlib import Path
from time import perf_counter_ns
import numpy as np

D=Path(__file__).resolve().parent
MODES=("native","raw","density","dp")
B=2048


def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix==".gz" else b)


def arrays(record):
    return dict(z=np.asarray(record["z"],dtype=np.float64),offset=np.asarray(record["offset"],dtype=np.float64),
        costs=np.asarray(record["costs"],dtype=np.int32),dense=np.asarray(record["dense"],dtype=np.int32),
        order=np.asarray(record["order"],dtype=np.int32),seed=str(record["seed"]))


class Reader:
    def __init__(self,learned=True):
        self.lib=ctypes.CDLL(str(D/"kernels.dll"))
        p=ctypes.c_void_p
        self.lib.pack.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,p,p,p,p]
        self.lib.pack.restype=ctypes.c_int
        self.lib.tree_values.argtypes=[ctypes.c_int,ctypes.c_int,p,p,ctypes.c_double,p,p]
        self.lib.tree_values.restype=None
        self.templates={}
        if learned:
            m=read(D/"model.json.gz")
            self.weights={s:np.asarray(v["coef"]) for s,v in m["ranks"].items()}
            self.intercepts={s:v["intercept"] for s,v in m["ranks"].items()}
            self.correction={k:np.asarray(m["correction"][k]) for k in ("center","scale","weights")}
            forest=m["trees"]
            self.base=forest["base"]
            roots,nodes=[],[]
            for tree in forest["trees"]:
                root=len(nodes)
                roots.append(root)
                for feature,threshold,left,right,val in tree:
                    nodes.append((feature,threshold,left+root,right+root,val))
            self.roots=np.asarray(roots,dtype=np.int32)
            self.tables=np.asarray(nodes,dtype=np.float64)

    def features(self,p):
        z=p["z"].copy()
        n=len(z);seed=p["seed"]
        # Templates depend only on the size of the pool, never on a question, rank or model output.
        if n not in self.templates:
            rank=np.arange(1,n+1)
            self.templates[n]=(np.column_stack((-np.log(rank),1/rank,(n-rank)/max(1,n-1))),np.log1p(rank))
        tmpl,logrank=self.templates[n]
        graph=p["offset"]-(tmpl@self.weights["13"]+self.intercepts["13"])
        z[p["dense"],0]=logrank
        prior=np.empty(n)
        prior[p["dense"]]=tmpl@self.weights[seed]+self.intercepts[seed]
        corr=self.correction
        score=graph+prior+(z-corr["center"])/corr["scale"]@corr["weights"]
        rank=np.empty(n,dtype=int)
        rank[np.argsort(-score,kind="stable")]=np.arange(1,n+1)
        return np.column_stack((z[:,0],z[:,1],z[:,2],graph,score,score.max()-score,np.log1p(rank),np.full(n,np.log1p(n))))

    def utility(self,x):
        logits=np.empty(len(x),dtype=np.float64)
        self.lib.tree_values(len(x),len(self.roots),self.roots.ctypes.data,self.tables.ctypes.data,
                             self.base,x.ctypes.data,logits.ctypes.data)
        return np.logaddexp(0,logits)

    def select(self,p,mode,gain):
        nd=p["costs"];order=p["order"]
        out=np.empty(len(nd),dtype=np.int32)
        k=self.lib.pack(len(nd),B,MODES.index(mode),order.ctypes.data,nd.ctypes.data,
                        gain.ctypes.data if gain is not None else None,out.ctypes.data)
        return out[:k].tolist()

    def run(self,p,mode):
        begin=perf_counter_ns()
        if mode=="native":
            result=self.select(p,mode,None)
            total=perf_counter_ns()-begin
            return result,(0,0,total,total)
        x=self.features(p)
        ready=perf_counter_ns()
        u=self.utility(x)
        ranked=perf_counter_ns()
        result=self.select(p,mode,u)
        end=perf_counter_ns()
        return result,(ready-begin,ranked-ready,end-ranked,end-begin)
