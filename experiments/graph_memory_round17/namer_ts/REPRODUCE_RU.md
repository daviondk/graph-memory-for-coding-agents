# Воспроизведение

Контрольные суммы авторской разметки и исходных результатов находятся в sources.json и transfer-label-sources.json. Версия NameRTS f1acdae0f2b2d1ed6e3e2956d510db49bb7c276f. Начальные URL, ревизии matplotlib, исходы по каждой паре и все выбранные файлы сохранены. Для автономной проверки отчётов достаточно сжатых результатов в каталоге. Для полного пересчёта чисел нужны сеть и Git, копия исходного пакета в D:/CodexResearch/x20-r17-namerts/NameRTS и полная история Delgan/loguru в соседнем каталоге loguru. Исследовательский Python для считывания AST и JSON — 3.12 или выше. Нативные прогоны выполнялись отдельным интерпретатором CPython 3.13.5 из D:/CodexResearch/x20-r17-namerts/runtime/Scripts/python.exe. Требуемые версии зависимостей записаны в transfer-plan.json. Установлены pytest 8.3.5, freezegun 1.5.1, colorama 0.4.6, win32-setctime 1.2.0, pytest-mypy-plugins 3.2.0.

```powershell
python audit.py
python transfer.py plan
python transfer.py run
python transfer_score.py
python verify.py
```

Скрипт transfer.py создаёт только новые изолированные worktree на нужных родителях, затем запускает каждый файл отдельно через warm_file.py. На каждом реальном прогоне проверяется путь импортированной копии loguru. В итоговом архиве хранятся stdout, результаты test item, наблюдения о функциях и строках, прогноз выбора, родительский SHA и статус для каждой из 45 единиц. Контрольная сумма SHA устанавливается до обращения к авторским результатам Loguru. Расчёт transfer_score.py использует сохранённые прогнозы. Внешние рабочие копии и дистрибутивы находятся на D отдельно от небольшого отчёта. Для нового независимого прогона укажите отдельный каталог кеша. [Исходники NameRTS](https://github.com/ZJU-CTAG/NameRTS/tree/f1acdae0f2b2d1ed6e3e2956d510db49bb7c276f) · [Исходники Loguru](https://github.com/Delgan/loguru)
