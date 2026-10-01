"""Оценка ответов исходной и дообученной модели отдельно от loss (только локальные файлы).

Validation loss показывает, насколько модель «узнаёт» эталонные ответы, но не
говорит, правильны ли её собственные ответы. Этот скрипт генерирует ответы
обеих моделей на validation-выборке и считает простые проверяемые признаки:

- token_f1 — пересечение слов с эталоном;
- numbers_recall — доля чисел/дат/номеров пунктов эталона, которые есть в ответе
  (ошибка в числе для нормы критична);
- refs_recall и invented_refs — воспроизведение идентификаторов [Кn-Фm] из эталона
  и ссылки, которых не было ни в эталоне, ни в контексте.

Результат: answer_eval.json и answer_review.csv (лист для оценки специалистом).
Автоматические метрики не подтверждают юридическую правильность ответа.

    runtime\\python.exe -I -X utf8 evaluate_lora.py --base-dir ПАПКА_БАЗЫ
        --tuned-dir РЕЗУЛЬТАТ\\merged_model --validation РЕЗУЛЬТАТ\\dataset\\validation.jsonl
        --output РЕЗУЛЬТАТ\\answer_eval [--max-new-tokens 256]
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY'):
    os.environ[key] = '1'

REF = re.compile(r'\[К\d+-Ф\d+\]')
NUMBER = re.compile(r'\d+(?:[.,]\d+)*')
WORD = re.compile(r'\w+', re.UNICODE)


def normalize(text):
    return ' '.join(str(text).casefold().split())


def token_f1(answer, reference):
    a, r = WORD.findall(answer.casefold()), WORD.findall(reference.casefold())
    if not a or not r:
        return 0.0
    common = {}
    for token in r:
        common[token] = common.get(token, 0) + 1
    overlap = 0
    for token in a:
        if common.get(token):
            overlap += 1
            common[token] -= 1
    if not overlap:
        return 0.0
    precision, recall = overlap / len(a), overlap / len(r)
    return round(2 * precision * recall / (precision + recall), 4)


def score(answer, row):
    reference = row['answer']
    numbers = set(NUMBER.findall(reference))
    refs = set(REF.findall(reference))
    allowed = refs | set(REF.findall(row.get('context', ''))) | set(REF.findall(row.get('source_refs', '')))
    cited = set(REF.findall(answer))
    return {'exact': normalize(answer) == normalize(reference), 'token_f1': token_f1(answer, reference),
            'numbers_recall': round(len(numbers & set(NUMBER.findall(answer))) / len(numbers), 4) if numbers else None,
            'refs_recall': round(len(refs & cited) / len(refs), 4) if refs else None,
            'invented_refs': sorted(cited - allowed), 'empty': not answer.strip()}


def prompt_ids(tokenizer, row):
    # Тот же формат, что и при обучении (train_lora.encode_example).
    task, context = row['task'], row.get('context', '')
    user_text = task + ('\n\nКонтекст:\n' + context if context else '')
    if getattr(tokenizer, 'chat_template', None):
        prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': user_text}], tokenize=False, add_generation_prompt=True)
        return tokenizer.encode(prompt, add_special_tokens=False)
    return tokenizer.encode('Задача:\n' + task + '\nКонтекст:\n' + context + '\nОтвет:\n', add_special_tokens=True)


def generate(model_dir, rows, max_new_tokens, device, dtype):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False, torch_dtype=dtype)
    model.to(device).eval()
    answers, seconds = [], []
    for row in rows:
        ids = torch.tensor([prompt_ids(tokenizer, row)], dtype=torch.long, device=device)
        begin = time.monotonic()
        with torch.no_grad():
            output = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), max_new_tokens=max_new_tokens,
                                    do_sample=False, pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id)
        seconds.append(round(time.monotonic() - begin, 2))
        answers.append(tokenizer.decode(output[0][ids.shape[1]:], skip_special_tokens=True).strip())
    del model
    if device.type == 'cuda':
        torch.cuda.empty_cache()
    return answers, seconds


def summary(scores):
    def mean(key):
        values = [s[key] for s in scores if s[key] is not None]
        return round(sum(values) / len(values), 4) if values else None
    return {'examples': len(scores), 'exact_match': sum(s['exact'] for s in scores), 'token_f1_mean': mean('token_f1'),
            'numbers_recall_mean': mean('numbers_recall'), 'refs_recall_mean': mean('refs_recall'),
            'answers_with_invented_refs': sum(bool(s['invented_refs']) for s in scores), 'empty_answers': sum(s['empty'] for s in scores)}


def run(args):
    import torch
    rows = [json.loads(line) for line in Path(args.validation).read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows:
        raise ValueError('Validation-набор пуст.')
    if any(not r.get('reviewed') for r in rows):
        raise ValueError('Оценка выполняется только на подтверждённых специалистом примерах.')
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    dtype = torch.bfloat16 if device.type == 'cuda' and torch.cuda.is_bf16_supported() else torch.float32
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, folder in (('base', args.base_dir), ('tuned', args.tuned_dir)):
        print('Генерация:', label, flush=True)
        answers, seconds = generate(Path(folder), rows, args.max_new_tokens, device, dtype)
        scores = [score(a, r) for a, r in zip(answers, rows)]
        results[label] = {'model_dir': str(folder), 'answers': answers, 'seconds': seconds, 'scores': scores, 'summary': summary(scores)}
    report = {'device': str(device), 'validation': str(Path(args.validation).resolve()), 'max_new_tokens': args.max_new_tokens,
              'base': results['base']['summary'], 'tuned': results['tuned']['summary'],
              'note': 'Автоматические признаки не заменяют оценку специалиста: заполните answer_review.csv.',
              'examples': [{'id': r.get('id'), 'task': r['task'], 'reference': r['answer'],
                            'base_answer': results['base']['answers'][i], 'base_score': results['base']['scores'][i],
                            'tuned_answer': results['tuned']['answers'][i], 'tuned_score': results['tuned']['scores'][i]}
                           for i, r in enumerate(rows)]}
    (output / 'answer_eval.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / 'answer_review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerow(['id', 'задача', 'эталон', 'ответ_исходной', 'ответ_дообученной', 'f1_исходной', 'f1_дообученной',
                         'выдуманные_ссылки_дообученной', 'оценка_исходной_0-2', 'оценка_дообученной_0-2', 'замечания_специалиста'])
        for item in report['examples']:
            writer.writerow([item['id'], item['task'], item['reference'], item['base_answer'], item['tuned_answer'],
                             item['base_score']['token_f1'], item['tuned_score']['token_f1'],
                             ' '.join(item['tuned_score']['invented_refs']), '', '', ''])
    print(json.dumps({'base': report['base'], 'tuned': report['tuned']}, ensure_ascii=False, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-dir', required=True)
    parser.add_argument('--tuned-dir', required=True)
    parser.add_argument('--validation', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--max-new-tokens', type=int, default=256)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        print('ОШИБКА: %s: %s' % (type(exc).__name__, exc), flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
