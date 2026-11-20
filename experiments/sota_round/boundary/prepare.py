"""Create a scorer-only view without annotations or readable source identifiers."""
import json,sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
ranks={r['question_id']:r for line in Path(sys.argv[2]).read_text(encoding='utf8').splitlines() if (r:=json.loads(line))}
with Path(sys.argv[3]).open('w',encoding='utf8') as dest:
    for i,q in enumerate(data):
        r=ranks[q['question_id']]
        corpus={}
        for sid,date,turns in zip(q['haystack_session_ids'],q['haystack_dates'],q['haystack_sessions']):
            corpus.setdefault(sid,(date,turns))
        sids=r['top20_session_ids']
        assert len(sids)==len(r['rerank_grades_0_10'])==20 and sids[:5]==r['top5_session_ids']
        slots=[]
        for j,sid in enumerate(sids):
            date,turns=corpus[sid]
            slots.append({'equiv':sids.index(sid),'date':date,'turns':[[str(t['role']),str(t['content'])] for t in turns]})
        dest.write(json.dumps({'row':i,'query':q['question'],'date':q['question_date'],'slots':slots,'grades':r['rerank_grades_0_10']},ensure_ascii=False)+'\n')

