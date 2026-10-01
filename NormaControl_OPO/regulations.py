"""Normative catalogue and controlled official-source import, without legal validation."""
import json
import hashlib
import re
import sqlite3
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from knowledge import KnowledgeBase, MAX_FILE

BASE = Path(__file__).resolve().parent
HOSTS = ('pravo.gov.ru', 'gosnadzor.ru', 'government.ru', 'eec.eaeunion.org',
         'docs.eaeunion.org', 'mintrud.gov.ru', 'mchs.gov.ru')
EXCLUDED_ACTS = {'FNP517'}  # Исключён по прямому указанию пользователя.
CARD_EDITION = 'карточка на 01.10.2026'
DISCLAIMER = ('ЭТО КАРТОЧКА КАТАЛОГА, НЕ ПОЛНЫЙ ТЕКСТ НОРМАТИВНОГО АКТА. '
              'Сведения взяты из подготовленного перечня. Проверка действующей редакции, '
              'изменений и применимости к конкретному ОПО автоматически не выполнена. '
              'Дата проверки записи не подтверждает юридическую актуальность нормы.')


def official_url(value):
    value = str(value).strip()
    p = urlsplit(value)
    host = (p.hostname or '').lower().rstrip('.')
    if (p.scheme not in ('http', 'https') or p.username or p.password or
            p.port not in (None, 80, 443) or not any(host == h or host.endswith('.' + h) for h in HOSTS)):
        raise ValueError('Разрешены только официальные адреса из списка нормативных источников.')
    return value


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NormativeCatalog:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.kb = KnowledgeBase(self.root)
        self.db_path = self.root / 'promcontrol.sqlite3'
        with self._db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS normative_catalog(
                act_id TEXT PRIMARY KEY, record_json TEXT NOT NULL,
                source_id INTEGER, local_status TEXT NOT NULL DEFAULT 'card_only',
                downloaded_source_id INTEGER, last_error TEXT NOT NULL DEFAULT '',
                checked TEXT NOT NULL DEFAULT '', imported_text_source_id INTEGER,
                provenance TEXT NOT NULL DEFAULT '')''')

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
    def _manifests():
        result, errors = {}, []
        for filename in ('regulations_industrial.json', 'regulations_related.json', 'regulations_library.json', 'regulations_uploaded.json'):
            path = BASE / filename
            if not path.is_file():
                errors.append('Перечень пока отсутствует: ' + filename)
                continue
            try:
                rows = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(rows, dict):
                    rows = rows.get('records', rows.get('acts', []))
                if not isinstance(rows, list):
                    raise ValueError('Ожидался список записей.')
                for row in rows:
                    if not isinstance(row, dict) or not row.get('id') or not row.get('title'):
                        errors.append('Неполная запись в ' + filename)
                        continue
                    act_id = str(row['id'])
                    if act_id in result:
                        errors.append('Повторяющийся идентификатор: ' + act_id)
                        continue
                    result[act_id] = dict(row, id=act_id)
            except Exception as exc:
                errors.append(filename + ': ' + str(exc))
        for act_id in EXCLUDED_ACTS:
            result.pop(act_id, None)
        return result, errors

    def authorize_uploaded_corpus(self):
        # User explicitly supplied ND for retrieval; this never marks legal review.
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS nc_corpus_permissions(act_id TEXT PRIMARY KEY, source_id INTEGER NOT NULL)')
            for rec in self.records():
                sid = rec.get('imported_text_source_id')
                if rec.get('archive_name') == 'НД.rar' and sid and not db.execute('SELECT 1 FROM nc_corpus_permissions WHERE act_id=?',(rec['id'],)).fetchone():
                    db.execute('UPDATE kb_sources SET retrieval_authorized=1 WHERE id=?',(sid,))
                    db.execute('INSERT INTO nc_corpus_permissions VALUES(?,?)',(rec['id'],sid))

    @staticmethod
    def _card_text(rec):
        lines = [DISCLAIMER, 'Наименование: ' + rec['title']]
        labels = {'issuer':'Орган', 'number':'Номер', 'date':'Дата', 'official_url':'Официальная ссылка (не загружена)', 'status':'Заявленный статус записи', 'applicability':'Применимость из перечня', 'summary':'Описание из перечня', 'known_validity':'Сведения о сроке из перечня (не проверены)', 'verification_note':'Примечания проверки', 'verification_notes':'Дополнительные примечания проверки', 'verified_on':'Дата проверки записи составителем'}
        for key, label in labels.items():
            lines.append(label + ': ' + str(rec.get(key, 'не указано')))
        return '\n'.join(lines)

    @staticmethod
    def _user_copy_provenance(rec):
        return ('Непроверенная пользовательская копия; идентификатор предоставленного файла: {}. Совпадение текста с официальным оригиналом и действующая редакция не подтверждены.'.format(rec.get('library_id','не указан')) +
                (' Исходное имя: ' + rec['original_filename'] if rec.get('original_filename') else '') +
                (' ' + rec['verification_note'] if rec.get('verification_note') else '') +
                (' ' + rec['service_text_removed'] if rec.get('service_text_removed') else ''))

    def _refresh_card(self, act_id, rec, source_id):
        # Карточка создаётся программой: при изменении перечня текст обновляется,
        # отметки пользователя (проверка, активность) и id фрагментов сохраняются.
        text = self._card_text(rec)
        try:
            if self.kb.open_path(source_id).read_text(encoding='utf-8', errors='replace') == text:
                return False
        except ValueError:
            pass  # файл карточки утрачен: создаётся заново
        except OSError:
            return False
        with tempfile.TemporaryDirectory(prefix='promcontrol-card-') as tmp:
            path = Path(tmp) / (re.sub(r'[^A-Za-z0-9_-]', '_', act_id) + '.txt')
            path.write_text(text, encoding='utf-8')
            self.kb.replace_source_content(source_id, path, title='КАРТОЧКА НПА — ' + rec['title'])
        return True

    def _upgrade_bundled_text(self, rec, source_id, candidate):
        """Прежняя копия из комплекта → очищенная копия того же документа."""
        source = self.kb.source(source_id)
        if source is None or not rec.get('original_sha256') or source['sha256'] != rec['original_sha256']:
            return False
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != rec.get('sha256'):
            raise ValueError('SHA256 очищенного файла не совпадает с манифестом.')
        edition = rec['edition_from_document'] if rec.get('edition_from_document') and source['edition'] == rec.get('legacy_edition') else None
        self.kb.replace_source_content(source_id, candidate, edition=edition, note=rec.get('service_text_removed', ''))
        if rec.get('content_kind') == 'user_copy':
            with self._db() as db:
                db.execute('UPDATE normative_catalog SET provenance=? WHERE act_id=?', (self._user_copy_provenance(rec), rec['id']))
        return True

    def seed(self, progress=None):
        manifests, errors = self._manifests()
        with self._db() as db:
            for act_id in EXCLUDED_ACTS:
                row = db.execute('SELECT source_id,downloaded_source_id,imported_text_source_id FROM normative_catalog WHERE act_id=?',(act_id,)).fetchone()
                if row:
                    for sid in row:
                        if sid is not None:
                            db.execute('UPDATE kb_sources SET active=0 WHERE id=?',(sid,))
        created, texts, texts_upgraded, cards_refreshed = 0, 0, 0, 0
        for index, (act_id, rec) in enumerate(manifests.items(), 1):
            if progress:
                progress(index, len(manifests), rec['title'])
            with self._db() as db:
                row = db.execute('SELECT * FROM normative_catalog WHERE act_id=?', (act_id,)).fetchone()
                if not row:
                    db.execute('INSERT INTO normative_catalog(act_id,record_json) VALUES(?,?)', (act_id, json.dumps(rec, ensure_ascii=False)))
                    created += 1
                else:
                    # Updating catalogue facts never resets a user's KB review or activation.
                    db.execute('UPDATE normative_catalog SET record_json=? WHERE act_id=?', (json.dumps(rec, ensure_ascii=False), act_id))
            try:
                if not row or row['source_id'] is None:
                    with tempfile.TemporaryDirectory(prefix='promcontrol-card-') as tmp:
                        path = Path(tmp) / (re.sub(r'[^A-Za-z0-9_-]', '_', act_id) + '.txt')
                        path.write_text(self._card_text(rec), encoding='utf-8')
                        sid = self.kb.import_file(path, title='КАРТОЧКА НПА — ' + rec['title'], source_url=rec.get('official_url', ''), edition=CARD_EDITION, reviewed=False)
                    with self._db() as db:
                        db.execute('UPDATE normative_catalog SET source_id=? WHERE act_id=?', (sid, act_id))
                elif self._refresh_card(act_id, rec, row['source_id']):
                    cards_refreshed += 1
                with self._db() as db:
                    state = db.execute('SELECT * FROM normative_catalog WHERE act_id=?', (act_id,)).fetchone()
                if state['imported_text_source_id'] is not None and rec.get('original_sha256') and rec.get('local_file'):
                    supplied = (BASE / rec['local_file']).resolve()
                    if supplied.is_relative_to((BASE / 'regulations_texts').resolve()) and supplied.is_file():
                        if self._upgrade_bundled_text(rec, state['imported_text_source_id'], supplied):
                            texts_upgraded += 1
                if state['imported_text_source_id'] is None and re.fullmatch(r'[A-Za-z0-9_-]+', act_id):
                    candidates = [BASE / 'regulations_texts' / (act_id + ext) for ext in ('.txt', '.pdf', '.docx')]
                    if rec.get('local_file'):
                        supplied = (BASE / rec['local_file']).resolve()
                        if not supplied.is_relative_to((BASE / 'regulations_texts').resolve()):
                            raise ValueError('Локальный материал должен находиться в regulations_texts.')
                        candidates.insert(0, supplied)
                    candidate = next((p for p in candidates if p.is_file()), None)
                    if candidate:
                        is_user_copy = rec.get('content_kind') == 'user_copy'
                        is_official = rec.get('content_kind') == 'official_publication'
                        if rec.get('sha256') and hashlib.sha256(candidate.read_bytes()).hexdigest() != rec['sha256']:
                            raise ValueError('SHA256 локального файла не совпадает с манифестом.')
                        source_url = official_url(rec.get('file_url') or rec.get('official_url','')) if is_official else rec.get('official_url','')
                        prefix = 'ОФИЦИАЛЬНЫЙ ФАЙЛ ПУБЛИКАЦИИ — ' if is_official else ('НЕПРОВЕРЕННАЯ ПОЛЬЗОВАТЕЛЬСКАЯ КОПИЯ — ' if is_user_copy else 'ЛОКАЛЬНЫЙ МАТЕРИАЛ НПА — ')
                        edition = 'официальный файл публикации; действующая сводная редакция не подтверждена' if is_official else ('пользовательская копия; происхождение, полнота и редакция не подтверждены' if is_user_copy else 'локальный материал; полнота и редакция не подтверждены')
                        if rec.get('edition_from_document'):
                            edition = rec['edition_from_document']
                        sid = self.kb.import_file(candidate, title=prefix + rec['title'], source_url=source_url, edition=edition, reviewed=False)
                        source = next(s for s in self.kb.sources() if s['id'] == sid)
                        with self._db() as db:
                            provenance = self._user_copy_provenance(rec) if is_user_copy else 'Локальный файл из regulations_texts; полнота и происхождение требуют проверки пользователем.'
                            status = 'user_copy_indexed' if is_user_copy else 'local_material_indexed'
                            if is_official:
                                provenance = 'Официальный файл из комплекта, полученный {} с {}. SHA256: {}. Исходная публикация; действующая сводная редакция не подтверждена. Извлечение: {}. {}'.format(rec.get('downloaded_on','дата не указана'), source_url, source['sha256'], source['status'], source['extraction_notes'])
                                status = 'official_file_partial' if source['status'] == 'partial' else 'official_file_indexed'
                            db.execute('UPDATE normative_catalog SET imported_text_source_id=?,local_status=?,provenance=?,downloaded_source_id=COALESCE(?,downloaded_source_id) WHERE act_id=?', (sid, status, provenance, sid if is_official else None, act_id))
                        texts += 1
            except Exception as exc:
                message = str(exc)[:2000]
                errors.append(act_id + ': ' + message)
                with self._db() as db:
                    if rec.get('content_kind') == 'official_publication':
                        db.execute("UPDATE normative_catalog SET last_error=?,local_status='official_file_error' WHERE act_id=?", (message,act_id))
                    else:
                        db.execute('UPDATE normative_catalog SET last_error=? WHERE act_id=?', (message, act_id))
        service_text = self.kb.clean_indexed_service_text()
        return {'count': len(manifests), 'created': created, 'local_texts_imported': texts,
                'local_texts_upgraded': texts_upgraded, 'cards_refreshed': cards_refreshed,
                'service_text_cleanup': service_text, 'errors': errors}

    def records(self):
        manifests, _ = self._manifests()
        with self._db() as db:
            states = {r['act_id']: dict(r) for r in db.execute('SELECT * FROM normative_catalog')}
        result = []
        for act_id in dict.fromkeys(list(manifests) + list(states)):
            if act_id in EXCLUDED_ACTS:
                continue
            state = states.get(act_id, {})
            rec = manifests.get(act_id) or json.loads(state.get('record_json', '{}'))
            result.append(dict(rec, act_id=act_id,
                source_id=state.get('source_id'), local_status=state.get('local_status', 'not_seeded'),
                downloaded_source_id=state.get('downloaded_source_id'), last_error=state.get('last_error',''),
                checked=state.get('checked',''), imported_text_source_id=state.get('imported_text_source_id'),
                provenance=state.get('provenance',''), normative_validation=False))
        return result

    def download_official(self, act_id, ocr_lang='rus+eng'):
        rec = next((r for r in self.records() if r['act_id'] == str(act_id)), None)
        if not rec:
            raise ValueError('Акт отсутствует в каталоге.')
        with self._db() as db:
            if not db.execute('SELECT 1 FROM normative_catalog WHERE act_id=?', (str(act_id),)).fetchone():
                db.execute('INSERT INTO normative_catalog(act_id,record_json) VALUES(?,?)', (str(act_id), json.dumps(rec,ensure_ascii=False)))
        checked = datetime.now().isoformat(timespec='seconds')
        try:
            url = official_url(rec.get('file_url') or rec.get('official_url') or '')
            req = Request(url, headers={'User-Agent': 'PromControl/1.0', 'Accept': 'application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain'})
            with build_opener(OfficialRedirects()).open(req, timeout=15) as response:
                final_url = official_url(response.geturl())
                declared = response.headers.get('Content-Length')
                if declared and int(declared) > MAX_FILE:
                    raise ValueError('Официальный файл превышает 32 МБ.')
                ctype = response.headers.get_content_type()
                raw = response.read(MAX_FILE + 1)
            if not raw or len(raw) > MAX_FILE:
                raise ValueError('Файл пуст или превышает 32 МБ.')
            probe = raw[:512].lstrip(b'\xef\xbb\xbf \t\r\n').lower()
            if b'<html' in probe or b'<!doctype html' in probe or ctype == 'text/html':
                raise ValueError('Получена HTML-страница, а не текст/файл акта. Полный текст не импортирован.')
            if raw.startswith(b'%PDF-'):
                suffix = '.pdf'
            elif raw.startswith(b'PK'):
                import io
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    if 'word/document.xml' not in archive.namelist():
                        raise ValueError('ZIP не является DOCX.')
                suffix = '.docx'
            elif ctype == 'text/plain' and b'\x00' not in raw[:4096]:
                suffix = '.txt'
            else:
                raise ValueError('Ответ не распознан как PDF, DOCX или TXT; полный текст не импортирован.')
            with tempfile.TemporaryDirectory(prefix='promcontrol-official-') as tmp:
                path = Path(tmp) / ('official_publication' + suffix)
                path.write_bytes(raw)
                sid = self.kb.import_file(path, title='ОФИЦИАЛЬНЫЙ ФАЙЛ ПУБЛИКАЦИИ — ' + rec['title'], source_url=final_url,
                    edition='официальный файл публикации; действующая сводная редакция не подтверждена', reviewed=False, ocr_lang=ocr_lang)
            source = next(s for s in self.kb.sources() if s['id'] == sid)
            status = 'official_file_partial' if source['status'] == 'partial' else 'official_file_indexed'
            provenance = 'Файл получен с официального адреса {}. Исходная публикация; изменения и действующая сводная редакция не подтверждены. Извлечение: {}. {}'.format(final_url,source['status'],source['extraction_notes'])
            with self._db() as db:
                db.execute("UPDATE normative_catalog SET downloaded_source_id=?,local_status=?,last_error='',checked=?,provenance=? WHERE act_id=?", (sid, status, checked, provenance, str(act_id)))
            return {'act_id': str(act_id), 'status': status, 'source_id': sid, 'extraction_status': source['status'], 'provenance': provenance, 'error': ''}
        except Exception as exc:
            message = str(exc)[:2000]
            with self._db() as db:
                # An earlier usable copy remains recorded; this attempt's error is explicit.
                db.execute("UPDATE normative_catalog SET last_error=?,checked=?,local_status='official_file_error' WHERE act_id=?", (message, checked, str(act_id)))
            return {'act_id': str(act_id), 'status': 'failed', 'error': message, 'source_id': None}

    def download_all(self, ocr_lang='rus+eng', progress=None, cancel_event=None):
        candidates = [r for r in self.records() if r.get('file_url')]
        results = []
        for index, rec in enumerate(candidates, 1):
            if cancel_event is not None and cancel_event.is_set():
                break
            result = self.download_official(rec['act_id'], ocr_lang)
            results.append(result)
            if progress:
                progress(index, len(candidates), result)
        return {'total': len(candidates), 'attempted': len(results),
                'indexed': sum(r['status']=='official_file_indexed' for r in results),
                'partial': sum(r['status']=='official_file_partial' for r in results),
                'failed': sum(r['status']=='failed' for r in results),
                'cancelled': len(results)<len(candidates), 'results': results}
