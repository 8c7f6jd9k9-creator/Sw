"""Сборка Windows-архива из исходников и неизменённого runtime (инструмент разработчика).

    python tools/build_release.py --runtime ПАПКА_RUNTIME --previous-manifest FILE_SHA256.json(RC1) --out ПАПКА

1. Проверяет runtime по SHA-256 из манифеста предыдущей поставки (runtime не меняется
   и не подменяется Linux-библиотеками).
2. Собирает папку NormaControl_OPO без служебных/локальных файлов, пишет FILE_SHA256.json.
3. Создаёт две части архива, как в RC1: Part1 — программа и документы, Part2 — runtime.
"""
import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {'__pycache__', 'acceptance', 'runtime', '.git'}
EXCLUDE_FILES = {'Windows_self_test.json', '_wine_shim.py', '.gitignore', 'FILE_SHA256.json'}
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
        if path.is_file() and not (set(rel.parts[:-1]) & EXCLUDE_DIRS) and rel.parts[0] not in EXCLUDE_DIRS \
                and path.name not in EXCLUDE_FILES and not path.name.endswith('.pyc'):
            yield rel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--previous-manifest', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--name', default='NormaControl_OPO_Windows_1.0_RC2')
    args = parser.parse_args()
    runtime = Path(args.runtime).resolve()
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
    manifest = []
    for rel in program_files():
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BASE / rel, target)
        manifest.append({'path': str(rel).replace('\\', '/'), 'bytes': target.stat().st_size, 'sha256': digest(target)})
    for path, source in sorted(actual.items()):
        manifest.append({'path': path, 'bytes': source.stat().st_size, 'sha256': expected[path]['sha256']})
    (stage / 'FILE_SHA256.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    parts = {out / (args.name + '_Part1.zip'): [r for r in manifest if not r['path'].startswith('runtime/')] + [{'path': 'FILE_SHA256.json'}],
             out / (args.name + '_Part2.zip'): [r for r in manifest if r['path'].startswith('runtime/')]}
    for archive_path, rows in parts.items():
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for row in rows:
                source = stage / row['path'] if not row['path'].startswith('runtime/') else actual[row['path']]
                info = zipfile.ZipInfo('NormaControl_OPO/' + row['path'], FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with source.open('rb') as stream:
                    archive.writestr(info, stream.read())
        with zipfile.ZipFile(archive_path) as archive:
            if archive.testzip():
                sys.exit('Архив повреждён: ' + archive_path.name)
    summary = {'program_files': sum(not r['path'].startswith('runtime/') for r in manifest), 'runtime_files': len(actual),
               'parts': {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in parts}}
    (out / 'RELEASE_SHA256.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
