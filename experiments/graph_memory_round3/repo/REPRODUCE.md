# Воспроизведение RepoBench

Использованы Python 3.12, NumPy, scikit-learn 1.7.2, PyArrow 22.0.0 и tokenizers 0.22.1 на CPU. В рабочей папке использован существующий Python из work/graph_memory_round2/multihop/dev_env, Rust-токенизатор находится в локальном каталоге lib. Для переносимого запуска в отдельной копии достаточно окружения с библиотеками из requirements.txt.

Скачайте Parquet авторского релиза и CodeGen-токенизатор. pickle-датасеты и удалённый код загрузчиков не исполняются. Затем выполните в каталоге:

```powershell
python fetch.py
Invoke-WebRequest -Uri 'https://huggingface.co/Salesforce/codegen-350M-multi/resolve/b25de779e2044ed5e7707505dea0e5a9bb08556a/tokenizer.json' -OutFile inputs/codegen_tokenizer.json
python run.py
python score.py
python verify.py
python external.py
python fetch_transfer.py
python transfer.py
python score_transfer.py
python verify_transfer.py
python pack_scores.py
```

run.py сначала фиксирует метод и выборку, затем строит признаки. В тестовой фазе признаков используются только имена проекта и файла как метаданные идентификации, исходный префикс code и список фрагментов context; содержимое next_line и gold отсутствует в считываемых столбцах. Только score.py открывает эталон. На v1.1 аналогичная роль отведена столбцам cropped_code и snippet; ranker не получает имена репозиториев, индекс gold и класс первого/повторного использования. Локальные pkl содержат только наши обученные модели, загружаются после проверки SHA; используйте модели, полученные вами либо из проверенного источника. Поштучные предсказания и опубликованные агрегаты позволяют оценить качество без обучения и исполнения программ из репозиториев.

Содержание outputs: один файл .pred.jsonl.gz для каждой части v0, затем scores.jsonl.gz. По каждой задаче в .pred записан ряд индекс, проект, хеш префикса, длины кандидатов и их порядок по каждому методу. external_predictions.json, external_results.json относятся к срезу Semlith. В v1.1 сохранены transfer_roster, transfer_predictions, transfer_scores, численные результаты и независимый аудит. Перегенерация gzip может создать другие байты из-за служебной даты, поэтому для проверки исходной серии используйте упакованные lock-файлы до перезапуска. Загрузка ориентирована на публичные адреса без авторизации. Для небольшого архива достаточно верхнеуровневых файлов ветви, в том числе собственных предсказаний и моделей. Большие входные данные/кэши/локальные site-packages в архив не нужны.

