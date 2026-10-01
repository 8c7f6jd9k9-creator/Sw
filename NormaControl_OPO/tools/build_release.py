"""Сборка клиентского Windows-архива и комплекта издателя (инструмент разработчика).

    python3.13 tools/build_release.py --runtime ПАПКА_RUNTIME --previous-manifest FILE_SHA256.json(RC1)
        --out ПАПКА [--vendor-key КЛЮЧ.json]

1. Проверяет runtime по SHA-256 из манифеста предыдущей поставки (runtime не меняется
   и не подменяется Linux-библиотеками).
2. Модули программы компилируются в байт-код Python 3.13 (.pyc без исходников); entry.pyc
   получает таблицу SHA-256 остальных модулей и при запуске отказывается работать с
   изменёнными или перекрытыми исходниками модулями. Исходный код — в репозитории.
3. Создаёт один архив программы и FILE_SHA256.json.
4. С --vendor-key — отдельный комплект издателя с закрытым ключом (в архив программы
   не попадает).
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
KEEP_TOOLS = {'lora_pipeline_check.py'}
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


def write_zip(path, root, rows):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel in rows:
            info = zipfile.ZipInfo(root.name + '/' + rel, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (root / rel).read_bytes())
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            sys.exit('Архив повреждён: ' + path.name)


def build_vendor_kit(out, key_path, name):
    kit = out / 'NormaControl_License_Kit'
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
    rows = sorted(str(p.relative_to(kit)).replace('\\', '/') for p in kit.rglob('*') if p.is_file())
    target = out / (name + '_License_Kit_PRIVATE.zip')
    write_zip(target, kit, rows)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--previous-manifest', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--name', default='NormaControl_OPO_Windows_1.0_RC3')
    parser.add_argument('--vendor-key')
    args = parser.parse_args()
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
    shutil.copytree(runtime, stage / 'runtime', ignore=shutil.ignore_patterns('__pycache__'))
    manifest = []
    for path in sorted(p for p in stage.rglob('*') if p.is_file()):
        rel = str(path.relative_to(stage)).replace('\\', '/')
        manifest.append({'path': rel, 'bytes': path.stat().st_size, 'sha256': digest(path)})
    (stage / 'FILE_SHA256.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    archive = out / (args.name + '.zip')
    write_zip(archive, stage, [r['path'] for r in manifest] + ['FILE_SHA256.json'])
    summary = {'archive': archive.name, 'bytes': archive.stat().st_size, 'sha256': digest(archive),
               'files': len(manifest), 'compiled_modules': len(protected) + 1, 'runtime_files': len(actual)}
    if args.vendor_key:
        kit = build_vendor_kit(out, args.vendor_key, args.name)
        summary['vendor_kit'] = {'archive': kit.name, 'bytes': kit.stat().st_size, 'sha256': digest(kit)}
    (out / 'RELEASE_SHA256.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
