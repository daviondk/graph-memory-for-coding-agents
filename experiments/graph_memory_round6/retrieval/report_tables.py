"""Build numeric Markdown tables verbatim from the graded paired artifacts."""
from run import D,load

LABELS={'full':'R6 с новыми рёбрами','direct':'R6 со сравнением полей','r4':'Граф R4',
        'r4_shape':'R4 + морфология','r4_alignment':'R4 + совпадения частей имён',
        'only_fields':'Только новые поля','placebo':'R6 с переставленными сообщениями',
        'unix':'UniXcoder','semlith':'Semlith 0.36.0','jaccard':'Jaccard','bm25':'BM25','r5_direct':'Смесь R5 (граф + UniXcoder)','r5_unix':'UniXcoder'}
def f(x):return f'{x:.2f}'.replace('.',',')
def signed(x):return ('+' if x>0 else '')+f(100*x)
def show(x):return f"{signed(x['delta'][0])} [{signed(x['lo'][0])}; {signed(x['hi'][0])}]"
def main():
    v=load(D/'results.json');overall=v['overall']
    sections={'primary_java':'Java HF, исходная панель','strict_java':'Java HF, строгая панель',
      'primary_python':'Python HF, исходная панель','fresh_python':'Python HF, новые проекты',
      'archive_java':'Java, архив, обрезка поставщика','fresh_encoder_python':'Python HF, подпанель энкодера',
      'author_python':'Python HF, авторская обрезка','author_java':'Java, исходный архив и авторская обрезка'}
    text=[]
    for k,b in overall.items():
        text += [f"### {sections[k]}, {b['n']} запросов и {b['projects']} проектов",'','| Метод | @1 | @3 | @5 | MRR | Δ @1 R6 − метод, п.п. [95% ДИ] |','|---|---:|---:|---:|---:|---|']
        for a in ['full','r4','r4_shape','r4_alignment','direct','placebo','only_fields','r5_direct','r5_unix','unix','semlith','jaccard','bm25']:
            if a not in b['items']:continue
            x=b['items'][a];d=b['diff'].get('full-'+a)
            mrr=f"{x['mrr']:.4f}".replace('.',',')
            text.append('| '+LABELS[a]+' | '+' | '.join(map(str,x['hits']))+' | '+mrr+' | '+(show(d) if d else '—')+' |')
        text+=['']
    (D/'TABLES_RU.md').write_text('# Полные результаты по панелям\n\n'+'\n'.join(text)+'\n',encoding='utf8')
if __name__=='__main__':main()
