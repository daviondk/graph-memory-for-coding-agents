"""Maintain existing ISETrace data.feeds semantics on successive events."""
from collections import Counter
from dataclasses import dataclass, field
from graph_memory.graphs.provenance.builder import _typed_tokens, _argument_contains


@dataclass
class Producer:
    source: str
    position: tuple[int, int]
    readers: set[str] = field(default_factory=set)


class FeedIndex:
    def __init__(self):
        self.values: dict[str, Producer | None] = {}
        self.support: Counter = Counter()
        self.ever: set[tuple[str,str]] = set()
        self.adds = self.removes = self.ambiguities = self.witness_deletions = 0
        self.preserved_multiple = 0

    def consume(self, event):
        pos = (event.position.message_index,event.position.sub_index)
        if event.event_type == "tool_call":
            for value, entry in self.values.items():
                if entry is None or entry.position >= pos:
                    continue
                if _argument_contains(event,value):
                    reader = event.call_id
                    assert reader not in entry.readers
                    entry.readers.add(reader)
                    edge = (entry.source, reader)
                    if self.support[edge] == 0:
                        self.adds += 1
                        self.ever.add(edge)
                    self.support[edge] += 1
        elif event.event_type == "tool_output":
            for _,value in sorted(_typed_tokens(event.content)):
                if value not in self.values:
                    self.values[value] = Producer(event.call_id,pos)
                    continue
                entry = self.values[value]
                if entry is None or entry.source == event.call_id:
                    continue
                self.ambiguities += 1
                for reader in entry.readers:
                    edge = (entry.source, reader)
                    self.support[edge] -= 1
                    self.witness_deletions += 1
                    if self.support[edge] == 0:
                        del self.support[edge]
                        self.removes += 1
                    else:
                        self.preserved_multiple += 1
                self.values[value] = None

    def state_size(self):
        return {"known_values":len(self.values), "unique_values":sum(v is not None for v in self.values.values()),
                "live_witnesses":sum(self.support.values()), "live_edges":len(self.support)}

