"""CAUK inspection tracking from the user's programme, not a legal rules engine."""
import hashlib
import html
import json
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

APPLICABILITY=('Применим','Не применим','Уточнить')
WORK_STATUS=('Не начат','В работе','Подготовлено','Есть замечания')

class InspectionStore:
    def init_cauk(self):
        seed_path=Path(__file__).with_name('cauk_questions.json')
        if not seed_path.is_file(): raise ValueError('Отсутствует cauk_questions.json. Распакуйте весь архив программы.')
        is_new=not self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='cauk_plans'").fetchone()
        if is_new and self.db.execute('SELECT 1 FROM assets LIMIT 1').fetchone():
            previous=self.root/'before_cauk_migration.sqlite3'
            if not previous.exists():
                backup=sqlite3.connect(previous)
                try: self.db.backup(backup)
                finally: backup.close()
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS cauk_plans(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, note TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cauk_members(plan_id INTEGER NOT NULL REFERENCES cauk_plans(id), asset_id INTEGER NOT NULL REFERENCES assets(seq), reg_no TEXT NOT NULL, name TEXT NOT NULL, danger_class INTEGER NOT NULL, signs TEXT NOT NULL, PRIMARY KEY(plan_id,asset_id));
        CREATE TABLE IF NOT EXISTS cauk_questions(plan_id INTEGER NOT NULL REFERENCES cauk_plans(id), no INTEGER NOT NULL, text TEXT NOT NULL, program_worker TEXT NOT NULL, condition TEXT NOT NULL, preparation TEXT NOT NULL, scope TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(plan_id,no));
        CREATE TABLE IF NOT EXISTS cauk_checks(id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL, asset_id INTEGER NOT NULL, question_no INTEGER NOT NULL, applicability TEXT NOT NULL DEFAULT 'Уточнить' CHECK(applicability IN ('Применим','Не применим','Уточнить')), confirmed INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '', work_status TEXT NOT NULL DEFAULT 'Не начат' CHECK(work_status IN ('Не начат','В работе','Подготовлено','Есть замечания')), answer TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '', deadline TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL DEFAULT '', UNIQUE(plan_id,asset_id,question_no), FOREIGN KEY(plan_id,asset_id) REFERENCES cauk_members(plan_id,asset_id), FOREIGN KEY(plan_id,question_no) REFERENCES cauk_questions(plan_id,no));
        CREATE TABLE IF NOT EXISTS cauk_evidence(id INTEGER PRIMARY KEY, check_id INTEGER NOT NULL REFERENCES cauk_checks(id), document_id INTEGER REFERENCES documents(id), original_name TEXT NOT NULL, stored_name TEXT NOT NULL DEFAULT '', sha256 TEXT NOT NULL DEFAULT '', added TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS cauk_document_link ON cauk_evidence(check_id,document_id) WHERE document_id IS NOT NULL;
        ''')
        if not self.db.execute('SELECT 1 FROM assets LIMIT 1').fetchone(): return
        questions=json.loads(seed_path.read_text(encoding='utf-8'))
        with self.db:
            cur=self.db.execute('INSERT OR IGNORE INTO cauk_plans(code,name,note,created) VALUES(?,?,?,?)',('cauk-october-2026','октябрь 2026','Вопросы 1–10: IMG_2002.jpeg и IMG_2003.jpeg. На IMG_2003 указано установочное совещание 09.10.2026, 14:00–15:00 (местное время). Полный период проверки на предоставленных фрагментах не указан.',datetime.now().isoformat(timespec='seconds')))
            if cur.rowcount==0: return
            plan_id=cur.lastrowid
            for q in questions:
                self.db.execute('INSERT INTO cauk_questions VALUES(?,?,?,?,?,?,?,?)',(plan_id,q['no'],q['text'],q['program_worker'],q['condition'],q['preparation'],q['scope'],q['source']))
            for asset in self.assets():
                self.db.execute('INSERT INTO cauk_members VALUES(?,?,?,?,?,?)',(plan_id,asset['seq'],asset['reg_no'],asset['name'],asset['danger_class'],asset['signs']))
                for q in questions:
                    app,reason=self.initial_applicability(asset,q)
                    self.db.execute('INSERT INTO cauk_checks(plan_id,asset_id,question_no,applicability,reason) VALUES(?,?,?,?,?)',(plan_id,asset['seq'],q['no'],app,reason))
            self.log('cauk_create','октябрь 2026: 33 ОПО × 10 вопросов; применимость предварительная')
    @staticmethod
    def initial_applicability(asset,question):
        n=question['no']
        if n==1 and 'фонд скважин' in asset['name'].casefold():
            return 'Применим','Предварительно: в наименовании ОПО указан фонд скважин. Подтвердить состав и границы объекта.'
        if question['scope']=='organization':
            return 'Применим','Предварительно: общий вопрос программы уровня ОГ/ПО. Подтвердить связь общих материалов и мер с данным объектом.'
        if n==1:
            return 'Уточнить','По наименованию нельзя подтвердить наличие скважин/кустовых площадок и охват этого объекта вопросом №1. Уточнить состав и объём проверки.'
        if n==9:
            return 'Уточнить','Установить связь ОПО с ID 169926 (29.09.2025) и ID 189114 (09.03.2026), включая исполнителей корректирующих мероприятий.'
        return 'Уточнить',question['condition']
    def cauk_plans(self): return self.db.execute('SELECT * FROM cauk_plans ORDER BY id').fetchall()
    def cauk_members(self,plan_id): return self.db.execute('SELECT * FROM cauk_members WHERE plan_id=? ORDER BY asset_id',(plan_id,)).fetchall()
    def cauk_checks(self,plan_id,asset_id=None):
        query='''SELECT c.*,q.text,q.program_worker,q.condition,q.preparation,q.scope,q.source,m.reg_no,m.name AS asset_name,m.danger_class,m.signs FROM cauk_checks c JOIN cauk_questions q ON q.plan_id=c.plan_id AND q.no=c.question_no JOIN cauk_members m ON m.plan_id=c.plan_id AND m.asset_id=c.asset_id WHERE c.plan_id=?'''
        args=[plan_id]
        if asset_id is not None: query+=' AND c.asset_id=?'; args.append(asset_id)
        return self.db.execute(query+' ORDER BY c.asset_id,c.question_no',args).fetchall()
    def cauk_check(self,check_id):
        return self.db.execute('''SELECT c.*,q.text,q.program_worker,q.condition,q.preparation,q.scope,q.source,m.reg_no,m.name AS asset_name FROM cauk_checks c JOIN cauk_questions q ON q.plan_id=c.plan_id AND q.no=c.question_no JOIN cauk_members m ON m.plan_id=c.plan_id AND m.asset_id=c.asset_id WHERE c.id=?''',(check_id,)).fetchone()
    def update_cauk_check(self,check_id,applicability,confirmed,reason,work_status,answer,owner,deadline):
        if self.cauk_check(check_id) is None: raise ValueError('Вопрос проверки не найден.')
        if applicability not in APPLICABILITY or work_status not in WORK_STATUS: raise ValueError('Неверное состояние вопроса.')
        if applicability=='Уточнить' and confirmed: raise ValueError('Применимость «Уточнить» нельзя подтвердить как окончательное решение.')
        if applicability=='Не применим' and (not confirmed or not reason.strip()): raise ValueError('Для исключения вопроса подтвердите решение и укажите основание неприменимости.')
        if confirmed and not reason.strip(): raise ValueError('Укажите основание подтверждённой применимости.')
        if work_status in ('Подготовлено','Есть замечания') and (applicability!='Применим' or not confirmed): raise ValueError('Сначала подтвердите применимость вопроса.')
        if work_status in ('Подготовлено','Есть замечания') and not answer.strip(): raise ValueError('Заполните результат / замечания и обоснование.')
        if applicability=='Не применим' and work_status!='Не начат': raise ValueError('Для неприменимого вопроса оставьте состояние «Не начат».')
        if work_status=='Подготовлено' and not any(self.cauk_evidence_path(item['id']).is_file() for item in self.cauk_evidence(check_id)):
            raise ValueError('Для состояния «Подготовлено» приложите или свяжите хотя бы один существующий файл подтверждения.')
        if deadline.strip(): datetime.strptime(deadline.strip(),'%d.%m.%Y')
        with self.db:
            self.db.execute('''UPDATE cauk_checks SET applicability=?,confirmed=?,reason=?,work_status=?,answer=?,owner=?,deadline=?,updated=? WHERE id=?''',(applicability,int(confirmed),reason.strip(),work_status,answer.strip(),owner.strip(),deadline.strip(),datetime.now().isoformat(timespec='seconds'),check_id))
            self.log('cauk_update',json.dumps(dict(check_id=check_id,applicability=applicability,confirmed=bool(confirmed),reason=reason,work_status=work_status,answer=answer,owner=owner,deadline=deadline),ensure_ascii=False))
    def cauk_evidence(self,check_id): return self.db.execute('SELECT * FROM cauk_evidence WHERE check_id=? ORDER BY id',(check_id,)).fetchall()
    def cauk_evidence_path(self,evidence_id):
        row=self.db.execute('SELECT * FROM cauk_evidence WHERE id=?',(evidence_id,)).fetchone()
        if row is None: raise ValueError('Вложение не найдено.')
        return self.document_path(row['document_id']) if row['document_id'] is not None else self.root/'files'/row['stored_name']
    def add_cauk_evidence(self,check_id,path):
        if self.cauk_check(check_id) is None: raise ValueError('Вопрос проверки не найден.')
        src=Path(path)
        if not src.is_file(): raise ValueError('Выберите существующий файл.')
        stored=uuid.uuid4().hex+src.suffix.lower(); target=self.root/'files'/stored
        try:
            shutil.copyfile(src,target); hasher=hashlib.sha256()
            with target.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''): hasher.update(block)
            with self.db:
                cur=self.db.execute('INSERT INTO cauk_evidence(check_id,original_name,stored_name,sha256,added) VALUES(?,?,?,?,?)',(check_id,src.name,stored,hasher.hexdigest(),datetime.now().isoformat(timespec='seconds')))
                self.log('cauk_evidence_add',f'check={check_id}; file={src.name}; SHA256={hasher.hexdigest()}')
            return cur.lastrowid
        except Exception:
            target.unlink(missing_ok=True); raise
    def cauk_linkable_documents(self,check_id):
        check=self.cauk_check(check_id)
        if check is None: raise ValueError('Вопрос проверки не найден.')
        if check['scope']=='organization':
            return self.db.execute('SELECT d.*,a.reg_no FROM documents d JOIN assets a ON a.seq=d.asset_id WHERE d.superseded=0 ORDER BY d.id DESC').fetchall()
        return self.db.execute('SELECT d.*,a.reg_no FROM documents d JOIN assets a ON a.seq=d.asset_id WHERE d.asset_id=? AND d.superseded=0 ORDER BY d.id DESC',(check['asset_id'],)).fetchall()
    def link_cauk_document(self,check_id,document_id):
        allowed={d['id'] for d in self.cauk_linkable_documents(check_id)}
        if document_id not in allowed: raise ValueError('Документ другого ОПО можно связать только с общим вопросом уровня организации. Архивные записи не связываются.')
        if not self.document_path(document_id).is_file(): raise ValueError('Файл документа отсутствует.')
        d=self.db.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone()
        with self.db:
            cur=self.db.execute('INSERT OR IGNORE INTO cauk_evidence(check_id,document_id,original_name,sha256,added) VALUES(?,?,?,?,?)',(check_id,document_id,d['original_name'],d['sha256'],datetime.now().isoformat(timespec='seconds')))
            if cur.rowcount: self.log('cauk_document_link',f'check={check_id}; document={document_id}')
    def cauk_summary(self,plan_id):
        checks=self.cauk_checks(plan_id)
        return dict(total=len(checks),applicable=sum(c['confirmed'] and c['applicability']=='Применим' for c in checks),excluded=sum(c['confirmed'] and c['applicability']=='Не применим' for c in checks),unresolved=sum(not c['confirmed'] or c['applicability']=='Уточнить' for c in checks),prepared=sum(c['work_status']=='Подготовлено' and c['confirmed'] and c['applicability']=='Применим' and any(self.cauk_evidence_path(e['id']).is_file() for e in self.cauk_evidence(c['id'])) for c in checks),issues=sum(c['work_status']=='Есть замечания' for c in checks))
    def cauk_report(self,plan_id,target):
        plan=self.db.execute('SELECT * FROM cauk_plans WHERE id=?',(plan_id,)).fetchone()
        if plan is None: raise ValueError('Проверка не найдена.')
        e=lambda value:html.escape(str(value)).replace('\n','<br>')
        parts=['<!doctype html><html lang="ru"><meta charset="utf-8"><title>Проверка ЦАУК</title><style>body{font:14px Arial;margin:28px;color:#183047}table{border-collapse:collapse;width:100%;margin-bottom:24px}td,th{border:1px solid #aabccc;padding:8px;vertical-align:top;text-align:left}h2{margin-top:30px}.note{background:#fff1cc;padding:12px}</style>',f'<h1>Проверки ЦАУК — {e(plan["name"])}</h1>',f'<p>{e(plan["note"])}</p>','<p class="note">Вопросы перенесены из программы пользователя. Условия применимости и список материалов — рабочие пояснения для подготовки. Предварительное распределение не заменяет подтверждение состава ОПО, работ и происшествий. «Подготовлено» — отметка пользователя, не заключение о соответствии.</p>']
        s=self.cauk_summary(plan_id)
        parts+=[f'<p>Вопросов: {s["total"]}; подтверждено применимых: {s["applicable"]}; исключено с основанием: {s["excluded"]}; требуют решения: {s["unresolved"]}; подготовлено: {s["prepared"]}; с замечаниями: {s["issues"]}.</p>']
        for member in self.cauk_members(plan_id):
            parts += [f'<h2>{e(member["reg_no"])} — {e(member["name"])}</h2>',f'<p>Класс {member["danger_class"]}; признаки {e(member["signs"])}. Снимок карточки при создании проверки.</p>']
            for c in self.cauk_checks(plan_id,member['asset_id']):
                evidence=self.cauk_evidence(c['id'])
                attachments='; '.join(e(item['original_name'])+(' [файл есть]' if self.cauk_evidence_path(item['id']).is_file() else ' [ФАЙЛ ОТСУТСТВУЕТ]') for item in evidence) or 'Не приложены'
                parts += [f'<h3>№{c["question_no"]}. {e(c["text"])}</h3>',f'<p>Источник: {e(c["source"])}. Ответственный работник по программе: {e(c["program_worker"])}.</p>',f'<p>Условие: {e(c["condition"])}</p>',f'<p>Применимость: <b>{e(c["applicability"])}</b> ({"подтверждено пользователем" if c["confirmed"] else "предварительно / требуется решение"}). Основание: {e(c["reason"])}</p>',f'<p>Состояние: {e(c["work_status"])}. Исполнитель подготовки: {e(c["owner"])}. Срок: {e(c["deadline"])}</p>',f'<p>Результат / замечания: {e(c["answer"])}</p>',f'<p>Материалы: {attachments}</p>']
        parts+=['</html>']; Path(target).write_text('\n'.join(parts),encoding='utf-8')
