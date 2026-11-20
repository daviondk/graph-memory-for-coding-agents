"""Uses only public observations and admissible command strings, shared across interventions."""
import hashlib
import re
from collections import Counter

def kind(x):return x.rsplit(' ',1)[0]

def visible(commands,place):
    types=set()
    for c in commands:
        if c.startswith('take ') and c.endswith(' from '+place):types.add(kind(c[5:c.index(' from ')]))
        if c.startswith('use '):types.add(kind(c[4:]))
    return types

def goals(text):
    desc=text.lower().split('your task is to:')[-1].strip().strip('.')
    if desc.startswith(('look at ','examine ')):
        m=re.match(r'(?:look at |examine )(?:the )?(\w+) (?:under|with) (?:the )?(\w+)',desc)
        if m:return m[1],m[2],'light',1
    end=desc.split()[-1]
    if desc.startswith('find two '):return desc.split()[2],end,'',2
    if desc.startswith(('heat ','clean ','cool ')):return desc.split()[2],end,desc.split()[0],1
    m=re.match(r'put (?:a|some|two) (?:(hot|clean|cool) )?(\w+) (?:in|on) ',desc)
    if m:return m[2],end,{'hot':'heat','clean':'clean','cool':'cool',None:''}[m[1]],2 if desc.startswith('put two') else 1
    return '',end,'',1

PRIOR=['countertop','sidetable','desk','shelf','bed','diningtable','coffeetable','sofa','dresser','sinkbasin','toilet','armchair','bathtubbasin','cabinet','drawer','fridge','garbagecan']
def order(place):
    cls,num=place.rsplit(' ',1)
    return (int(num),PRIOR.index(cls) if cls in PRIOR else len(PRIOR),cls)
class Actor:
    def __init__(self,first,commands,arm,priors):
        self.obj,self.dst,self.op,self.required=goals(first)
        self.places=sorted({c[6:] for c in commands if c.startswith('go to ')},key=order)
        self.arm=arm;self.priors=priors;self.place='';self.held='';self.processed=False
        self.delivered=[];self.history=[];self.cursor=None;self.searched=None
    def reset_search(self):
        self.history=[];self.cursor=None
    def remember(self,place):
        if not place:return
        self.searched=place
        if self.arm=='none':return
        if self.arm=='cursor':
            self.cursor=place;return
        if place in self.history:self.history.remove(place)
        self.history.append(place)
        if self.arm=='recent':self.history=self.history[-4:]
    def travel(self,options,commands):
        return next(('go to '+p for p in options if 'go to '+p in commands),None)
    def search(self,target,commands):
        if 'open '+self.place in commands:return 'open '+self.place
        self.remember(self.place)
        def rank(p):
            cls=kind(p);hits=self.priors.get('hits',{}).get(target,{}).get(cls,0)
            seen=self.priors.get('seen',{}).get(cls,0)
            if self.arm=='raw':return -hits
            if self.arm=='rate':return -(hits+1)/(seen+2)
            return 0
        pool=sorted(self.places,key=lambda p:(rank(p),order(p)))
        if self.arm=='cursor' and self.cursor in pool:
            i=pool.index(self.cursor)+1;pool=pool[i:]+pool[:i]
        else:pool=[p for p in pool if p not in self.history]+[p for p in pool if p in self.history]
        return self.travel(pool,commands) or 'look'
    def act(self,commands):
        self.searched=None
        if not self.held:
            options=[c for c in commands if c.startswith('take '+self.obj+' ') and c.split(' from ')[0][5:] not in self.delivered]
            if options:return sorted(options)[0]
            return self.search(self.obj,commands)
        if self.op=='light':
            option=next((c for c in commands if c.startswith('use '+self.dst+' ')),None)
            return option or self.search(self.dst,commands)
        if self.op and not self.processed:
            option=next((c for c in commands if c.startswith(self.op+' '+self.held+' ')),None)
            if option:return option
            target={'heat':'microwave','cool':'fridge','clean':'sinkbasin'}[self.op]
        else:
            target=self.dst
            for c in commands:
                if c.startswith(('move '+self.held+' to '+target+' ','put '+self.held+' in/on '+target+' ','put '+self.held+' in '+target+' ','put '+self.held+' into '+target+' ')):return c
        if kind(self.place)==target and 'open '+self.place in commands:return 'open '+self.place
        return self.travel([p for p in self.places if kind(p)==target],commands) or 'look'
    def update(self,c,feedback):
        if 'nothing happens' in feedback.lower():return
        if c.startswith('go to '):self.place=c[6:]
        elif c.startswith('take '):
            self.held=c[5:c.index(' from ')];self.processed=False;self.reset_search()
        elif c.startswith(('clean ','heat ','cool ')):self.processed=True
        elif c.startswith(('move ','put ')):
            self.delivered.append(self.held);self.held='';self.processed=False;self.reset_search()

