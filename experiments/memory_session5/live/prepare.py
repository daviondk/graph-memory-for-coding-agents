from common import *
from worker import checked
def main():
    xs=corpus();roster=[];exclude={}
    for i,r in xs.items():
        reason=None;s=src(r)
        if i in ('Python/0','Python/1','Python/6') or r['entry_point'] in ('do_algebra','encrypt','string_to_md5'):reason='scope/schema sample'
        elif not 4<=sum(bool(l.strip()) for l in lines(s))<=65:reason='source size'
        else:
            try:checked(s)
            except (SyntaxError,ValueError) as e:reason=str(e)
        if reason:exclude[i]=reason
        else:roster.append(i)
    roster.sort(key=lambda i:digest('qwen-boundary-5|'+i));save('roster.json',{'ids':roster[:48],'eligible':len(roster),'excluded':exclude})
    for i in roster[:48]:
        r=xs[i];path=ROOT/'work'/slug(i)/'solution.py';path.parent.mkdir(exist_ok=True,parents=True);path.write_text(src(r),encoding='utf8')
    print(len(roster),'eligible',roster[:48])
if __name__=='__main__':main()
