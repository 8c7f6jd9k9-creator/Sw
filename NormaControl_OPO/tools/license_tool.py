"""Инструмент издателя: запись лицензии НормаКонтроль ОПО на USB-флешку.

Входит только в комплект издателя вместе с закрытым ключом. В архив программы
и на флешки клиентов не передаётся.

    python license_tool.py                       — пошаговый режим
    python license_tool.py drives                — USB-накопители и их лицензии
    python license_tool.py issue --drive E: --licensee "ООО Пример" [--expires 2027-12-31] [--note ...]
    python license_tool.py verify [--drive E:]   — проверка так же, как в программе
    python license_tool.py keygen --out новый_ключ.json — новый ключ (нужна пересборка программы)
"""
import argparse
import csv
import json
import os
import secrets
import stat
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for candidate in (HERE.parent, HERE.parent / 'NormaControl_OPO'):
    if (candidate / 'usb_license.py').is_file():
        sys.path.insert(1, str(candidate))

import nc_ed25519  # noqa: E402
import usb_license  # noqa: E402

DEFAULT_KEY = HERE / 'NormaControl_vendor_key.json'
REGISTRY = HERE / 'issued_licenses.csv'


def load_key(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    seed = bytes.fromhex(data['private_seed_hex'])
    public = nc_ed25519.public_key(seed).hex()
    if public != data.get('public_key_hex'):
        raise SystemExit('Файл ключа повреждён: открытый ключ не соответствует закрытому.')
    if usb_license.PUBLIC_KEYS.get(data['key_id']) != public:
        raise SystemExit('Этот ключ ({}) не встроен в данную сборку программы: лицензия не будет принята.'.format(data['key_id']))
    return data['key_id'], seed


def masked(serial):
    serial = str(serial or '')
    return (serial[:3] + '…' + serial[-3:]) if len(serial) > 8 else ('есть' if serial else 'НЕТ')


def find_drive(letter):
    letter = letter.strip().rstrip(':\\/').upper()
    for drive in usb_license.list_usb_drives():
        if drive.root.upper().startswith(letter + ':'):
            return drive
    raise SystemExit('USB-накопитель {}: не найден. Команда drives покажет подключённые накопители.'.format(letter))


def cmd_drives(_args=None):
    drives = usb_license.list_usb_drives()
    if not drives:
        print('USB-накопители не найдены.')
        return 1
    for d in drives:
        status = usb_license.find_license([d])
        lic = 'лицензия: ' + (status.payload['licensee'] + ', ' + status.payload['license_id'] if status.ok else ('нет файла' if not (Path(d.root) / usb_license.LICENSE_FILE).exists() else status.reason))
        print('{}  {} {}  метка «{}»  серийный номер: {}  {}'.format(d.root, d.vendor, d.product, d.label, masked(d.serial), lic))
    return 0


def issue(drive, key_id, seed, licensee, expires='', note='', license_id='', force=False, today=None):
    if not drive.serial:
        raise SystemExit('У этой флешки нет серийного номера USB: привязка невозможна. Используйте другую флешку.')
    if not str(licensee).strip():
        raise SystemExit('Укажите владельца лицензии.')
    if expires:
        date.fromisoformat(expires)
    target = Path(drive.root) / usb_license.LICENSE_FILE
    if target.exists() and not force:
        raise SystemExit('На флешке уже есть {}. Для перезаписи добавьте --force.'.format(usb_license.LICENSE_FILE))
    today = today or date.today()
    payload = {'product': usb_license.PRODUCT, 'product_major': usb_license.PRODUCT_MAJOR,
               'license_id': license_id or 'NC-{:%Y%m%d}-{}'.format(today, secrets.token_hex(3).upper()),
               'licensee': str(licensee).strip(), 'issued': today.isoformat(), 'expires': expires or '',
               'device': {'bus': 'USB', 'vendor': drive.vendor, 'product': drive.product,
                          'serial': drive.serial, 'volume_serial': drive.volume_serial},
               'note': str(note).strip()}
    document = usb_license.sign_document(payload, seed, key_id)
    temporary = target.with_name(target.name + '.tmp')
    if target.exists():
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)
    os.chmod(target, stat.S_IREAD)  # только чтение: защита от случайного удаления
    status = usb_license.find_license([drive])
    if not status.ok:
        raise SystemExit('Лицензия записана, но проверка не пройдена: ' + status.reason)
    new = not REGISTRY.exists()
    with REGISTRY.open('a', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, delimiter=';')
        if new:
            writer.writerow(['дата', 'номер лицензии', 'владелец', 'срок', 'флешка', 'серийный номер', 'том', 'примечание'])
        writer.writerow([datetime.now().isoformat(timespec='seconds'), payload['license_id'], payload['licensee'],
                         payload['expires'] or 'бессрочно', drive.vendor + ' ' + drive.product, drive.serial, drive.volume_serial, payload['note']])
    return payload


def cmd_issue(args):
    key_id, seed = load_key(args.key)
    payload = issue(find_drive(args.drive), key_id, seed, args.licensee, args.expires or '', args.note or '', args.id or '', args.force)
    print('Лицензия {} записана на {} для «{}», срок: {}. Запись добавлена в {}.'.format(
        payload['license_id'], args.drive, payload['licensee'], payload['expires'] or 'бессрочно', REGISTRY.name))
    return 0


def cmd_verify(args):
    drives = [find_drive(args.drive)] if args.drive else None
    status = usb_license.find_license(drives)
    print(json.dumps(status.public(), ensure_ascii=False, indent=2))
    return 0 if status.ok else 1


def cmd_keygen(args):
    out = Path(args.out)
    if out.exists():
        raise SystemExit('Файл уже существует: ' + str(out))
    seed = secrets.token_bytes(32)
    key_id = args.key_id or 'nc-{:%Y%m%d}'.format(date.today())
    out.write_text(json.dumps({'format': 'NormaControl-OPO-vendor-key-v1', 'key_id': key_id,
                               'created': datetime.now().isoformat(timespec='seconds'), 'private_seed_hex': seed.hex(),
                               'public_key_hex': nc_ed25519.public_key(seed).hex(),
                               'warning': 'ЗАКРЫТЫЙ КЛЮЧ ИЗДАТЕЛЯ. Не передавайте, не кладите в папку программы и на флешки клиентов.'},
                              ensure_ascii=False, indent=2), encoding='utf-8')
    print('Создан ключ {}. Открытый ключ нужно встроить в usb_license.PUBLIC_KEYS и пересобрать программу.'.format(key_id))
    return 0


def interactive():
    print('НормаКонтроль ОПО — выдача лицензии на USB-флешку\n')
    key_id, seed = load_key(DEFAULT_KEY)
    if cmd_drives():
        return 1
    letter = input('\nБуква флешки для лицензии (например, E): ').strip()
    drive = find_drive(letter)
    licensee = input('Владелец лицензии (организация / подразделение): ').strip()
    expires = input('Срок действия ГГГГ-ММ-ДД (пусто — бессрочно): ').strip()
    note = input('Примечание (необязательно): ').strip()
    force = False
    if (Path(drive.root) / usb_license.LICENSE_FILE).exists():
        force = input('На флешке уже есть лицензия. Перезаписать? (да/нет): ').strip().lower() in ('да', 'y', 'yes', 'д')
        if not force:
            return 1
    payload = issue(drive, key_id, seed, licensee, expires, note, '', force)
    print('\nГотово: лицензия {} для «{}», срок: {}.'.format(payload['license_id'], payload['licensee'], payload['expires'] or 'бессрочно'))
    print('Проверьте флешку на компьютере пользователя: Diagnostics_Windows.cmd покажет раздел license.')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('drives')
    p = sub.add_parser('issue')
    p.add_argument('--drive', required=True)
    p.add_argument('--licensee', required=True)
    p.add_argument('--expires')
    p.add_argument('--note')
    p.add_argument('--id')
    p.add_argument('--force', action='store_true')
    p.add_argument('--key', default=str(DEFAULT_KEY))
    p = sub.add_parser('verify')
    p.add_argument('--drive')
    p = sub.add_parser('keygen')
    p.add_argument('--out', required=True)
    p.add_argument('--key-id')
    args = parser.parse_args(argv)
    commands = {'drives': cmd_drives, 'issue': cmd_issue, 'verify': cmd_verify, 'keygen': cmd_keygen}
    if not args.command:
        return interactive()
    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
