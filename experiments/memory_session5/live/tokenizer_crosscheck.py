"""Compare the stored tokenizer's wire budget to actual llama.cpp GGUF tokenization for every note."""
import requests
from tokenizers import Tokenizer
from common import *
def main():
    tok=Tokenizer.from_file(str(ROOT/'tokenizer.json'))
    ids=read('roster.json')['ids']+read('transfer/roster.json')['ids'];notes={}
    for s in ('','transfer'):
        expected=read((ROOT/s/'roster.json').relative_to(ROOT))['ids']
        for i in expected:
            pref=read((ROOT/s/'prefix'/(slug(i)+'.json')).relative_to(ROOT))
            for a,text in pref['notes'].items():
                k=digest(text)
                notes.setdefault(k,{'value':text,'appearances':[]})['appearances'].append([i,a])
    session=requests.Session();out=[]
    for k,v in sorted(notes.items()):
        text=v['value'];loc=tok.encode(text,add_special_tokens=False).ids
        r=session.post('http://127.0.0.1:18951/tokenize',json={'content':text,'add_special':False,'parse_special':False},timeout=30)
        r.raise_for_status();native=r.json()['tokens']
        out.append({'sha':k,'arms':v['appearances'],'local':len(loc),'native':len(native),'identical_ids':loc==native})
    save('runtime/tokenizer_native.json.gz',out)
    print('unique strings',len(out),'different token counts',sum(v['native']!=v['local'] for v in out),
          'over cap limited presentations',sum(sum(a in ('bundle','center','recent') for _,a in v['arms']) for v in out if v['native']>80))
if __name__=='__main__':main()
