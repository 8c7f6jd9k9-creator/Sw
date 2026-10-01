"""Offline supervised LoRA. Launch via training.TrainingStore, never from the UI thread.
Loss is measured on a fixed held-out set; it does not certify factual/legal quality.
Requires locally installed torch, transformers, peft and safetensors; no download.
"""
import argparse
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys

for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY'):
    os.environ[key] = '1'


def message(text):
    print(text, flush=True)


def read_examples(path):
    with Path(path).open(encoding='utf-8') as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    if not rows:
        raise ValueError('Набор пуст: ' + str(path))
    for row in rows:
        if not row.get('reviewed') or not str(row.get('answer', '')).strip() or not str(row.get('task', '')).strip():
            raise ValueError('Обучение разрешено только на подтверждённых эталонных примерах.')
    return rows


def input_key(row):
    return tuple(' '.join(str(row.get(key, '')).split()).casefold() for key in ('task', 'context'))


def encode_example(tokenizer, row, maximum):
    """Keep the full answer and EOS; trim only prompt, or fail on oversize target."""
    task = row['task']
    context = row.get('context', '')
    user_text = task + ('\n\nКонтекст:\n' + context if context else '')
    if getattr(tokenizer, 'chat_template', None):
        prompt = tokenizer.apply_chat_template([{'role': 'user', 'content': user_text}],
                                              tokenize=False, add_generation_prompt=True)
        prefix = tokenizer.encode(prompt, add_special_tokens=False)
    else:
        prompt = 'Задача:\n' + task + '\nКонтекст:\n' + context + '\nОтвет:\n'
        prefix = tokenizer.encode(prompt, add_special_tokens=True)
    target = tokenizer.encode(row['answer'], add_special_tokens=False)
    if not target:
        raise ValueError('Эталонный ответ не содержит токенов.')
    if tokenizer.eos_token_id is not None:
        target.append(tokenizer.eos_token_id)
    if len(target) >= maximum:
        raise ValueError('Ответ примера %s имеет %s токенов: увеличьте max_length (%s). Ответ не обрезается.' % (row.get('id', '?'), len(target), maximum))
    available = maximum - len(target)
    truncated = len(prefix) > available
    # Keep leading task and trailing assistant marker when context exceeds the window.
    if truncated:
        if available == 1:
            prefix = prefix[-1:]
        else:
            head = max(1, available // 2)
            prefix = prefix[:head] + prefix[-(available-head):]
    if not prefix:
        raise ValueError('Промпт пуст после токенизации.')
    ids = prefix + target
    labels = [-100] * len(prefix) + target
    return {'input_ids': ids, 'labels': labels, 'truncated_prompt': truncated,
            'target_tokens': len(target), 'id': row.get('id')}


def run(args):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, TaskType, get_peft_model, PeftModel
    if not 1 <= args.epochs <= 20 or not 64 <= args.max_length <= 8192:
        raise ValueError('Некорректные epochs/max_length.')
    base_path = Path(args.model_dir).resolve()
    output = Path(args.output_dir).resolve()
    if not base_path.is_dir() or not (base_path / 'config.json').is_file():
        raise ValueError('Нужна локальная модель Hugging Face; GGUF для обучения не поддерживается.')
    if base_path == output or base_path in output.parents or output in base_path.parents:
        raise ValueError('Папки модели и результата должны быть раздельными.')
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ('adapter', 'merged_model', 'result.json')):
        raise ValueError('Результат уже существует. Используйте новую папку.')
    train_rows = read_examples(args.train)
    val_rows = read_examples(args.validation)
    if {input_key(r) for r in train_rows} & {input_key(r) for r in val_rows}:
        raise ValueError('Утечка: совпадение задачи/контекста между train и validation.')
    for rows, split in ((train_rows, 'train'), (val_rows, 'validation')):
        seen = {}
        for row in rows:
            if row.get('split') != split:
                raise ValueError('Неверная принадлежность примера набору: ' + split)
            key = input_key(row)
            if key in seen:
                raise ValueError('Дублирующийся ввод в наборе ' + split)
            seen[key] = row['answer']
    random.seed(42)
    torch.manual_seed(42)
    device = torch.device('cuda' if torch.cuda.is_available() else
                          'mps' if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() else 'cpu')
    # Float32 avoids unsupported FP16 training on CPU/MPS. BF16 only on supported CUDA.
    dtype = torch.bfloat16 if device.type == 'cuda' and torch.cuda.is_bf16_supported() else torch.float32
    message('Устройство: %s; dtype: %s. Загрузка только локальных файлов.' % (device, dtype))
    tokenizer = AutoTokenizer.from_pretrained(str(base_path), local_files_only=True, trust_remote_code=False)
    training = [encode_example(tokenizer, row, args.max_length) for row in train_rows]
    validation = [encode_example(tokenizer, row, args.max_length) for row in val_rows]
    message('Train: %s, validation: %s; усечённых промптов: %s; ответы сохранены полностью.' %
            (len(training), len(validation), sum(r['truncated_prompt'] for r in training + validation)))
    base = AutoModelForCausalLM.from_pretrained(str(base_path), local_files_only=True,
                                               trust_remote_code=False, torch_dtype=dtype)
    base.config.use_cache = False
    base.to(device)
    available = {name.rsplit('.', 1)[-1] for name, _ in base.named_modules()}
    if not {'q_proj', 'v_proj'}.issubset(available):
        raise ValueError('Эта архитектура не содержит q_proj/v_proj. Для неё требуется отдельная конфигурация LoRA; автоматическая подмена запрещена.')

    def tensor_batch(row):
        ids = torch.tensor([row['input_ids']], dtype=torch.long, device=device)
        labels = torch.tensor([row['labels']], dtype=torch.long, device=device)
        return {'input_ids': ids, 'attention_mask': torch.ones_like(ids), 'labels': labels}

    def evaluate(model):
        model.eval()
        loss_sum, token_count = 0.0, 0
        with torch.no_grad():
            for row in validation:
                loss = float(model(**tensor_batch(row)).loss.detach().float().cpu())
                if not math.isfinite(loss):
                    raise ValueError('Validation loss не является конечным числом.')
                # Causal loss shifts labels; prompt has at least one token.
                count = sum(label != -100 for label in row['labels'][1:])
                loss_sum += loss * count
                token_count += count
        return loss_sum / token_count

    message('Оценка исходной модели на независимой validation выборке.')
    base_loss = evaluate(base)
    message('Base validation loss: %.6f' % base_loss)
    config = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
                        target_modules=['q_proj', 'v_proj'], bias='none', task_type=TaskType.CAUSAL_LM)
    model = get_peft_model(base, config)
    parameters = [p for p in model.parameters() if p.requires_grad]
    if not parameters:
        raise ValueError('Не найдены обучаемые параметры LoRA.')
    optimizer = torch.optim.AdamW(parameters, lr=2e-4)
    history = []
    order = list(range(len(training)))
    for epoch in range(args.epochs):
        model.train()
        random.shuffle(order)
        summed = 0.0
        for step, index in enumerate(order, 1):
            optimizer.zero_grad(set_to_none=True)
            loss = model(**tensor_batch(training[index])).loss
            if not bool(torch.isfinite(loss).item()):
                raise ValueError('Train loss не является конечным числом; остановлено.')
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters, 1.0)
            optimizer.step()
            summed += float(loss.detach().float().cpu())
            message('Эпоха %s/%s; шаг %s/%s; loss %.6f' % (epoch+1, args.epochs, step, len(order), float(loss.detach().float().cpu())))
        val_loss = evaluate(model)
        checkpoint = output / ('checkpoint-epoch-%s' % (epoch+1))
        model.save_pretrained(str(checkpoint), safe_serialization=True)
        tokenizer.save_pretrained(str(checkpoint))
        history.append({'epoch': epoch+1, 'train_loss_mean_examples': summed / len(training),
                        'validation_loss': val_loss, 'checkpoint': str(checkpoint)})
        message('Validation loss после эпохи %s: %.6f' % (epoch+1, val_loss))
    adapter_path = output / 'adapter'
    model.save_pretrained(str(adapter_path), safe_serialization=True)
    tokenizer.save_pretrained(str(adapter_path))
    final_loss = history[-1]['validation_loss']
    metrics = {'base_validation_loss': base_loss, 'adapter_validation_loss': final_loss,
               'loss_difference_adapter_minus_base': final_loss-base_loss,
               'validation_examples': len(validation), 'train_examples': len(training),
               'validation_sha256': hashlib.sha256(Path(args.validation).read_bytes()).hexdigest(),
               'epochs': history, 'prompt_truncated_count': sum(r['truncated_prompt'] for r in training+validation),
               'quality_note': 'Loss на фиксированной validation выборке; не оценка правовой точности и не гарантия улучшения ответов.'}
    metrics_path = output / 'evaluation.json'
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    # Release optimizer and trained model before loading a clean base for merging.
    del optimizer, parameters, model, base, loss
    gc.collect()
    if device.type == 'cuda':
        torch.cuda.empty_cache()
    elif device.type == 'mps':
        torch.mps.empty_cache()
    message('Адаптер сохранён. Объединение с чистой исходной моделью на CPU.')
    fresh_base = AutoModelForCausalLM.from_pretrained(str(base_path), local_files_only=True,
                                                     trust_remote_code=False, torch_dtype=dtype)
    merge_model = PeftModel.from_pretrained(fresh_base, str(adapter_path), local_files_only=True,
                                            is_trainable=False)
    merged = merge_model.merge_and_unload(safe_merge=True)
    merged.config.use_cache = True
    merged_path = output / 'merged_model'
    merged.save_pretrained(str(merged_path), safe_serialization=True, max_shard_size='2GB')
    tokenizer.save_pretrained(str(merged_path))
    result = {'adapter_dir': str(adapter_path), 'merged_model_dir': str(merged_path),
              'evaluation_path': str(metrics_path), 'metrics': metrics, 'device': str(device),
              'base_model_dir': str(base_path)}
    (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    message('Обучение и объединение завершены. Импорт в Ollama — отдельное действие.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--train', required=True)
    parser.add_argument('--validation', required=True)
    parser.add_argument('--epochs', type=int, default=1)
    parser.add_argument('--max-length', type=int, default=512)
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        message('ОШИБКА: %s: %s' % (type(exc).__name__, exc))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
