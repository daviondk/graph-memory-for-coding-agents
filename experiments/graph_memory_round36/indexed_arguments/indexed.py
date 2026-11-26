"""A per-call representation with exact substring semantics; no cross-call index."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"deferred_match"))
from common_match import eager
from graph_memory.graphs.provenance.builder import _iter_string_leaves

def all_leaves(call):
    return tuple(_iter_string_leaves(call.arguments))

def uncovered_leaves(call):
    raw=call.raw_arguments
    return tuple(leaf for leaf in dict.fromkeys(_iter_string_leaves(call.arguments)) if leaf not in raw)

def contains(raw,leaves,value):
    if value in raw:
        return True
    return bool(leaves) and any(value in leaf for leaf in leaves)

class PreparedFeeds(eager.HistoricalFeeds):
    def __init__(self,prepare):
        super().__init__()
        self.prepare=prepare

    def consume(self,event,has_output_chunks=False):
        if event.event_type!="tool_call":
            return super().consume(event,has_output_chunks)
        call=event.call_id
        position=event.position.message_index,event.position.sub_index
        assert call not in self.open_calls
        leaves=self.prepare(event)
        raw=event.raw_arguments
        self.open_calls[call]=[
            (value,origin[0]) for value,origin in self.producer.items()
            if origin is not None and origin[1]<position and contains(raw,leaves,value)
        ]
