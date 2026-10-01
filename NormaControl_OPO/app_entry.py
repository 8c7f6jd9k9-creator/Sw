"""Точка запуска НормаКонтроль ОПО (вызывается NormaControl.exe и .cmd-файлами).

Логика запуска, проверка лицензии и целостности — в модуле entry.
"""
import sys
from pathlib import Path

BASE = str(Path(__file__).resolve().parent)
if BASE not in sys.path:
    sys.path.append(BASE)  # в конце пути: стандартные модули не перекрываются файлами из папки

if __name__ == '__main__':
    from entry import run
    sys.exit(run())
