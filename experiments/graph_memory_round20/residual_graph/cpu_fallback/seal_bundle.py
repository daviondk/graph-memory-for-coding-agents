"""Archive both CPU panels before the deferred full-train study finishes."""
from shutil import copyfile
from pathlib import Path
from verify_panel import HERE,ROOT,v
import json
def pct(c):
    d=c['differences']['full_support'];a,b=d['cluster_ci95'];f=lambda x:f'{100*x:.2f}'.replace('.',',')
    return f"{f(d['estimate'])} [{f(a)}; {f(b)}]"
def main():
    logdir=Path('D:/CodexResearch/x20-isetrace-residual/logs');dest=HERE/'logs';dest.mkdir(exist_ok=True)
    for n in ['available-encode.log','available-encode.err','fallback.log','fallback.err','restart-panels-01.log','restart-panels-01.err','cpu-bench.log','cpu-bench.err','vectors.log','vectors.err']:
        if (logdir/n).exists():copyfile(logdir/n,dest/n)
    for n in ['gpu-outage.json','outage-coverage.json','outage-train-availability.json.gz','cpu-bench.json']:
        copyfile(ROOT/n,HERE/'inputs'/n)
    for n in ['topologies.json.gz','edge-invariants.json','PROTOCOL_RU.md']:
        copyfile(ROOT/'topology'/n,HERE/'inputs'/('topology-'+n))
    res={k:v.get(HERE/k/'results.json')['test'] for k in ('availability','hash64')}
    topo=v.get(HERE/'hash64/topology-results.json');coh=v.get(HERE/'cohorts.json')
    L=['# Два нативных R-GCN на уменьшенных обучающих панелях', '',
       'После отключения GPU весь официальный test уже имел все нужные FP32-признаки. Для двух заранее зафиксированных подмножеств оригинального train недостающие эмбеддинги были дорассчитаны на CPU. Обе модели прошли штатное обучение residual R-GCN с авторским miner и всеми 500 dev для выбора эпохи. Их проверили на всех 2 000 test и точно согласованном cosine seed. Hash64 выбрана по хешу из всех 2 410 train-траекторий. Выбор availability обусловлен состоянием кэша в момент прерывания.', '',
       '| Обучающая панель | Траекторий / вопросов train | Prefix, R-GCN / seed | Условный вклад графа, п.п. [95% ДИ] | R-GCN skip / related | Related − skip, п.п. [95% ДИ] |','|---|---:|---:|---:|---:|---:|']
    for k in ['hash64','availability']:
        M=res[k]['metrics'];d=res[k]['contrasts'];c=coh[k]
        L.append(f"| {k} | {len(c['t'])} / {len(c['q'])} | {M['rgcn/prefix']['hits']} / {M['seed/prefix']['hits']} | {pct(d['rgcn/prefix - seed/prefix'])} | {M['rgcn/skip']['hits']} / {M['rgcn/related']['hits']} | {pct(d['rgcn/related - rgcn/skip'])} |")
    M=topo['metrics'];p=topo['paired']
    L+=['',f"При фиксированных весах hash64 и неизменных узлах исходный граф дал {M['native']['hits']} полных выдач, нативная degree-preserving перестановка — {M['random']['hits']}, удаление всех сообщений — {M['empty']['hits']}. Разности исходной конфигурации против этих двух контролей: **{pct(p['random'])}** и **{pct(p['empty'])}** п.п. Перестановка сохранила входящую и исходящую степень каждого типа для каждого узла, изменив 522 854/574 402 направленных сообщений по сравнению множеств. Альтернативы в этом опыте не переобучались. [Интервенция](hash64/topology-results.json) · [Её протокол](TOPOLOGY_RU.md)",'',
        'Уменьшение train изменило число градиентных обновлений. Опубликованные R-GCN 77,33 ± 0,53% Full Support@2048 относятся к 3 894 train-вопросам и пяти seed; эти две уменьшенные CPU-панели решают задачу с иным объёмом обучения. Статистической единицей доверительных интервалов выступает траектория; полное попадание означает включение всех размеченных символов при 2 048 исходных токенах. [Hash64](hash64/REPORT_RU.md) · [Availability](availability/REPORT_RU.md) · [Источник](https://arxiv.org/html/2609.25913v3#S7.T2)','',
        'В этом каталоге имеются веса обоих графовых слоёв, исходные размеченные координаты обеих оценочных выборок, признаки связи вызова, полные ранги и выходы по каждому вопросу. Проверка всех 36 000 исходов из распакованного каталога: python -B verify_bundle.py. Для нового обучения потребуются исходные траектории и E5 из R19. [Воспроизведение](REPRODUCE_RU.md)']
    (HERE/'REPORT_RU.md').write_text('\n'.join(L)+'\n',encoding='utf8')
    dig={p.relative_to(HERE).as_posix():v.sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p!=HERE/'MANIFEST_SHA256.json' and '__pycache__' not in p.parts}
    path=HERE/'MANIFEST_SHA256.json';path.write_bytes((json.dumps(dig,sort_keys=True,indent=2)+'\n').encode())
    print(len(dig),v.sha(path))
if __name__=='__main__':main()

