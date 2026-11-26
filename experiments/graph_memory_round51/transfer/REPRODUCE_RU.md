# Воспроизведение проверки переноса

Проверить запечатанный комплект можно автономно командой `python -B verify.py --manifest` из этого каталога. Для проверки каждой метрики служат `contexts.json.gz` (адреса, хеши и длины), `prompts.json.gz` (полные токены), `answers.json.gz` (текст и число выходных токенов), `gold.json.gz` и `outcomes.json.gz`. Отдельные файлы `retrieval-seal.json`, `input-seal.json`, `answer-seal.json` связывают этапы.

Для полного повторения нужен checkout предшествующих серий из этого репозитория, оба локальных GGUF и llama.cpp из `graph_memory_round50/gate_confirmation/paths_a.py`, научный Python с NumPy, pyarrow, tokenizers и requests. Исходные публичные корпуса и tokenizer E5 должны находиться по адресам той же серии. Переменная `P` в `study.py` задаёт приватный каталог данных и логов. Исходники GGUF по содержанию и движок закреплены в `registration.json`. Первичное обучение порога входит в заархивированный R50 `adaptive_address`.

Для полного нового прогона сделайте рабочую копию экспериментальных исходников в структуре `experiments/graph_memory_round51/transfer` на чистом checkout с предыдущими сериями, пустым каталогом вывода и R50 `runtime.py` из этой поставки. Исходные двоичные файлы данных доступны через `fetch.py`. Выполните последовательно:

```powershell
python -B fetch.py
python -B study.py register select lex_orders projection encode
python -B reader.py
python -B study.py costs
python -B score.py
python -B secondary.py
python -B verify.py
```

При полном повторении меняются измерения времени, абсолютные пути локального процесса и хеши зависимых от них отчётов. Архивированные прогнозы проверяются автономно. Парный bootstrap воспроизводит код R50 при 10 000 выборках. Дедупликация промптов сохраняет одинаковое предсказание одной и той же детерминированной модели при тождественном полном входном массиве. `timing-events.json.gz` сопоставляет хеш физического запроса с временем prefill и декодирования, числом токенов и признаком проверочного повтора.

Данные HotpotQA и их производные (в том числе токенизированные фрагменты) распространяются авторами под [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). В этой выборке контексты укорочены и сильнее ограничен доступ к документам. Авторы корпуса: Zhilin Yang, Peng Qi, Saizheng Zhang, Yoshua Bengio, William Cohen, Ruslan Salakhutdinov, Christopher D. Manning. [Публикация](https://aclanthology.org/D18-1259/) · [Данные и штатные условия оценки](https://hotpotqa.github.io/) · [Исходный официальный оценщик](https://github.com/hotpotqa/hotpot/blob/fa3a36370899e1d85822de61e58c85ea19993154/hotpot_evaluate_v1.py).
