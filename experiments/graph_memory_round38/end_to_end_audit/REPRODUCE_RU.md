# Воспроизведение

Сначала проверить подписанные SHA256 командой `python -B manifest.py --check`. Доказательства, роли 12 историй, происхождение входа и исторических изменений сохранены в public-files.json, history.json, prior-provenance.json и solver-export.json. Результаты Windows находятся в results.json и logs/*.txt, фактические Linux-прогоны в logs/linux-empty.* и logs/linux-gold-final.*. Файл scorer-check.json сравнивает их с вердиктом исходной функции публикации. Файл failure-check.json проверяет отдельную ошибку наложения патча. Там, где время выполнения или имя временного каталога различается, сравнивать следует идентичности тестов, статусы и хеши содержимого.

## Использование уже подготовленного оценщика на D

Рабочая папка — D:/CodexResearch/x20-bench-workspace/work/graph_memory_round38/end_to_end_audit. Запускать со стороны оценщика, когда зафиксированы ваши изменения исходников и их хеши:

```powershell
$reader = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $reader -B grade_patch.py --patch D:/path/to/frozen.diff --out D:/path/to/evaluation.json
```

Нужен включённый Docker Desktop с готовым образом x20-traitlets-reference:r38. Название хостового Python-интерпретатора историческое. Грейдер использует его для чтения Parquet (PyArrow 22.0.0); вычисления выполняются на CPU. Стандартный набор аргументов принимает либо `--patch`, либо `--baseline`. Вариант `--baseline` подаёт пустой diff. Сохранённый JSON включает `complete_observation`, `passed_match`, две числовые пары, SHA256 кандидата и фактический ID образа. Код выхода грейдера 0 обозначает полный результат в JSON, включая честный провал исправления; 2 означает неполное наблюдение. Неприменимый diff нельзя засчитывать как очередное наблюдение 0/2. Кандидат сдаёт стандартный текстовый Git diff с префиксами a/ и b/. Свои новые тесты и сопутствующую документацию можно архивировать отдельно. До передачи оценщику разделить изменения исходников и тестов, сохранить оба хеша. Тестовый дифф как решение отклоняется.

## Чистый эксперимент с решателями

* Нейтральный экспорт D:/CodexResearch/x20-r38-traitlets-solver-export содержит только repo/ и problem_statement.txt. Создать две отдельные копии. После копирования можно инициализировать новый независимый Git-корень с единственным базовым коммитом для записи diff. Нельзя использовать git worktree от полной истории.
* Единственное различие — содержимое D:/CodexResearch/x20-r38-traitlets-history-export/memory.txt во втором условии. Та же копия для сверки в memory-packet.txt, размер 331 байт. Запрещать доступ решателю к родительской рабочей области, сети, разметке, журналам и оценщику. Если доступ к ФС разделён только инструкцией, так и описать. Контекст родительского исследователя исключить из обоих входов.
* Зафиксировать модель, версию, усилие рассуждения, лимиты, порядок назначения, доступные инструменты, число чтений/токенов, сбои и два финальных SHA. Фиксация до просмотра скрытых исходов. Тот же доступный участнику публичный тестовый набор на обеих копиях. Публичный исторический репозиторий допускает знакомство модели с предыдущим ответом в ходе предобучения. Одна пара допускает вывод о работоспособности связки.
* Проверяющий процесс запускается отдельно в контейнере как UID 65534, без сети, с корневой системой только для чтения, tmpfs, 2 CPU, 512 МБ, до 160 процессов. Два diff доставляются по stdin, mount с хостовой ФС отсутствует, контейнер удаляется по завершении. Это рассчитано на обычные добросовестные кандидатные исправления.

## Повторная сборка для аудита

При воспроизведении использовать новую копию настоящего каталога для скриптов и логов. Исходное состояние под Windows организовано как D:/CodexResearch/x20-official-vibe/VibeMemBench (переопределяется VIBE_CHECKOUT). Там benchmark/test.parquet и benchmark/history/python/ipython__traitlets/ берутся из закреплённого [набора на Hugging Face](https://huggingface.co/datasets/Tongyi-ConvAI/VibeMemBench/tree/11164976b4f920cdb0d0cd570ca572e49acea1e8), а scripts/vendor и LICENSE из закреплённого [релиза оценщика](https://github.com/AlibabaResearch/DAMO-ConvAI/tree/7152cf96809b45343ccc1caf7115a7d3fa43f956/VibeMemBench). При подготовке history/ загружать **только 12 разрешённых ID из отчёта**. Папка HF содержит и целевую задачу.

```powershell
$reader = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
./image_metadata.ps1
& $reader -B inputs.py
& $reader -B export_solver.py
& $reader -B source_inventory.py
git clone --bare --filter=tree:0 https://github.com/ipython/traitlets.git runtime/ancestry.git
& $reader -B history_check.py
& $reader -B patch_provenance.py
docker build -t x20-traitlets-reference:r38 -f Dockerfile.reference D:/CodexResearch/x20-r38-traitlets-solver-export
& $reader -B grade_patch.py --baseline --out logs/linux-empty.json
& $reader -B grade_patch.py --patch runtime/patch.diff --out logs/linux-gold-final.json
& $reader -B verify_controls.py
& $reader -B grader_failure_check.py
```

Список фактических Linux-зависимостей сохранён в linux-environment.txt. Dockerfile фиксирует digest исходного образа и прямые зависимости. Сборка в будущем может разрешить транзитивные пакеты и apt-репозиторий в другие версии. Для точного повтора на этой машине использовать зафиксированный локальный image ID из журналов. На подготовленном диске исходники, окружение и рабочие буферы аудита заняли около 70 МБ отдельно от образа.

Для независимой проверки Windows в новой копии после `inputs.py`:

```powershell
$env:UV_PYTHON_INSTALL_DIR = (Join-Path (Get-Location) 'runtime/py-install')
$env:UV_CACHE_DIR = (Join-Path (Get-Location) 'runtime/cache')
uv python install 3.10.20
uv venv --python 3.10.20 runtime/venv
uv pip install --python runtime/venv/Scripts/python.exe pytest==7.4.4 ipython-genutils==0.2.0
& $reader -B replay.py
```

Результат должен совпасть по таблице отчёта, включая независимую сверку с JUnit XML. Если тестовые файлы модифицированы предыдущей попыткой, `inputs.py` восстанавливает файлы исходного архива. Работу нового решателя следует вести только в его отдельной копии.
