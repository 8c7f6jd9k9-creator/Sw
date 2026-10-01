"""Situational inspections adapted from the original NormaKontrol workflow.

Lexical retrieval suggests sources; only a named specialist records a decision.
All data uses the existing local SQLite and backup file directory.
"""
import csv
import hashlib
import html
import json
import re
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from knowledge import KnowledgeBase

CATEGORIES = ['РВС / РГС', 'Сосуды / сепараторы', 'Скважины', 'Трубопроводы',
              'Газоопасные / огневые / ремонтные работы', 'Площадка', 'Общие вопросы']
RISKS = {'unknown': 'Не оценён', 'low': 'Низкий', 'medium': 'Средний',
         'high': 'Высокий', 'critical': 'Критический'}
STATES = {'created': 'Создана', 'analyzed': 'Источники подобраны',
          'confirmed': 'Решение специалиста', 'closed': 'Закрыта'}
STOP = {'и', 'в', 'на', 'по', 'с', 'со', 'к', 'для', 'из', 'от', 'или', 'не',
        'что', 'это', 'при', 'как', 'а', 'у', 'о'}


def tokens(text):
    return {w for w in re.findall(r'[a-zа-яё0-9-]+', str(text).lower())
            if len(w) > 2 and w not in STOP}


class SituationStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.kb = KnowledgeBase(self.root)
        self.db_path = self.root / 'promcontrol.sqlite3'
        with self._db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS nc_situations(
              id INTEGER PRIMARY KEY, number TEXT UNIQUE NOT NULL,
              title TEXT NOT NULL, asset_id INTEGER, category TEXT NOT NULL,
              location TEXT NOT NULL, description TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'created', risk TEXT NOT NULL DEFAULT 'unknown',
              reviewer TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL DEFAULT '',
              matches_json TEXT NOT NULL DEFAULT '[]', created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS nc_materials(
              id INTEGER PRIMARY KEY, situation_id INTEGER NOT NULL,
              original_name TEXT NOT NULL, stored_name TEXT NOT NULL, sha256 TEXT NOT NULL,
              created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS nc_requirements(
              id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
              clause TEXT NOT NULL, text TEXT NOT NULL, keywords TEXT NOT NULL DEFAULT '',
              action TEXT NOT NULL DEFAULT '', source_id INTEGER NOT NULL, chunk_id INTEGER NOT NULL,
              reviewed INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
              created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS nc_audit(
              id INTEGER PRIMARY KEY, situation_id INTEGER, occurred TEXT NOT NULL,
              action TEXT NOT NULL, payload TEXT NOT NULL);
            ''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec='seconds')

    def _audit(self, db, sid, action, payload):
        db.execute('INSERT INTO nc_audit(situation_id,occurred,action,payload) VALUES(?,?,?,?)',
                   (sid, self._now(), action, json.dumps(payload, ensure_ascii=False)))

    def list(self):
        with self._db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM nc_situations ORDER BY id DESC')]

    def get(self, sid):
        with self._db() as db:
            row = db.execute('SELECT * FROM nc_situations WHERE id=?', (sid,)).fetchone()
        if row is None:
            raise ValueError('Ситуация не найдена.')
        result = dict(row)
        result['matches'] = json.loads(result.pop('matches_json'))
        return result

    def save(self, title, asset_id, category, location, description, sid=None):
        title, description = str(title).strip(), str(description).strip()
        if not title or not description:
            raise ValueError('Заполните наименование и описание ситуации.')
        if category not in CATEGORIES:
            raise ValueError('Выберите категорию.')
        if len(title) > 300 or len(description) > 50000:
            raise ValueError('Слишком длинное наименование или описание.')
        with self._db() as db:
            if asset_id is not None and not db.execute('SELECT 1 FROM assets WHERE seq=?', (asset_id,)).fetchone():
                raise ValueError('ОПО не найден.')
            if sid is None:
                cur = db.execute('INSERT INTO nc_situations(number,title,asset_id,category,location,description,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                                 ('НК-' + uuid.uuid4().hex[:10].upper(), title, asset_id, category,
                                  str(location).strip(), description, self._now(), self._now()))
                sid = cur.lastrowid
            else:
                previous = db.execute('SELECT * FROM nc_situations WHERE id=?', (sid,)).fetchone()
                if previous is None:
                    raise ValueError('Ситуация не найдена.')
                changed = (title, asset_id, category, str(location).strip(), description) != tuple(previous[k] for k in ('title', 'asset_id', 'category', 'location', 'description'))
                self._audit(db, sid, 'before_edit', dict(previous))
                db.execute('UPDATE nc_situations SET title=?,asset_id=?,category=?,location=?,description=?,updated=? WHERE id=?',
                           (title, asset_id, category, str(location).strip(), description, self._now(), sid))
                if changed:
                    db.execute("UPDATE nc_situations SET status='created',risk='unknown',reviewer='',decision='',matches_json='[]' WHERE id=?", (sid,))
            self._audit(db, sid, 'save', {'title': title, 'asset_id': asset_id})
        return sid

    def attach(self, sid, path):
        self.get(sid)
        path = Path(path).resolve()
        if not path.is_file() or path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Файл отсутствует либо больше 32 МБ.')
        if path.suffix.lower() not in ('.pdf', '.docx', '.txt', '.jpg', '.jpeg', '.png', '.tif', '.tiff'):
            raise ValueError('Допустимы документы и изображения.')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with self._db() as db:
            row = db.execute('SELECT id FROM nc_materials WHERE situation_id=? AND sha256=?', (sid, digest)).fetchone()
            if row:
                return row['id']
            stored = 'nc_' + uuid.uuid4().hex + path.suffix.lower()
            shutil.copy2(path, self.root / 'files' / stored)
            try:
                cur = db.execute('INSERT INTO nc_materials(situation_id,original_name,stored_name,sha256,created) VALUES(?,?,?,?,?)',
                                 (sid, path.name, stored, digest, self._now()))
                self._audit(db, sid, 'attach', {'name': path.name, 'sha256': digest, 'previous': self.get(sid)})
                db.execute("UPDATE nc_situations SET status='created',risk='unknown',reviewer='',decision='',matches_json='[]' WHERE id=?", (sid,))
                return cur.lastrowid
            except Exception:
                (self.root / 'files' / stored).unlink(missing_ok=True)
                raise

    def materials(self, sid):
        with self._db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM nc_materials WHERE situation_id=? ORDER BY id', (sid,))]

    def material_path(self, mid):
        with self._db() as db:
            row = db.execute('SELECT stored_name FROM nc_materials WHERE id=?', (mid,)).fetchone()
        if row is None:
            raise ValueError('Материал не найден.')
        path = (self.root / 'files' / row['stored_name']).resolve()
        if path.parent != (self.root / 'files').resolve() or not path.is_file():
            raise ValueError('Файл материала отсутствует.')
        return path

    def requirements(self):
        with self._db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM nc_requirements ORDER BY id DESC')]

    def save_requirement(self, title, category, clause, text, source_id, chunk_id,
                         keywords='', action='', reviewed=False, active=True, rid=None):
        if not str(title).strip() or not str(text).strip() or not str(clause).strip():
            raise ValueError('Нужны документ, пункт и текст требования.')
        if category not in CATEGORIES:
            raise ValueError('Некорректная категория.')
        with self._db() as db:
            source = db.execute('SELECT s.id FROM kb_sources s JOIN kb_chunks c ON c.source_id=s.id WHERE s.id=? AND c.id=?',
                                (int(source_id), int(chunk_id))).fetchone()
            if source is None:
                raise ValueError('Источник и фрагмент не совпадают или отсутствуют.')
            values = (str(title).strip(), category, str(clause).strip(), str(text).strip(),
                      str(keywords), str(action), int(source_id), int(chunk_id), int(reviewed), int(active))
            if rid is None:
                cur = db.execute('INSERT INTO nc_requirements(title,category,clause,text,keywords,action,source_id,chunk_id,reviewed,active,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', values + (self._now(), self._now()))
                return cur.lastrowid
            if not db.execute('SELECT 1 FROM nc_requirements WHERE id=?', (rid,)).fetchone():
                raise ValueError('Требование не найдено.')
            db.execute('UPDATE nc_requirements SET title=?,category=?,clause=?,text=?,keywords=?,action=?,source_id=?,chunk_id=?,reviewed=?,active=?,updated=? WHERE id=?', values + (self._now(), rid))
            return rid

    def import_requirements_csv(self, path):
        with Path(path).open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            required = {'title', 'category', 'clause', 'text', 'source_id', 'chunk_id'}
            if not required.issubset(reader.fieldnames or []):
                raise ValueError('CSV требует колонки: ' + ', '.join(sorted(required)))
            rows = list(reader)
        if len(rows) > 5000:
            raise ValueError('В CSV больше 5000 строк.')
        # Validate every row before the first mutation; external review flags ignored.
        with self._db() as db:
            for index, r in enumerate(rows, 2):
                if not all(r.get(k, '').strip() for k in required) or r['category'] not in CATEGORIES:
                    raise ValueError('Неполная строка CSV ' + str(index))
                if not db.execute('SELECT 1 FROM kb_chunks WHERE source_id=? AND id=?', (int(r['source_id']), int(r['chunk_id']))).fetchone():
                    raise ValueError('Не найдена ссылка в строке CSV ' + str(index))
            for r in rows:
                db.execute('INSERT INTO nc_requirements(title,category,clause,text,keywords,action,source_id,chunk_id,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (r['title'], r['category'], r['clause'], r['text'], r.get('keywords', ''), r.get('action', ''), int(r['source_id']), int(r['chunk_id']), self._now(), self._now()))
        return len(rows)

    def analyze(self, sid, include_unreviewed=False, include_authorized=True):
        record = self.get(sid)
        words = tokens(record['description'])
        with self._db() as db:
            requirements = [dict(r) for r in db.execute('SELECT r.*,s.edition,s.title AS source_title FROM nc_requirements r JOIN kb_sources s ON s.id=r.source_id JOIN kb_chunks c ON c.id=r.chunk_id AND c.source_id=r.source_id WHERE r.reviewed=1 AND r.active=1 AND s.active=1 AND s.status IN ("indexed","partial") AND (s.valid_from="" OR s.valid_from<=?) AND (s.valid_to="" OR s.valid_to>=?) AND (s.asset_id IS NULL OR s.asset_id=?)', (date.today().isoformat(),date.today().isoformat(),record['asset_id']))]
        matches = []
        for r in requirements:
            overlap = words & tokens(r['text'] + ' ' + r['keywords'])
            if not overlap:
                continue
            score = len(words & tokens(r['keywords'])) * 2 + len(words & tokens(r['text'])) + (5 if r['category'] == record['category'] else 0)
            matches.append({'kind': 'reviewed_requirement', 'source_id': r['source_id'],
                            'id': r['chunk_id'], 'title': r['source_title'], 'edition': r['edition'],
                            'clause': r['clause'], 'text': r['text'], 'score': score,
                            'reason': 'Совпадения: ' + ', '.join(sorted(overlap)), 'action': r['action']})
        matches.sort(key=lambda x: (-x['score'], x['id']))
        matches = matches[:5]
        for r in self.kb.search(record['description'], record['asset_id'], 5,
                                include_unreviewed=include_unreviewed, include_authorized=include_authorized):
            if any(m['source_id'] == r['source_id'] and m['id'] == r['id'] for m in matches):
                continue
            matches.append(dict(r, kind='source_fragment', clause=r['location'],
                                reason='Лексический поиск; применимость не установлена', action=''))
        with self._db() as db:
            self._audit(db, sid, 'analyze', {'matches': matches, 'previous': record})
            db.execute("UPDATE nc_situations SET matches_json=?,status='analyzed',risk='unknown',reviewer='',decision='',updated=? WHERE id=?",
                       (json.dumps(matches, ensure_ascii=False), self._now(), sid))
        return matches

    def decide(self, sid, risk, reviewer, decision, close=False):
        record = self.get(sid)
        if risk not in RISKS or risk == 'unknown' or not str(reviewer).strip() or not str(decision).strip():
            raise ValueError('Укажите оценку риска, специалиста и обоснование решения.')
        if close and record['status'] != 'confirmed':
            raise ValueError('Сначала сохраните решение специалиста, затем закройте ситуацию.')
        with self._db() as db:
            self._audit(db, sid, 'decision', {'previous': record, 'risk': risk,
                                           'reviewer': reviewer, 'decision': decision, 'close': close})
            db.execute('UPDATE nc_situations SET risk=?,reviewer=?,decision=?,status=?,updated=? WHERE id=?',
                       (risk, str(reviewer).strip(), str(decision).strip(), 'closed' if close else 'confirmed', self._now(), sid))

    def export_report(self, sid, target):
        record = self.get(sid)
        if Path(target).suffix.lower() == '.pdf':
            return self._pdf(record, Path(target))
        chunks = [f'<h1>НормаКонтроль ОПО — {html.escape(record["number"])}</h1>',
                  '<p>Подбор источников не подтверждает нарушение или соответствие.</p>']
        for name, key in [('Ситуация', 'title'), ('Описание', 'description'), ('Специалист', 'reviewer'), ('Решение', 'decision')]:
            chunks.append('<h2>' + name + '</h2><p>' + html.escape(record[key]).replace('\n', '<br>') + '</p>')
        chunks.append('<p>Риск: ' + RISKS[record['risk']] + '; статус: ' + STATES[record['status']] + '</p>')
        for m in record['matches']:
            chunks.append('<h3>' + html.escape(m['title']) + f' [К{m["source_id"]}-Ф{m["id"]}]</h3><p>' + html.escape(m['edition']) + '</p><p>' + html.escape(m['text']) + '</p>')
        Path(target).write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>НормаКонтроль ОПО</title><body>' + '\n'.join(chunks) + '</body></html>', encoding='utf-8')
        return Path(target)

    def _pdf(self, record, target):
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        fonts = [Path(__file__).parent / 'resources' / 'DejaVuSans.ttf',
                 Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
        font = next((p for p in fonts if p.is_file()), None)
        if font is None:
            raise ValueError('Для PDF нужен шрифт с кириллицей.')
        pdfmetrics.registerFont(TTFont('NormaFont', str(font)))
        styles = getSampleStyleSheet()
        for style in styles.byName.values():
            style.fontName = 'NormaFont'
        story = [Paragraph('НормаКонтроль ОПО', styles['Title']),
                 Paragraph(html.escape(record['number']), styles['Heading2'])]
        fields = [('Ситуация', record['title']), ('Категория', record['category']),
                  ('Место', record['location']), ('Статус', STATES[record['status']]),
                  ('Риск — оценка специалиста', RISKS[record['risk']]),
                  ('Описание', record['description']), ('Специалист', record['reviewer']),
                  ('Решение', record['decision'])]
        for label, value in fields:
            story += [Paragraph(label, styles['Heading3']),
                      Paragraph(html.escape(str(value)).replace('\n', '<br/>'), styles['BodyText'])]
        for m in record['matches']:
            story += [Paragraph(html.escape(m['title']) + f' [К{m["source_id"]}-Ф{m["id"]}]', styles['Heading3']),
                      Paragraph(html.escape(m['edition']), styles['BodyText']),
                      Paragraph(html.escape(m['text']).replace('\n', '<br/>'), styles['BodyText']), Spacer(1, 8)]
        photos = [m for m in self.materials(record['id']) if Path(m['stored_name']).suffix in ('.jpg', '.jpeg', '.png')]
        if photos:
            story.append(PageBreak())
        with tempfile.TemporaryDirectory(prefix='normacontrol-pdf-') as tmp:
            for m in self.materials(record['id']):
                path = self.material_path(m['id'])
                story.append(Paragraph(html.escape(m['original_name']), styles['Heading3']))
                if path.suffix.lower() in ('.jpg', '.jpeg', '.png'):
                    try:
                        story += [Image(str(self._pdf_photo(path, Path(tmp))), width=460, height=300, kind='proportional'), Spacer(1, 8)]
                    except Exception as exc:
                        raise ValueError('Не удалось включить изображение в PDF: ' + m['original_name']) from exc
            styles['BodyText'].textColor = colors.black
            story.append(Paragraph('Подбор источников предварительный. Редакция и применимость требуют проверки. Решение фиксирует указанный специалист. Фотографии приложены без автоматического анализа.', styles['BodyText']))
            SimpleDocTemplate(str(target), pagesize=A4, leftMargin=42, rightMargin=42, topMargin=42, bottomMargin=42).build(story)
        return target

    @staticmethod
    def _pdf_photo(path, folder):
        """Копия фото для отчёта: поворот по EXIF (снимки телефона) и разумное разрешение.

        Оригинал в базе не меняется."""
        from PIL import Image as PILImage, ImageOps
        with PILImage.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ('RGB', 'L'):
                image = image.convert('RGB')
            image.thumbnail((2000, 2000))
            target = folder / (uuid.uuid4().hex + '.jpg')
            image.save(target, 'JPEG', quality=88)
        return target
