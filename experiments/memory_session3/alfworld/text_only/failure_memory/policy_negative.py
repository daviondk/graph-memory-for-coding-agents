"""Additional transient/pose-scoped memory. Base controller copied byte-for-byte."""
from base_actor import Actor
class NegativeActor(Actor):
    def __init__(self,initial,mode,priors):
        super().__init__(initial,'trained',priors)
        self.mode=mode;self.rejected=set();self.last=None;self.active=0
    def action(self):
        denied=self.rejected if self.mode=='pose_set' else {self.last} if self.mode=='one_step' and self.last else set()
        self.active=len(denied)
        original_places=self.places
        if denied:self.places=[p for p in original_places if p not in denied]
        try:return super().action()
        finally:self.places=original_places
    def update(self,action,feedback):
        previous=self.place
        accepted=super().update(action,feedback)
        self.last=None
        if previous!=self.place:self.rejected.clear()
        if action.startswith('go to ') and feedback.strip().lower()=='nothing happens.':
            destination=action[6:]
            if self.mode=='one_step':self.last=destination
            if self.mode=='pose_set':self.rejected.add(destination)
        return accepted

