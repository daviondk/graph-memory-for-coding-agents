# Воспроизведение SERBench

Для автономной проверки переданных файлов и пересчёта средних из поштучных исходов запустите `python verify.py`. Вычисление не требует сетевого доступа или весов модели. SHA256 в manifest.json включает данные обоих этапов, исходные протоколы и проверку привязки. Собранные файлы содержат только идентификаторы и числовые признаки. Авторы исходного корпуса распространяют текст и сертификаты отдельно с условиями доступа. [Репозиторий SERBench](https://github.com/LordTARN1SHED/SERBench/tree/8c27a88e48dcbcd4a5745573c95937a4740f4406)

Для полного пересчёта ранжирований и нативной оценки используется существующая рабочая раскладка D. Папка memory_session5/serbench содержит авторский SDK, публичный Cal500 и подготовленные ранее dense_inputs.jsonl.gz, dense_vectors.npy и dense_runtime.json. Замороженный BGE-large-en-v1.5 при ревизии d4aa6901d3a41ba39fb536a557fa166f842b0e09 был вычислен в старой серии на RTX 3090, max_seq=512, float16. В данной серии считаются только косинусные сходства и CPU-модели. Папка memory_session5/packets содержит Qwen-токенизатор, x20-isetrace-runtime/e5-base-v2 — E5, а R20 и R33 — неизменённые коэффициенты rank prior и cost_worst. Сборка признаков сверяет векторы с исходным SHA из журнала, вычисляет два вида расхода и сохраняет реестр репозиториев.

```powershell
Set-Location 'D:/CodexResearch/x20-bench-workspace/work/graph_memory_round34/external_transfer'
$py = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $py prepare.py
& $py experiment.py
& $py grade_external.py
& $py strong.py
& $py ablation.py
& $py alignment.py
python verify.py
```

Модули требуют NumPy, SciPy и tokenizers. Для основного просмотра достаточно REPORT_RU.md. Первичные эффекты сохранены в results.json, последующий повтор на более сильном читателе — в strong/results.json, диагностические эффекты — в ablation.json и alignment.json. В strong/results.json исторический внутренний ключ rrf указывает на фактически выбранный dense_state, что явно зафиксировано в strong/anchor.json. Отдельный столбец dense_state сохраняет идентичные предсказания. Все поля долей в JSON записаны в шкале 0–1, последние два столбца отражают Qwen-токены и число прочитанных элементов. Интервалы конфигурированы как нижний и верхний векторы в том же порядке, что и metrics. При повторении на других платформах возможны небольшие расхождения версий библиотек при проведении оптимизации. Отдельный пересчёт лучше проводить в копии папки.
