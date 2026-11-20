from common import *
class Cache:
    def __init__(self,rule,cap):
        self.rule=rule;self.cap=cap;self.slots={};self.clock=0
    def obs(self,keys,after_edit):
        keys=sorted(set(keys));before={x:tuple(v) for x,v in self.slots.items()};hits=[x for x in keys if x in before and before[x][0]]
        updates=[];promoted=[];enrolled=[];evicted=[];ghosts=[]
        for key in keys:
            self.clock+=1
            if self.rule=='never':continue
            if self.rule=='bottomk':
                if key in self.slots:continue
                score=digest('admit-bottom6|'+key)
                if len(self.slots)==self.cap:
                    worst=max(self.slots,key=lambda x:(self.slots[x][1],x))
                    if (score,key)>=(self.slots[worst][1],worst):continue
                    del self.slots[worst];evicted.append(worst)
                self.slots[key]=(True,score,0);enrolled.append(key);updates.append(key);continue
            isdoor=self.rule in ('twohit','edit_twohit')
            prior=before.get(key)
            now=self.slots.get(key)
            active=not isdoor or prior is not None or (self.rule=='edit_twohit' and after_edit)
            if now is None and len(self.slots)==self.cap:
                victim=min(self.slots,key=lambda x:((self.slots[x][2] if self.rule=='lfu' else 0),self.slots[x][1],x))
                del self.slots[victim];evicted.append(victim)
            if active and (now is None or not now[0]):
                enrolled.append(key)
                if now is not None:promoted.append(key)
            if not active and now is None:ghosts.append(key)
            count=(now[2]+1 if now else 1) if self.rule=='lfu' else 0
            self.slots[key]=(active,self.clock,count);updates.append(key)
        assert len(self.slots)<=self.cap
        return [hits,enrolled,updates,ghosts,evicted,promoted,sorted(x for x,v in self.slots.items() if v[0])]

