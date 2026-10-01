"""Техническая проверка конвейера дообучения без загрузки весов (1–3 минуты).

Создаёт крошечную случайную модель архитектуры Qwen2 (q_proj/v_proj) и
токенизатор, обученный локально на текстах комплекта, затем выполняет те же
шаги, что и программа: TrainingStore → train_lora.py (LoRA, held-out loss,
адаптер, объединённая модель) → evaluate_lora.py (ответы отдельно от loss).

Модель случайная: её ответы бессмысленны. Проверка подтверждает только, что
torch/transformers/peft установлены, CUDA видна, а файлы результата создаются.
Набор примеров технический (о самой программе), не правовой и не для эксплуатации.

    runtime\\python.exe -I -X utf8 tools\\lora_pipeline_check.py [--output ПАПКА]
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# Технические факты о программе, проверенные по исходному коду и README.
EXAMPLES = [
    ('Где по умолчанию хранится база новой установки?', '%LOCALAPPDATA%\\NormaControlOPO'),
    ('Какой адрес у локального сервера Ollama?', 'http://127.0.0.1:11434'),
    ('Как создать резервную копию?', 'Кнопкой «Резервная копия»; файл сохраняется вне папки данных.'),
    ('Какая модель предлагается для локальных ответов?', 'qwen2.5:14b; при нехватке памяти qwen2.5:7b.'),
    ('Кто фиксирует риск в ситуационной проверке?', 'Специалист; подбор источников не устанавливает нарушение.'),
    ('Какие языки нужны Tesseract?', 'rus и eng.'),
    ('Какой лимит размера файла базы знаний?', '32 МБ.'),
    ('Сколько страниц PDF извлекается?', 'Не более 150 страниц.'),
    ('Как называется вкладка для ситуаций?', 'Ситуационные проверки.'),
    ('Сколько ОПО в реестре?', '33.'),
    ('Сколько вопросов ЦАУК?', '330.'),
    ('Какой приказ исключён из комплекта?', '№517.'),
    ('Как обозначается ссылка на фрагмент?', '[Кномер-Фномер].'),
    ('Отправляются ли документы в облако?', 'Нет, модели работают только через loopback 127.0.0.1.'),
    ('Какие модули LoRA обучаются?', 'q_proj и v_proj.'),
    ('Что подтверждает validation loss?', 'Только близость к эталонам, не правовую точность.'),
]


def corpus_text(limit=400000):
    parts = []
    w = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    for path in sorted((BASE / 'regulations_texts').rglob('*.docx')):
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
        parts.append('\n'.join(''.join(t.text or '' for t in p.iter(w + 't')) for p in root.iter(w + 'p')))
        if sum(map(len, parts)) > limit:
            break
    parts += [q + '\n' + a for q, a in EXAMPLES]
    return '\n'.join(parts)[:limit]


def tiny_model(folder):
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
    from transformers import PreTrainedTokenizerFast, Qwen2Config, Qwen2ForCausalLM
    specials = ['<|endoftext|>', '<|im_start|>', '<|im_end|>']
    tokenizer = Tokenizer(models.BPE(unk_token=None))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    tokenizer.train_from_iterator([corpus_text()], trainers.BpeTrainer(vocab_size=3000, special_tokens=specials,
                                                                       initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    fast = PreTrainedTokenizerFast(tokenizer_object=tokenizer, eos_token='<|im_end|>', pad_token='<|endoftext|>')
    fast.chat_template = ("{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}<|im_end|>\n{% endfor %}"
                          "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}")
    config = Qwen2Config(vocab_size=len(fast), hidden_size=64, intermediate_size=128, num_hidden_layers=2,
                         num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=1024,
                         eos_token_id=fast.eos_token_id, pad_token_id=fast.pad_token_id, tie_word_embeddings=True)
    model = Qwen2ForCausalLM(config)
    model.save_pretrained(str(folder), safe_serialization=True)
    fast.save_pretrained(str(folder))
    return sum(p.numel() for p in model.parameters())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='папка результата (по умолчанию временная)')
    parser.add_argument('--epochs', type=int, default=3)
    args = parser.parse_args()
    from training import TrainingStore
    work = Path(args.output).resolve() if args.output else Path(tempfile.mkdtemp(prefix='normacontrol_lora_check_'))
    work.mkdir(parents=True, exist_ok=True)
    report = {'warning': 'Случайная крошечная модель: проверяется конвейер, а не качество ответов.'}
    begin = time.monotonic()
    report['tiny_model_parameters'] = tiny_model(work / 'tiny_base')
    store = TrainingStore(work / 'db')
    for index, (task, answer) in enumerate(EXAMPLES):
        store.add_example(task, '', answer, 'исходный код и README_RU.md', reviewed=True,
                          split='validation' if index % 4 == 3 else 'train')
    report['diagnostics'] = store.diagnostics()
    result = store.run_training(work / 'tiny_base', work / 'result', epochs=args.epochs, max_length=128)
    report['training'] = {k: result.get(k) for k in ('status', 'error', 'adapter_dir', 'merged_model_dir', 'device')}
    report['loss'] = {k: (result.get('metrics') or {}).get(k) for k in ('base_validation_loss', 'adapter_validation_loss', 'loss_difference_adapter_minus_base')}
    report['loss']['train_loss_by_epoch'] = [round(e['train_loss_mean_examples'], 4) for e in (result.get('metrics') or {}).get('epochs', [])]
    if result.get('status') == 'completed':
        proc = subprocess.run([sys.executable, str(BASE / 'evaluate_lora.py'), '--base-dir', str(work / 'tiny_base'),
                               '--tuned-dir', result['merged_model_dir'], '--validation', str(work / 'result' / 'dataset' / 'validation.jsonl'),
                               '--output', str(work / 'result' / 'answer_eval'), '--max-new-tokens', '24'],
                              capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=1800)
        evaluation = work / 'result' / 'answer_eval' / 'answer_eval.json'
        report['answer_evaluation'] = json.loads(evaluation.read_text(encoding='utf-8')) if evaluation.is_file() else {'error': proc.stdout[-2000:] + proc.stderr[-2000:]}
        report['answer_evaluation'].pop('examples', None)
        report['files'] = sorted(str(p.relative_to(work)) for p in (work / 'result').rglob('*') if p.is_file() and 'checkpoint' not in str(p))
    report['seconds'] = round(time.monotonic() - begin, 1)
    report['work_dir'] = str(work)
    (work / 'pipeline_check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['training']['status'] == 'completed' and 'error' not in report.get('answer_evaluation', {'error': 1}) else 1


if __name__ == '__main__':
    sys.exit(main())
