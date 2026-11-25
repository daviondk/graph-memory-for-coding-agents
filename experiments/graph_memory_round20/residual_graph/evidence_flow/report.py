"""Generate the experiment tables only from saved per-query results."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_bytes())

def percent(x):
    return f'{100*x:.2f}'.replace('.',',')

def estimate(c):
    lo,hi=c['ci95']
    return f"{percent(c['difference'])} [{percent(lo)}; {percent(hi)}]"

def run():
    notes=['# Извлечение отдельных событий и их совместная доступность в памяти',
        '', 'На ISETrace мы проверили, повышает ли структура графа вероятность одновременно поместить в контекст свидетельства из разных событий. Эталонное событие считается видимым только при полном покрытии его исходных символьных координат. У всех читателей одинаковый пул кандидатов и лимит 2 048 токенов. [Постановка и формулы](PROTOCOL_RU.md) · [Связанная работа о передаче фактов между агентами](https://arxiv.org/abs/2611.22245)',
        '', 'На 516 из 2 000 вопросов требуются свидетельства минимум из двух разных событий. Они относятся к 481 траектории. В 484 вопросах из 450 траекторий требуются ровно два события. Во втором случае совместное извлечение пары равносильно полному покрытию эталона. Каждому вопросу присвоен одинаковый вес.','']
    structural=HERE/'train_structural-results.json'
    if structural.exists():
        z=read(structural)['partitions']['minimum_two']
        delta=z['contrasts']['role_degrees minus dense']
        notes += ['## Лёгкий структурный читатель',
            '',f"Обучение весов роли и степеней использовало только исходный train (3 894 вопроса). При переходе от Dense-FT к роли и степеням выбор одного требуемого события улучшился с {percent(z['arms']['dense']['event'])}% до {percent(z['arms']['role_degrees']['event'])}%, совместное появление пары — с {percent(z['arms']['dense']['pair'])}% до {percent(z['arms']['role_degrees']['pair'])}%. Разность совместного покрытия {estimate(delta['pair'])} п.п.",
            '',f"Алгебраически прирост совместного покрытия раскладывается на {estimate(delta['marginal_square'])} п.п. от изменения квадрата средней вероятности события и {estimate(delta['covariance'])} п.п. от изменения внутривопросной ковариации двух индикаторов. Выигрыш совместим с улучшением рангов каждого требуемого события. Интервал дополнительного эффекта ковариации включает ноль. Трудность вопроса, размер события и конкуренция за контекст влияют на ковариацию. Для причинного вывода о взаимодействии событий потребуется отдельная интервенция. [Протокол переноса](STRUCTURAL_RU.md) · [Результаты](train_structural-results.json)",'']
    notes += ['## Как меняется доступность пары',
        '', 'Значения — парные разности в п.п., скобки — 95% процентильные доверительные интервалы по 10 000 кластерных повторов с возвращением. Подборок несколько, поэтому интервалы отражают неопределённость внутри отдельного сравнения.',
        '', '| Читатель, A − B | Число событий | Δ одного | Δ пары | Δ всех | Δ партнёра при найденном первом |',
        '|---|---|---:|---:|---:|---:|']
    labels={'rgcn/prefix minus seed/prefix':'R-GCN prefix − cosine prefix','rgcn/related minus rgcn/skip':'related − skip',
            'role_degrees minus dense':'роль и степени − Dense-FT','typed minus shuffled':'истинные − переставленные соседи'}
    for panel in ('train_structural','availability','hash64','full'):
        path=HERE/f'{panel}-results.json'
        if not path.exists():
            continue
        res=read(path)['partitions']
        for scope,grp in res.items():
            for key,delta in grp['contrasts'].items():
                sign='≥2' if scope=='minimum_two' else '=2'
                notes.append(f"| {panel}, {labels[key]} | {sign} | "+' | '.join(estimate(delta[k]) for k in ('event','pair','all','partner_given_first'))+' |')
    notes += ['', 'Все исходы дополнительно сверены с оригинальным Full Support на уровне вопроса. Графовый prefix останавливается при первом переполнении, skip пропускает слишком длинную следующую запись, related отдаёт предпочтение комплементарной стороне уже выбранного вызова. Группы моделей используют разные объёмы обучающих данных. Ранее были известны основные агрегаты на том же тесте, включая Full Support в группе вопросов с несколькими событиями. Настоящий разбор характеризует механизм на известном корпусе. Для многоагентной передачи и обнаружения конфликтов нужен самостоятельный эксперимент с видимыми и переданными сообщениями. [Код основной проверки](analyze.py) · [Код переноса](structural.py) · [Проверка](verify.py)',
              '', 'В исходной структуре данных запуск производится из этого каталога. Для готовых весов и рангов выполните `python -B analyze.py score availability`, `python -B analyze.py score hash64` (после готовности панели), `python -B structural.py score`, затем `python -B report.py` и `python -B verify.py`. При наличии полной модели поддерживается `python -B analyze.py score full`. Этап lock применяется только при первом создании неизменяемого протокола.']
    (HERE/'REPORT_RU.md').write_text('\n'.join(notes)+'\n', encoding='utf8')
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='MANIFEST_SHA256.json'}
    (HERE/'MANIFEST_SHA256.json').write_text(json.dumps(files,sort_keys=True,indent=2)+'\n',encoding='utf8')

if __name__=='__main__':
    run()
