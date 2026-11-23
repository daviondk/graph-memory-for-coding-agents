"""Retrospective localization of lost actionable evidence in unmodified forecast masks."""
from study import PRIV, ROOT, stream, trace, read_spans, parse_failure, load, dg, put


def main():
    seal=load(ROOT/"forecast-seal.json");assert dg(ROOT/"forecasts.json.gz")==seal["forecast"]
    obs=load(PRIV/"observation.json");plan=load(ROOT/"design-lock.json")
    truth={(r["target"],r["state"]):r for r in load(ROOT/"outcomes.json.gz")}
    tok=stream.Tokenizer.from_file(str(stream.TOKENIZER));tok.no_truncation();tok.no_padding()
    records=[]
    for row in load(ROOT/"forecasts.json.gz"):
        target=row["target"];state=row["state"];out=truth[target,state]
        if out["unknown"] or not out["gold"]:
            continue
        fields,pool=trace(plan["roster"][target],target,state,obs)
        ad,blocks,keys,miss=stream.stream_blocks(fields,pool,tok)
        assert not miss and len(blocks)==row["blocks"]
        for arm,record in row["arms"].items():
            if "kept" not in record:
                continue
            def found(ids):
                c=set().union(*(parse_failure(s) for s in read_spans(ids,blocks,ad,fields)))
                return bool(c.intersection(out["gold"]))
            records.append(dict(target=target,state=state,arm=arm,stored=found(record["kept"]),
                read=found(record["picked"]),action=out["actions"][arm]["success"]))
    summary={}
    for arm in sorted({r["arm"] for r in records}):
        rows=[r for r in records if r["arm"]==arm]
        summary[arm]={k:sum(r[k] for r in rows) for k in ("stored","read","action")}
    put(ROOT/"stage-loss.json",dict(seal=dg(ROOT/"forecast-seal.json"),results=dg(ROOT/"results.json"),
        rows=records,summary=summary))
    print(summary)


if __name__=="__main__":
    main()
