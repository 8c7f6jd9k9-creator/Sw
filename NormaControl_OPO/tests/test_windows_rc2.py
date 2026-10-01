"""RC2: резервная копия и восстановление, фото в PDF, окно по размеру экрана, прогресс индексации."""
import json
import tempfile
import tkinter as tk
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader

from core import Store, restore_backup, verify_backup
from regulations import NormativeCatalog
from situations import CATEGORIES, SituationStore
import ui_scale

BASE = Path(__file__).resolve().parents[1]


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'data', BASE / 'registry.json')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_backup_is_verified_and_restores_into_empty_folder_only(self):
        doc = self.root / 'permit.txt'
        doc.write_text('Разрешение', encoding='utf-8')
        self.store.add_document(1, doc, 'Разрешение', reviewed=True)
        target = self.root / 'out' / 'backup.zip'
        target.parent.mkdir()
        result = self.store.backup(target)
        self.assertEqual((result['integrity'], result['files'], result['missing_files']), ('ok', 1, []))
        self.assertEqual([p.name for p in target.parent.iterdir()], ['backup.zip'])  # временный файл удалён
        restored = self.root / 'restored'
        self.assertEqual(restore_backup(target, restored)['counts']['documents'], 1)
        copy = Store(restored, BASE / 'registry.json')
        try:
            self.assertEqual(len(copy.documents(1)), 1)
            self.assertTrue(copy.document_path(copy.documents(1)[0]['id']).is_file())
        finally:
            copy.close()
        with self.assertRaises(ValueError):
            restore_backup(target, restored)
        broken = self.root / 'out' / 'broken.zip'
        with zipfile.ZipFile(broken, 'w') as archive:
            archive.writestr('files/x.txt', 'x')
        with self.assertRaises(ValueError):
            verify_backup(broken)

    def test_failed_backup_keeps_previous_copy(self):
        target = self.root / 'backup.zip'
        target.write_bytes(b'previous')
        with patch('core.verify_backup', side_effect=ValueError('сбой')):
            with self.assertRaises(ValueError):
                self.store.backup(target)
        self.assertEqual(target.read_bytes(), b'previous')
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.is_file()), ['backup.zip'])


class PhotoReportTests(unittest.TestCase):
    def test_phone_photo_rotated_by_exif_and_downscaled_original_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / 'data', BASE / 'registry.json')
            try:
                situations = SituationStore(store.root)
                sid = situations.save('Фото', None, CATEGORIES[3], 'Участок', 'Трубопровод')
                photo = root / 'phone.jpg'
                exif = Image.Exif()
                exif[0x0112] = 6  # снимок телефона: повернуть на 90°
                Image.new('RGB', (3000, 1500), 'gray').save(photo, exif=exif.tobytes())
                mid = situations.attach(sid, photo)
                prepared = SituationStore._pdf_photo(situations.material_path(mid), root)
                with Image.open(prepared) as image:
                    self.assertEqual(image.size, (1000, 2000))
                with Image.open(situations.material_path(mid)) as original:
                    self.assertEqual(original.size, (3000, 1500))
                situations.export_report(sid, root / 'report.pdf')
                self.assertTrue(any(page.images for page in PdfReader(root / 'report.pdf').pages))
            finally:
                store.close()


class WindowFitTests(unittest.TestCase):
    def setUp(self):
        try:
            self.tk = tk.Tk()
        except tk.TclError as exc:
            self.skipTest('Нет графического дисплея: ' + str(exc))
        self.tk.withdraw()

    def tearDown(self):
        self.tk.destroy()

    def test_window_never_exceeds_work_area(self):
        with patch('ui_scale.work_area', return_value=(0, 0, 1366, 728)), patch('ui_scale.factor', return_value=1.0):
            state, width, height = ui_scale.fit_window(self.tk, 1380, 850, 1000, 680)
        self.assertEqual(state, 'normal')
        self.assertLessEqual(width, 1366)
        self.assertLessEqual(height, 728 - 40)
        with patch('ui_scale.work_area', return_value=(0, 0, 2560, 1400)), patch('ui_scale.factor', return_value=1.5):
            state, width, height = ui_scale.fit_window(self.tk, 1380, 850)
        self.assertEqual((width, height), (2070, 1275))


class SeedProgressTests(unittest.TestCase):
    def test_progress_reported_for_every_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifests = Path(tmp) / 'package'
            manifests.mkdir()
            records = [{'id': 'A%d' % i, 'title': 'Акт %d' % i} for i in range(3)]
            for name in ('regulations_industrial.json', 'regulations_related.json', 'regulations_library.json', 'regulations_uploaded.json'):
                (manifests / name).write_text(json.dumps(records if name == 'regulations_industrial.json' else []), encoding='utf-8')
            calls = []
            with patch('regulations.BASE', manifests):
                NormativeCatalog(Path(tmp) / 'data').seed(progress=lambda i, n, title: calls.append((i, n)))
            self.assertEqual(calls, [(1, 3), (2, 3), (3, 3)])


if __name__ == '__main__':
    unittest.main()
