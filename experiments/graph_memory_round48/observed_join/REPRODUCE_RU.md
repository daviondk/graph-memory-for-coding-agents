# Контракт числовой проекции и воспроизведение

`projection.json.gz` — JSON UTF-8, gzip, с полями `version=1` и `queries`. Ключи запросов `q01`–`q40` совпадают с R39/provenance_packet_demo/reader.sqlite. Каждому q соответствует одна траектория. Идентификаторы источников — SHA256 в шестнадцатеричном виде, прямо сопоставимые с колонками `origin.source` и `span.source`. Все остальные ID и позиции локальны к q.

| Поле внутри запроса | Состав |
|---|---|
| `producers[a]` | `[output_content_hash, first_output_step, call_arguments_hash, first_call_step]`. Индекс a с нуля в точности соответствует идентификатору источника R44, поля результата и вызова различны. |
| `sources` | Массив пар `[source_hash, first_visible_step]` для всех источников, действительно имеющихся в R39. Видимые к шагу j — записи с `first_visible_step <= j`. |
| `steps[j-1]` | `[last_event_ordinal, last_message_index, updates, ordered_packet_after]` для закрытой группы j, начиная с 1. Счётчики событий и сообщений начинаются с 0. Обновление группы публикуется атомарно. |
| `updates` | Список троек `[producer_ordinal, old_outgoing_count, new_outgoing_count]` в порядке номера производителя. Учитывается чистое изменение числа свидетелей с кратностями; пропущенное значение остаётся прежним. Начальные численности нулевые. |
| `ordered_packet_after` | Полный упорядоченный массив числовых `node.id` R39, выбранных из временно доступных кандидатов при нулевой поправке. Пакет до j равен пакету после j−1. Пакет и список доступных источников на шаге 0 пусты. |

Минимальное чтение в Python для любой границы:

```python
import gzip, json

with gzip.open("projection.json.gz", "rt", encoding="utf8") as stream:
    traces = json.load(stream)["queries"]
trace = traces["q01"]
step = 1
event_end, message_end, changes, packet_after = trace["steps"][step - 1]
packet_before = trace["steps"][step - 2][3] if step > 1 else []
seen_before = {source for source, born in trace["sources"] if born < step}
seen_after = {source for source, born in trace["sources"] if born <= step}
changed_outputs = [(trace["producers"][a][0], old, new) for a, old, new in changes]
```

Команда `python -B verify.py` использует подписанные R39 reader, R44 fixture и исходное C++17-ядро R46/source_sensitivity. Нужен g++ в PATH. Архив траекторий для этой проверки не требуется. Проверяются все срезы fixture и их исходная позиция, все до/после-счётчики, хронология, поля, полные пакеты и основные показатели.

Полное воспроизведение из исходных файлов на исследовательской машине последовательно выполняет следующие команды:

```powershell
$runner = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $runner -B join.py
& $runner -B analyze.py
python -B verify.py
```

Первая команда использует CPU и зарегистрированные адаптер и токенизацию R44, находит строки архива по исходному session_id, сверяет входные candidate shards R39 и повторяет извлечение FEEDS. Фиксированный hash seed влияет только на диагностическое сравнение порядка одновременно возникших дельт. Вторая команда вычисляет интервалы по 40 целым траекториям. Артефакты не содержат сырых сообщений, идентификаторов исходных событий, значений свидетелей, команд или gold. [Описание источника ISETrace и лицензии в R39](../../graph_memory_round39/provenance_packet_demo/DATA_SOURCE.md)
