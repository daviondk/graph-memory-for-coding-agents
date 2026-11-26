# Воспроизведение R46

Проверка в выгрузке использует только стандартный Python. Она восстанавливает все метрики короткого ответа и парные разности из сохранённых строк модели и эталонов, проверяет SHA256 каждого запроса по его точным токенам и проверяет равенство бюджета всех четырёх контекстных ветвей.

```powershell
python -B verify.py
Get-FileHash -Algorithm SHA256 -LiteralPath manifest.json
```

Для повторной генерации в копии рабочего дерева требуются фиксированная публичная выборка, токенизатор и исходные файлы R31–R33, модель Qwen3-4B-Instruct-2507 Q4_K_M, llama.cpp и GPU. Модель, исполняемый файл, шаблон и исходный JSONL указаны через SHA256 в `plan.json`. Исходный файл данных (Git blob `fc4d1ad626d73d9dcaef00394a3a6d8e837f6448`, 241 046 755 байт) должен находиться в `D:/CodexResearch/x20-r46-reader-transfer/musique-train.jsonl`. Полная версия исследовательского кода и фиксации происхождения модели указаны ниже. [MuSiQue](https://github.com/StonyBrookNLP/musique) · [Версия зеркала данных](https://huggingface.co/datasets/voidful/MuSiQue/tree/a7d9f9adf6191604fc67cde318ee1a86fcf7babc) · [Квантизованные веса](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/a06e946bb6b655725eafa393f4a9745d460374c9)

Запускали `llama-server.exe` версии b12441-164ab018f с аргументами `-m MODEL --host 127.0.0.1 --port 18864 --parallel 1 --ctx-size 1024 --n-gpu-layers all --flash-attn on --threads 4 --no-warmup`. Для отдельных строк используется штатный эндпоинт /completion с готовыми ID токенов в шаблоне Qwen ChatML, temperature=0, top_k=1, seed=460001, cache_prompt=false, прекращение при первой новой строке, штатном конце или 24 токенах. Изображения, инструменты и внешние поисковые вызовы в запросах отсутствуют. Переменные TRUTH и исходные эталоны не передаются. Чтобы воспроизвести саму панель на другом быстродействии, возьмите подписанный plan.json с зафиксированным n; engine.py отдельно переизмеряет объём панели по исходному правилу.

```powershell
$runner='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
python -B engine.py
python -B panel.py
& $runner -B contexts.py
python -B answer.py
python -B delivery.py
& $runner -B evaluate.py
& $runner -B overlap.py
```

Для переисполнения только ридера достаточно подписанных `prompts.json.gz`, `input-seal.json`, установленных весов/сервера и скриптов `answer.py`, `engine.py`, `io46.py`. Для чистого повторного прогона задайте свободный приватный каталог `PRIVATE` в рабочей копии. Все методы обращаются к кэшу по хешу полной последовательности ID токенов. Одинаковые последовательности между вопросами и методами разделяют ровно один ответ. Публикуются точные ответы, число токенов, остановка и длина входа в `answers.json.gz`. Файл `grading-view.json.gz` выпущен оценщиком после подписи всех ответов и содержит только эталонные короткие ответы, алиасы и ID опор. [Метрика авторов](https://github.com/StonyBrookNLP/musique/blob/922ac98f19a201998dbdae6d7f2887a5258dbdeb/metrics/answer.py)
