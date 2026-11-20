"""Independent stream. All arms call exactly the same frozen native interfaces as on Kimi."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import gzip
import json
import sys
import native
import multiple
import hybrid

FILE_AND_SINGLE=native.retrieve


def all_modes(*args):
    return dict(standard=FILE_AND_SINGLE(*args),multiple=multiple.retrieve_many(*args),hybrid=hybrid.choose(*args))


if __name__=='__main__':
    native.retrieve=all_modes
    data=native.HERE/'external'
    output=data/(sys.argv[1] if len(sys.argv)>1 else 'measured')
    output.mkdir(exist_ok=False)
    inputs=list(native.rows('external/stream.jsonl.gz'))
    assert len(inputs)==48
    qindex=defaultdict(list)
    for q in native.rows('external/queries.jsonl.gz'):
        qindex[q['id']].append(q)
    hybrid.HOT.update({k:v['address'] for k,v in native.rows('external/graph.jsonl.gz')})
    with (ProcessPoolExecutor(4) as pool, gzip.open(output/'rendered.jsonl.gz','wt',encoding='utf8') as writer,
          open(output/'cost.jsonl','w',encoding='utf8') as costs):
        jobs=[(s,qindex[s['id']],output) for s in inputs if qindex.get(s['id'])]
        for num,(receipt,predictions) in enumerate(pool.map(native.process,jobs),1):
            for pr in predictions:
                writer.write(json.dumps(pr,ensure_ascii=True,separators=(',',':'))+'\n')
            costs.write(json.dumps(receipt)+'\n')
            costs.flush()
            print(num,len(jobs),receipt,flush=True)
