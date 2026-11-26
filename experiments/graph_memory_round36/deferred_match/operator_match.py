"""Resolve original, immutable call arguments only after the corresponding output is visible."""
from graph_memory.graphs.provenance.builder import _argument_contains,_typed_tokens
class DeferredFeeds:
    def __init__(self,read_call,contains=_argument_contains):
        self.read_call=read_call
        self.contains=contains
        self.producer={}
        self.pending={}
        self.visible_outputs=set()
        self.observed_pairs=set()

    def consume(self,event,handle,has_output_chunks=False):
        call=event.call_id
        pos=(event.position.message_index,event.position.sub_index)
        if event.event_type=="tool_call":
            assert call not in self.pending
            self.pending[call]=(handle,pos)
            return
        if event.event_type!="tool_output":
            return
        for _,value in _typed_tokens(event.content):
            known=self.producer.get(value)
            if value not in self.producer:
                self.producer[value]=(call,pos)
            elif known is not None and known[0]!=call:
                self.producer[value]=None
        h,original=self.pending.pop(call)
        if not has_output_chunks:
            return
        self.visible_outputs.add(call)
        args=None
        for value,source in self.producer.items():
            if source is None or source[1]>=original or source[0] not in self.visible_outputs:
                continue
            if args is None:
                args=self.read_call(h)
            if self.contains(args,value):
                self.observed_pairs.add((source[0],call))