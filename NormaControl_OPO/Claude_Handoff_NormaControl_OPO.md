# Промт для передачи в Claude — НормаКонтроль ОПО Windows 1.0 RC3

Ты продолжаешь разработку существующего Windows-продукта «НормаКонтроль ОПО» (Tkinter + SQLite, встроенный Python 3.13.16 x64, NormaControl.exe → runtime\pythonw.exe -I -X utf8 app_entry.py). Не переписывай приложение и не заменяй локальную архитектуру (Ollama на 127.0.0.1, LoRA офлайн) облачными API. Сохраняй пользовательские данные и прежние ссылки [Кисточник-Ффрагмент]. Сначала прочитай README_RU.md, docs/VALIDATION_WINDOWS_RC2.md, ND_IMPORT_RU.md, LOCAL_AI_RU.md.

Целевая машина: Windows 10 Pro 22H2 x64, i7-10700, 64 ГБ RAM, NVIDIA RTX A5000 (24 ГБ), драйвер 597.06. Идентификаторы устройства не нужны и не передаются.

## Лицензирование (RC3)

- Программа запускается только с USB-флешкой, на которой лежит NormaControl.lic, подписанный Ed25519 закрытым ключом издателя и привязанный к серийным номерам USB-устройства и тома (usb_license.py, nc_ed25519.py, license_ui.py; проверка в entry.main и App.__init__, контроль каждые 15 с, закрытие через 60 с без ключа).
- Закрытый ключ хранится только в комплекте издателя (NormaControl_License_Kit, tools/license_tool.py). Никогда не добавляй его в репозиторий, архив программы или ответы. Для новой сборки сохраняй открытый ключ в usb_license.PUBLIC_KEYS, иначе выданные лицензии перестанут действовать.
- Клиентский архив собирается tools/build_release.py (Python 3.13): модули в .pyc, entry.pyc с таблицей SHA-256 и списком допустимых файлов. Исходники — в репозитории разработчика.
- Для тестов под Wine прокладка заменяет только перечисление USB-дисков (в поставку не входит); App и entry не имеют обходов по переменным окружения или ключам командной строки — не добавляй их.

## Состояние RC2

- По запросу пользователя из нормативной базы удалены служебные надписи справочных систем (плашки, «Дата сохранения», колонтитулы, логотипы, 66 редакционных примечаний, ссылки на сайт системы, метаданные выгрузки, строки сайта-распространителя в копии №534). Инструменты: tools/clean_docx_service.py (сборка, lxml), service_text.py (фильтр при извлечении и однократная очистка индекса). Нумерация блоков DOCX сохранена; база RC1 обновляется на месте без смены id фрагментов (KnowledgeBase.replace_source_content / _store_chunks). Исходные SHA256 — original_sha256 в манифестах.
- №517 исключён и не возвращается.
- Исправления Windows: -X utf8 (в RC1 UTF-8 режим не работал из-за -I), .cmd в CRLF, окно по рабочей области и DPI (ui_scale.py), прогресс первичной индексации, CREATE_NO_WINDOW (winproc.py), EXIF-поворот фото в PDF, атомарная проверяемая резервная копия и восстановление в пустую папку (core.verify_backup/restore_backup), индекс kb_chunks(source_id), установка CUDA-сборки torch (cu130 → cu128 → cu126).
- Новые инструменты: Acceptance_Windows.cmd (acceptance.py) — приёмка на временной базе с отчётом без идентификаторов; evaluate_lora.py — оценка ответов отдельно от loss + лист answer_review.csv; tools/lora_pipeline_check.py — проверка конвейера LoRA на крошечной случайной модели; tools/build_release.py — сборка двух частей архива с проверкой runtime по SHA-256.
- Проверено: 77 unittest (Linux; Win64-runtime под Wine), приёмка под Wine 10 OK/0 FAIL, NormaControl.exe под Wine, обновление базы RC1, OCR rus на Linux, конвейер LoRA с torch 2.14.1/transformers 4.57.6/peft 0.21.1 на CPU (случайная модель).
- НЕ проверено: настоящая Windows, Ollama и веса (сеть среды блокировала ollama.com, registry.ollama.ai, huggingface.co, download.pytorch.org), GPU/VRAM/скорость, LoRA на реальной базе, OCR на Windows, torch под Windows (под Wine torch не запускается: нет ucrtbase.crealf), юридическая актуальность.

## Следующая задача

1. Получить от пользователя: Windows_self_test.json, папку acceptance (Acceptance_report_*.json/.txt, PDF, снимок окна), при наличии — pipeline_check.json, answer_eval.json/answer_review.csv, журналы %LOCALAPPDATA%\NormaControlOPO\logs.
2. Разобрать FAIL/SKIP и исправить именно текущую поставку; повторно собрать архив tools/build_release.py (runtime не менять, проверка по FILE_SHA256.json RC1/RC2).
3. По отчёту Ollama выбрать qwen2.5:14b или 7b (критерии: model_in_vram_percent = 100, приемлемая скорость, нет выдуманных [К-Ф], нет внешних соединений).
4. Обучение: база 7B (Qwen2.5-7B-Instruct, формат Hugging Face), датасет только из проверенных специалистом пар, Ollama выгружен на время обучения, оценка evaluate_lora.py и лист специалиста; импорт в Ollama под новым именем только после положительной оценки.
5. Обновить docs/VALIDATION_WINDOWS_RC2.md фактическими результатами. Не утверждать промышленную готовность и правовую актуальность.

Команды: runtime\python.exe -I -X utf8 app_entry.py --self-test; runtime\python.exe -I -X utf8 app_entry.py --acceptance [--model qwen2.5:14b] [--photo …] [--document …]; runtime\python.exe -X utf8 -m unittest discover -s tests -v; лаунчер: x86_64-w64-mingw32-gcc -municode -mwindows -static -Os windows_launcher.c -o NormaControl.exe -luser32. Под Wine для тестов нужна прокладка без KERNEL32.CopyFile2 (в поставку не входит).
