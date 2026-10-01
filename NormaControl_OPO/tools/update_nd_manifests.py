"""Обновить манифесты после очистки DOCX (инструмент сборки, однократный).

Для каждого очищенного файла: sha256 → хэш очищенной копии, original_sha256 →
хэш файла из архива НД (по нему программа распознаёт прежнюю установку и
заменяет текст без потери ссылок), нейтральное примечание без названия
справочной системы. Удаляются внутренние метки прежнего веб-инструмента
(source_ref/source_refs вида turnNsearchM): пользователю они ничего не дают.

    python tools/update_nd_manifests.py ОТЧЁТ_ОЧИСТКИ.json
"""
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ARTIFACT = re.compile(r'^turn\d+(?:search|view|fetch|news|image)\d+$')
CLEANING_NOTE = ('Служебные надписи справочной правовой системы (плашка и логотип, колонтитулы, '
                 'редакционные примечания, ссылки на сайт системы, сведения о программе выгрузки) '
                 'удалены при подготовке комплекта; текст норм не изменялся. Исходный SHA256: {}.')


def neutral_note(rec):
    revision = rec.get('revision_from_document')
    return ('Предоставлено пользователем в НД.rar (выгрузка {}). '.format(rec.get('saved_on_from_document', 'без даты')) +
            ('Редакция «ред. от {}» взята из заголовка документа'.format(revision) if revision else 'Редакция в заголовке не указана') +
            ' и не подтверждена независимой правовой сверкой.')


def neutral_edition(rec):
    revision = rec.get('revision_from_document')
    head = 'ред. от {} (по заголовку документа)'.format(revision) if revision else 'редакция в заголовке не указана'
    return head + '; выгрузка {}; актуальность независимо не подтверждена'.format(rec.get('saved_on_from_document', 'без даты'))


def strip_artifacts(rec):
    if isinstance(rec.get('source_ref'), str) and ARTIFACT.match(rec['source_ref']):
        del rec['source_ref']
    if isinstance(rec.get('source_refs'), list):
        kept = [r for r in rec['source_refs'] if not (isinstance(r, str) and ARTIFACT.match(r))]
        if kept:
            rec['source_refs'] = kept
        else:
            del rec['source_refs']


def main(report_path):
    report = json.loads(Path(report_path).read_text(encoding='utf-8'))
    by_file = {'regulations_texts/' + name: item for name, item in report.items()}
    for manifest in ('regulations_industrial.json', 'regulations_uploaded.json',
                     'regulations_related.json', 'regulations_library.json'):
        path = BASE / manifest
        raw = path.read_text(encoding='utf-8')
        rows = json.loads(raw)
        for rec in rows:
            strip_artifacts(rec)
            item = by_file.get(rec.get('local_file', ''))
            if not item:
                continue
            original = rec.get('original_sha256') or item['original_sha256']
            if rec.get('sha256') and rec['sha256'] not in (original, item['sha256']):
                raise SystemExit('Неожиданный SHA256 в манифесте: ' + rec['id'])
            rec['original_sha256'] = original
            rec['sha256'] = item['sha256']
            rec['service_text_removed'] = CLEANING_NOTE.format(original)
            if rec.get('archive_name') == 'НД.rar':
                if 'legacy_edition' not in rec and rec.get('edition_from_document'):
                    rec['legacy_edition'] = rec['edition_from_document']
                rec['edition_from_document'] = neutral_edition(rec)
                rec['verification_note'] = neutral_note(rec)
            elif rec.get('content_kind') == 'user_copy':
                rec['summary'] = rec.get('summary', '').replace(
                    'в конце обозначен вторичный источник', 'обозначение сайта-распространителя и его логотип удалены при очистке')
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + ('\n' if raw.endswith('\n') else ''), encoding='utf-8')
    inventory_path = BASE / 'ND_INVENTORY.json'
    raw = inventory_path.read_text(encoding='utf-8')
    inventory = json.loads(raw)
    for doc in inventory['documents']:
        item = by_file.get(doc['local_file'])
        if item:
            doc['original_sha256'] = doc.get('original_sha256') or item['original_sha256']
            doc['sha256'] = item['sha256']
            doc['indexed_chunks'] = item['chunks_new']
            doc['service_blocks_removed'] = item['removed_locations']
    inventory['service_text_cleaning'] = ('Служебные надписи справочной правовой системы удалены '
                                          'инструментом tools/clean_docx_service.py; нумерация блоков сохранена.')
    inventory_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + ('\n' if raw.endswith('\n') else ''), encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
