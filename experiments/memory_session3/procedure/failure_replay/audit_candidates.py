"""Verify ALL guarded antecedents in upstream model-visible messages. No reasoning or native raw text written."""
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import csv,hashlib,json,re,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    rows=[r for r in csv.DictReader((ROOT/'casewise.csv').open()) if r['arm']=='guard8']
    m={(s['model'],s['id']):s for s in json.loads((ROOT.parent/'list.json').read_bytes())}
    expected={(s['model'],s['id']):s['sha256'] for s in json.loads((ROOT.parent/'sources.json').read_bytes())}
    def verify(key):
        import gzip
        mod,id_=key; source=m[key]
        data=urllib.request.urlopen(source['url'],timeout=90).read();assert sha(data)==expected[key]
        raw=json.loads(data);proj=json.loads(gzip.decompress((ROOT.parent/'events'/mod/(id_+'.json.gz')).read_bytes()))
        matches={}
        for v in raw['messages']:
            if v.get('role')=='tool' or v.get('type')=='function_call_output':
                cid=v.get('tool_call_id',v.get('call_id')); matches.setdefault(cid,[]).append(v)
        log=[]
        for r in rows:
            if (r['model'],r['issue'])!=key:continue
            stages={}
            for group in [r['from_group'],r['group']]:
                ev=proj['groups'][int(group)][0]; out=ev['result'];cand=[]
                for msg in matches[ev['call']]:
                    ex=msg['extra'];txt=msg.get('content',msg.get('output',''))
                    visible=ex.get('raw_output','')
                    if ex.get('returncode')==out['rc'] and sha(visible.encode())==out['sha']:cand.append((txt,visible,str(ex.get('exception_type') or '')))
                assert cand and len(set(cand))==1
                txt,visible,exception_class=cand[0]
                explicitly_displayed=bool(re.search(r'<returncode>\s*'+str(out['rc'])+r'\s*</returncode>',txt,re.I))
                labels=[]
                for word,pat in [('timeout',r'time[ -]?out|timed out'),('transport',r'connection|transport|socket|HTTPConnectionPool|max retries|RemoteDisconnected|connecterror'),('container',r'container|docker|podman'),('permission',r'permission denied|operation not permitted'),('assertion',r'assertionerror|assert .*='),('not_found',r'no such file or directory|not found')]:
                    if re.search(pat,visible,re.I):labels.append(word)
                error_part=re.search(r'<exception>(.*?)</exception>',txt,re.S)
                stages[group]={'rc':out['rc'],'visible_rc_xml':explicitly_displayed,'raw_output_in_feedback':visible in txt,'native_output_bytes':len(visible.encode()),'sha':out['sha'],'markers':labels,'exception_type':exception_class,'public_exception_present':bool(error_part),'full_feedback_sha256':sha(txt.encode()),'exception_reports_timeout':bool(error_part and re.search(r'timed out|timeouterror|timeoutexpired',error_part[1],re.I))}
                if group==r['from_group']:assert out['visible'] and visible in txt
            log.append({'model':mod,'issue':id_,'command_sha':r['cmd_sha'],'readonly':r['readonly']=='True','before':stages[r['from_group']],'after':stages[r['group']],'native_trajectory_sha':expected[key],'groups':[int(r['from_group']),int(r['group'])]})
        return log
    pairs=sorted({(r['model'],r['issue']) for r in rows})
    with ThreadPoolExecutor(8) as pool:logs=[x for group in pool.map(verify,pairs) for x in group]
    assert len(logs)==len(rows)
    (ROOT/'upstream_guard_audit.json').write_text(json.dumps(logs,indent=1),encoding='utf8')
    for x in logs:print(x['issue'],x['readonly'],x['before']['rc'],x['after']['rc'],x['before']['exception_type'],x['before']['exception_reports_timeout'],x['before']['full_feedback_sha256']==x['after']['full_feedback_sha256'])
if __name__=='__main__':main()

