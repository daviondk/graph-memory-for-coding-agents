# Проверка результата и оценивание нового патча

Запустите команды из каталога этого отчёта. Для проверки отпечатков и контрольных результатов достаточно стандартной библиотеки Python 3.10 или выше.

~~~powershell
python -B verify.py
~~~

## Повтор исполнения на Windows

Нужны Git и uv, доступ к закреплённому публичному исходному архиву и пакеты из lock-файлов. Переменная VIBE_CHECKOUT задаёт каталог с тремя исходными модулями авторского оценщика. prepare_runtime.py загружает недостающее, проверяет SHA-256 и создаёт метаданные дистрибутива PyBaMM из базового дерева. В существующем локальном окружении можно сразу вызывать grade_patch.py. Для чистой установки выполните следующие команды.

~~~powershell
$env:VIBE_CHECKOUT=Join-Path (Get-Location) 'evaluator/vendor-checkout'
$env:PYBAMM_GRADE_TMP=Join-Path (Get-Location) 'evaluator/temp-checkouts'
$env:UV_CACHE_DIR=Join-Path (Get-Location) 'evaluator/uv-cache'
uv venv --python 3.10.20 evaluator/venv
uv pip install --python evaluator/venv/Scripts/python.exe -r environment.lock
uv pip install --only-binary :all: --no-deps --target evaluator/jax-supplement --python evaluator/venv/Scripts/python.exe -r extras.lock
python -B prepare_runtime.py
python -B grade_patch.py --paper-extras --baseline --out rerun/base.json
python -B grade_patch.py --paper-extras --patch specs/pybamm-team__pybamm-4267/patch.diff --out rerun/reference.json
~~~

Для независимого решения укажите зафиксированный до просмотра проверочных данных патч и новое имя результата.

~~~powershell
python -B grade_patch.py --paper-extras --patch D:/path/to/candidate.diff --out rerun/candidate.json
~~~

Допускается обычный текстовый unified diff, меняющий существующие Python-файлы реализации в pybamm/. Каждый запуск получает свежую рабочую копию, отдельные TEMP и TMP и ограниченный набор переменных окружения. Оценщик выполняет обычный процесс Windows с правами текущего пользователя. Такая изоляция служит воспроизводимости и рассчитана на проверенные локальные патчи. Входы с чужим непроверенным кодом требуют изоляции на уровне ОС.

Код завершения оболочки 0 означает, что все восемь зарегистрированных результатов получены и два парсера согласовались. При сравнении патчей читайте official_exact_passed_match, registered_success, fail_to_pass и pass_to_pass в JSON. Код завершения самого pytest находится в exit_code. Рядом сохраняются исходный текстовый вывод и отчёт JUnit XML. В уже существующие файлы оболочка писать откажется. Из-за временных путей и продолжительности тестов у нового вывода будет другой SHA-256.

specs/ содержит закрытые для решателя эталоны и тестовые материалы публичного бенчмарка. Для слепого эксперимента храните весь пакет оценщика вне рабочей копии решателя. Исходный журнал порядка кандидатов находится в screen.json, минимальная проверка трёх архивных историй каждой цели — в specs/*/history-minimum.json.
