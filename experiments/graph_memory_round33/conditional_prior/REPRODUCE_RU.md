# Воспроизведение

Рабочий каталог — graph_memory_round33/conditional_prior. Среда — Python проекта x20-isetrace-e5-gpu с numpy, scipy, sklearn, torch и исходной библиотекой ISETrace. input_rows.py принудительно отключает CUDA. На диске D должны быть исходные проверенные кэши этапов R18–R22, каталог dev-графов official580 и файлы, указанные в шести квитанциях происхождения и моделей. Локальные кэши сведены в D:/CodexResearch/x20-r33-conditional. Файлы публичных прогнозов содержат индексы в соответствующем исходном нативном порядке Dense seed 13.

```powershell
$researchPy = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $researchPy -B input_rows.py train
& $researchPy -B input_rows.py dev
& $researchPy -B models.py train
& $researchPy -B models.py dev
& $researchPy -B score.py dev
& $researchPy -B input_rows.py test
& $researchPy -B models.py test
& $researchPy -B score.py test
& $researchPy -B dev_oracle.py
& $researchPy -B seed_transfer/transfer.py predict
& $researchPy -B seed_transfer/transfer.py score
```

Для проверки уже сохранённых результатов достаточно пересчитать SHA-256 файлов из manifest.json. Для перепроверки качества выбираются исходные raw orders в R19, голды R18, sealed ranks этой серии и штатные span_metrics.py/функция span_mrr. Записи источников используются только как данные. Результаты R20 не переоценивались новыми гиперпараметрами на тестовой разметке.