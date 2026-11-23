"""Measure the persistent state of a streaming equivalent of the exact failing-ID control."""
from study import PRIV, ROOT, STATUS, SUMMARY, dg, load, put, trace


def measure():
    design=load(ROOT/"design-lock.json")
    obs=load(PRIV/"observation.json")
    measures=[]
    sealed=load(ROOT/"forecast-seal.json")
    assert dg(ROOT/"forecasts.json.gz")==sealed["forecast"]
    for forecast in load(ROOT/"forecasts.json.gz"):
        target=forecast["target"];state=forecast["state"]
        fields,events=trace(design["roster"][target],target,state,obs)
        # Encoding is an empty/non-empty byte, then the UTF-8 nodeid. The live text
        # for the current tool observation is shared by all event-level writers.
        value=b"\0";peak=1
        for event in events:
            if event["metadata"]["tool_name"]!="exec" or event["metadata"]["node_kind"]!="content.tool_output":
                continue
            text=fields[event["source_spans"][0]["event_id"]]
            for parser in (STATUS,SUMMARY):
                for match in parser.finditer(text):
                    candidate=match[1].encode()
                    if value==b"\0" or candidate<value[1:]:
                        value=b"\1"+candidate
                        peak=max(peak,len(value))
        got=None if value==b"\0" else value[1:].decode()
        ref=forecast["arms"]["failure_index"]
        assert got==ref["selected"] and len(value)==ref["bytes"]
        measures.append(dict(target=target,state=state,peak_bytes=peak,final_bytes=len(value)))
    put(ROOT/"stream-index.json",dict(seal=dg(ROOT/"forecast-seal.json"),rows=measures,
        max_peak=max(r["peak_bytes"] for r in measures),max_final=max(r["final_bytes"] for r in measures)))

if __name__=="__main__":
    measure()
