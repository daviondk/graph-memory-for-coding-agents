from pathlib import Path
import json
p=Path(__file__).resolve().parent
def edit(file, fn):
    path=p/(file+'.json')
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    fn(data)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def update_sources(obj):
    q=obj[1]
    q['blocks'][1]['text']='MemCut исследует косвенные улики, AfterDeleteBench — влияние производных записей. В StateGraph уже извлекаются зависимости, проверяется второе независимое основание и каскадно пересматриваются выводы. Классическая система truth maintenance также учитывает несколько оснований. Остаётся более узкий вопрос о цене и ошибках локального пересмотра смешанных текстовых сводок, когда два документа могут цитировать один отозванный первоисточник.'
    q['blocks'][2]['text']=q['blocks'][2]['text'].replace('локально восстановить предложения из оставшихся оснований, пересобрать память','пересмотреть зависимости и альтернативные основания по схеме StateGraph, локально пересобрать затронутые предложения, полностью пересобрать память')
    q['blocks'][3]['text']=q['blocks'][3]['text'].replace('четыре условия','пять условий')
    q['sources'].append({'label':'StateGraph · зависимости и альтернативные основания','url':'https://arxiv.org/abs/2611.02912'})
edit('candidates',update_sources)
def update_end(pages):
    for b in pages[-1]['blocks']:
        b['text']=b['text'].replace('Пилотные бюджеты ниже следует понимать как оценки подготовки.','Число запусков и трудозатраты в карточках служат ориентирами для планирования.')
edit('endmatter',update_end)

