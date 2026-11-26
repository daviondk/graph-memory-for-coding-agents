"""Exact dynamic role-conditional midranks for provenance-unit degree channels."""
import os
for key in ("OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","OMP_NUM_THREADS","NUMEXPR_NUM_THREADS"):os.environ[key]="1"
import numpy as np
NCH=8
def edge_array(edges):
    return np.asarray(edges,dtype=np.int64).reshape(-1,3)
def update_degrees(deg,edges,sign):
    if len(edges):
        a,b,z=edges.T
        np.add.at(deg,(a,2*z),sign)
        np.add.at(deg,(b,2*z+1),sign)
def cdf_histogram(roles,degrees):
    d=degrees.max(initial=0)+1
    cells=np.empty((2,NCH,d),dtype=np.int64)
    for role in (0,1):
        vals=degrees[roles==role]
        for k in range(NCH):
            cells[role,k]=np.bincount(vals[:,k],minlength=d)
    return cells
def shape(meta):
    role,tok,pos,size=meta.T
    return np.column_stack((role,np.log1p(tok),np.log1p(pos),pos/np.maximum(1,size-1),pos==0,pos==size-1,np.log1p(size)))
def score_rows(meta,deg,rel,coef,bias):
    return np.column_stack((shape(meta),np.log1p(deg),rel))@coef+bias
def signal(n,n_out,rank):
    idx=np.arange(1,n_out+1);coef=np.asarray(rank["coef"])
    return -np.log(idx)*coef[0]+coef[1]/idx+coef[2]*(n-idx)/max(n-1,1)+rank["intercept"]
class DegreeIndex:
    """incremental or deferred histogram, or deferred raw-edge rebuild."""
    def __init__(self,mode):
        assert mode in ("incremental","deferred_hist","deferred_edges")
        self.mode=mode;self.alive=np.zeros(0,bool);self.meta=np.empty((0,4),int)
        self.deg=np.zeros((0,NCH),int);self.edges=set() if mode=="deferred_edges" else None
        self.hist=np.zeros((2,NCH,1),int) if mode=="incremental" else None
        self.cdf=None;self.live_hist=None;self.read_deg=None
    def _reserve(self,n):
        if n<=len(self.alive):return
        pad=max(n,2*len(self.alive),8)-len(self.alive)
        self.alive=np.pad(self.alive,(0,pad));self.meta=np.pad(self.meta,((0,pad),(0,0)))
        if self.mode!="deferred_edges":self.deg=np.pad(self.deg,((0,pad),(0,0)))
    def update(self,state):
        up=state["up"];removed=state["rm"];plus=edge_array(state["plus"]);minus=edge_array(state["minus"])
        if up:self._reserve(max(row[0] for row in up)+1)
        touched=np.asarray(sorted({row[0] for row in up}|set(removed)|{v for es in (state["plus"],state["minus"]) for a,b,_ in es for v in (a,b)}),int)
        if self.hist is not None:
            olda=self.alive[touched];oldr=self.meta[touched,0];oldd=self.deg[touched].copy()
        self.alive[removed]=False
        if up:
            u=np.array(up);self.meta[u[:,0]]=u[:,1:];self.alive[u[:,0]]=True
        if self.mode=="deferred_edges":
            self.edges.difference_update(map(tuple,state["minus"]))
            self.edges.update(map(tuple,state["plus"]))
        else:
            update_degrees(self.deg,minus,-1);update_degrees(self.deg,plus,1)
        if self.hist is not None:
            newa=self.alive[touched];newr=self.meta[touched,0];newd=self.deg[touched]
            assert newd.min(initial=0)>=0
            d=newd.max(initial=0)+1;cap=self.hist.shape[-1]
            if d>cap:self.hist=np.pad(self.hist,((0,0),(0,0),(0,max(d,2*cap)-cap)))
            changed=(oldd!=newd)|((olda!=newa)|(newr!=oldr))[:,None]
            a,k=np.nonzero(changed&olda[:,None]);np.add.at(self.hist,(oldr[a],k,oldd[a,k]),-1)
            a,k=np.nonzero(changed&newa[:,None]);np.add.at(self.hist,(newr[a],k,newd[a,k]),1)
        self.cdf=None;self.live_hist=None;self.read_deg=None
    def prepare_read(self):
        if self.cdf is not None:return
        if self.mode=="deferred_edges":
            self.read_deg=np.zeros((len(self.alive),NCH),int)
            update_degrees(self.read_deg,edge_array(list(self.edges)),1)
        else:self.read_deg=self.deg
        if self.hist is None:self.live_hist=cdf_histogram(self.meta[self.alive,0],self.read_deg[self.alive])
        else:self.live_hist=self.hist
        self.cdf=self.live_hist.cumsum(axis=2)
    def rows(self,ids):
        self.prepare_read()
        roles=self.meta[ids,0];deg=self.read_deg[ids];idx=(roles[:,None],np.arange(NCH),deg)
        eq=self.live_hist[idx];at_most=self.cdf[idx];n=self.cdf[roles,0,-1][:,None]
        return self.meta[ids],deg,(at_most-.5*eq)/n-.5
    def read(self,ids,c,b):
        m,deg,r=self.rows(ids)
        return score_rows(m,deg,r,c,b)
