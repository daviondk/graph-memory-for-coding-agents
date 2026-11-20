"""Generate complete human-readable metric and uncertainty tables."""
from forecast import D,read
PAN={'primary':'Основная панель','replication':'Повторная панель'}
END={'patch':'Производственные Python-файлы патча','next':'Следующее наблюдаемое чтение','plain':'Следующее прямое чтение','patch_all_py':'Все Python-файлы патча'}
ORDER=('last_scope','last_read','bm25','strong','graph','uniform','shuffled','dense','dense_issue','dense_path','rrf_strong','rrf_graph','rrf_uniform','rrf_shuffled')
def main():
    result=read(D/'results.json');pairs=read(D/'paired.json');lines=['# Полные результаты','',
        'H@k показан числом попаданий; знаменатель общий для всех строк внутри таблицы. MRR — средний обратный ранг первой цели по всему меню, ноль при пропуске. Знаки дельт в нижних таблицах относятся к первому методу в паре.','']
    for p,panel in result.items():
        lines.extend(['## '+PAN[p],''])
        for ep,description in END.items():
            s=panel[ep]
            lines.extend(['### '+description,'',f"Прогнозов {s['n']}, независимых идентификаторов задач {s['tasks']}, репозиториев {s['repos']}. Достижима хотя бы одна цель в {s['reachable']} меню. Пустых меню с размеченным исходом {s['empty']}.",'',
                              '| Метод | H@1 | H@3 | MRR |','|---|---:|---:|---:|'])
            for name in ORDER:
                m=s['methods'][name]
                lines.append(f"| {name} | {m['h1']} | {m['h3']} | {m['mrr']:.4f} |")
            lines.extend(['','| Пара методов | ΔH@1 [95%] | ΔH@3 [95%] | ΔMRR [95%] |','|---|---:|---:|---:|'])
            for name,m in pairs[p][ep].items():
                desc=name.replace('__minus__',' минус ')
                vals=[f"{m[k]['delta']:+.4f} [{m[k]['ci95'][0]:+.4f}, {m[k]['ci95'][1]:+.4f}]" for k in ('h1','h3','mrr')]
                lines.append('| '+' | '.join([desc,*vals])+' |')
            lines.append('')
    (D/'TABLES_RU.md').write_text('\n'.join(lines),encoding='utf8')
if __name__=='__main__':main()
