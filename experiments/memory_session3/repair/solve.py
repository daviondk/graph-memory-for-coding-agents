"""Fresh-context handoffs. Cache only identical full payloads and keep every actual native response."""
import json
import re
import time
from urllib.request import Request,urlopen
from common import ROOT,utc,read,save,sha,obj,freeze
URL='http://127.0.0.1:18839/replicate/0/v1/chat/completions'
SYSTEM=('You are the engineer resuming a Python algorithm repair after an interrupted test run. Return the complete corrected Python module inside one Python code fence. Preserve its public function name and signature. Implement the algorithm generally. Use only the Python standard library. Your reply will be executed directly. No explanation.')
def main():
    lock=read('solver_lock.json')['files'];assert freeze(lock)==lock
    inputs=read('solver_inputs.json'); decisions=[]
    for r in read('schedule.json'):
        item=inputs[r['name']];note=item['memory'][r['arm']] or '(no retained execution observations)'
        user='Current Python module:\n'+item['buggy_source']+'\n\nRetained observations from the interrupted run:\n'+note+'\n\nComplete the repair.'
        payload={'model':'qwen38-27b-ud-q4km','messages':[{'role':'system','content':SYSTEM},{'role':'user','content':user}],'temperature':0,'seed':17112026,'max_tokens':1536,'stream':False}
        key=sha(obj(payload));n='calls/'+key+'.json'
        if not (ROOT/n).exists():
            start=time.time()
            req=Request(URL,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urlopen(req,timeout=480) as res:reply=json.load(res)
            save(n,{'utc':utc(),'seconds':time.time()-start,'payload':payload,'response':reply})
        reply=read(n)['response'];txt=reply['choices'][0]['message'].get('content') or ''
        f=re.search(r'```(?:python|py)?\s*\n(.*?)```',txt,re.S|re.I)
        code=(f[1] if f else txt).strip()+'\n'
        decisions.append({**r,'key':key,'candidate':code,'length_finish':reply['choices'][0]['finish_reason']=='length','usage':reply['usage'],'response_id':reply['id']})
        save('decisions.partial.json',decisions)
    save('decisions.json',decisions)
    paths=['decisions.json','solver_lock.json']+sorted(set('calls/'+d['key']+'.json' for d in decisions))
    save('output_lock.json',{'utc':utc(),'files':freeze(paths)})
    print(len(decisions),'assignments',len(paths)-2,'actual calls')
if __name__=='__main__':main()

