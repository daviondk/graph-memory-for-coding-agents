# Как воспроизвести подтверждение

В распакованной папке выполните `python -I -B verify.py`. Независимая стандартная реализация воспроизводит адреса, порог и точную рациональную надбавку, 72 скалярных произведения из float32, тождественность префикса и фактических длин, официально эквивалентные F1/EM, покрытие документов и парные разности. Для точных тестов со сменой знаков выполняется полный независимый перебор. Для режима Монте-Карло проверяется арифметика квитанции; повтор того же генератора использует NumPy в signflip.py.

Полный инференс использует те же пинованные среды, исходные классификаторы, веса, официальный датасет и пути, что и adaptive_address. В paths_a.py находятся каталоги предшествующих опытов и приватная рабочая область. Архивные тексты обрабатываются только как данные. Предсказания запечатываются до чтения золотых ответов. Оценщик использует публичные Wikidata aliases/demonyms. [Официальный оценщик](https://github.com/Alab-NII/2wikimultihop/blob/13800e5be57df1b4040b9b1588c6c811779e69e9/2wikimultihop_evaluate_v1.1.py) · [Пинованные официальные веса энкодера](https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF/tree/69d0e58a13e463cd99a9b83e3f5fee7c10265fab)

```powershell
$runner = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:OPENBLAS_NUM_THREADS='1'
& $runner -B selection.py
& $runner -B lex_orders.py
& $runner -B projection.py
& $runner -B novelty.py
& $runner -B encode.py
& $runner -B bonus.py
& ./serve.ps1
& $runner -B grade.py
& $runner -B signflip.py old
& $runner -B signflip.py new
& $runner -B costs.py
& $runner -B report.py
python -I -B verify.py
python -I -B replay_randomization.py
```

Чистый запуск использует пустую приватную папку, куда пишутся журналы GPU. Стоимость включает собственные процессы сервера и обработку каждого уникального запроса с нуля. Подбор порога для этого исследования не требуется.
