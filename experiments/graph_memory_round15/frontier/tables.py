"""Generate readable per-panel tables and competitor uncertainty intervals."""
from frontier import D,read
def main():
    src=read(D/'results.json');paired=read(D/'paired.json')
    lines=['# Результаты по источникам и целям','',
           'H@k — число попаданий среди всех размеченных событий. MRR включает нули для недостижимых целей. Добавленные слоты — среднее число ранее не просмотренных путей среди первых шести. Для источников с известной меткой Git количество строк может отличаться от дополнительной официальной разметки patch.','']
    for panel in ['primary','replication','grounded_all','grounded_original','grounded_other_tasks','external']:
        lines.extend(['## '+panel,''])
        for ep,agg in src[panel].items():
            lines.extend(['### '+ep,'',f"Размечено {agg['n']} событий в {agg['tasks']} задачах. Потолок по старому меню {agg['old_oracle']}, по расширенному {agg['union_oracle']}.",'',
              '| Метод | H@1 | H@3 | H@6 | MRR | Новых слотов @6 |','|---|---:|---:|---:|---:|---:|'])
            for m in ('view_graph','flat_recent','bm25_all','alternating_union','flat_union','typed_union','shuffled_union','random_all'):
                r=agg['methods'][m]
                lines.append(f"| {m} | {r['h1']} | {r['h3']} | {r['h6']} | {r['mrr']:.4f} | {r['avg_new_slots'][2]:.3f} |")
            lines.extend(['','| Сравнение typed_union с контролем | ΔH@6, п.п. | Парный кластерный 95% ДИ, п.п. | Выигрыш / потеря |','|---|---:|---:|---:|'])
            for m,v in paired[panel][ep].items():
                a=v['h6'];lo,hi=a['ci95']
                lines.append(f"| {m} | {a['delta']*100:+.2f} | {lo*100:+.2f} … {hi*100:+.2f} | {a['wins']} / {a['losses']} |")
            lines.append('')
    (D/'TABLES_RU.md').write_text('\n'.join(lines),encoding='utf8')
if __name__=='__main__':main()
