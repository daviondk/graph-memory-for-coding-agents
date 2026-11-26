# Воспроизведение

Запуск из graph_memory_round34/typed_neighbors. Используются исходные траектории, проекции, E5-эмбеддинги и зафиксированные файлы R18–R22 и R33, перечисленные в channels.py и квитанциях. Для повторной проверки номинальных результатов достаточно числовых предсказаний, исходных нативных рангов кандидатов и эталонных координат. При полной пересборке промежуточные матрицы пишутся на диск D в x20-r34-typed-neighbors. GPU отключён.

```powershell
$researchPy = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $researchPy -B verify.py
& $researchPy -B channels.py train
& $researchPy -B channels.py dev
& $researchPy -B fit_neighbors.py fit
& $researchPy -B fit_neighbors.py dev
& $researchPy -B evaluate_neighbors.py dev
& $researchPy -B channels.py test
& $researchPy -B fit_neighbors.py test
& $researchPy -B evaluate_neighbors.py test
& $researchPy -B audit.py
```

Здесь новая матрица имеет один столбец собственной силы, восемь сумм, восемь нормированных каналов, один показатель согласия, восемь каналов контрфактического графа и его показатель согласия. Скрипт verify.py дополнительно пересчитывает основной выигрыш и потери из исходов, сверяет ранги с обоих этапов фиксации и проверяет SHA-256 всех файлов из manifest.json.