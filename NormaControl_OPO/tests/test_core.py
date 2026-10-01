import hashlib
import json
import sqlite3
import tempfile
import unittest
import zipfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from core import Store, document_status

BASE=Path(__file__).resolve().parents[1]

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.store=Store(self.root/'data',BASE/'registry.json')
        self.source=self.root/'document.txt'; self.source.write_text('Документ для функциональной проверки',encoding='utf-8')
    def tearDown(self): self.store.close(); self.temp.cleanup()
    def test_registry_and_reopen(self):
        rows=self.store.assets(); self.assertEqual(len(rows),33)
        self.assertEqual(Counter(r['danger_class'] for r in rows),{1:4,2:9,3:18,4:2})
        self.assertEqual({r['reg_no'] for r in rows if r['signs']!='2.1'},{'А59-50115-0040'})
        self.assertEqual(self.store.asset(19)['signs'],'2.1; 2.2 (а)')
        self.store.update_asset(19,'Антон','Сверено',True)
        self.store.close(); self.store=Store(self.root/'data',BASE/'registry.json')
        self.assertEqual(len(self.store.assets()),33); self.assertEqual(self.store.asset(19)['owner'],'Антон')
    def test_date_boundaries(self):
        today=date(2026,10,1)
        for days,expected in [(-1,'expired'),(0,'due30'),(30,'due30'),(31,'due60'),(60,'due60'),(61,'current')]:
            self.assertEqual(document_status((today+timedelta(days=days)).strftime('%d.%m.%Y'),False,today),expected)
        self.assertEqual(document_status('',False,today),'unknown')
        self.assertEqual(document_status('',True,today),'permanent')
        with self.assertRaises(ValueError): document_status('31.02.2026',False,today)
    def test_file_copy_and_digest(self):
        doc=self.store.add_document(1,self.source,'Тест')
        self.assertEqual(self.store.document_path(doc).read_bytes(),self.source.read_bytes())
        row=self.store.documents(1)[0]; self.assertEqual(row['sha256'],hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.source.unlink(); self.assertTrue(self.store.document_path(doc).is_file())
    def test_completeness_unknown_review_archive(self):
        today=date(2026,10,1); req=self.store.add_requirement(1,'Тест','Внутренний перечень пользователя')
        self.assertEqual(self.store.completeness(1,today)[0][1],'Не загружен')
        doc=self.store.add_document(1,self.source,'Тест',reviewed=True,requirement_id=req)
        self.assertIn('проверить',self.store.completeness(1,today)[0][1])
        self.store.supersede(doc)
        doc=self.store.add_document(1,self.source,'Тест',expiry='01.10.2026',reviewed=True,requirement_id=req)
        self.assertIn('срок не истёк',self.store.completeness(1,today)[0][1])
        self.store.document_path(doc).unlink()
        self.assertIn('проверить',self.store.completeness(1,today)[0][1])
        self.store.supersede(doc)
        self.assertEqual(self.store.completeness(1,today)[0][1],'Не загружен')
    def test_cross_asset_requirement_and_invalid_dates(self):
        req=self.store.add_requirement(2,'Тест','Основание')
        for options in [dict(requirement_id=req),dict(issued='03.10.2026',expiry='01.10.2026'),dict(permanent=True,expiry='01.10.2026'),dict(expiry='31.02.2026')]:
            with self.assertRaises(ValueError): self.store.add_document(1,self.source,'Тест',**options)
        self.assertEqual(len(self.store.documents(1)),0); self.assertEqual(list((self.store.root/'files').iterdir()),[])
    def test_expired_unreviewed_unlinked(self):
        req=self.store.add_requirement(1,'Тест','Основание'); today=date(2026,10,1)
        self.store.add_document(1,self.source,'Тест',permanent=True,reviewed=True)
        self.assertEqual(self.store.completeness(1,today)[0][1],'Не загружен')
        self.store.add_document(1,self.source,'Тест',expiry='30.09.2026',reviewed=True,requirement_id=req)
        self.store.add_document(1,self.source,'Тест',expiry='31.12.2026',reviewed=False,requirement_id=req)
        self.assertIn('проверить',self.store.completeness(1,today)[0][1])
    def test_backup_restores_database_and_files(self):
        doc=self.store.add_document(19,self.source,'Резервирование'); backup=self.root/'backup.zip'
        self.store.backup(backup); restored=self.root/'restored'
        with zipfile.ZipFile(backup) as archive: archive.extractall(restored)
        other=Store(restored)
        try:
            self.assertEqual(len(other.assets()),33)
            self.assertEqual(other.document_path(doc).read_bytes(),self.source.read_bytes())
            self.assertEqual(other.documents(19)[0]['title'],'Резервирование')
        finally: other.close()
        with self.assertRaises(ValueError): self.store.backup(self.store.root/'invalid.zip')
    def test_report_escaping_and_unknown_completeness(self):
        self.store.add_requirement(1,'<script>alert(1)</script>','Ручной перечень')
        self.store.add_document(1,self.source,'Тест <b>',expiry='30.09.2026')
        out=self.root/'report.html'; self.store.report(out,date(2026,10,1)); text=out.read_text(encoding='utf-8')
        self.assertNotIn('<script>',text); self.assertIn('&lt;script&gt;',text)
        self.assertIn('Полнота не оценена',text); self.assertIn('Просрочен',text)
        self.assertIn('не заключение о соответствии',text)

if __name__=='__main__': unittest.main()
