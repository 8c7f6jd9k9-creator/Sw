"""Offline storage and user-defined document completeness tracking. No legal inference."""
import hashlib
import html
import json
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from datetime import date, datetime
from pathlib import Path
from inspections import InspectionStore

LABELS = {'expired':'Просрочен','due30':'Истекает ≤30 дней','due60':'Истекает 31–60 дней','current':'Срок не истёк','unknown':'Срок не задан','permanent':'Срок не ограничен (указано пользователем)'}

def parse_date(value):
    value=value.strip()
    return datetime.strptime(value,'%d.%m.%Y').date() if value else None

def document_status(expiry, permanent=False, today=None):
    today=today or date.today()
    if permanent:
        return 'permanent'
    due=parse_date(expiry or '')
    if due is None: return 'unknown'
    days=(due-today).days
    return 'expired' if days<0 else 'due30' if days<=30 else 'due60' if days<=60 else 'current'

class Store(InspectionStore):
    def __init__(self, root, seed=None):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'files').mkdir(exist_ok=True)
        self.db=sqlite3.connect(self.root/'promcontrol.sqlite3')
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS assets(seq INTEGER PRIMARY KEY, reg_no TEXT UNIQUE NOT NULL, name TEXT NOT NULL, registered TEXT NOT NULL, danger_class INTEGER NOT NULL CHECK(danger_class BETWEEN 1 AND 4), signs TEXT NOT NULL, source TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS requirements(id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(seq), title TEXT NOT NULL, basis TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(seq), requirement_id INTEGER REFERENCES requirements(id), title TEXT NOT NULL, number TEXT NOT NULL, issued TEXT NOT NULL, expiry TEXT NOT NULL, permanent INTEGER NOT NULL, reviewed INTEGER NOT NULL, original_name TEXT NOT NULL, stored_name TEXT NOT NULL, sha256 TEXT NOT NULL, added TEXT NOT NULL, superseded INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, occurred TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL);
        ''')
        if not self.db.execute('SELECT 1 FROM assets LIMIT 1').fetchone() and seed:
            items=json.loads(Path(seed).read_text(encoding='utf-8'))
            with self.db:
                for item in items:
                    self.db.execute('INSERT INTO assets VALUES (:seq,:reg_no,:name,:registered,:danger_class,:signs,:source,:verified,:notes,:owner)',item)
                self.log('seed','33 ОПО: фотографии; признаки опасности: уточнение пользователя 01.10.2026')
        self.init_cauk()
    def log(self, action, details):
        self.db.execute('INSERT INTO events(occurred,action,details) VALUES(?,?,?)',(datetime.now().isoformat(timespec='seconds'),action,details))
    def assets(self): return self.db.execute('SELECT * FROM assets ORDER BY seq').fetchall()
    def asset(self, asset_id): return self.db.execute('SELECT * FROM assets WHERE seq=?',(asset_id,)).fetchone()
    def update_asset(self, asset_id, owner, notes, verified):
        with self.db:
            self.db.execute('UPDATE assets SET owner=?,notes=?,verified=? WHERE seq=?',(owner,notes,int(verified),asset_id))
            self.log('asset_update',str(asset_id))
    def requirements(self, asset_id): return self.db.execute('SELECT * FROM requirements WHERE asset_id=? AND active=1 ORDER BY id',(asset_id,)).fetchall()
    def add_requirement(self, asset_id, title, basis):
        if not title.strip() or not basis.strip(): raise ValueError('Заполните вид документа и основание включения в перечень.')
        with self.db:
            cur=self.db.execute('INSERT INTO requirements(asset_id,title,basis) VALUES(?,?,?)',(asset_id,title.strip(),basis.strip()))
            self.log('requirement_add',f'{asset_id}: {title}; {basis}')
        return cur.lastrowid
    def documents(self, asset_id): return self.db.execute('SELECT * FROM documents WHERE asset_id=? ORDER BY id DESC',(asset_id,)).fetchall()
    def add_document(self, asset_id, path, title, number='', issued='', expiry='', permanent=False, reviewed=False, requirement_id=None):
        src=Path(path)
        if not src.is_file(): raise ValueError('Выберите существующий файл.')
        if not title.strip(): raise ValueError('Заполните название документа.')
        issued_date=parse_date(issued); expiry_date=parse_date(expiry)
        if permanent and expiry.strip(): raise ValueError('При неограниченном сроке поле окончания должно быть пустым.')
        if issued_date and expiry_date and expiry_date<issued_date: raise ValueError('Окончание срока раньше даты документа.')
        if requirement_id is not None:
            req=self.db.execute('SELECT * FROM requirements WHERE id=? AND asset_id=? AND active=1',(requirement_id,asset_id)).fetchone()
            if req is None: raise ValueError('Требование относится к другому ОПО или отсутствует.')
        stored=uuid.uuid4().hex+src.suffix.lower()
        target=self.root/'files'/stored
        try:
            shutil.copyfile(src,target)
            hasher=hashlib.sha256()
            with target.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''): hasher.update(block)
            digest=hasher.hexdigest()
            with self.db:
                cur=self.db.execute('''INSERT INTO documents(asset_id,requirement_id,title,number,issued,expiry,permanent,reviewed,original_name,stored_name,sha256,added) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(asset_id,requirement_id,title.strip(),number.strip(),issued.strip(),expiry.strip(),int(permanent),int(reviewed),src.name,stored,digest,datetime.now().isoformat(timespec='seconds')))
                self.log('document_add',f'{asset_id}: {src.name}; SHA256={digest}')
            return cur.lastrowid
        except Exception:
            target.unlink(missing_ok=True)
            raise
    def supersede(self, document_id):
        with self.db:
            self.db.execute('UPDATE documents SET superseded=1 WHERE id=?',(document_id,))
            self.log('document_archive',str(document_id))
    def document_path(self, document_id):
        row=self.db.execute('SELECT stored_name FROM documents WHERE id=?',(document_id,)).fetchone()
        if row is None: raise ValueError('Документ не найден.')
        return self.root/'files'/row['stored_name']
    def completeness(self, asset_id, today=None):
        docs=[d for d in self.documents(asset_id) if not d['superseded']]
        out=[]
        for req in self.requirements(asset_id):
            found=[d for d in docs if d['requirement_id']==req['id']]
            if not found: status='Не загружен'
            elif any(self.document_path(d['id']).is_file() and d['reviewed'] and document_status(d['expiry'],d['permanent'],today) in ('current','due30','due60','permanent') for d in found): status='Есть файл, проверен пользователем, срок не истёк'
            else: status='Есть запись; проверить файл, срок и содержание'
            out.append((req,status))
        return out
    def report(self, target, today=None):
        today=today or date.today()
        e=lambda v:html.escape(str(v))
        parts=['<!doctype html><html lang="ru"><meta charset="utf-8"><title>НормаКонтроль ОПО — статус документов</title><style>body{font:15px Arial;margin:32px;color:#183047}table{border-collapse:collapse;width:100%;margin:15px 0}td,th{border:1px solid #bac8d1;padding:8px;text-align:left}h2{margin-top:32px}.notice{background:#fff3ce;padding:16px}</style>',f'<h1>Статус документов ОПО на {today:%d.%m.%Y}</h1>','<p class="notice">Это учётный отчёт первого этапа, не заключение о соответствии. Перечень документов задаёт пользователь. Наличие файла и неистёкший срок не подтверждают соответствие требованиям. Распознавание и нормативный анализ не подключены.</p>']
        for asset in self.assets():
            parts += [f'<h2>{e(asset["reg_no"])} — {e(asset["name"])}</h2>',f'<p>Класс: {asset["danger_class"]}; признаки: {e(asset["signs"])}. Источник: {e(asset["source"])}; признаки — уточнение пользователя 01.10.2026. Сверка с оригиналом: {"выполнена пользователем" if asset["verified"] else "требуется"}.</p>',f'<p>Ответственный: {e(asset["owner"])}. Примечание: {e(asset["notes"])}</p>']
            checks=self.completeness(asset['seq'],today)
            if not checks: parts += ['<p><b>Перечень не настроен. Полнота не оценена.</b></p>']
            else:
                parts += ['<table><tr><th>Вид документа</th><th>Основание пользователя</th><th>Статус</th></tr>']
                parts += [f'<tr><td>{e(r["title"])}</td><td>{e(r["basis"])}</td><td>{e(s)}</td></tr>' for r,s in checks]
                parts += ['</table>']
            docs=self.documents(asset['seq'])
            if docs:
                parts += ['<table><tr><th>Документ</th><th>Номер / дата</th><th>Окончание</th><th>Состояние</th><th>Проверка</th></tr>']
                for d in docs:
                    status='Архив' if d['superseded'] else LABELS[document_status(d['expiry'],d['permanent'],today)]
                    exists=self.document_path(d['id']).is_file()
                    parts += [f'<tr><td>{e(d["title"])}</td><td>{e(d["number"])} / {e(d["issued"])}</td><td>{e(d["expiry"])}</td><td>{e(status)}; {"файл есть" if exists else "ФАЙЛ ОТСУТСТВУЕТ"}</td><td>{"Проверен пользователем" if d["reviewed"] else "Не проверен"}</td></tr>']
                parts += ['</table>']
        parts+=['</html>']
        Path(target).write_text('\n'.join(parts),encoding='utf-8')
    def backup(self, target):
        target=Path(target).resolve()
        if target.is_relative_to(self.root): raise ValueError('Резервную копию сохраняйте вне папки данных.')
        # Сначала временный файл рядом с целью: прерванная запись не портит прежнюю копию.
        partial=target.with_name(target.name+'.'+uuid.uuid4().hex[:8]+'.tmp')
        try:
            with tempfile.TemporaryDirectory() as tmp:
                db_path=Path(tmp)/'promcontrol.sqlite3'
                dest=sqlite3.connect(db_path)
                try: self.db.backup(dest)
                finally: dest.close()
                with zipfile.ZipFile(partial,'w',zipfile.ZIP_DEFLATED) as archive:
                    archive.write(db_path,'promcontrol.sqlite3')
                    for p in sorted((self.root/'files').iterdir()):
                        if p.is_file(): archive.write(p,'files/'+p.name)
                    archive.writestr('RESTORE.txt','Закройте программу. Сохраните старую папку данных отдельно. Распакуйте эту копию в пустую папку и задайте PROMCONTROL_DATA_DIR либо используйте штатную папку данных. Не объединяйте разные базы.')
            result=verify_backup(partial)
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
        self.log_event('backup',f'{target.name}; файлов {result["files"]}; integrity {result["integrity"]}')
        return result
    def log_event(self, action, details):
        with self.db: self.log(action,details)
    def close(self): self.db.close()

# Таблицы, где хранятся имена файлов из папки files/.
FILE_COLUMNS=(('documents','stored_name'),('kb_sources','stored_name'),('nc_materials','stored_name'),('cauk_evidence','stored_name'))

def verify_backup(path):
    """Проверить резервную копию без распаковки в папку данных."""
    path=Path(path)
    with zipfile.ZipFile(path) as archive:
        bad=archive.testzip()
        if bad: raise ValueError('Резервная копия повреждена: '+bad)
        names=set(archive.namelist())
        if 'promcontrol.sqlite3' not in names: raise ValueError('В резервной копии нет базы promcontrol.sqlite3.')
        files={n[6:] for n in names if n.startswith('files/') and not n.endswith('/')}
        with tempfile.TemporaryDirectory() as tmp:
            db_path=Path(tmp)/'promcontrol.sqlite3'
            db_path.write_bytes(archive.read('promcontrol.sqlite3'))
            db=sqlite3.connect(db_path)
            try:
                integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
                tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                counts={t:db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('assets','documents','kb_sources','kb_chunks','nc_situations','nc_materials','cauk_checks') if t in tables}
                missing=[]
                for table,column in FILE_COLUMNS:
                    if table in tables:
                        missing+=[r[0] for r in db.execute(f'SELECT {column} FROM {table}') if r[0] and r[0] not in files]
            finally: db.close()
    if integrity!='ok': raise ValueError('База в резервной копии не прошла integrity_check: '+integrity)
    return {'integrity':integrity,'files':len(files),'missing_files':sorted(set(missing)),'counts':counts,'bytes':path.stat().st_size}

def restore_backup(path, target):
    """Распаковать копию в пустую папку (проверочную или новую); текущие данные не трогаются."""
    target=Path(target).resolve()
    if target.exists() and any(target.iterdir()): raise ValueError('Восстановление выполняется только в пустую папку.')
    result=verify_backup(path)
    target.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            destination=(target/info.filename).resolve()
            if not destination.is_relative_to(target): raise ValueError('Недопустимый путь в архиве: '+info.filename)
            if info.is_dir(): destination.mkdir(parents=True,exist_ok=True); continue
            destination.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(info) as source, destination.open('wb') as out: shutil.copyfileobj(source,out)
    return result
