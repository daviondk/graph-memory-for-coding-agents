# Входы, границы доступа и повтор

Полная панель — `data/musique_ans_v1.0_dev.jsonl` из архива, на который ссылаются авторы MuSiQue. Байты train и dev сверены с двумя закреплёнными локальными файлами. Источник для получения архива и его SHA256 приведены в `source-seal.json`. Рядом сохранены число повторяющихся документов и нормализованных вопросов. [Официальный репозиторий корпуса](https://github.com/StonyBrookNLP/musique) · [Ссылка авторов на архив](https://github.com/StonyBrookNLP/musique/blob/922ac98f19a201998dbdae6d7f2887a5258dbdeb/download_data.sh)

Файл `orders.json.gz` содержит адрес первого документа и порядок вторых, исходные упоминания и назначение placebo для каждого семени. Сначала `orders.py` подтверждает, что интерфейс раскрыл один абзац. Затем `inputs.py` передаёт в фиксированный токенизатор тексты выбранных вторых документов и запирает полный список запросов. Последнее обращение к модели завершает `generate.py`; повтор 32 выбранных по SHA256 входов тоже проходит до открытия эталонов. В `contexts.json.gz` записи `refs[arm] = [second_paragraph_id, prompt_hash, complete_token_length]` связывают выбранный документ с точным входом и ответом в `answers.json.gz`. `gold.json.gz` и `outcomes.json.gz` создаются после `answer-seal.json`.

В готовом каталоге `python -B verify.py` проверяет полные вводы, равенство фактической длины, все ребра и 16 919 назначений ответа, по каждому сверяет EM, Answer F1 и ID опор. Для этой проверки достаточно стандартного Python; GPU, модель и исходный корпус не требуются.

Полный повтор использует копию с сохранённым `registration.json`, прежние подписанные каталоги R31–R33 и R46–R47, Python с NumPy, PyArrow и tokenizers. Путь к исполняемому файлу llama.cpp, GGUF модели и порту задаёт `common.py`. Стандартные аргументы сервера R47 на этом порту — `--host 127.0.0.1 --port 18896 --parallel 1 --ctx-size 1024 --n-gpu-layers all --flash-attn on --threads 4 --no-warmup`. В источниках и выходах используются строго текстовые документы, их инструкции не исполняются. [Фиксированные веса Qwen](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/a06e946bb6b655725eafa393f4a9745d460374c9) · [Официальная метрика](https://github.com/StonyBrookNLP/musique/blob/922ac98f19a201998dbdae6d7f2887a5258dbdeb/metrics/answer.py)

```powershell
$runner = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $runner -B source.py
& $runner -B orders.py
& $runner -B inputs.py
& $runner -B generate.py
& $runner -B grade.py
& $runner -B cost.py
& $runner -B report.py
python -B verify.py
```

В Windows `serve.ps1` поднимает собственный loopback-сервер, выполняет `inputs.py` и `generate.py`, затем закрывает этот процесс. При повторе можно вызвать этот скрипт вместо двух отдельных команд. В новой копии используйте отдельный приватный каталог `P` для входного архива, видимой проекции, доставленных текстов и журнала. Генератор читает ранее сохранённые записи по хешу запечатанного набора и дополняет отсутствующие ответы. Измеренный сеанс прошёл одним запуском; `cost.py` сверяет числовой журнал каждого запроса с этим условием, включая повторы. В `hardware.json` сохранён отдельный снимок nvidia-smi во время GPU-инференса.
