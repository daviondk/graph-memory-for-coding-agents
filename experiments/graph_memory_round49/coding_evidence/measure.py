"""Open assignment after scores are fixed and record bytes from the actual HTTP sessions."""
import gzip,json
from collections import Counter
from datetime import datetime
from settings import D,P,load,dump,sha,h
def size(s):return len(s.encode('utf8'))
def main():
    lock=load(D/'locked.json');sealed=load(D/'grade-seal.json')
    assert sealed['lock']==sha(D/'locked.json') and (D/'suite/summary.json').is_file()
    assert all(sha(D/'grading'/n)==v for n,v in sealed['files'].items())
    mapping=load(P/'assignment.json');assert sha(P/'assignment.json')==load(D/'handoff-seal.json')['assignment']
    rows={};traces={}
    for token,record in sorted(mapping.items(),key=lambda x:x[1]['label']):
        actor=record['label'];arm=record['condition'];blind='blind'+actor.split('-')[1];folder=P/actor
        state=load(folder/'session.json');frozen=state['frozen']
        assert frozen['patch_sha256']==lock['cases'][blind]['sha256']==sha(folder/'change.patch')
        mem=(folder/'memory.txt').read_bytes();assert h(mem)==load(D/'packet-seal.json')['digest'][arm]
        ops=Counter();charged=Counter();returned=Counter();codes=Counter();events=[];paths=set();touched=set();truncated=0
        for event in state['logs']:
            payload=event['request'].copy();resp=event['response'];op=payload['op']
            ops[op]+=1;codes[event['code']]+=1;returned[op]+=size(json.dumps(resp,ensure_ascii=False))
            if op in ('read','search','list') and 'text' in resp:
                assert resp['charged_bytes']==size(resp['text'])
                charged[op]+=resp['charged_bytes'];truncated+=bool(resp['truncated'])
            if op=='start' and 'memory' in resp:
                assert resp['memory'].encode()==mem;charged['memory']+=len(mem)
            if op=='read' and 'text' in resp:paths.add(payload['path'])
            if op=='edit':
                if event['code']==200:touched.add(payload['path'])
                for name in ('old','new'):
                    s=payload.pop(name);payload[name+'_sha256']=h(s.encode());payload[name+'_bytes']=size(s)
            events.append(dict(seq=event['seq'],request=payload,response=resp,utc=event['utc'],code=event['code']))
        assert sum(charged.values())==state['bytes']==frozen['budget']['source_bytes']
        assert token not in json.dumps(events)
        first=events[0]['response'];assert ops['start']==ops['finish']==1
        prompt=(D/'ACTOR_PROMPT.txt').read_text(encoding='utf8').rstrip('\r\n').replace('{ACTOR}',actor).replace('{ENDPOINT}','http://127.0.0.1:18891/v1/'+token)
        times=[datetime.fromisoformat(ev['utc']) for ev in events]
        rows[blind]={'condition':arm,'actor':actor,'prompt_template_rendered_bytes':size(prompt),'issue_delivered_bytes':size(first['issue']),
                     'operations':dict(ops),'http_codes':dict(codes),'gateway_bytes':state['bytes'],'charged':dict(charged),
                     'response_json_body_bytes':sum(returned.values()),'responses_by_op':dict(returned),'read_paths':sorted(paths),
                     'touched_paths':sorted(touched),'truncated_responses':truncated,'patch_bytes':frozen['patch_bytes'],
                     'elapsed_first_to_finish_s':round((times[-1]-times[0]).total_seconds(),3),
                     'session_sha256':sha(folder/'session.json'),'patch_sha256':frozen['patch_sha256']}
        traces[blind]=events
    raw=(json.dumps(traces,sort_keys=True,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    (D/'responses.json.gz').write_bytes(gzip.compress(raw,mtime=0));dump(D/'profiles.json',rows)
    print(json.dumps({k:[v['condition'],v['gateway_bytes'],v['charged'],v['operations'],v['patch_bytes'],v['truncated_responses'],len(v['read_paths'])] for k,v in rows.items()}))
if __name__=='__main__':main()
