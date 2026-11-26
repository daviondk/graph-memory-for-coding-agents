# Воспроизведение

Запускать из каталога опыта, на CPU, в окружении, содержащем исходный native scorer и локальные кэши Dense-FT. Исходное исследование подписано SHA-256 75c562b1ea3f028731c5e653c20a3698b917fb22f1d0ea15f05fe332fd541cfe. Для основных артефактов его SHA проверяются перед запуском. Ранжирование фиксируется отдельным манифестом до вычисления оценок, контроль R33 сверяется до совпадения полного порядка и с историческими метриками каждого вопроса.

```powershell
$experimentPython='D:/CodexResearch/x20-isetrace-e5-gpu/venv/Scripts/python.exe'
& $experimentPython -X utf8 transfer.py run
& $experimentPython -X utf8 verify.py
```

Шаги forecast, measure и compare доступны отдельно. verify.py пересчитывает пять величин через атомарные интервалы и ручную трапецию по log₂-бюджету для каждой пары вопрос–модель–seed. Исходы и исходный Dense-порядок сохраняются с нулевыми индексами.

```powershell
$files = (Get-Content manifest.json -Raw | ConvertFrom-Json).files
foreach ($entry in $files.psobject.Properties) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Name).Hash.ToLowerInvariant() -ne $entry.Value) {throw $entry.Name}
}
```