from pathlib import Path
import json
p=Path(__file__).parent
def load(n):return json.loads((p/(n+'.json')).read_text(encoding='utf-8-sig'))
def save(n,d):(p/(n+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
d=load('candidates')
b=d[0]['blocks'][2]
b['text']=b['text'].replace('сырой вызов с выводом, либо ту же информацию с нормализованной областью поиска','сырой вывод и манифест исполнения (каталог, фильтры, обрезание, тайм-аут), либо те же сведения с нормализованной областью поиска')
save('candidates',d)
d=load('personal')
b=d[0]['blocks'][1]
b['text']=b['text'].replace('явные поля «чьё правило» и «при каком условии» помогают','явное указание условия исключения при известном владельце правила помогает').replace('ту же цитату и разметку этих двух полей без новых фактов','ту же цитату с отдельно выделенным условием без новых фактов. Владелец правила явно указан в обоих вариантах')
d[0]['blocks'][2]['text']=d[0]['blocks'][2]['text'].replace('Двенадцать шаблонов,','Двенадцать шаблонов, поровну обычных случаев и исключений,')
save('personal',d)

