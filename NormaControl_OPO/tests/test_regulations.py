"""Catalogue tests with isolated manifests and mocked network only."""
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch

from regulations import NormativeCatalog, official_url, OfficialRedirects


class RegulationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifests = self.root / 'manifests'
        self.manifests.mkdir()
        self.base_patch = patch('regulations.BASE', self.manifests)
        self.base_patch.start()
        self.record = {'id': 'test_act', 'title': 'Тестовый нормативный трубопровод',
                       'official_url': 'https://pravo.gov.ru/test-act', 'number': 'TEST',
                       'status': 'Тестовая запись без правового заключения'}
        self.write_manifest()
        self.catalog = NormativeCatalog(self.root / 'data')

    def tearDown(self):
        self.base_patch.stop()
        self.temp.cleanup()

    def write_manifest(self):
        for name in ('regulations_industrial.json', 'regulations_related.json', 'regulations_library.json', 'regulations_uploaded.json'):
            data = [self.record] if name == 'regulations_industrial.json' else []
            (self.manifests / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def response(self, raw, content_type='text/plain', final_url='https://pravo.gov.ru/test-act'):
        headers = Message()
        headers['Content-Type'] = content_type
        headers['Content-Length'] = str(len(raw))
        response = Mock()
        response.headers = headers
        response.geturl.return_value = final_url
        response.read.return_value = raw
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_seed_idempotent_cards_excluded_and_user_flags_preserved(self):
        first = self.catalog.seed()
        self.assertEqual(first['created'], 1)
        self.assertEqual(first['errors'], [])
        source_id = self.catalog.records()[0]['source_id']
        self.assertEqual(self.catalog.kb.search('трубопровод'), [])
        source = self.catalog.kb.sources()[0]
        self.assertFalse(source['reviewed'])
        text = self.catalog.kb.open_path(source_id).read_text(encoding='utf-8')
        self.assertIn('НЕ ПОЛНЫЙ ТЕКСТ', text)
        self.assertEqual(self.catalog.records()[0]['normative_validation'], False)
        self.catalog.kb.update_source(source_id, True, False, edition=source['edition'], source_url=source['source_url'])
        second = self.catalog.seed()
        self.assertEqual(second['created'], 0)
        self.assertEqual(len(self.catalog.kb.sources()), 1)
        self.assertEqual(self.catalog.records()[0]['source_id'], source_id)
        source = self.catalog.kb.sources()[0]
        self.assertTrue(source['reviewed'])
        self.assertFalse(source['active'])

    def test_local_usercopy_indexed_without_claim_of_authenticity(self):
        texts = self.manifests / 'regulations_texts'
        texts.mkdir()
        (texts / 'test_act.txt').write_text('Локальная пользовательская копия трубопровод', encoding='utf-8')
        self.record.update(content_kind='user_copy', library_id='test_library_id')
        self.write_manifest()
        result = self.catalog.seed()
        self.assertEqual(result['local_texts_imported'], 1)
        row = self.catalog.records()[0]
        self.assertEqual(row['local_status'], 'user_copy_indexed')
        self.assertIn('test_library_id', row['provenance'])
        self.assertIn('не подтверждены', row['provenance'])
        self.assertFalse(row['normative_validation'])
        source = next(s for s in self.catalog.kb.sources() if s['id'] == row['imported_text_source_id'])
        self.assertFalse(source['reviewed'])
        self.assertIn('НЕПРОВЕРЕННАЯ ПОЛЬЗОВАТЕЛЬСКАЯ КОПИЯ', source['title'])
        self.assertEqual(self.catalog.kb.search('трубопровод'), [])
        self.assertEqual(self.catalog.seed()['local_texts_imported'], 0)
        self.assertEqual(len(self.catalog.kb.sources()), 2)

    def test_declared_edition_and_hash_preserved(self):
        import hashlib
        folder = self.manifests / 'regulations_texts'
        folder.mkdir()
        path = folder / 'test_act.txt'
        path.write_text('Документ редакции 2026 трубопровод', encoding='utf-8')
        self.record.update(content_kind='user_copy', edition_from_document='ред. от 03.03.2026; не сверена',
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.write_manifest()
        self.assertEqual(self.catalog.seed()['errors'], [])
        sid = self.catalog.records()[0]['imported_text_source_id']
        source = next(r for r in self.catalog.kb.sources() if r['id'] == sid)
        self.assertEqual(source['edition'], self.record['edition_from_document'])
        self.assertFalse(source['reviewed'])

    def test_hash_mismatch_does_not_import_file(self):
        folder = self.manifests / 'regulations_texts'
        folder.mkdir()
        (folder / 'test_act.txt').write_text('Подменённый текст', encoding='utf-8')
        self.record.update(content_kind='user_copy', sha256='0'*64)
        self.write_manifest()
        self.assertTrue(self.catalog.seed()['errors'])
        self.assertIsNone(self.catalog.records()[0]['imported_text_source_id'])

    def test_user_excluded_517_hidden_and_previous_sources_disabled(self):
        path = self.root / 'excluded.txt'
        path.write_text('исключаемый трубопровод', encoding='utf-8')
        sid = self.catalog.kb.import_file(path, reviewed=True)
        with self.catalog._db() as db:
            db.execute('INSERT INTO normative_catalog(act_id,record_json,source_id,imported_text_source_id) VALUES(?,?,?,?)',
                       ('FNP517', json.dumps({'id':'FNP517','title':'Старый 517'}), sid, sid))
        self.catalog.seed()
        self.assertNotIn('FNP517', [r['act_id'] for r in self.catalog.records()])
        self.assertEqual(self.catalog.kb.search('исключаемый'), [])
        self.assertFalse(next(s for s in self.catalog.kb.sources() if s['id']==sid)['active'])

    def test_local_path_escape_rejected(self):
        self.record['local_file'] = '../outside.txt'
        self.write_manifest()
        result = self.catalog.seed()
        self.assertTrue(any('regulations_texts' in e for e in result['errors']))
        self.assertIsNone(self.catalog.records()[0]['imported_text_source_id'])

    def test_official_host_allowlist_and_redirect_refusal(self):
        for url in ('https://pravo.gov.ru/path', 'https://publication.pravo.gov.ru/path', 'http://gosnadzor.ru/path'):
            self.assertEqual(official_url(url), url)
        for url in ('https://pravo.gov.ru.evil.test/path', 'https://evilpravo.gov.ru/path',
                    'https://user:pass@pravo.gov.ru/path', 'file:///tmp/act',
                    'https://pravo.gov.ru:8000/path', 'https://127.0.0.1/path'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                official_url(url)
        with self.assertRaises(ValueError):
            OfficialRedirects().redirect_request(None, None, 302, '', {}, 'https://evil.test/file.pdf')

    def test_nonofficial_url_refused_before_network(self):
        self.record['file_url'] = 'https://evil.test/rules.pdf'
        self.write_manifest()
        self.catalog.seed()
        with patch('regulations.build_opener') as opener:
            result = self.catalog.download_official('test_act')
        opener.assert_not_called()
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(result['source_id'])
        self.assertIsNone(self.catalog.records()[0]['downloaded_source_id'])

    def test_html_and_external_final_url_refused_no_kb_import(self):
        self.catalog.seed()
        for response in (self.response(b'<html>Not an act</html>', 'text/plain'),
                         self.response(b'<!DOCTYPE html>Not an act', 'application/pdf'),
                         self.response(b'text', 'text/html'),
                         self.response(b'Rules', final_url='https://evil.test/file.txt')):
            with patch('regulations.build_opener') as opener:
                opener.return_value.open.return_value = response
                result = self.catalog.download_official('test_act')
            self.assertEqual(result['status'], 'failed')
            self.assertIsNone(result['source_id'])
            self.assertEqual(len(self.catalog.kb.sources()), 1)
            self.assertTrue(self.catalog.records()[0]['last_error'])

    def test_mocked_official_text_remains_unreviewed_and_prior_copy_survives_failure(self):
        self.catalog.seed()
        with patch('regulations.build_opener') as opener:
            opener.return_value.open.return_value = self.response('Официальный тестовый файл трубопровод'.encode())
            result = self.catalog.download_official('test_act')
        self.assertEqual(result['status'], 'official_file_indexed')
        sid = result['source_id']
        source = next(s for s in self.catalog.kb.sources() if s['id'] == sid)
        self.assertFalse(source['reviewed'])
        self.assertIn('редакция не подтверждена', source['edition'])
        self.assertEqual(self.catalog.kb.search('трубопровод'), [])
        with patch('regulations.build_opener') as opener:
            opener.return_value.open.return_value = self.response(b'<html>Error</html>', 'text/html')
            self.assertEqual(self.catalog.download_official('test_act')['status'], 'failed')
        row = self.catalog.records()[0]
        self.assertEqual(row['downloaded_source_id'], sid)
        self.assertTrue(row['last_error'])
        self.assertFalse(row['normative_validation'])


if __name__ == '__main__':
    unittest.main()
