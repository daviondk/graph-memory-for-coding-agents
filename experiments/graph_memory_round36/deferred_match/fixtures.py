"""Synthetic boundary cases. Only fixture identities and outcomes are persisted."""
from common_match import D, DeferredFeeds, eager, put
from types import SimpleNamespace as N
from dataclasses import dataclass

A, B = "/tmp/alpha_test.txt", "/tmp/beta_test.txt"

@dataclass
class Event:
    event_type: str
    call_id: str
    position: N
    raw_arguments: str=""
    arguments: object=None
    content: str=""

def call(key, pos, raw="", parsed=None):
    return Event("tool_call",key,N(message_index=pos//10,sub_index=pos%10),raw,parsed or {})

def result(key,pos,content=""):
    return Event("tool_output",key,N(message_index=pos//10,sub_index=pos%10),content=content)

def check(events,expected,hidden=(),mutation=None,divergence=False):
    early=eager.HistoricalFeeds()
    live=list(events)
    later=DeferredFeeds(live.__getitem__)
    for i,e in enumerate(live):
        if mutation:
            mutation(i,early,later,live)
        visible=e.call_id not in hidden
        early.consume(e,visible)
        later.consume(e,i,visible)
        if not divergence:
            assert early.observed_pairs==later.observed_pairs
    assert early.observed_pairs==set(expected)
    if divergence:
        assert early.observed_pairs!=later.observed_pairs
    return dict(events=len(events),early=len(early.observed_pairs),late=len(later.observed_pairs),equality=early.observed_pairs==later.observed_pairs)

def fixtures():
    assert eager._typed_tokens(A+" "+B)=={("path",A),("path",B)}
    source=[call("producer",10),result("producer",20,A)]
    reader=[call("reader",30,A),result("reader",40)]
    edge=[("producer","reader")]
    checks={
        "producer_appears_after_original_call":check([call("producer",10),call("reader",20,A),result("producer",21,A),result("reader",22)],[]),
        "strict_subposition_parallel_readers":check([call("producer",10),call("r1",20,A),result("producer",21,A),call("r2",22,A),result("r2",30),result("r1",40)],[("producer","r2")]),
        "collision_in_own_result":check(source+[call("reader",30,A),result("reader",40,A)],[]),
        "one_witness_survives":check([call("producer",10),result("producer",20,A+" "+B),call("reader",30,A+" "+B),result("reader",40,A)],edge),
        "invisible_producer":check(source+reader,[],["producer"]),
        "invisible_consumer":check(source+reader,[],["reader"]),
        "argument_only_in_parsed_leaf":check(source+[call("reader",30,"opaque",{"group":[A]}),result("reader",40)],edge),
        "argument_only_in_raw_form":check(source+reader,edge)}
    def mutate(i,early,later,live):
        if i==3:live[2].raw_arguments=""
    checks["counterexample_mutable_arguments"]=check(source+reader,edge,mutation=mutate,divergence=True)
    def resurrect(i,early,later,live):
        if i==5:
            for op in (early,later):
                assert op.producer[A] is None
                op.producer[A]=("producer",(2,0))
    checks["counterexample_recovered_uniqueness"]=check(source+[call("other",21),result("other",22,A),call("reader",30,A),result("reader",40)],[],mutation=resurrect,divergence=True)
    put(D/"fixture_results.json",checks)
    return checks

if __name__=="__main__":
    fixtures()
