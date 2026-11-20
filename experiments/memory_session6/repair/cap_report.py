import csv
from collections import Counter
from common import *
from report import contrast_text, TITLE, ORDER, n, num
from cap_generate import parse
BASE='cap1024/'
def main():
    dl=read(BASE+'design_lock.json');pl=read(BASE+'prediction_lock.json')
    check(dl['hashes']);check(pl['hashes'])
    roster=read(BASE+'roster.json');res=read(BASE+'results.json');raw=read('results.json')
    oldscores={'author':read('scores.json'),'enhanced':read('plus_scores.json')}; final={ep:read(BASE+ep+'_scores.json') for ep in oldscores}
    policies=read('allocations.json');its=read('roster.json')['items']
    full_receipts={}
    for k,m in roster['planned'].items():
        old=read('calls/'+k+'.json.gz');fresh=read(BASE+'calls/'+k+'.json.gz')
        assert dl['created']<=fresh['start']<pl['created']
        assert fresh['request']==dict(old['request'],max_tokens=1024)
        assert (m['role']=='cap_hit')==(old['response']['choices'][0]['finish_reason']=='length')
        ans=fresh['response']['choices'][0]['message']['content'].strip()
        assert parse(ans).encode()==(ROOT/(BASE+'programs/'+k+'.py')).read_bytes()
        assert fresh['same_old_text']==(ans==old['response']['choices'][0]['message']['content'].strip())
        full_receipts[k]=fresh
    rows=[]
    for ep,new in final.items():
        for r in its:
            i=r['id'];c=r['cohort'];original=oldscores[ep][str(i)]
            if not original.get('covered',True):continue
            for pol,alloc in policies[c].items():
                b=alloc[str(i)];k=read(path(i,b+'.json'))['call'];old=read('calls/'+k+'.json.gz');updated=k in full_receipts and roster['planned'][k]['role']=='cap_hit'
                if updated:
                    assert new[str(i)][b]['code_sha']==sha((ROOT/(BASE+'programs/'+k+'.py')).read_bytes())
                else:assert new[str(i)][b]==original[b]
                rows.append({'endpoint':ep,'cohort':c,'id':i,'policy':pol,'branch':b,'old_key':k,'regenerated_cap_hit':int(updated),'old_status':original[b]['status'],'new_status':new[str(i)][b]['status'],'original_finish':old['response']['choices'][0]['finish_reason'],'effective_new_finish':full_receipts[k]['response']['choices'][0]['finish_reason'] if updated else old['response']['choices'][0]['finish_reason']})
    for ep,coh in res['results'].items():
        for c,o in coh.items():
            for pol,count in o['solves'].items():assert count==sum(r['new_status']=='pass' for r in rows if r['endpoint']==ep and r['cohort']==c and r['policy']==pol)
    with (ROOT/(BASE+'item_outcomes.csv')).open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader();w.writerows(rows)
    ncap=len(res['hits']);nctrl=len(res['audit']);same=sum(x['same_complete_text'] for x in res['audit']);sameprefix=sum(x['same_prefix'] for x in res['hits'])
    rem=sum(x['new_finish']=='length' for x in res['hits']); logic=sum(len(x['uses']) for x in res['hits']);cost=res['costs']
    lines=['## Дополнительная проверка лимита генерации','',
           f'Эта проверка запланирована после открытия результатов при 416 токенах. До нового запроса список повторов зафиксировал все {ncap} уникальных усечённых ответов из {logic} ветвей решения и {nctrl} контрольных завершённых ответов. При увеличении лимита до 1024 изменён один параметр запросов. Предыдущий текст воспроизвёлся целиком у {same} из {nctrl} завершённых контролей. Для усечённых ответов исходный текст сохранился как префикс у {sameprefix} из {ncap}. Число ответов, снова достигших лимита, равно {rem}. Остальные первоначально завершённые ответы перенесены без новой генерации.','',
           '| Тесты и выборка | SHA / слепое при 416 | SHA / слепое при 1024 | Парная разница при 1024 | Выигрыши / потери | Точный p |','|---|---:|---:|---:|---:|---:|']
    for ep,ename in [('author','MBPP'),('enhanced','MBPP+')]:
        for c,cname in [('primary','основная'),('replication','проверочная')]:
            o=raw[ep][c]['policy'];x=res['results'][ep][c];cp=x['contrast']
            lines.append(f"| {ename}, {cname} ({x['n']}) | {o['version_note']['solve']} / {o['blind_note']['solve']} | {x['solves']['version_note']} / {x['solves']['blind_note']} | {n(round(cp['delta_pp'],2))} п.п. | {cp['wins']} / {cp['losses']} | {n(round(cp['p'],4))} |")
    lines+=['','На исходном срезе Google, где в обоих сравниваемых способах генерация остановилась естественно, результаты выделены до пересчёта по новому лимиту.']
    for c,label in [('primary','Основная'),('replication','Проверочная')]:
        q=res['results']['author'][c]['original_on_neither_capped']
        lines.append(f"{label} выборка содержит {q['n']} таких заданий, парная разница {contrast_text(q)}.")
    lines+=['',f"Дополнительный прогон потребовал {cost['unique_calls']} настоящих вызовов, {num(cost['prompt_tokens'])} входных и {num(cost['completion_tokens'])} выходных токенов. Сервер сообщил {n(round(cost['native_prompt_ms']/1000,1))} с расчёта входов и {n(round(cost['native_decode_ms']/1000,1))} с декодирования. Сервер обслуживал также другую очередь, поэтому HTTP-время в эту оценку не входит. В таблицах cap1024 сохранены все старые и новые исходы, отдельные затраты и дополнительная проверка неизменности запросов."]
    (ROOT/(BASE+'summary_ru.md')).write_text('\n'.join(lines)+'\n',encoding='utf8')
    save(BASE+'verification.json',dict(reconstructed_changed_requests=len(full_receipts),audit_matches=same,cap_prefix_matches=sameprefix,policy_rows=len(rows),all_old_vs_new_hashes_checked=True))
    print('\n'.join(lines))
if __name__=='__main__':main()

