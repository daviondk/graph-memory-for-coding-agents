"""Text feedback only. Policy interface is reset text -> action -> feedback."""
import re
from collections import Counter
ENT=re.compile(r'\b([a-z][a-z0-9]* [0-9]+)\b')
PRIOR=['countertop','sidetable','desk','shelf','bed','diningtable','coffeetable','sofa','dresser','sinkbasin','toilet','armchair','bathtubbasin','cabinet','drawer','fridge','garbagecan']
def kind(s):return s.rsplit(' ',1)[0]
def order(s):
    typ,num=s.rsplit(' ',1);return (int(num),PRIOR.index(typ) if typ in PRIOR else len(PRIOR),typ)
def locations(text):
    overview=text.lower().split('your task is to:')[0]
    return sorted(set(ENT.findall(overview)),key=order)
def goals(text):
    desc=text.lower().split('your task is to:')[-1].strip().strip('.')
    m=re.match(r'(?:look at |examine )(?:the )?(\w+) (?:under|with) (?:the )?(\w+)',desc)
    if m:return m[1],m[2],'light'
    if desc.startswith('find two '):return desc.split()[2],desc.split()[-1],''
    if desc.startswith(('heat ','clean ','cool ')):return desc.split()[2],desc.split()[-1],desc.split()[0]
    m=re.match(r'put (?:a|some|two) (?:(hot|clean|cool) )?(\w+) (?:in|on) (\w+)',desc)
    if m:return m[2],m[3],{'hot':'heat','clean':'clean','cool':'cool',None:''}[m[1]]
    return '','',''
class Actor:
    def __init__(self,initial,arm,priors):
        self.obj,self.dst,self.op=goals(initial);self.places=locations(initial);self.arm=arm;self.priors=priors
        self.place='';self.local=[];self.closed=False;self.held='';self.processed=False;self.delivered=[]
        self.history=[];self.cursor=None
    def view(self,feedback):
        t=feedback.lower();self.closed=' is closed.' in t
        self.local=sorted(set(ENT.findall(t.split('you see ',1)[1]))) if 'you see ' in t else []
    def search(self,target):
        if self.closed:return 'open '+self.place
        if self.place:
            if self.arm=='cursor':self.cursor=self.place
            if self.arm in ('full','trained') and self.place not in self.history:self.history.append(self.place)
        def rank(p):
            return (-self.priors.get(target,{}).get(kind(p),0) if self.arm=='trained' else 0,order(p))
        pool=sorted(self.places,key=rank)
        anchor=self.place if self.arm=='pose_cycle' else self.cursor if self.arm=='cursor' else None
        if anchor in pool:
            i=pool.index(anchor)+1;pool=pool[i:]+pool[:i]
        else:pool=[p for p in pool if p not in self.history]+[p for p in pool if p in self.history]
        return next(('go to '+p for p in pool if p!=self.place),'look')
    def action(self):
        if not self.held:
            matching=[x for x in self.local if kind(x)==self.obj and x not in self.delivered]
            if matching:return 'take '+matching[0]+' from '+self.place
            return self.search(self.obj)
        if self.op=='light':
            lamps=[x for x in self.local if kind(x)==self.dst]
            return 'use '+lamps[0] if lamps else self.search(self.dst)
        need=self.op and not self.processed
        target={'heat':'microwave','clean':'sinkbasin','cool':'fridge'}[self.op] if need else self.dst
        if kind(self.place)==target:
            if need:return self.op+' '+self.held+' with '+self.place
            if self.closed:return 'open '+self.place
            return 'move '+self.held+' to '+self.place
        return next(('go to '+p for p in self.places if kind(p)==target),'look')
    def update(self,action,feedback):
        t=feedback.lower()
        if action.startswith('go to ') and 'you arrive at ' in t:
            self.place=action[6:];self.view(t);return True
        if action.startswith('open ') and 'you open the ' in t:
            self.view(t);return True
        if action.startswith('take ') and 'you pick up ' in t:
            self.held=action[5:].split(' from ')[0];self.processed=False
            if self.held in self.local:self.local.remove(self.held)
            self.history=[];self.cursor=None;return True
        if action.startswith(('cool ','heat ','clean ')) and ('you '+action.split()[0]+' the ') in t:
            self.processed=True;return True
        if action.startswith('move ') and 'you move the ' in t:
            self.delivered.append(self.held);self.held='';self.processed=False;self.history=[];self.cursor=None;return True
        if action.startswith('use ') and 'you turn ' in t:return True
        return action=='look' and ('you are ' in t or 'you see ' in t)
class Scout:
    def __init__(self,initial):
        self.actor=Actor(initial,'none',{})
        self.samples={};self.next=iter(self.actor.places)
    def action(self):
        a=self.actor
        if a.closed:return 'open '+a.place
        if a.place and a.place not in self.samples:self.samples[a.place]=sorted({kind(x) for x in a.local})
        p=next(self.next,None)
        return 'go to '+p if p else None
    def update(self,action,feedback):return self.actor.update(action,feedback)

