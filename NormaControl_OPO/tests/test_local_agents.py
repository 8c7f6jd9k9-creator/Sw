"""Integration checks with a loopback HTTP stub; no real model generation."""
import json
import socket
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from core import Store
from local_agents import AgentService, ROLES

BASE = Path(__file__).resolve().parents[1]


class LocalAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'data', BASE / 'registry.json')
        self.service = AgentService(self.store)
        self.calls = []
        self.responses = {
            '/api/tags': {'models': [{'name': 'local:test'}, {'name': 'remote-cloud'}, {'name': 'local:test'}]},
            '/api/show': {'capabilities': ['completion'], 'model_info': {'general.architecture': 'test'}},
            '/api/chat': {'message': {'content': 'Ответ HTTP-заглушки'}, 'done': True},
        }
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def respond(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                owner.calls.append((self.path, json.loads(body) if body else None))
                reply = owner.responses[self.path]
                status = 200
                if isinstance(reply, tuple):
                    status, reply = reply
                encoded = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = 'http://127.0.0.1:' + str(self.server.server_port)
        self.service.save_settings(self.endpoint, 'local:test')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.store.close()
        self.temp.cleanup()

    def test_list_and_individual_role_dispatch(self):
        self.assertEqual(self.service.list_models(), ['local:test'])
        for role in ROLES:
            before = len(self.calls)
            self.assertEqual(self.service.run(role, 'Контрольная задача', 'Контрольный контекст'), 'Ответ HTTP-заглушки')
            calls = self.calls[before:]
            self.assertEqual([p for p, _ in calls], ['/api/show', '/api/chat'])
            payload = calls[-1][1]
            self.assertIn(ROLES[role]['instructions'], payload['messages'][0]['content'])
            self.assertIn('Контрольный контекст', payload['messages'][1]['content'])
            self.assertEqual(payload['model'], 'local:test')
            self.assertFalse(payload['stream'])

    def test_team_dispatch_and_coordinator_receives_specialist_results(self):
        result = self.service.run('coordinator', 'Проверка команды', 'Данные', team=True)
        chats = [payload for path, payload in self.calls if path == '/api/chat']
        self.assertEqual(len(chats), 5)
        for payload, role in zip(chats, ('developer', 'ui', 'qa', 'regulatory', 'coordinator')):
            self.assertIn(ROLES[role]['instructions'], payload['messages'][0]['content'])
        synthesis_input = chats[-1]['messages'][1]['content']
        for role in ('developer', 'ui', 'qa', 'regulatory'):
            self.assertIn(ROLES[role]['name'], synthesis_input)
            self.assertIn(ROLES[role]['name'], result)
        self.assertIn('Ответ HTTP-заглушки', synthesis_input)
        self.assertEqual(self.service.history(), [])

    def test_named_cloud_models_rejected_without_http(self):
        for name in ('model:cloud', 'model-cloud', 'MODEL:CLOUD'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.service.save_settings(self.endpoint, name)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.service.settings()['model'], 'local:test')

    def test_alias_remote_metadata_rejected_before_chat(self):
        for metadata in (
            {'capabilities': ['completion'], 'remote_host': 'https://ollama.com'},
            {'capabilities': ['completion'], 'details': {'remote_model': 'hidden-alias'}},
            {'capabilities': ['completion'], 'model': 'secret:cloud'},
            {'capabilities': ['embedding']},
        ):
            with self.subTest(metadata=metadata):
                self.responses['/api/show'] = metadata
                self.calls.clear()
                with self.assertRaises(ValueError):
                    self.service.run('qa', 'Задача', 'Данные')
                self.assertEqual([p for p, _ in self.calls], ['/api/show'])

    def test_external_endpoint_rejected_before_requests(self):
        saved = self.service.settings()
        for endpoint in ('https://127.0.0.1:11434', 'http://example.com:11434',
                         'http://192.168.0.1:11434', 'http://127.0.0.1.evil.test',
                         self.endpoint + '/api', 'http://user:pass@127.0.0.1:11434'):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    self.service.save_settings(endpoint, 'local:test')
                with self.assertRaises(ValueError):
                    self.service.list_models(endpoint)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.service.settings(), saved)

    def test_malformed_server_and_chat_errors_are_reported(self):
        for reply in (b'not JSON', b'\xff', [], {'models': 'wrong'}, (503, {'error': 'unavailable'})):
            with self.subTest(reply=reply):
                self.responses['/api/tags'] = reply
                with self.assertRaises(ValueError):
                    self.service.list_models()
        for reply in ({'message': {}}, {'message': {'content': 12}}, {'error': 'failed'}, b'{'):
            with self.subTest(reply=reply):
                self.responses['/api/chat'] = reply
                with self.assertRaises(ValueError):
                    self.service.run('qa', 'Задача', 'Данные')
        self.assertEqual(self.service.history(), [])

    def test_unavailable_loopback_server(self):
        # Reserve a port without listening: deterministic connection refusal.
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            endpoint = 'http://127.0.0.1:' + str(sock.getsockname()[1])
            with self.assertRaisesRegex(ValueError, 'Не удалось связаться'):
                self.service.list_models(endpoint)
        self.assertEqual(self.calls, [])

    def test_context_is_non_mutating_and_includes_assets_cauk_and_metadata(self):
        source = self.root / 'source.txt'
        source.write_text('BINARY_FILE_CONTENT_MUST_NOT_BE_READ', encoding='utf-8')
        self.store.add_document(19, source, 'Документ для ОПО 19')
        before = list(self.store.db.iterdump())
        context = self.service.build_context()
        cards = context.split('Реестр ОПО: ', 1)[1].split('\n', 1)[0]
        self.assertEqual(len(json.loads(cards)), 33)
        self.assertIn('Проверка ЦАУК:', context)
        self.assertIn('октябрь 2026', context)
        one = self.service.build_context(19)
        self.assertIn('Документ для ОПО 19', one)
        self.assertIn('Вопросы и записи ответов ОПО 19:', one)
        self.assertNotIn('BINARY_FILE_CONTENT_MUST_NOT_BE_READ', one)
        self.assertEqual(list(self.store.db.iterdump()), before)
        with self.assertRaises(ValueError):
            self.service.build_context(999)
        self.assertEqual(self.calls, [])

    def test_settings_history_restart_and_backup(self):
        success = self.service.save_run('qa', 'Задача', 'local:test', 'Контекст', 'Сохранённый ответ')
        failed = self.service.save_run('regulatory', 'Ошибка', 'local:test', 'Контекст', '', 'Не удалось связаться')
        settings = self.service.settings()
        self.store.close()
        self.store = Store(self.root / 'data', BASE / 'registry.json')
        self.service = AgentService(self.store)
        self.assertEqual(self.service.settings(), settings)
        self.assertEqual([r['id'] for r in self.service.history()], [failed, success])
        self.assertEqual(self.service.history()[0]['error'], 'Не удалось связаться')
        self.assertEqual(self.service.history()[1]['result'], 'Сохранённый ответ')
        backup = self.root / 'backup.zip'
        self.store.backup(backup)
        with zipfile.ZipFile(backup) as archive:
            archive.extractall(self.root / 'restore')
        restored = Store(self.root / 'restore')
        try:
            other = AgentService(restored)
            self.assertEqual(other.settings(), settings)
            self.assertEqual(other.history(), self.service.history())
            self.assertEqual(len(restored.assets()), 33)
            self.assertEqual(restored.cauk_plans()[0]['name'], 'октябрь 2026')
        finally:
            restored.close()

    def test_utf8_request_budget_and_visible_truncation_warning(self):
        self.responses['/api/chat'] = {'message': {'content': 'А' * 20000}}
        result = self.service.run('coordinator', 'Задача 🧪' * 2000, 'Контекст Ж' * 15000, team=True)
        chats = [payload for path, payload in self.calls if path == '/api/chat']
        self.assertEqual(len(chats), 5)
        for payload in chats:
            total = sum(len(message['content'].encode('utf-8')) for message in payload['messages'])
            self.assertLessEqual(total, 11000)
            self.assertEqual(payload['options']['num_ctx'], 16384)
            self.assertEqual(payload['options']['num_predict'], 4096)
            self.assertIn('[ОБРЕЗАНО:', payload['messages'][1]['content'])
        self.assertIn('Контекст запроса был обрезан', result)
        self.assertIn('СИНТЕЗ КООРДИНАТОРА', result)

    def test_output_token_limit_warning(self):
        self.responses['/api/chat'] = {'message': {'content': 'Часть ответа'}, 'done_reason': 'length'}
        result = self.service.run('qa', 'Задача', 'Данные')
        self.assertIn('Часть ответа', result)
        self.assertIn('модель достигла предела генерации', result)

    def test_exact_citation_ids_warn_on_unprovided_fragment(self):
        self.responses['/api/chat'] = {'message': {'content': 'Вывод [К1-Ф1]'}}
        result = self.service.run('regulatory', 'Задача', 'Фрагмент [К1-Ф1] проверяемый текст')
        self.assertNotIn('ПРОВЕРКА ССЫЛОК', result)
        self.responses['/api/chat'] = {'message': {'content': 'Вывод [К1-Ф2]'}}
        result = self.service.run('regulatory', 'Задача', 'Фрагмент [К1-Ф1] проверяемый текст')
        self.assertIn('ПРОВЕРКА ССЫЛОК', result)
        self.assertIn('[К1-Ф2]', result)
        self.assertIn('не подтверждены', result)

    def test_bad_role_and_empty_task_rejected_before_http(self):
        for role, task in (('missing', 'Задача'), ('qa', '   ')):
            with self.assertRaises(ValueError):
                self.service.run(role, task, 'Контекст')
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
