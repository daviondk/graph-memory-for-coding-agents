"""Check exact reader consistency for the same prompt and generation seed on overlapping D/E calls."""
from collections import Counter
from independent import INPUT,read,save,sha
def main():
    for p in ('D','E'):
        m=read(INPUT/f'{p}_decisions.json')
        assert all(sha(INPUT/(p+'_calls')/k)==v for k,v in m.items())
    d=read(INPUT/'D_assignment.json');e=read(INPUT/'E_assignment.json')
    ids=set(d)&set(e);ct=Counter(); details=[]
    for uid in sorted(ids):
        for arm in ('bridge','order'):
            h=d[uid][arm];assert h==e[uid][arm]
            a,b=[read(INPUT/(p+'_calls')/(h+'.json.gz')) for p in ('D','E')]
            assert a['request']==b['request']
            ac,bc=[ob['reply']['choices'][0]['message']['content'] for ob in (a,b)]
            ct['shared_calls']+=1;ct['raw_text_equal']+=int(ac==bc)
            ct['whole_record_equal']+=int(a==b)
            details.append([uid,arm,h,ac==bc,a==b])
    save('cross_panel_consistency.json',dict(counts=ct,details=details))
    print(ct)
if __name__=='__main__':main()

