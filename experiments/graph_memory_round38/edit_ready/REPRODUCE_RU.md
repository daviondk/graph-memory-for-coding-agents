# Воспроизведение

Из этой папки выполните следующие команды в указанном порядке. Для независимого replay достаточно стандартной библиотеки Python и подписанных соседних каталогов R37. В predictions.json.gz находятся списки ссылок в порядке приоритета. В scored.json.gz одна запись на операцию с массивом оценок по 21 конфигурации. Схема полей находится в том же файле.

```powershell
python -B predict.py
python -B score.py
python -B verify.py
python -B whitespace.py
```

Полная первоначальная проекция и независимая проверка исходных событий используют PyArrow, опубликованные 319 шардов ревизии из input-seal.json и соседнюю R31/natural_handoff. Восстановление исходной проекции выполняйте в копии с теми же относительными путями, до построения прогнозов. Независимый разбор сырых событий доступен после завершения прогнозов.

```powershell
$runner = 'D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $runner -B project.py
python -B predict.py
python -B score.py
python -B verify.py
& $runner -B verify_native.py
python -B whitespace.py
```

Список SHA-256 приведён в manifest.json. Результаты gzip создаются с нулевой отметкой времени. Версия Python и реализация сжатия могут влиять на двоичный хеш при полном переиздании.
