"""Recover the preregistered frozen CPU run. Persist successful exact text embeddings between requests."""
from pathlib import Path
import hashlib
import json
import sys
import os
import numpy as np
import dense

CACHE=dense.pilot.CACHE.parent/"e5-restart-cache"
PREFIX=b"r17/e5/float32/cpu/st2.7/64/v1\0"
def key(text):
    return hashlib.sha256(PREFIX+text.encode("utf8")).hexdigest()
original=dense.Cached.encode
def encode(self,texts,**kwargs):
    absent=list(dict.fromkeys(t for t in texts if t not in self.cache))
    written=[]
    for text in absent:
        tag=key(text);f=CACHE/(tag+".npy")
        if f.exists():
            vector=np.load(f,allow_pickle=False)
            assert vector.dtype==np.float32 and vector.shape==(768,) and np.all(np.isfinite(vector))
            self.cache[text]=vector
        else:written.append((text,tag))
    out=original(self,texts,**kwargs)
    for text,tag in written:
        target=CACHE/(tag+".npy");tmp=CACHE/(tag+".tmp")
        with tmp.open("wb") as file:np.save(file,self.cache[text],allow_pickle=False)
        tmp.replace(target)
    return out
if __name__=="__main__":
    assert dense.pilot.sha(dense.ROOT/"dense.py")==dense.load(dense.ROOT/"plan-seal.json")["dense.py"]
    CACHE.mkdir(exist_ok=True)
    dense.Cached.encode=encode
    dense.rank()
    dense.score()
