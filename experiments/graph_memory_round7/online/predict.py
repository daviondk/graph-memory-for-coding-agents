"""One decision before observing each action. Input is an iterator of completed actions."""
import collections
import gzip
import json
from prepare import HERE, digest, dumps, rows, save

RULES = ("recency","forward","return","previous","graph")
ARMS = RULES+("pooled","typed")

class State:
    def __init__(self):
        self.latest = None
        self.history = []
        self.edges = collections.defaultdict(dict)
        self.pooled = collections.Counter()
        self.by_kind = collections.defaultdict(collections.Counter)
        self.time=0

    def make_prediction(self):
        if not self.latest:
            return dict.fromkeys(ARMS), "cold"
        kind,path,first,last = self.latest
        start=(path,first)
        other=next((node for node in reversed(self.history[:-1]) if node[0]!=path),start)
        prev=next((node for node in reversed(self.history[:-1]) if node[0]==path),start)
        edge=self.edges.get(start,{})
        successor=max(edge,key=edge.get) if edge else start
        pred=dict(zip(RULES,(start,(path,last+1),other,prev,successor)))
        pred["pooled"]=pred[max(RULES,key=lambda k:self.pooled[k])]
        pred["typed"]=pred[max(RULES,key=lambda k:self.by_kind[kind][k])]
        return pred,kind

    def observe(self,event,forecasts,context):
        self.time+=1
        if event is None:
            return
        kind,path,start,end=event
        address=(path,start)
        if kind=="view" and self.latest:
            for arm in RULES:
                if forecasts[arm]==address:
                    self.pooled[arm]+=1
                    self.by_kind[context][arm]+=1
            last_address=self.history[-1]
            store=self.edges[last_address]
            count=store.get(address,(0,0))[0]+1
            store[address]=(count,self.time)
        self.history.append(address)
        self.latest=kind,path,start,end

def predict(events):
    state=State()
    for step,event in enumerate(events):
        forecasts,context=state.make_prediction()
        yield step+1,context,forecasts
        # The prediction above has already been emitted. The supplied action is revealed now.
        state.observe(event,forecasts,context)

def validate():
    examples=[["view","a.py",2,4],None,["edit","b.py",8,8],["view","a.py",2,2],
              ["view","a.py",6,7],["view","a.py",2,2],["view","b.py",3,5]]
    original=list(predict(iter(examples)))
    for i in range(len(examples)):
        replacement=examples[:i]+[["edit","unseen.py",999,1000]]*(len(examples)-i)
        assert original[:i+1]==list(predict(iter(replacement)))[:i+1]
    assert set(original[0][2].values())=={None}
    assert original[2][2]["forward"]==("a.py",5)

def main():
    validate()
    lock=json.loads((HERE/"freeze.json").read_bytes())
    assert all(digest(HERE/k)==v for k,v in lock["files"].items())
    n=0
    with gzip.GzipFile(filename=str(HERE/"predictions.jsonl.gz"),mode="wb",mtime=0) as out:
        for row in rows(HERE/"observations.jsonl.gz"):
            for step,context,forecasts in predict(iter(row["events"])):
                out.write((dumps([row["id"],step,context,[forecasts[k] for k in ARMS]])+"\n").encode())
                n+=1
    save(HERE/"predictions_lock.json",{"arms":ARMS,"rows":n,"sha256":digest(HERE/"predictions.jsonl.gz"),
                                       "freeze":digest(HERE/"freeze.json"),"suffix_invariance":True})
    print("predictions sealed",n)

if __name__=="__main__":
    main()
