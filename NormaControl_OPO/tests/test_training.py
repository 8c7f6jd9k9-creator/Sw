import importlib.metadata
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from training import TrainingStore, import_model


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.training = TrainingStore(self.root / 'data')

    def tearDown(self):
        self.temp.cleanup()

    def examples(self):
        self.training.add_example('Задача обучения', 'Контекст', 'Эталон', '[К1-Ф1]', True, 'train')
        self.training.add_example('Проверочная задача', 'Контекст', 'Проверочный эталон', '[К1-Ф2]', True, 'validation')
        self.training.add_example('Не проверено', '', 'Не экспортировать')

    def model(self):
        model = self.root / 'local_model'
        model.mkdir()
        (model / 'config.json').write_text('{}')
        return model

    def test_reviewed_only_export_and_persistence(self):
        self.examples()
        result = self.training.export_dataset(self.root / 'dataset')
        self.assertEqual(result['counts'], {'train': 1, 'validation': 1})
        for split in ('train', 'validation'):
            rows = [json.loads(line) for line in Path(result[split]).read_text(encoding='utf-8').splitlines()]
            self.assertTrue(all(r['reviewed'] for r in rows))
            self.assertEqual({r['split'] for r in rows}, {split})
        self.assertEqual(TrainingStore(self.root / 'data').examples(), self.training.examples())
        row = self.training.examples()[-1]
        self.training.update_example(row['id'], row['task'], row['context'], row['answer'], '', True, 'train')
        self.assertEqual(self.training.export_dataset(self.root / 'dataset')['train_count'], 2)

    def test_examples_and_jobs_survive_store_backup(self):
        import zipfile
        from core import Store
        store = Store(self.root / 'data', Path(__file__).resolve().parents[1] / 'registry.json')
        try:
            self.examples()
            process = Mock()
            process.poll.return_value = 1
            process.returncode = 1
            with patch('training.subprocess.Popen', return_value=process):
                self.training.run_training(self.model(), self.root / 'failed_job')
            backup = self.root / 'backup.zip'
            store.backup(backup)
            with zipfile.ZipFile(backup) as archive:
                archive.extractall(self.root / 'restore')
            restored = TrainingStore(self.root / 'restore')
            self.assertEqual(restored.examples(), self.training.examples())
            self.assertEqual(restored.jobs(), self.training.jobs())
        finally:
            store.close()

    def test_split_leakage_case_and_whitespace_rejected(self):
        self.training.add_example('ABC task', 'Context', 'Answer', reviewed=True)
        self.training.add_example(' abc   TASK ', ' context ', 'Answer', reviewed=True, split='validation')
        with self.assertRaisesRegex(ValueError, 'Утечка'):
            self.training.export_dataset(self.root / 'dataset')
        self.assertFalse((self.root / 'dataset' / 'train.jsonl').exists())

    def test_conflicting_answers_and_invalid_examples(self):
        self.training.add_example('Task', 'Context', 'Answer', reviewed=True)
        self.training.add_example('Task', 'Context', 'Different', reviewed=True)
        with self.assertRaisesRegex(ValueError, 'Конфликт'):
            self.training.export_dataset(self.root / 'dataset')
        for task, answer, split in (('', 'a', 'train'), ('t', '', 'train'), ('t', 'a', 'test')):
            with self.assertRaises(ValueError):
                self.training.add_example(task, '', answer, split=split)

    def test_diagnostics_report_installed_versions(self):
        d = self.training.diagnostics()
        for name in ('torch', 'transformers', 'peft', 'safetensors'):
            try:
                actual = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                actual = None
            self.assertEqual(d[name], actual)
        self.assertIsInstance(d['cuda'], bool)
        self.assertIsInstance(d['mps'], bool)

    def test_local_model_required_and_existing_output_preserved(self):
        with patch('training.subprocess.Popen') as spawn:
            with self.assertRaises(ValueError):
                self.training.run_training('remote/model', self.root / 'out')
            model = self.model()
            output = self.root / 'output'
            output.mkdir()
            kept = output / 'keep.txt'
            kept.write_text('unchanged')
            with self.assertRaises(ValueError):
                self.training.run_training(model, output)
            self.assertEqual(kept.read_text(), 'unchanged')
            spawn.assert_not_called()

    def test_mocked_training_subprocess_failure_logged_offline(self):
        self.examples()
        model = self.model()
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1
        def spawn(*args, **kwargs):
            kwargs['stdout'].write('Missing training dependencies\n')
            return process
        with patch('training.subprocess.Popen', side_effect=spawn) as popen:
            result = self.training.run_training(model, self.root / 'out')
            self.assertEqual(result['status'], 'failed')
            self.assertIn('Missing training dependencies', result['error'])
            kwargs = popen.call_args.kwargs
            self.assertFalse(kwargs['shell'])
            for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE', 'OLLAMA_NO_CLOUD'):
                self.assertEqual(kwargs['env'][key], '1')
        jobs = TrainingStore(self.root / 'data').jobs()
        self.assertEqual(jobs[0]['status'], 'failed')
        self.assertTrue(jobs[0]['ended_at'])

    def test_zero_exit_without_result_is_failure(self):
        self.examples()
        process = Mock()
        process.poll.return_value = 0
        process.returncode = 0
        with patch('training.subprocess.Popen', return_value=process):
            result = self.training.run_training(self.model(), self.root / 'out')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('без result.json', result['error'])

    def test_mocked_gguf_and_hf_import_no_overwrite_and_offline(self):
        gguf = self.root / 'model.gguf'
        gguf.write_bytes(b'GGUF_TEST_PLACEHOLDER')
        hf = self.model()
        (hf / 'model.safetensors').write_bytes(b'TEST_PLACEHOLDER')
        for model in (gguf, hf):
            with patch('training.shutil.which', return_value='/mock/ollama'), patch('local_agents.request_json', return_value={'models': [{'name': 'existing:latest'}]}), patch('training.subprocess.run') as runner:
                with self.assertRaisesRegex(ValueError, 'уже установлена'):
                    import_model('existing', model)
                runner.assert_not_called()
            replies = [ {'models': []}, {'capabilities': ['completion'], 'details': {}}, {'models': [{'name': 'new:latest'}]} ]
            with patch('training.shutil.which', return_value='/mock/ollama'), patch('local_agents.request_json', side_effect=replies), patch('training.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'stub imported', '')) as runner:
                result = import_model('new', model)
                self.assertEqual(result['status'], 'imported')
                self.assertEqual(result['name'], 'new:latest')
                self.assertFalse(runner.call_args.kwargs['shell'])
                self.assertEqual(runner.call_args.kwargs['env']['OLLAMA_NO_CLOUD'], '1')
                self.assertEqual(list(model.parent.glob('Modelfile-*')), [])


if __name__ == '__main__':
    unittest.main()
