"""Accumulate only FEEDS pairs which have coexisted between visible output chunks."""
from graph_memory.graphs.provenance.builder import _argument_contains, _typed_tokens

class HistoricalFeeds:
    def __init__(self):
        self.producer = {}
        self.open_calls = {}
        self.visible_outputs = set()
        self.observed_pairs = set()

    def consume(self, event, has_output_chunks=False):
        call_id = event.call_id
        position = (event.position.message_index, event.position.sub_index)
        if event.event_type == "tool_call":
            assert call_id not in self.open_calls
            self.open_calls[call_id] = [
                (value, definition[0]) for value, definition in self.producer.items()
                if definition is not None and definition[1] < position and _argument_contains(event, value)
            ]
        elif event.event_type == "tool_output":
            for _, value in _typed_tokens(event.content):
                if value not in self.producer:
                    self.producer[value] = (call_id, position)
                elif self.producer[value] is not None and self.producer[value][0] != call_id:
                    self.producer[value] = None
            candidates = self.open_calls.pop(call_id)
            if has_output_chunks:
                self.visible_outputs.add(call_id)
                for value, source in candidates:
                    current = self.producer[value]
                    if current is not None and current[0] == source and source in self.visible_outputs:
                        self.observed_pairs.add((source, call_id))

    def pending_references(self):
        return sum(len(candidates) for candidates in self.open_calls.values())

