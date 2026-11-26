# Воспроизведение

Подготовьте официальный dev MuSiQue-Ans по [протоколу выбора абзацев](../../graph_memory_round32/musique_links/REPRODUCE_RU.md). Хеш входного JSONL и пути указаны в reader.py. Сохраните metrics/answer.py и metrics/metric.py из [этой ревизии](https://github.com/StonyBrookNLP/musique/tree/922ac98f19a201998dbdae6d7f2887a5258dbdeb/metrics) в D:/CodexResearch/x20-r32-musique/author/metrics. Имена, хеши весов и токенизатора указаны в plan.json. Точный репозиторий модели указан в [отчёте](REPORT_RU.md). Для модели нужны ONNX Runtime 1.23.2 CPU, tokenizers и NumPy. Создайте служебный каталог D:/CodexResearch/x20-r33-musique-answers для проекции текстов и возобновления расчёта.

```powershell
python reader.py prepare
python reader.py predict
python score.py
python matched.py
```

Не передавайте ответы и декомпозицию в предсказатель. Прогноз — номер документа, поле, начало и конец цитаты в символах, длина входа. Записи считываются по идентификатору исходного вопроса. Скрипт оценки дополнительно сверяет среднее индивидуальных значений с официальным накопительным классом AnswerMetric.
