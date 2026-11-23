# Воспроизведение

Для автономного вычисления всех результатов из зафиксированных координат и решений достаточно Python 3.11+ и `python -B verify.py`. Скрипт пересчитывает Full Support, Coverage, Density и стоимость в токенах для каждой пары вопрос–политика на чтении и сохранении; проверяет покрытие отпечатками SHA-256.

Полная реконструкция использует структуру каталогов исходного R18 и R19, публичный ISETrace e40e04d41c04e4eb4bae181ebdd41b61c688081b, выпуск естественных вопросов 3130aeeaeb2b8d292c29f4c8e23303be7463732c, upstream GraphMemory и нативный E5-токенизатор из подписанного source-lock в isetrace_official. Точные версии и алгоритмы фиксирует design-lock.json. Достаточно CPU. Одинаковый BM25 переоценивает IDF на сохранённых блоках отдельно для каждого способа записи. Запрос поступает читателю после последовательного применения политики записи ко всей истории, признаков будущего вопроса в селекторе записи нет.

Команды для нового каталога при заданном Python-окружении R18:

```powershell
$env:OPENBLAS_NUM_THREADS='1'
foreach ($stage in @('lock','split','project','forecast','score')) {
    python -B transfer.py $stage
    if ($LASTEXITCODE -ne 0) {exit $LASTEXITCODE}
}
python -B report.py
python -B verify.py
```

Только локальный частный каталог D:/CodexResearch/x20-isetrace-runtime/write-dev-private содержит тексты вопросов и полей инструментов. Все публичные прогнозы содержат координаты и числовые индексы блоков. Данные обучаемой модели dev с positive labels при построении прогнозов не читаются; сверяются лишь заранее сохранённые списки ID для назначения. Две функции из native resolver извлекают точные эталонные интервалы после фиксации восьми файлов предсказаний. Оригинальные predict.py и graph_write.py импортируются по SHA и получают только переназначенный путь к этой проекции и основной writer cap из уже проверенной спецификации. Поля output means в results.json идут в порядке write Full Support, Coverage, Density, затем read Full Support, Coverage, Density, фактические read E5 tokens. В storage.json.gz указаны физический текст UTF-8, число блоков и токенаж. [Код основных правил](../online_write/predict.py) · [Графовые правила](../online_write/graph_write.py).