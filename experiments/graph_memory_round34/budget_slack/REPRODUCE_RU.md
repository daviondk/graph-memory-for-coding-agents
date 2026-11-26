# Воспроизведение

Исходные численные представления и обученные E5 доступны в прежней среде R19–R33 на диске D. Для проверки готовых результатов нужен только стандартный Python. Для повторного эксперимента требуются NumPy, SciPy, пакет исходного ISETrace, подписанные кэши R33/budget_loss и R21. Используется CPU, веса Dense-FT берутся из зафиксированных обучений.

```powershell
$researchPy = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $researchPy -B verify.py
& $researchPy -B slack.py fit
& $researchPy -B slack.py dev
& $researchPy -B measure.py dev
& $researchPy -B slack.py test
& $researchPy -B measure.py test
& $researchPy -B bound_audit.py dev
& $researchPy -B bound_audit.py test
& $researchPy -B sensitivity.py
```

В train-query-weights.json.gz сохранены P, N, L и вес каждого обучающего вопроса во всех режимах. В dev-proxy.json.gz и test-proxy.json.gz для каждого seed и метода порядок полей — стоимость отвлекающих до последнего положительного, индикатор префиксной прокси-полноты, индикатор нативной полноты. В results.json ключ all5 отвечает заранее выбранному первичному сравнению. Среднее сначала вычислено внутри каждого вопроса по согласованным seed; доверительный интервал получен пересэмплированием 1 207 целых траекторий 10 000 раз с seed 13. Ресэмплирование характеризует разброс по траекториям при фиксированных пяти моделях.