"""Сборка клиентского Windows-архива и комплекта издателя (инструмент разработчика).

    python3.13 tools/build_release.py --runtime ПАПКА_RUNTIME --previous-manifest FILE_SHA256.json(RC1)
        --out ПАПКА --vendor-key КЛЮЧ.json --bundle [--split-mb 20] [--lean]

1. Проверяет runtime по SHA-256 из манифеста предыдущей поставки (runtime не меняется
   и не подменяется Linux-библиотеками).
2. Модули программы компилируются в байт-код Python 3.13 (.pyc без исходников); entry.pyc
   получает таблицу SHA-256 остальных модулей и при запуске отказывается работать с
   изменёнными или перекрытыми исходниками модулями. Исходный код — в репозитории.
3. Создаёт архив программы и FILE_SHA256.json. Runtime полный; --lean исключает неиспользуемые
   части (LEAN_REMOVE) — только по явному решению.
4. С --vendor-key — комплект издателя с закрытым ключом (в папку программы не попадает).
5. С --bundle — всё в одном архиве: папка программы, папка комплекта издателя с пометкой
   PRIVATE и READ_ME_FIRST_RU.txt; с --split-mb архив режется на части для передачи,
   Join_Archive.cmd собирает их и сверяет SHA-256.
"""
import argparse
import hashlib
import json
import py_compile
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {'__pycache__', 'acceptance', 'runtime', '.git', 'tests'}
EXCLUDE_FILES = {'Windows_self_test.json', '_wine_shim.py', '.gitignore', 'FILE_SHA256.json',
                 'make_seed.py', 'make_cauk_seed.py'}
# Остаются исходным текстом: заглушка запуска и самостоятельные утилиты обучения.
KEEP_SOURCE = {'app_entry.py', 'train_lora.py', 'evaluate_lora.py'}
KEEP_TOOLS = {'lora_pipeline_check.py', 'bootstrap_pip.py'}
# Облегчённый runtime: части официального дистрибутива, которые программа не использует.
# Остальные файлы runtime сверяются с SHA-256 поставки RC1 (без изменений).
LEAN_REMOVE = (
    'Lib/site-packages/PIL/_avif.cp313-win_amd64.pyd',  # AVIF: Pillow штатно отключает формат
    'Lib/site-packages/PIL/_webp.cp313-win_amd64.pyd',  # WebP: то же
    'Lib/site-packages/reportlab/fonts/',  # образцы шрифтов; отчёты используют resources/DejaVuSans.ttf
    'Lib/ensurepip/_bundled/',  # pip загружается по требованию tools/bootstrap_pip.py
    'Lib/idlelib/', 'Lib/venv/', 'Lib/pydoc_data/', 'NEWS.txt',
    'tcl/tk8.6/demos/', 'tcl/tk8.6/images/', 'tcl/tcl8.6/tzdata/', 'tcl/nmake/',
    'tcl/tcl86t.lib', 'tcl/tclstub86.lib', 'tcl/tk86t.lib', 'tcl/tkstub86.lib',
    'tcl/tclConfig.sh', 'tcl/tclooConfig.sh', 'libs/',
)


def lean_removed(rel):
    rel = rel[len('runtime/'):] if rel.startswith('runtime/') else rel
    return any(rel == item or (item.endswith('/') and rel.startswith(item)) for item in LEAN_REMOVE)
VENDOR_FILES = ('tools/license_tool.py', 'usb_license.py', 'nc_ed25519.py')
FIXED_TIME = (2026, 10, 1, 12, 0, 0)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def program_files():
    for path in sorted(BASE.rglob('*')):
        rel = path.relative_to(BASE)
        if not path.is_file() or set(rel.parts) & EXCLUDE_DIRS or path.name in EXCLUDE_FILES or path.suffix == '.pyc':
            continue
        if rel.parts[0] == 'tools' and path.name not in KEEP_TOOLS:
            continue
        yield rel


def runtime_magic(runtime):
    text = (runtime / 'Lib' / 'importlib' / '_bootstrap_external.py').read_text(encoding='utf-8')
    number = int(re.search(r"^MAGIC_NUMBER = \((\d+)\)\.to_bytes\(2, 'little'\) \+ b'\\r\\n'", text, re.M).group(1))
    return number.to_bytes(2, 'little') + b'\r\n'


def compile_module(source, target, name):
    py_compile.compile(str(source), cfile=str(target), dfile=name, doraise=True,
                       invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)


def write_zip(path, root, rows, prefix=None):
    prefix = root.name + '/' if prefix is None else prefix
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel in rows:
            info = zipfile.ZipInfo(prefix + rel, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (root / rel).read_bytes())
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            sys.exit('Архив повреждён: ' + path.name)


def build_vendor_kit(out, key_path, name, folder='NormaControl_License_Kit', archive=True):
    kit = out / folder
    if kit.exists():
        shutil.rmtree(kit)
    kit.mkdir(parents=True)
    for rel in VENDOR_FILES:
        shutil.copy2(BASE / rel, kit / Path(rel).name)
    for rel in (BASE / 'tools' / 'vendor_kit').iterdir():
        data = rel.read_bytes()
        if rel.suffix == '.cmd':
            data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        (kit / rel.name).write_bytes(data)
    key = json.loads(Path(key_path).read_text(encoding='utf-8'))
    sys.path.insert(0, str(BASE))
    import usb_license
    if usb_license.PUBLIC_KEYS.get(key['key_id']) != key['public_key_hex']:
        sys.exit('Ключ издателя не соответствует открытому ключу в программе.')
    shutil.copy2(key_path, kit / 'NormaControl_vendor_key.json')
    if not archive:
        return kit
    rows = sorted(str(p.relative_to(kit)).replace('\\', '/') for p in kit.rglob('*') if p.is_file())
    target = out / (name + '_License_Kit_PRIVATE.zip')
    write_zip(target, kit, rows)
    return target


KIT_FOLDER = 'NormaControl_License_Kit_PRIVATE'
README_FIRST = """НормаКонтроль ОПО 1.0 RC3 — полный комплект

NormaControl_OPO
    Программа. Пользователям передавайте только эту папку (вместе с флешкой-ключом).
    Без флешки-ключа программа не запускается. Подробно: NormaControl_OPO\\README_RU.md

{kit}
    Комплект издателя с ЗАКРЫТЫМ ключом для выдачи лицензий на флешки.
    НЕ передавайте его пользователям и не кладите на флешки-ключи.
    Сделайте две резервные копии этой папки на разных носителях.
    Подробно: {kit}\\README_VENDOR_RU.md

Порядок первого запуска
    1. Вставьте флешку, которая станет ключом.
    2. Запустите {kit}\\Issue_License.cmd: выберите флешку, укажите владельца и срок.
    3. Запустите NormaControl_OPO\\NormaControl.exe (флешка должна оставаться подключённой).
    4. Проверка установки: NormaControl_OPO\\Diagnostics_Windows.cmd и Acceptance_Windows.cmd.
"""
JOIN_CMD = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "NAME={name}"
{checks}
echo Собирается %NAME% из частей...
copy /b {sources} "%NAME%" >nul
if errorlevel 1 goto failed
where powershell >nul 2>nul
if errorlevel 1 goto certutil
powershell -NoProfile -Command "if ((Get-FileHash -Algorithm SHA256 -LiteralPath '%NAME%').Hash -ieq '{sha256}') {{ exit 0 }} else {{ exit 1 }}"
if errorlevel 1 goto badhash
goto ok
:certutil
where certutil >nul 2>nul
if errorlevel 1 goto nohash
certutil -hashfile "%NAME%" SHA256 | findstr /i /c:"{sha256}" >nul
if errorlevel 1 goto badhash
:ok
echo Готово: %NAME% собран, контрольная сумма SHA-256 совпадает.
echo Распакуйте его: правой кнопкой мыши - Извлечь все. Затем откройте READ_ME_FIRST_RU.txt.
pause
exit /b 0
:nohash
echo Архив %NAME% собран. Проверить контрольную сумму автоматически не удалось.
echo Ожидаемый SHA-256: {sha256}
pause
exit /b 0
:missing
echo Не найдены все части архива. Положите в одну папку с этим файлом: {listing}
pause
exit /b 1
:failed
echo Не удалось собрать архив. Проверьте свободное место на диске.
pause
exit /b 1
:badhash
echo ВНИМАНИЕ: контрольная сумма собранного архива не совпадает с ожидаемой.
echo Вероятно, одна из частей загружена не полностью. Скачайте части заново и запустите этот файл снова.
echo Ожидаемый SHA-256: {sha256}
pause
exit /b 1
"""


def split_archive(archive, size, sha256):
    data = archive.read_bytes()
    parts = []
    for index, offset in enumerate(range(0, len(data), size), 1):
        part = archive.with_name('{}.{:03d}'.format(archive.name, index))
        part.write_bytes(data[offset:offset + size])
        parts.append({'file': part.name, 'bytes': part.stat().st_size, 'sha256': digest(part)})
    names = [p['file'] for p in parts]
    text = JOIN_CMD.format(name=archive.name, sha256=sha256, listing=', '.join(names),
                           checks='\n'.join('if not exist "{}" goto missing'.format(n) for n in names),
                           sources=' + '.join('"{}"'.format(n) for n in names))
    (archive.parent / 'Join_Archive.cmd').write_bytes(text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--previous-manifest', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--name', default='NormaControl_OPO_Windows_1.0_RC3')
    parser.add_argument('--vendor-key')
    parser.add_argument('--bundle', action='store_true', help='программа и комплект издателя в одном архиве')
    parser.add_argument('--split-mb', type=int, default=0, help='разрезать архив на части не больше N МиБ')
    parser.add_argument('--lean', action='store_true', help='исключить неиспользуемые части runtime')
    args = parser.parse_args()
    if args.bundle and not args.vendor_key:
        sys.exit('--bundle требует --vendor-key.')
    import importlib.util
    runtime = Path(args.runtime).resolve()
    if importlib.util.MAGIC_NUMBER != runtime_magic(runtime):
        sys.exit('Байт-код этой версии Python несовместим со встроенным runtime: запустите сборку Python 3.13.')
    previous = {row['path']: row for row in json.loads(Path(args.previous_manifest).read_text(encoding='utf-8'))}
    expected = {p: r for p, r in previous.items() if p.startswith('runtime/')}
    actual = {'runtime/' + str(p.relative_to(runtime)).replace('\\', '/'): p for p in runtime.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    mismatched = [p for p, r in expected.items() if p not in actual or digest(actual[p]) != r['sha256']]
    extra = sorted(set(actual) - set(expected))
    if mismatched or extra:
        sys.exit('runtime не совпадает с предыдущей поставкой: {} / лишние: {}'.format(mismatched[:5], extra[:5]))
    out = Path(args.out).resolve()
    stage = out / 'NormaControl_OPO'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    protected = []
    for rel in program_files():
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel.suffix == '.py' and len(rel.parts) == 1 and rel.name not in KEEP_SOURCE and rel.name != 'entry.py':
            compile_module(BASE / rel, target.with_suffix('.pyc'), rel.name)
            protected.append(rel.with_suffix('.pyc').name)
        elif rel.name != 'entry.py':
            shutil.copy2(BASE / rel, target)
    hashes = {name: digest(stage / name) for name in sorted(protected)}
    source = (BASE / 'entry.py').read_text(encoding='utf-8')
    if 'BUILD_HASHES = {}' not in source:
        sys.exit('В entry.py не найдено место для таблицы целостности.')
    with tempfile.TemporaryDirectory() as tmp:
        generated = Path(tmp) / 'entry.py'
        sources = sorted(name for name in KEEP_SOURCE if (stage / name).is_file())
        if 'BUILD_SOURCES = []' not in source:
            sys.exit('В entry.py не найден список допустимых исходных файлов.')
        generated.write_text(source.replace('BUILD_HASHES = {}', 'BUILD_HASHES = ' + json.dumps(hashes, indent=1))
                             .replace('BUILD_SOURCES = []', 'BUILD_SOURCES = ' + json.dumps(sources)), encoding='utf-8')
        compile_module(generated, stage / 'entry.pyc', 'entry.py')
    removed = 0
    for path, source in sorted(actual.items()):
        if args.lean and lean_removed(path):
            removed += 1
            continue
        target = stage / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = []
    for path in sorted(p for p in stage.rglob('*') if p.is_file()):
        rel = str(path.relative_to(stage)).replace('\\', '/')
        manifest.append({'path': rel, 'bytes': path.stat().st_size, 'sha256': digest(path)})
    (stage / 'FILE_SHA256.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    rows = [r['path'] for r in manifest] + ['FILE_SHA256.json']
    summary = {'files': len(manifest), 'compiled_modules': len(protected) + 1,
               'runtime_files': len(actual) - removed, 'runtime_files_removed_lean': removed}
    if args.bundle:
        bundle = out / 'bundle'
        if bundle.exists():
            shutil.rmtree(bundle)
        bundle.mkdir()
        kit = build_vendor_kit(bundle, args.vendor_key, args.name, KIT_FOLDER, archive=False)
        (bundle / 'READ_ME_FIRST_RU.txt').write_bytes(('\ufeff' + README_FIRST.replace('{kit}', KIT_FOLDER)).replace('\n', '\r\n').encode('utf-8'))
        kit_rows = sorted(str(p.relative_to(kit)).replace('\\', '/') for p in kit.rglob('*') if p.is_file())
        archive = out / (args.name + '.zip')
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as target:
            for prefix, root, items in (('', bundle, ['READ_ME_FIRST_RU.txt']), ('NormaControl_OPO/', stage, rows),
                                        (KIT_FOLDER + '/', kit, kit_rows)):
                for rel in items:
                    info = zipfile.ZipInfo(prefix + rel, FIXED_TIME)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    target.writestr(info, (root / rel).read_bytes())
        with zipfile.ZipFile(archive) as check:
            if check.testzip():
                sys.exit('Архив повреждён.')
        summary.update(archive=archive.name, bytes=archive.stat().st_size, sha256=digest(archive))
        if args.split_mb:
            summary['parts'] = split_archive(archive, args.split_mb * 1024 * 1024, summary['sha256'])
    else:
        archive = out / (args.name + '.zip')
        write_zip(archive, stage, rows)
        summary.update(archive=archive.name, bytes=archive.stat().st_size, sha256=digest(archive))
        if args.vendor_key:
            kit = build_vendor_kit(out, args.vendor_key, args.name)
            summary['vendor_kit'] = {'archive': kit.name, 'bytes': kit.stat().st_size, 'sha256': digest(kit)}
    (out / 'RELEASE_SHA256.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
