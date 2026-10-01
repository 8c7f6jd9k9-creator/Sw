import json
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path

from core import Store
from knowledge import KnowledgeBase
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

BASE = Path(__file__).resolve().parents[1]


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'data', BASE / 'registry.json')
        self.kb = KnowledgeBase(self.store.root)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def txt(self, name, text):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return path

    def image(self):
        image = Image.new('RGB', (1400, 300), 'white')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(str(BASE / 'resources' / 'DejaVuSans.ttf'), 55)  # шрифт комплекта: есть и на Windows
        draw.text((50, 80), 'PIPELINE SAFETY CHECK 2026', font=font, fill='black')
        path = self.root / 'scan.png'
        image.save(path)
        return path

    def test_txt_checked_scope_and_injection(self):
        global_id = self.kb.import_file(self.txt('global.txt', 'Проверка трубопровода глобальный'), reviewed=True)
        asset_id = self.kb.import_file(self.txt('asset.txt', 'Проверка трубопровода локальный'), asset_id=19, reviewed=True)
        pending_id = self.kb.import_file(self.txt('pending.txt', 'Проверка трубопровода непроверенный'))
        self.assertEqual({r['source_id'] for r in self.kb.search('трубопровода', 19)}, {global_id, asset_id})
        self.assertEqual({r['source_id'] for r in self.kb.search('трубопровода', 1)}, {global_id})
        self.assertIn(pending_id, {r['source_id'] for r in self.kb.search('трубопровода', include_unreviewed=True)})
        self.kb.search("'\"; DROP TABLE kb_sources; -- OR *")
        self.assertEqual(len(self.kb.sources()), 3)

    def test_docx_paragraph_table_and_truthful_location(self):
        path = self.root / 'document.docx'
        xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Абзац трубопровода</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Таблица трубопровода</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'''
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('word/document.xml', xml)
        sid = self.kb.import_file(path, reviewed=True)
        matches = self.kb.search('трубопровода')
        self.assertEqual(len(matches), 2)
        self.assertTrue(all(m['page'] is None for m in matches))
        self.assertTrue(any('таблица' in m['location'] for m in matches))
        self.assertTrue(any('абзац' in m['location'] for m in matches))
        self.assertEqual({m['source_id'] for m in matches}, {sid})

    def test_real_pdf_page_text_and_exact_citations(self):
        path = self.root / 'text.pdf'
        pdf = canvas.Canvas(str(path))
        pdf.drawString(40, 700, 'PIPELINE safety first page')
        pdf.showPage()
        pdf.drawString(40, 700, 'PIPELINE safety second page')
        pdf.save()
        sid = self.kb.import_file(path, reviewed=True, edition='2026', source_url='https://example.test/reference')
        matches = self.kb.search('PIPELINE')
        self.assertEqual({r['page'] for r in matches}, {1, 2})
        context = self.kb.context('PIPELINE')
        for match in matches:
            self.assertIn('[К{}-Ф{}]'.format(sid, match['id']), context)
            self.assertIn(match['text'], context)
        self.assertIn('2026', context)
        self.assertIn('https://example.test/reference', context)

    def test_actual_image_and_scanned_pdf_ocr_eng(self):
        diagnostics = self.kb.diagnostics()
        if not diagnostics['eng_available']:
            self.skipTest('Tesseract eng unavailable; actual OCR not verified')
        image = self.image()
        sid = self.kb.import_file(image, reviewed=True, ocr_lang='eng')
        self.assertEqual(self.kb.search('PIPELINE')[0]['source_id'], sid)
        if not diagnostics['pypdfium2']:
            self.skipTest('pypdfium2 unavailable; scanned PDF not verified')
        path = self.root / 'scanned.pdf'
        pdf = canvas.Canvas(str(path), pagesize=(700, 150))
        pdf.drawImage(ImageReader(str(image)), 0, 0, width=700, height=150)
        pdf.save()
        sid = self.kb.import_file(path, reviewed=True, ocr_lang='eng')
        matches = self.kb.search('PIPELINE')
        self.assertTrue(any(r['source_id'] == sid and r['page'] == 1 for r in matches))
        self.assertIn('OCR', next(s['extraction_notes'] for s in self.kb.sources() if s['id'] == sid))

    def test_missing_russian_language_reports_truthfully(self):
        if self.kb.diagnostics()['rus_available']:
            self.skipTest('Russian language is installed; missing-language case not applicable')
        with self.assertRaisesRegex(ValueError, 'rus'):
            self.kb.import_file(self.image())
        source = self.kb.sources()[0]
        self.assertEqual(source['status'], 'error')
        self.assertIn('rus', source['extraction_notes'])
        self.assertEqual(self.kb.search('PIPELINE', include_unreviewed=True), [])

    def test_version_archive_dates_and_no_invalid_reindex(self):
        path = self.txt('rules.txt', 'Устойчивость трубопровода')
        current = self.kb.import_file(path, reviewed=True, edition='new')
        old = self.kb.import_file(path, reviewed=True, edition='old', valid_to=(date.today()-timedelta(days=1)).isoformat())
        future = self.kb.import_file(path, reviewed=True, edition='future', valid_from=(date.today()+timedelta(days=1)).isoformat())
        self.assertEqual({r['source_id'] for r in self.kb.search('Устойчивость')}, {current})
        self.kb.update_source(current, True, False, edition='new')
        self.assertEqual(self.kb.search('Устойчивость'), [])
        for args in (dict(valid_from='31.02.2026'), dict(valid_from='2026-10-02', valid_to='2026-10-01')):
            with self.assertRaises(ValueError):
                self.kb.import_file(path, **args)
        self.assertEqual({s['id'] for s in self.kb.sources()}, {current, old, future})

    def test_registered_documents_archive_persistence_and_backup(self):
        path = self.txt('registered.txt', 'Зарегистрированный трубопровод')
        doc = self.store.add_document(19, path, 'Тестовый документ', reviewed=True)
        self.assertEqual(self.kb.index_registered_documents(19)['count'], 1)
        sid = self.kb.search('Зарегистрированный', 19)[0]['source_id']
        self.store.supersede(doc)
        self.assertEqual(self.kb.search('Зарегистрированный', 19), [])
        self.assertEqual(self.kb.index_registered_documents(19)['count'], 0)
        extra = self.kb.import_file(self.txt('kept.txt', 'Сохраняемый источник'), reviewed=True)
        self.assertEqual(KnowledgeBase(self.store.root).search('Сохраняемый')[0]['source_id'], extra)
        backup = self.root / 'backup.zip'
        self.store.backup(backup)
        restored = self.root / 'restored'
        with zipfile.ZipFile(backup) as archive:
            archive.extractall(restored)
        other = KnowledgeBase(restored)
        self.assertEqual(other.search('Сохраняемый')[0]['source_id'], extra)
        self.assertEqual(other.open_path(extra).read_text(encoding='utf-8'), 'Сохраняемый источник')
        self.assertEqual(other.search('Зарегистрированный', 19), [])
        self.assertTrue(self.kb.open_path(sid).is_file())

    def test_direct_cauk_evidence_index_and_missing_registered_file_errors(self):
        plan = self.store.cauk_plans()[0]['id']
        check = self.store.cauk_checks(plan, 19)[0]['id']
        evidence = self.store.add_cauk_evidence(check, self.txt('evidence.txt', 'CAUK EVIDENCE UNIQUE'))
        result = self.kb.index_registered_documents(19)
        self.assertEqual(result['errors'], [])
        self.assertTrue(self.kb.search('UNIQUE', 19, include_unreviewed=True))
        self.assertEqual(self.kb.search('UNIQUE', 19), [])
        self.assertEqual(self.kb.search('UNIQUE', 1, include_unreviewed=True), [])
        doc = self.store.add_document(19, self.txt('missing.txt', 'MISSING'), 'Отсутствующий файл', reviewed=True)
        self.store.document_path(doc).unlink()
        errors = self.kb.index_registered_documents(19)['errors']
        self.assertTrue(any('Документ #' + str(doc) in error for error in errors))
        sid = self.kb.sources()[0]['id']
        self.kb.open_path(sid).unlink()
        with self.assertRaisesRegex(ValueError, 'отсутствует'):
            self.kb.open_path(sid)

    def test_diagnostics_real_dependencies_and_missing_source(self):
        import importlib.util
        import shutil
        d = self.kb.diagnostics()
        self.assertEqual(d['tesseract'], bool(shutil.which('tesseract')))
        self.assertEqual(d['pypdf'], importlib.util.find_spec('pypdf') is not None)
        self.assertEqual(d['pypdfium2'], importlib.util.find_spec('pypdfium2') is not None)
        self.assertIn('не проверено', self.kb.context('unknown'))
        with self.assertRaises(ValueError):
            self.kb.open_path(999)


if __name__ == '__main__':
    unittest.main()
