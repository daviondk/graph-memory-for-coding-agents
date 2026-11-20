"""Generate a concise verified accounting, including empty/harness cases as separate events."""
from audit import HERE,VIBE,load,main as audit
from collections import Counter
def main():
    audit()
    result=load(HERE/"results.json");rows=result["rows"];parts=["# Результаты штатного оценщика VibeMemBench",""]
    parts.extend([f"Готовы {len(rows)} из {result['expected']} записей. Для каждой сохранён точный SHA-256 поданной строки патча. Числа F2P и потерь P2P показываются только для фактически исполнявшихся тестов.","",
        "| Задача | Условие | Результат | Патч, Б | Прошли F2P | Потеряны P2P | Журнал |","|---|---|---|---:|---:|---:|---|"])
    labels={"no_patch":"пустая правка","resolved":"решено","unresolved":"не решено","harness_error":"ошибка оценщика"}
    for r in rows:
        f=(HERE/r["output"]).parent
        units=(f/"unit.log").is_file()
        fail=r["measured_F2P"];lost=r["measured_P2P_lost"]
        path=(f/("unit.log" if units else "eval_stdout.log")).relative_to(HERE).as_posix()
        parts.append(f"| {r['instance']} | {r['method']} | {labels[r['status']]} | {r['patch_bytes']} | {str(fail)+'/'+str(r['expected_F2P']) if fail is not None else '—'} | {str(lost)+'/'+str(r['expected_P2P']) if lost is not None else '—'} | [выход]({path}) |")
    if result["complete"]:
        parts.extend(["","| Условие решателя | Решено | Правка непуста | Фактический запуск тестов |","|---|---:|---:|---:|"])
        for method in ("base","raw","graph"):
            members=[r for r in rows if r["method"]==method]
            parts.append(f"| {method} | {sum(r['status']=='resolved' for r in members)}/{len(members)} | {sum(r['patch_bytes']>0 for r in members)}/{len(members)} | {sum(r['execution_stage']=='ran_tests' for r in members)}/{len(members)} |")
    parts.extend(["","При пустой правке нативный vendor завершает обработку записи до Docker. Список потерянных P2P, который отчёт по умолчанию заполняет в этой ветке, не является наблюдаемым провалом тестов. Для причин и статуса на уровне тестов см. построчные записи. [JSON со статусами](results.json) · [Окружение](environment.json) · [Воспроизведение](README_RU.md)"])
    (HERE/"REPORT_RU.md").write_text("\n".join(parts)+"\n",encoding="utf8")
if __name__=="__main__":main()
