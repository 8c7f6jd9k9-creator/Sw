import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from core import Store
from situations import SituationStore, CATEGORIES
from pypdf import PdfReader
from PIL import Image
BASE=Path(__file__).resolve().parents[1]

class SituationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.store=Store(self.root/'data', BASE/'registry.json')
        self.s=SituationStore(self.store.root)
        path=self.root/'source.txt'
        path.write_text('Трубопровод ремонт безопасность огневые работы',encoding='utf-8')
        self.source=self.s.kb.import_file(path)
        with self.s._db() as db:
            self.chunk=db.execute('SELECT id FROM kb_chunks WHERE source_id=?',(self.source,)).fetchone()[0]
    def tearDown(self):
        self.store.close(); self.temp.cleanup()
    def case(self,description='Трубопровод ремонт'):
        return self.s.save('Наблюдение',None,CATEGORIES[3],'Участок',description)
    def test_human_decision_and_edit_invalidation_with_audit(self):
        sid=self.case()
        self.assertEqual(self.s.get(sid)['risk'],'unknown')
        with self.assertRaises(ValueError): self.s.decide(sid,'high','','Решение')
        with self.assertRaises(ValueError): self.s.decide(sid,'high','Иванов','Решение',True)
        self.s.decide(sid,'high','Иванов','Обоснование')
        self.s.decide(sid,'high','Иванов','Обоснование',True)
        self.assertEqual(self.s.get(sid)['status'],'closed')
        self.s.save('Наблюдение',None,CATEGORIES[3],'Участок','Трубопровод ремонт',sid)
        self.assertEqual(self.s.get(sid)['status'],'closed')
        self.s.save('Изменено',None,CATEGORIES[3],'Участок','Трубопровод ремонт',sid)
        self.assertEqual(self.s.get(sid)['risk'],'unknown')
        with self.s._db() as db:
            self.assertGreater(db.execute('SELECT COUNT(*) FROM nc_audit').fetchone()[0],3)
    def test_authorization_is_separate_from_review(self):
        self.assertEqual(self.s.analyze(self.case()),[])
        with self.s._db() as db: db.execute('UPDATE kb_sources SET retrieval_authorized=1 WHERE id=?',(self.source,))
        self.assertTrue(self.s.analyze(self.case()))
        self.assertEqual(self.s.analyze(self.case(),include_authorized=False),[])
        self.assertFalse(self.s.kb.sources()[0]['reviewed'])
    def test_real_links_and_category_without_words_not_a_match(self):
        with self.assertRaises(ValueError):
            self.s.save_requirement('Правило',CATEGORIES[3],'1','Трубопровод',self.source,self.chunk+999)
        self.s.save_requirement('Правило',CATEGORIES[3],'1','Трубопровод',self.source,self.chunk,reviewed=True)
        self.assertEqual(self.s.analyze(self.case('Несвязанное наблюдение')),[])
        found=self.s.analyze(self.case())
        self.assertEqual(found[0]['kind'],'reviewed_requirement')
        self.assertEqual(found[0]['id'],self.chunk)
    def test_csv_atomic_and_review_not_trusted(self):
        fields=['title','category','clause','text','source_id','chunk_id','reviewed']
        path=self.root/'requirements.csv'
        valid=['Правило',CATEGORIES[3],'1','Трубопровод',self.source,self.chunk,'1']
        with path.open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f); w.writerow(fields); w.writerow(valid); w.writerow(valid[:5]+[999999,'1'])
        with self.assertRaises(ValueError): self.s.import_requirements_csv(path)
        self.assertEqual(self.s.requirements(),[])
        with path.open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f); w.writerow(fields); w.writerow(valid)
        self.assertEqual(self.s.import_requirements_csv(path),1)
        self.assertFalse(self.s.requirements()[0]['reviewed'])
    def test_reports_escape_text_include_photo_and_persist_material(self):
        sid=self.case('<script>Трубопровод & ремонт</script>')
        photo=self.root/'photo.png'; Image.new('RGB',(80,60),'green').save(photo)
        mid=self.s.attach(sid,photo); self.assertEqual(mid,self.s.attach(sid,photo))
        photo.unlink(); self.assertTrue(self.s.material_path(mid).is_file())
        self.s.export_report(sid,self.root/'report.html')
        self.assertIn('&lt;script&gt;', (self.root/'report.html').read_text())
        self.s.export_report(sid,self.root/'report.pdf')
        pdf=PdfReader(self.root/'report.pdf')
        self.assertIn('НормаКонтроль',pdf.pages[0].extract_text())
        self.assertGreaterEqual(len(pdf.pages),2)
        self.assertTrue(any(page.images for page in pdf.pages))
    def test_curated_source_scope_dates_and_archive_respected(self):
        self.s.save_requirement('Правило',CATEGORIES[3],'1','Трубопровод',self.source,self.chunk,reviewed=True)
        with self.s._db() as db: db.execute('UPDATE kb_sources SET valid_to=? WHERE id=?',('2000-01-01',self.source))
        self.assertEqual(self.s.analyze(self.case()),[])
        with self.s._db() as db: db.execute('UPDATE kb_sources SET valid_to="",asset_id=19 WHERE id=?',(self.source,))
        self.assertEqual(self.s.analyze(self.case()),[])
        with self.s._db() as db: db.execute('UPDATE kb_sources SET asset_id=NULL,active=0 WHERE id=?',(self.source,))
        self.assertEqual(self.s.analyze(self.case(),True),[])

    def test_new_material_invalidates_decision_but_duplicate_does_not(self):
        sid=self.case()
        self.s.decide(sid,'high','Иванов','Решение')
        path=self.root/'material.txt';path.write_text('Новое доказательство',encoding='utf-8')
        mid=self.s.attach(sid,path)
        self.assertEqual(self.s.get(sid)['risk'],'unknown')
        self.s.decide(sid,'medium','Иванов','Повторная проверка')
        self.assertEqual(self.s.attach(sid,path),mid)
        self.assertEqual(self.s.get(sid)['risk'],'medium')
