"""Publication-facing report and immutable archive."""
from study import D,load,pilot,save
def report():
    s=load(D/"results.json");p=load(D/"panel-lock.json")["counts"];all=s["all"]
    v=all["stats"];paired=all["pairs"]["qwen_full"];coverage=all["pairs"]["qwen_coverage"]
    def interval(z):return f"{100*z['delta']:+.2f} п.п. [{100*z['ci95'][0]:+.2f}; {100*z['ci95'][1]:+.2f}]".replace(".",",").replace("п,п,","п.п.")
    notes=["# Политика записи и действие Qwen при открытии источника","",
       f"Обученное правило записи дало {v['full']['qwen']['full']}/36 случаев полной поддержки после одного реального действия Qwen, эвристика приоритета начал результатов — {v['head']['qwen']['full']}/36. Парный контраст Full−output_head: {paired['wins']} выигрышей, {paired['losses']} потерь, {interval(paired)}. Среднее покрытие изменилось на {interval(coverage)}. Для каждого вопроса сравниваются две истории одного и того же агента, одно ограничение записи в 8 192 и одно ограничение на чтение в 2 048 E5-токенов.",
       "", "| Что проверяется | Обученная запись, число / 36 | Приоритет начал, число / 36 | Coverage, обученная / начала, % |",
       "|---|---:|---:|---:|"]
    for method,desc in (("raw_read","Полный комплект при штатной выдаче BM25"),("all_visible","Полный комплект в реально разрешённом меню"),("oracle","Достижимо одним открытием любого события"),("top1","Событие лучшего видимого блока BM25"),("qwen","Событие, выбранное Qwen")):
        a,b=v["full"][method],v["head"][method]
        notes.append((f"| {desc} | {a['full']} | {b['full']} | {100*a['coverage']:.2f} / {100*b['coverage']:.2f} |").replace(".",","))
    notes.extend(["","Oracle в Coverage выбирает достижимый максимум среди результатов одного события. Открытие возвращает только реально присутствовавшие в меню части события. Пропуски остаются недоступными. Выбор производится native tool call на локальном Qwen3.8-27B-UD-Q4_K_M, llama.cpp b12441, RTX 3090; названия политики и номера мест в выдаче от модели скрыты.",
     "","| Издержки и прохождение действий | Обученная | Приоритет начал |","|---|---:|---:|",
     f"| Валидных действий / 36 | {v['full']['valid']} | {v['head']['valid']} |"])
    for k,name in (("stored","Средний write, E5-токены"),("raw_tokens","Штатная выдача BM25, E5-токены"),("visible_tokens","Фактически показано источников, E5-токены"),("opened_tokens","Открыто одним действием, E5-токены"),("prompt_tokens","Полный вход модели, Qwen-токены"),("visible_events","Событий в меню")):
        notes.append((f"| {name} | {v['full'][k]:.1f} | {v['head'][k]:.1f} |").replace(".",","))
    notes.extend(["",f"Применён единый фиксированный фильтр полного исходного поля независимо от политики. У обученной записи фильтр скрыл {p['full_sensitive_blocks']} возвращённых BM25 блоков в {p['full_contexts_filtered']} из 36 меню, у эвристики — {p['head_sensitive_blocks']} в {p['head_contexts_filtered']} меню. Обе полные выборки остаются в знаменателе. Шесть меню совпали байт-в-байт, поэтому для 72 условий выполнено {p['unique_requests']} уникальных запросов модели.",
     "","| Состав меню пары | Вопросы | Полное подтверждение после Qwen, обученная / начала | Выигрыши / потери |","|---|---:|---:|---:|"])
    for label,title in (("new_different","Разные меню"),("new_equal","Идентичные меню")):
        u=s[label]
        if not u["n"]:continue
        a,b=u["stats"]["full"],u["stats"]["head"];k=u["pairs"]["qwen_full"]
        notes.append(f"| {title} | {u['n']} | {a['qwen']['full']} / {b['qwen']['full']} | {k['wins']} / {k['losses']} |")
    notes.extend(["","**Интерпретация.** Эффект на полном ISETrace с BM25 измеряет доступность доказательств. Здесь дополнительно требуются сохранение всех нужных частей в одном доступном событии и корректный выбор этого события моделью. Все 36 прямых вопросов взяты из прежнего узко отфильтрованного эксперимента. Результат относится к этим задачам и одному фиксированному читателю. Разбиение по совпадению меню описательное. Качество свободного ответа и выполнения задач разработки не измерялось. [Протокол](PROTOCOL_RU.md) · [Все парные исходы](results.json) · [Воспроизведение](REPRODUCE_RU.md)"])
    (D/"REPORT_RU.md").write_text("\n".join(notes)+"\n",encoding="utf8",newline="\n")
    fs=sorted(f for f in D.rglob("*") if f.is_file() and "__pycache__" not in f.parts and f.name!="MANIFEST_SHA256.json")
    save("MANIFEST_SHA256.json",{f.relative_to(D).as_posix():pilot.sha(f) for f in fs});print(len(fs),sum(f.stat().st_size for f in fs),pilot.sha(D/"MANIFEST_SHA256.json"))
if __name__=="__main__":report()
