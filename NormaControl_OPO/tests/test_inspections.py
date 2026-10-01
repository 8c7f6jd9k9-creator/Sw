import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from core import Store

BASE=Path(__file__).resolve().parents[1]

class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.store=Store(self.root/'data',BASE/'registry.json'); self.plan=self.store.cauk_plans()[0]['id']
        self.source=self.root/'evidence.txt'; self.source.write_text('Подтверждающий документ',encoding='utf-8')
    def tearDown(self): self.store.close(); self.temp.cleanup()
    def check(self,asset,no): return next(c for c in self.store.cauk_checks(self.plan,asset) if c['question_no']==no)
    def test_complete_structure(self):
        self.assertEqual(self.store.cauk_plans()[0]['name'],'октябрь 2026')
        self.assertEqual(len(self.store.cauk_members(self.plan)),33)
        self.assertEqual(len(self.store.cauk_checks(self.plan)),330)
        for asset in self.store.assets(): self.assertEqual([c['question_no'] for c in self.store.cauk_checks(self.plan,asset['seq'])],list(range(1,11)))
        self.assertEqual(self.store.cauk_summary(self.plan)['unresolved'],330)
    def test_applicability_uses_known_conditions(self):
        self.assertEqual(self.check(5,1)['applicability'],'Применим'); self.assertFalse(self.check(5,1)['confirmed'])
        self.assertEqual(self.check(19,1)['applicability'],'Уточнить')
        for asset in self.store.assets():
            for no in (2,3,5,6,9,10): self.assertEqual(self.check(asset['seq'],no)['applicability'],'Уточнить')
            for no in (4,7,8): self.assertEqual(self.check(asset['seq'],no)['scope'],'organization')
        q9=self.check(19,9)
        for token in ('169926','189114','29.09.2025','09.03.2026'): self.assertIn(token,q9['text'])
    def test_unjustified_exclusion_and_false_completion_rejected(self):
        cid=self.check(1,2)['id']
        for app,confirmed,reason,state,answer in [('Не применим',False,'нет','Не начат',''),('Не применим',True,'','Не начат',''),('Уточнить',True,'проверено','Не начат',''),('Уточнить',False,'','Подготовлено','проверено'),('Применим',True,'есть оборудование','Подготовлено','проверено')]:
            with self.assertRaises(ValueError): self.store.update_cauk_check(cid,app,confirmed,reason,state,answer,'','')
        self.store.update_cauk_check(cid,'Не применим',True,'Перечень оборудования проверен: оборудование с указанным условием отсутствует.','Не начат','','Антон','')
        self.assertEqual(self.store.cauk_summary(self.plan)['excluded'],1)
    def test_answer_evidence_and_restart(self):
        cid=self.check(5,1)['id']; evidence=self.store.add_cauk_evidence(cid,self.source)
        self.store.update_cauk_check(cid,'Применим',True,'Фонд скважин подтверждён по составу ОПО.','Подготовлено','Материалы подготовлены.','Исполнитель','09.10.2026')
        self.assertEqual(self.store.cauk_evidence(cid)[0]['sha256'],hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.source.unlink(); self.assertTrue(self.store.cauk_evidence_path(evidence).is_file())
        self.store.close(); self.store=Store(self.root/'data',BASE/'registry.json')
        self.assertEqual(len(self.store.cauk_checks(self.plan)),330)
        self.assertEqual(self.store.cauk_check(cid)['answer'],'Материалы подготовлены.')
        self.assertEqual(self.store.cauk_summary(self.plan)['prepared'],1)
        self.store.cauk_evidence_path(evidence).unlink()
        self.assertEqual(self.store.cauk_summary(self.plan)['prepared'],0)
    def test_common_document_can_be_reused_without_copy(self):
        doc=self.store.add_document(1,self.source,'Общая концепция')
        for asset in (1,19,33): self.store.link_cauk_document(self.check(asset,4)['id'],doc)
        self.assertEqual(len(list((self.store.root/'files').iterdir())),1)
        for asset in (1,19,33): self.assertEqual(self.store.cauk_evidence(self.check(asset,4)['id'])[0]['document_id'],doc)
        with self.assertRaises(ValueError): self.store.link_cauk_document(self.check(19,2)['id'],doc)
        self.store.link_cauk_document(self.check(1,4)['id'],doc)
        self.assertEqual(len(self.store.cauk_evidence(self.check(1,4)['id'])),1)
    def test_backup_restores_checks_and_evidence(self):
        cid=self.check(19,9)['id']; eid=self.store.add_cauk_evidence(cid,self.source)
        self.store.update_cauk_check(cid,'Применим',True,'Объект указан в материалах расследования (тестовое основание).','Есть замечания','Проверить выполнение мероприятия.','Исполнитель','08.10.2026')
        backup=self.root/'backup.zip'; self.store.backup(backup)
        with zipfile.ZipFile(backup) as z: z.extractall(self.root/'restore')
        restored=Store(self.root/'restore')
        try:
            self.assertEqual(restored.cauk_check(cid)['work_status'],'Есть замечания')
            self.assertEqual(restored.cauk_evidence_path(eid).read_bytes(),self.source.read_bytes())
            self.assertEqual(len(restored.cauk_checks(self.plan)),330)
        finally: restored.close()
    def test_report_includes_all_assets_and_unresolved_conditions(self):
        cid=self.check(1,9)['id']
        self.store.update_cauk_check(cid,'Уточнить',False,'<script>','В работе','<b>','Имя','')
        out=self.root/'cauk.html'; self.store.cauk_report(self.plan,out); text=out.read_text(encoding='utf-8')
        self.assertEqual(text.count('<h2>'),33); self.assertEqual(text.count('<h3>'),330)
        self.assertIn('169926',text); self.assertIn('октябрь 2026',text)
        self.assertNotIn('<script>',text); self.assertIn('&lt;script&gt;',text)
        self.assertIn('предварительно / требуется решение',text)
    def test_members_are_snapshot_and_migration_not_reseeded(self):
        original=self.store.cauk_members(self.plan)[0]['name']
        with self.store.db: self.store.db.execute('UPDATE assets SET name=? WHERE seq=1',('Новое название после проверки',))
        self.assertEqual(self.store.cauk_members(self.plan)[0]['name'],original)
        cid=self.check(1,2)['id']; self.store.update_cauk_check(cid,'Уточнить',False,'Сохранённое условие','В работе','Результат','А','')
        self.store.init_cauk(); self.assertEqual(self.store.cauk_check(cid)['reason'],'Сохранённое условие')
        self.assertEqual(len(self.store.cauk_plans()),1)
    def test_missing_file_prevents_prepared(self):
        cid=self.check(1,4)['id']; eid=self.store.add_cauk_evidence(cid,self.source)
        self.store.cauk_evidence_path(eid).unlink()
        with self.assertRaises(ValueError): self.store.update_cauk_check(cid,'Применим',True,'Основание','Подготовлено','Проверено','А','')

if __name__=='__main__': unittest.main()
