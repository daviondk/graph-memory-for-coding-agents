from data import *
def f(x,d=2):return f'{x:.{d}f}'.replace('.',',')
def result(label,entry):
    a,b=entry['cluster95_pp'];return f"{label} {f(entry['change_pp'])} п. п. [95% ДИ {f(a)}; {f(b)}], {entry['wins']} выигрышей и {entry['losses']} потерь, p={entry['two_sided_p']:.4g}".replace('p=0.','p=0,')
def main():
    res=read(D/'results.json');ver=read(D/'verified.json');native=read(D/'native-receipt.json');assert ver['results']==sha(D/'results.json')
    key='boundary_window';primary=res['full_panel'][key+'-equal'];pair=res['eq'][key]
    names={'both':'Границы R26','window':'Окно вокруг BM25-предложения, ±3','boundary_window':'Три новых соседних предложения от каждого края'}
    lines=['# Токенные границы и окна предложений при чтении исходной памяти','',
           f"Первичное сравнение на {res['n']} вопросах из {res['articles']} статей SQuAD использует одинаковые исходную память, выбранную компоненту и фактическую стоимость дополнительного чтения. При {f(pair[0]['mean_paid'])} WordPiece на запрос метод R26 полностью восстанавливает эталонный адрес в **{pair[0]['hits']}** случаях, двухкраевое окно предложений — в **{pair[1]['hits']}**. "+result('Разность R26 минус двухкраевое окно',primary)+'. [Фиксация сравнения](PROTOCOL_RU.md) · [парные интервалы](results.json)','',
           '| Правило при онлайн-потолке 256 | Весь ответ в контексте | Частичное покрытие | Оплачено, токены | Доля уже известных символов в выдаче |','| --- | ---: | ---: | ---: | ---: |']
    for a,label in names.items():
        r=res['online'][a]
        lines.append(f"| {label} | {r['hits']}/{res['n']} | {f(100*r['coverage'])}% | {f(r['mean_paid'])} | {f(100*r['known_char_fraction'])}% |")
    simple=res['eq']['window'];d=res['full_panel']['window-equal'];m=res['initial_misses']['boundary_window-equal']
    lines+=['',f"При попарном выравнивании с одиночным окном R26 даёт {simple[0]['hits']} попаданий и окно {simple[1]['hits']}, средняя стоимость каждого {f(simple[0]['mean_paid'])} токена. "+result('Разность',d)+'. По исходному онлайн-потолку '+result('R26 минус двухкраевое окно',res['full_panel']['boundary_window-online'])+'.',
            '',f"До хода чтения покрыты {res['initial_hits']} вопросов. Среди {m['queries']} исходных пропусков "+result('первичный условный эффект',m)+f". В {res['no_component']} вопросах отсутствует подходящая компонента для действия. [Построчные результаты](outcomes.json.gz) · [независимая верификация](verified.json)",'',
            f"Настоящий SentenceWindowNodeParser 0.14.26 построил {native['sentences']} узлов для 442 целых статей. У каждого совпали исходная подстрока и строка metadata[window] из авторской реализации. Центральное предложение определяется по видимому пересечению с одной заранее определённой компонентой. Только в ходе дополнительного чтения возвращается скрытый текст соседей. Нативный парсер хранит окно, ранжировщик BM25 и бюджетный адаптер добавлены для данного сравнения. Двухкраевое окно вычитает уже известные диапазоны и переносит неиспользованную квоту. У него нет потерь бюджета на повторно выданные символы источника. [Индекс и версия](native-receipt.json) · [код LlamaIndex](https://github.com/run-llama/llama_index/blob/0d4f96876cfe7e325f3c1b72ec5f5f580f173bb5/llama-index-core/llama_index/core/node_parser/text/sentence_window.py)",'',
            'Пара с одинаковой ценой использует фактические длины обеих выдач. В онлайн-режиме обе политики заранее получают потолок 256 и могут потратить разные суммы. Кластеры для доверительного интервала — статьи. Измеряется доступность адресуемого эталонного текста, а сравнение ограничено выбранной статьёй и ранее использованной выборкой R26. Доступ ко всем границам предложений требует заблаговременного разбора документа. Генерация ответа и полный поиск документов системы лежат за пределами этой проверки.']
    (D/'REPORT_RU.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    files={p.name:sha(p) for p in sorted(D.iterdir()) if p.is_file() and p.name!='manifest.json'}
    save(D/'manifest.json',{'files':files,'count':len(files),'bytes':sum((D/n).stat().st_size for n in files)})
if __name__=='__main__':main()
