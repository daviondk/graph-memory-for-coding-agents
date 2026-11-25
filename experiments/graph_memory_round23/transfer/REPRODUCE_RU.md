# Воспроизведение

Исходные открытые данные и модель находятся в локальном кэше `D:/CodexResearch/x20-r23-multidoc2dial`. Можно задать другой путь в переменной MD2D_CACHE. Ревизия модели и SHA256 всех файлов, включая исходный ZIP и веса fine_train, закреплены в [input-lock.json](input-lock.json). Каталог с кодом должен сохранять относительное положение по отношению к `graph_memory_round20/fine_train/model.json`.

Использован CPython 3.12 из `D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe`, ONNX Runtime 1.23.2 CPU и модель INT8 для x86 с AVX-512 VNNI. Только имя существующего интерпретатора содержит GPU. Энкодер принудительно использует CPUExecutionProvider, два внутриграфовых потока и последовательное исполнение. В остальных шагах BLAS/Rayon ограничены одним потоком. Версии ПО указаны в [протоколе кодирования](encoder-receipt.json) и [фиксации прогнозов](forecast-seal.json).

```powershell
$py = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
$env:MD2D_CACHE = 'D:/CodexResearch/x20-r23-multidoc2dial'
uv pip install --python $py --target "$env:MD2D_CACHE/libs" --no-deps onnxruntime==1.23.2
& $py -B fetch.py
& $py -B common.py
& $py -B blind_audit.py
& $py -B encode.py
& $py -B predict.py
& $py -B score.py
```

`fetch.py` запрашивает публичный архив и модель, проверяет SHA и сохраняет их на диск D. `common.py` создаёт отделённую от аннотаций проекцию. `blind_audit.py` проверяет её побайтовую эквивалентность на данных с удалёнными полями разметки и проверяет, что каждая история заканчивается до оцениваемой реплики. `encode.py` сохраняет матрицу из 10 314 × 384 значений float32. `predict.py` сохраняет публичные обезличенные идентификаторы, индексы фрагментов, фактическую стоимость, хеш всего выданного текста и общий SHA всей серии. После этого `score.py` открывает размеченные эталонные диапазоны. Числа секунд отражают конкретный запуск, поэтому воспроизведённые файлы с длительностью могут иметь иные SHA. Для содержательной проверки сравнивают прежде всего fingerprints самих массивов, `predictions.json.gz`, `per-query-scores.json.gz` и численные эффекты. Выходы не содержат исходных текстов реплик или ответов.

Исходный ZIP доступен по [авторской ссылке](https://doc2dial.github.io/multidoc2dial/file/multidoc2dial.zip). Схема кодировки и объединения непрерывных spans сопоставлены с [закреплённым загрузчиком IBM](https://huggingface.co/datasets/IBM/multidoc2dial/blob/66809f999db39c5b260bb447a62844377fb2c854/multidoc2dial.py). Наш оценщик использует объединение фактически аннотированных диапазонов. Сторонний загрузчик для задачи чтения может заполнять промежуток между первым и последним span.
