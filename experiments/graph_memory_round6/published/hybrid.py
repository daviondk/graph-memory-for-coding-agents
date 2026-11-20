"""Hot complete-range lookup followed by a whole MemTrace cold query on any miss."""
import json
import native
from multiple import retrieve_many

HOT={}
BYTE_CAP=32768*3


def wire(q,lines):
    return json.dumps({'file':q['path'],'first':q['lo'],'lines':lines},ensure_ascii=False,separators=(',',':'))


def choose(reader,milestone,repo,q,current,directory,has_any_page):
    lines=HOT[q['key']]
    assert len(lines)==q['n']
    response=wire(q,lines)
    if all(line is not None for line in lines) and len(response.encode('utf8'))<=BYTE_CAP:
        return {'route':'hot','response':response}
    return {'route':'cold','response':retrieve_many(reader,milestone,repo,q,current,directory,has_any_page)}


if __name__=='__main__':
    HOT.update({k:v['address'] for k,v in native.rows('graph.jsonl.gz')})
    native.retrieve=choose
    native.main()
