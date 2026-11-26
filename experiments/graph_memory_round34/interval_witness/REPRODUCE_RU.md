# Воспроизведение

Запустить из каталога этого опыта PowerShell с Python окружения ISETrace на диске D. Все стадии работают на CPU. Данные в траекториях обрабатываются только как JSON. Требуются подписанные данные R19, R20, R22, R33/budget_loss и R34/cost_push, зафиксированные в геометрии и моделях.

```powershell
$experimentPython='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $experimentPython -X utf8 geometry.py train
& $experimentPython -X utf8 geometry.py dev
& $experimentPython -X utf8 learn.py fit
& $experimentPython -X utf8 learn.py dev
& $experimentPython -X utf8 measure.py dev
& $experimentPython -X utf8 learn.py test
& $experimentPython -X utf8 geometry.py test
& $experimentPython -X utf8 measure.py test
& $experimentPython -X utf8 train_census.py
& $experimentPython -X utf8 binding.py
& $experimentPython -X utf8 verify.py
```

Каждый шаг должен завершиться с кодом 0. geometry.py применяет официальное разрешение координат к выбранной обучающей панели во всех восьми подписанных шардах, проверяет SHA корпуса запросов и каждой исходной строки по предварительно сохранённой проекции. В dev/test первоначальные координаты восстанавливаются из нативной атрибуции ранее зафиксированных разбиений. Файлы *-atoms содержат хеши адресов, исходные полуинтервалы символов и номера покрывающих кандидатов. Порядок индексов относится к исходному Dense-FT, отсчёт с нуля. Геометрия dev/test служит только для оценки результатов уже вычисленных score. Файлы *-costs содержат точную стоимость префикса, отвлекающих и необязательных положительных узлов. При полном повторном запуске в исходном каталоге будут обновлены его выходные файлы.

Из файлов, включённых в manifest.json, можно проверить SHA-256 без расчёта рангов.

```powershell
$checks = (Get-Content manifest.json -Raw | ConvertFrom-Json).files
foreach ($entry in $checks.psobject.Properties) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Name).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "SHA mismatch $($entry.Name)"
    }
}
```