"""Lossless predicate cases with independent truth and standard-library serialization."""
import json,itertools
from types import SimpleNamespace
from indexed import eager,contains,all_leaves,uncovered_leaves
from experiment import D,put
from graph_memory.graphs.provenance.builder import _iter_string_leaves

def check():
    cases={}
    def case(name,value,query,expected,raw=None):
        wire=json.dumps(value,ensure_ascii=True,separators=(",",":")) if raw is None else raw
        call=SimpleNamespace(raw_arguments=wire,arguments=value)
        native=eager._argument_contains(call,query)
        assert native==contains(wire,all_leaves(call),query)==contains(wire,uncovered_leaves(call),query)==expected
        cases[name]=dict(positive=expected,raw=bool(query in wire),all=len(all_leaves(call)),uncovered=len(uncovered_leaves(call)))
    case("unicode_escape",{"x":["дом"]},"до",True)
    case("escaped_quote",{"x":['foo"bar']} ,'o"b',True)
    case("escaped_backslash",["a\\b"],"a\\b",True)
    case("escaped_control_character",["a\nb"],"a\nb",True)
    case("repeated_escaped_leaves",[["дом"],["дом"]],"до",True)
    case("raw_covers_decoded",["alpha","alpha"],"pha",True)
    case("raw_keys_count",{"needle_key":"v"},"needle_key",True)
    case("separate_leaves",["left","right"],"leftright",False)
    case("empty_query",[],"",True)
    case("missing",{"x":[3,None]},"somevalue",False)
    case("no_unicode_normalization",["é"],"e\u0301",False)
    case("preparation_with_noncanonical_raw",{"x":["hidden"]},"idd",True,"opaque")
    case("raw_outside_decoded_value",{},"abc",True,"specialabc")
    assert cases["repeated_escaped_leaves"]["uncovered"]==1
    assert cases["raw_covers_decoded"]["uncovered"]==0
    # Enumerate every substring of serialized input and decoded leaves, including punctuation and empty value.
    objs=[["a","b"],["\\"], {"key":['ab"cd','ab"cd']},{"\u0301":[None,'\u00e9','e\u0301']}, "",{}, {"n":[0,False]},["x\ny"],["left","right"]]
    queries=0
    for obj in objs:
        for ascii_form in (True,False):
            raw=json.dumps(obj,ensure_ascii=ascii_form,separators=(",",":"))
            call=SimpleNamespace(raw_arguments=raw,arguments=obj)
            leaves=tuple(_iter_string_leaves(obj))
            probes={x[i:j] for x in (raw,*leaves) for i in range(len(x)+1) for j in range(i,len(x)+1)}
            probes.update(["absent_xyz","ab"+"\0"+"cd","".join(leaves)])
            for q in probes:
                answer=q in raw or any(q in s for s in leaves)
                assert answer==eager._argument_contains(call,q)==contains(raw,all_leaves(call),q)==contains(raw,uncovered_leaves(call),q)
            queries+=len(probes)
    out=dict(cases=cases,enumerated_queries=queries,serialization_variants=2,enumerated_objects=len(objs))
    put(D/"fixture-results.json",out)
    print(len(cases),queries)
if __name__=="__main__":check()
