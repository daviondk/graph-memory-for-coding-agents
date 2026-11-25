"""Summarize physically measured SQLite plans without conflating warm queries and upstream embedding."""
import statistics
from collections import defaultdict
from measure import HERE,load,put,boot_ratio

def fmt(v,n=2):return f"{v:.{n}f}".replace(".",",")
def count(v):return f"{v:,}".replace(","," ")
def rng(ci):return f"[{fmt(ci[0])} … {fmt(ci[1])}]"
labels={"vector":"Полное чтение и сортировка","heap":"Полное чтение и heapify","stream":"Пороговый курсор","sql":"SQL JOIN + ORDER BY","final":"Материализованный итоговый порядок"}
def main():
    py=load(HERE/"sqlite-results.json");native=load(HERE/"native-results.json");b=load(HERE/"sqlite-build.json")
    timing=load(HERE/"native-times.json.gz");by=defaultdict(list)
    for row in timing:by[row["q"]].append(row)
    extra={}
    for pol in ("prefix","skip"):
        for timer in ("inside_ns","outside_ns"):
            rows={q:{"t":v[0]["t"],pol+"/stream":statistics.median(r[timer][pol+"/stream"] for r in v),pol+"/vector":statistics.median(r[timer][pol+"/heap"] for r in v)} for q,v in by.items()}
            num=statistics.median(r[pol+"/stream"] for r in rows.values());den=statistics.median(r[pol+"/vector"] for r in rows.values())
            extra[timer+"/"+pol]={"ratio_to_heap":num/den,"ci":boot_ratio(rows,pol,"stream")}
    put(HERE/"native-heap-control.json",extra)
    text=["# Точный пороговый поиск в настоящей SQLite",
        "При нативном обращении к SQLite пороговое чтение возвращало ровно тот же упорядоченный префикс и сократило медианную задержку с 20,80 до 17,25 мкс по сравнению с полной сортировкой C++. В Python чтение с порогом и полная выгрузка с NumPy дали практически одинаковую задержку. Результат зависит от цены передачи и обработки строк.",
        "## Реализация C++17",
        "Все пять вариантов используют один подготовленный запрос на операцию, одну версию SQLite, общие статические оценки фрагментов и кэш 64 MiB. Время от привязки параметров до сброса SQL-выражения включает извлечение фактических строк и выбор списка PU. Второй таймер охватывает вызов DLL из внешнего процесса Python. Оба ранжировщика получают уже рассчитанный плотный ранг. Полное чтение использует std::sort или std::make_heap. В режиме добора все варианты завершают работу, если минимальная цена оставшегося узла выше остатка.",
        "| Операция | Метод | Выдано sqlite3_step строк | Инструкции SQLite VM | Нативная медиана / p95, мкс | Отношение к std::sort [95% ДИ] | Медиана со стоимостью FFI, мкс |\n|---|---|---:|---:|---:|---:|---:|"]
    for p,name in (("prefix","Префикс"),("skip","Добор")):
        for m in ("vector","heap","stream","sql","final"):
            k=p+"/"+m;v=native["times"]["inside_ns/"+k];all_time=native["times"]["outside_ns/"+k]
            c=native["totals"][k]
            text[-1]+=f"\n| {name} | {labels[m]} | {count(c['rows'])} | {count(c['vm'])} | {fmt(v['median_us'])} / {fmt(v['p95_us'])} | {fmt(v['ratio'])} {rng(v['ratio_ci'])} | {fmt(all_time['median_us'])} |"
    v=extra["inside_ns/prefix"];t=native["times"]["outside_ns/prefix/stream"]
    text.append(f"Для префикса отношение нативных медиан к варианту heapify равно {fmt(v['ratio_to_heap'])} {rng(v['ci'])}. С учётом внешнего вызова отношение к std::sort составляет {fmt(t['ratio'])} {rng(t['ratio_ci'])}. На рассмотренных 256 запросах за семь чередующихся повторений SQLite зарегистрировала 0 пропусков page cache для всех методов. Число виртуальных инструкций — показатель работы SQL-выражения. Оно не учитывает арифметику и структуры данных в C++. [Исходные замеры](native-times.json.gz) · [Все метрики](native-results.json) · [Описание SQLite VM_STEP](https://www.sqlite.org/c3ref/c_stmtstatus_counter.html)")
    text.extend(["## Python и постраничное извлечение",
        "SQLite возвращает ранговые строки в страницы по 16. Полная NumPy-загрузка забирает все строки, даже если итоговый контекст короток. Рассматривается интервал от исполнения SQL до готового списка PU. Самостоятельный SQL JOIN может получить мало строк в приложении и одновременно просмотреть всю внутреннюю таблицу для сортировки.",
        "| Операция | Метод | Строк, переданных приложению | Медиана / p95, мкс | Отношение к полной выгрузке [95% ДИ] |\n|---|---|---:|---:|---:|"])
    for p,name in (("prefix","Префикс"),("skip","Добор")):
        for m in ("vector","stream","sql","final"):
            q=py["summary"][p+"/"+m];text[-1]+=f"\n| {name} | {labels[m]} | {q['rows']} | {fmt(q['median_us'])} / {fmt(q['p95_us'])} | {fmt(q['ratio'])} {rng(q['ratio_ci'])} |"
    text.extend(["## Что оплачивает материализация",
        f"База исходного Dense и статических полей содержит 249 089 ранговых строк на 2 000 вопросов. Её размер {count(b['base_bytes'])} байт. Сохранение отдельного итогового порядка для всех известных вопросов добавило {count(b['final_extra_bytes'])} байт и {fmt(b['final_seconds'],3)} с времени построения на этой машине. Новому вопросу нужно вычислить собственный итоговый порядок. Независимо от вопроса кэш приоритета строится по графу каждой истории. Однократная выгрузка и подготовка статических массивов через Python заняла медианно {fmt(py['prep_median_us'],1)} мкс на историю, всего прочитано {py['static_rows']} статических строк. [EXPLAIN QUERY PLAN и размер](sqlite-build.json)",
        "Порог применяет известную технику верхних границ к разным ценам PU и выдаёт ровно нативный префикс R20. Эксперимент охватывает тёплую локальную SQLite, фиксированную версию графа и уже материализованный входной Dense-ранг. Холодное хранилище, сетевой сервис, обновление prior между вопросами и латентность encoder здесь не измерялись. [Протокол Python](SQL_PROTOCOL_RU.md) · [Протокол C++](NATIVE_PROTOCOL_RU.md) · [Результаты in-memory](REPORT_RU.md)"])
    (HERE/"SQL_RU.md").write_text("\n\n".join(text)+"\n",encoding="utf8")
if __name__=="__main__":main()

