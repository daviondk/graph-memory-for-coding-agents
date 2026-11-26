# Воспроизведение

Все команды запускаются из каталога опыта на CPU с доступом к прежним кэшам ISETrace. Содержимое траекторий обрабатывается только как входные данные.

```powershell
$experimentPython='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $experimentPython -X utf8 materialize.py
& $experimentPython -X utf8 native_check.py build
& $experimentPython -X utf8 native_check.py compare
& $experimentPython -X utf8 analysis.py
& $experimentPython -X utf8 verify.py
```

orders-*.json.gz содержит строки [q, trajectory, cut, selections], где E/M/L задают выбранные индексы исходного Dense-порядка в пределах 512, 1024 и 2048 токенов. graphs-*.json.gz содержит на каждую траекторию и срез мощности логических и фактически наблюдаемых PU-отношений, их разностей и количество видимых фрагментов. sample-*.json.gz и native-raw-states.json.gz содержат только мощности, номера шага и хеши идентичности направленных PU-пар для независимой проверки. Сырые входные тексты в артефакты не вложены. Пофайловые контрольные суммы приведены в manifest.json.