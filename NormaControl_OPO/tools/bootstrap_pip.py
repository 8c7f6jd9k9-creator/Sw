"""Установка pip во встроенный Python при подготовке инструментов обучения.

Колесо pip не входит в архив программы (экономия размера). Скрипт берёт с PyPI
последний выпуск pip (только с pypi.org / files.pythonhosted.org), сверяет
SHA-256 с данными PyPI и устанавливает его. Нужен интернет — как и для PyTorch.

    runtime\\python.exe -I -X utf8 tools\\bootstrap_pip.py
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ALLOWED = ('pypi.org', 'files.pythonhosted.org')


def fetch(url, limit):
    host = urlsplit(url).hostname or ''
    if urlsplit(url).scheme != 'https' or host not in ALLOWED:
        raise SystemExit('Недопустимый адрес загрузки: ' + url)
    with urlopen(url, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise SystemExit('Ответ слишком большой: ' + url)
    return data


def main():
    try:
        import pip  # noqa: F401
        print('pip уже установлен.')
        return 0
    except ImportError:
        pass
    info = json.loads(fetch('https://pypi.org/pypi/pip/json', 5 * 1024 * 1024))
    files = [f for f in info['urls'] if f['packagetype'] == 'bdist_wheel' and f['filename'].endswith('py3-none-any.whl')]
    if not files:
        raise SystemExit('На PyPI не найдено колесо pip.')
    wheel = files[0]
    data = fetch(wheel['url'], 50 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != wheel['digests']['sha256']:
        raise SystemExit('SHA-256 загруженного pip не совпадает с PyPI. Установка прервана.')
    with tempfile.TemporaryDirectory(prefix='normacontrol-pip-') as tmp:
        path = Path(tmp) / wheel['filename']
        path.write_bytes(data)
        print('Установка', wheel['filename'], flush=True)
        # Колесо — zip-архив с модулем pip: им же и устанавливается. Запуск как «python -m pip»:
        # иначе pip на Windows отказывается устанавливать сам себя.
        code = ('import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = ["pip"] + sys.argv[2:]; '
                'runpy.run_module("pip", run_name="__main__", alter_sys=True)')
        return subprocess.call([sys.executable, '-I', '-X', 'utf8', '-c', code, str(path),
                                'install', '--no-warn-script-location', str(path)])


if __name__ == '__main__':
    sys.exit(main())
