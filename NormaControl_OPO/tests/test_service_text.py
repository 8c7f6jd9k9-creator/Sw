"""Удаление служебных надписей справочных систем и перенос очищенных текстов без потери ссылок."""
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from core import Store
from knowledge import KnowledgeBase
from regulations import NormativeCatalog
from service_text import REMOVED_MARK, clean_text, contains_brand
from situations import SituationStore

BASE = Path(__file__).resolve().parents[1]
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
PLAQUE = ('<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Федеральный закон от 01.01.2000 N 1-ФЗ (ред. от 01.02.2026) "О трубопроводах"</w:t></w:r></w:p></w:tc></w:tr>'
          '<w:tr><w:tc><w:p><w:r><w:t>Документ предоставлен </w:t></w:r><w:r><w:t>КонсультантПлюс</w:t></w:r><w:r><w:t>www.consultant.ru</w:t></w:r>'
          '<w:r><w:t>Дата сохранения: 01.10.2026</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
NOTE = ('<w:tbl><w:tr><w:tc><w:p/></w:tc><w:tc><w:p><w:r><w:t>КонсультантПлюс: примечание.</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>С 01.03.2027 в ст. 2 вносятся изменения. См. будущую редакцию.</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
ARTICLE = '<w:p><w:r><w:t>Статья 2. Трубопровод должен проходить испытания.</w:t></w:r></w:p>'
NOTE_ON_ARTICLE_3 = ('<w:tbl><w:tr><w:tc><w:p/></w:tc><w:tc><w:p><w:r><w:t>КонсультантПлюс: примечание.</w:t></w:r></w:p>'
                     '<w:p><w:r><w:t>О применении ст. 3 см. письмо.</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
ARTICLE_3 = '<w:p><w:r><w:t>Статья 3. Сосуд под давлением подлежит освидетельствованию.</w:t></w:r></w:p>'


def write_docx(path, blocks):
    xml = '<w:document {}><w:body>{}</w:body></w:document>'.format(W, ''.join(blocks))
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return path


class CleanTextTests(unittest.TestCase):
    def test_service_lines_removed_norm_text_kept(self):
        text = ('Федеральный закон от 21.07.1997 N 116-ФЗ (ред. от 31.07.2025)\n'
                'Документ предоставлен  КонсультантПлюс www.consultant.ru Дата сохранения: 01.10.2026 \n'
                'Страница 5 из 39\n'
                '(в ред. Федерального закона от 04.03.2013 N 22-ФЗ)\n'
                'гарантированная подача воздуха; статья 962 Гражданского кодекса')
        cleaned, removed = clean_text(text)
        self.assertEqual(removed, 4)  # плашка: 3 фразы; колонтитул страницы: 1 строка
        self.assertNotIn('Консультант', cleaned)
        self.assertNotIn('Страница', cleaned)
        self.assertIn('(ред. от 31.07.2025)', cleaned)
        self.assertIn('(в ред. Федерального закона от 04.03.2013 N 22-ФЗ)', cleaned)
        self.assertIn('гарантированная подача воздуха; статья 962 Гражданского кодекса', cleaned)

    def test_note_block_and_watermark(self):
        self.assertEqual(clean_text('|  | КонсультантПлюс: примечание. Текст приведен по официальной публикации. |'), ('', 1))
        self.assertEqual(clean_text('Локализация: промышленная безопасность на блог-инженера.рф')[0], '')
        self.assertEqual(clean_text('Обычный текст без надписей'), ('Обычный текст без надписей', 0))
        self.assertTrue(contains_brand('www.consultant.ru'))
        self.assertFalse(contains_brand('Гражданский кодекс; гарантийные стыки'))


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.kb = KnowledgeBase(self.root / 'data')

    def tearDown(self):
        self.temp.cleanup()

    def test_docx_plaque_and_notes_not_indexed_block_numbers_kept(self):
        path = write_docx(self.root / 'law.docx', [PLAQUE, NOTE, ARTICLE])
        sid = self.kb.import_file(path, reviewed=True)
        with sqlite3.connect(self.kb.db_path) as db:
            rows = db.execute('SELECT location,text FROM kb_chunks WHERE source_id=? ORDER BY id', (sid,)).fetchall()
        self.assertEqual([r[0] for r in rows], ['DOCX блок 1 (таблица), фрагмент 1', 'DOCX блок 3 (абзац), фрагмент 1'])
        self.assertFalse(any(contains_brand(r[1]) for r in rows))
        self.assertIn('ред. от 01.02.2026', rows[0][1])
        self.assertEqual(self.kb.search('КонсультантПлюс', include_unreviewed=True), [])
        notes = self.kb.sources()[0]['extraction_notes']
        self.assertIn('Удалены служебные надписи', notes)

    def test_reindex_same_file_keeps_fragment_ids(self):
        path = self.root / 'rules.txt'
        path.write_text('Трубопровод проверяется ежегодно.', encoding='utf-8')
        sid = self.kb.import_file(path, reviewed=True)
        first = self.kb.search('Трубопровод')[0]['id']
        self.assertEqual(self.kb.import_file(path, reviewed=True), sid)
        self.assertEqual(self.kb.search('Трубопровод')[0]['id'], first)

    def test_indexed_user_source_cleaned_once_ids_kept(self):
        path = self.root / 'export.txt'
        path.write_text('Сосуд подлежит освидетельствованию.\nДокумент предоставлен КонсультантПлюс\nwww.consultant.ru\nСтраница 1 из 2', encoding='utf-8')
        with patch('knowledge.clean_text', lambda text: (text, 0)):  # индекс прежней версии без очистки
            sid = self.kb.import_file(path, reviewed=True)
        before = self.kb.search('освидетельствованию')[0]
        self.assertTrue(contains_brand(before['text']))
        result = self.kb.clean_indexed_service_text()
        self.assertEqual(result['sources'], 1)
        after = self.kb.search('освидетельствованию')[0]
        self.assertEqual(after['id'], before['id'])
        self.assertEqual(after['text'], 'Сосуд подлежит освидетельствованию.')
        self.assertIsNone(self.kb.clean_indexed_service_text())
        self.assertIn('исходный файл не изменён', self.kb.sources()[0]['extraction_notes'].lower())
        self.assertTrue(contains_brand(self.kb.open_path(sid).read_text(encoding='utf-8')))


class BundledUpgradeTests(unittest.TestCase):
    """Прежняя установка с выгрузкой справочной системы получает очищенную копию."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / 'package'
        (self.base / 'regulations_texts' / 'ND').mkdir(parents=True)
        self.patch = patch('regulations.BASE', self.base)
        self.patch.start()
        self.store = Store(self.root / 'data', BASE / 'registry.json')
        self.file = self.base / 'regulations_texts' / 'ND' / 'TEST1.docx'

    def tearDown(self):
        self.store.close()
        self.patch.stop()
        self.temp.cleanup()

    def manifest(self, record):
        for name in ('regulations_industrial.json', 'regulations_related.json', 'regulations_library.json', 'regulations_uploaded.json'):
            data = [record] if name == 'regulations_uploaded.json' else []
            (self.base / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def test_upgrade_keeps_ids_flags_and_references(self):
        record = {'id': 'TEST1', 'title': 'О трубопроводах', 'local_file': 'regulations_texts/ND/TEST1.docx',
                  'content_kind': 'user_copy', 'archive_name': 'НД.rar',
                  'verification_note': 'В самом документе указаны КонсультантПлюс и дата сохранения 01.10.2026.',
                  'edition_from_document': 'ред. от 01.02.2026; дата сохранения в документе 01.10.2026'}
        with patch('knowledge.clean_text', lambda text: (text, 0)):  # установка RC1: очистки ещё нет
            write_docx(self.file, [PLAQUE, NOTE, ARTICLE, NOTE_ON_ARTICLE_3, ARTICLE_3])
            original = hashlib.sha256(self.file.read_bytes()).hexdigest()
            self.manifest(dict(record, sha256=original))
            catalog = NormativeCatalog(self.store.root)
            self.assertEqual(catalog.seed()['errors'], [])
            catalog.authorize_uploaded_corpus()
        with sqlite3.connect(catalog.kb.db_path) as db:
            db.execute('DROP TABLE kb_maintenance')  # в базе RC1 этой таблицы нет
        sid = catalog.records()[0]['imported_text_source_id']
        catalog.kb.update_source(sid, True, True, edition=record['edition_from_document'])
        with sqlite3.connect(catalog.kb.db_path) as db:
            before = dict(db.execute('SELECT location,id FROM kb_chunks WHERE source_id=?', (sid,)).fetchall())
        note_id = before['DOCX блок 4 (таблица), фрагмент 1']
        situations = SituationStore(self.store.root)
        situations.save_requirement('Ст. 3', 'Общие вопросы', 'ст. 3', 'Освидетельствование', sid, note_id, reviewed=True)
        # Новая версия комплекта: служебные блоки заменены пустыми абзацами.
        write_docx(self.file, ['<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Федеральный закон от 01.01.2000 N 1-ФЗ (ред. от 01.02.2026) "О трубопроводах"</w:t></w:r></w:p></w:tc></w:tr></w:tbl>',
                               '<w:p/>', ARTICLE, '<w:p/>', ARTICLE_3])
        self.manifest(dict(record, sha256=hashlib.sha256(self.file.read_bytes()).hexdigest(), original_sha256=original,
                           legacy_edition=record['edition_from_document'], edition_from_document='ред. от 01.02.2026 (по заголовку документа)',
                           verification_note='Редакция взята из заголовка документа.', service_text_removed='Служебные надписи удалены.'))
        result = NormativeCatalog(self.store.root).seed()
        self.assertEqual((result['local_texts_upgraded'], result['cards_refreshed'], result['errors']), (1, 1, []))
        source = next(s for s in catalog.kb.sources() if s['id'] == sid)
        self.assertEqual((source['reviewed'], source['active'], source['retrieval_authorized']), (1, 1, 1))
        self.assertEqual(source['edition'], 'ред. от 01.02.2026 (по заголовку документа)')
        with sqlite3.connect(catalog.kb.db_path) as db:
            after = dict(db.execute('SELECT location,id FROM kb_chunks WHERE source_id=?', (sid,)).fetchall())
            texts = [r[0] for r in db.execute('SELECT text FROM kb_chunks')]
            provenance = db.execute("SELECT provenance FROM normative_catalog WHERE act_id='TEST1'").fetchone()[0]
        for location in ('DOCX блок 1 (таблица), фрагмент 1', 'DOCX блок 3 (абзац), фрагмент 1', 'DOCX блок 5 (абзац), фрагмент 1'):
            self.assertEqual(after[location], before[location])
        self.assertNotIn('DOCX блок 2 (таблица), фрагмент 1', after)
        self.assertEqual(after['DOCX блок 4 (таблица), фрагмент 1'], note_id)
        self.assertIn(REMOVED_MARK, texts)
        self.assertFalse(any(contains_brand(t) for t in texts))
        self.assertFalse(contains_brand(provenance))
        self.assertEqual(situations.requirements()[0]['chunk_id'], note_id)
        self.assertEqual(catalog.kb.search('КонсультантПлюс', include_unreviewed=True), [])
        self.assertEqual(len(catalog.kb.search('освидетельствованию')), 1)
        self.assertEqual(sorted(p.name for p in (self.store.root / 'files').iterdir()),
                         sorted(s['stored_name'] for s in catalog.kb.sources()))
        again = NormativeCatalog(self.store.root).seed()
        self.assertEqual((again['local_texts_upgraded'], again['cards_refreshed']), (0, 0))


@unittest.skipUnless(importlib.util.find_spec('lxml'), 'lxml не установлен: инструмент сборки не проверен')
class DocxToolTests(unittest.TestCase):
    def test_tool_removes_brand_and_preserves_blocks(self):
        import sys
        sys.path.insert(0, str(BASE / 'tools'))
        from clean_docx_service import clean_file
        with tempfile.TemporaryDirectory() as tmp:
            source = write_docx(Path(tmp) / 'in.docx', [PLAQUE, NOTE, ARTICLE])
            report = clean_file(source, Path(tmp) / 'out.docx')
            self.assertEqual((report['residual'], report['partial']), ([], []))
            kb = KnowledgeBase(Path(tmp) / 'data')
            old, _ = kb._extract(source, False, 'rus')
            new, _ = kb._extract(Path(tmp) / 'out.docx', False, 'rus')
            self.assertEqual(old, new)
            with zipfile.ZipFile(Path(tmp) / 'out.docx') as archive:
                self.assertNotIn('Консультант', archive.read('word/document.xml').decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
