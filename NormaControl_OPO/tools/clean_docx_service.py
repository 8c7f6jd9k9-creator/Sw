"""Очистка DOCX комплекта НД от служебных надписей справочных систем.

Инструмент сборки (нужен lxml; в программу и runtime не входит). Нумерация
блоков тела документа сохраняется: удалённый служебный блок заменяется пустым
абзацем, поэтому места «DOCX блок N» и ссылки [Кисточник-Ффрагмент],
созданные на прежней версии, указывают на тот же текст.

Удаляется: логотип и плашка «Документ предоставлен … / Дата сохранения»,
колонтитулы системы (номера страниц сохраняются), таблицы
«КонсультантПлюс: примечание.», строки сайтов-распространителей,
гиперссылки на сайты систем (текст ссылки остаётся), сведения о программе
выгрузки и авторе в docProps. Текст норм не переписывается.

    python tools/clean_docx_service.py ВХОД.docx ВЫХОД.docx
"""
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from service_text import BRAND_CHECK, NOTE_BLOCK, clean_text  # noqa: E402

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PR = 'http://schemas.openxmlformats.org/package/2006/relationships'
NS = {'w': W, 'r': R}
LOGO_SHA256 = {
    'ca6dbb70020b4f898db19280d335d5d25a2d068a7db06b8bc057cfb9672be135',  # логотип КонсультантПлюс
    'd7f1f3f781d2ed8c5f15921eab82ea4cca803ddf6d4d18c218a33bb6d0efc7f2',  # баннер сайта-распространителя
}
SERVICE_HOSTS = ('consultant.ru', 'garant.ru', 'cntd.ru', 'kodeks.ru', 'techexpert.ru',
                 'блог-инженера.рф', 'xn----9sbkdcdtfm5bf6gc.xn--p1ai')
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def _q(tag):
    prefix, name = tag.split(':')
    return '{%s}%s' % (NS[prefix], name)


def _text(element):
    return ''.join(t.text or '' for t in element.iter(_q('w:t')))


def _service_host(target):
    host = (urlsplit(target).hostname or '').lower().rstrip('.')
    try:
        host_unicode = host.encode('ascii').decode('idna')
    except (UnicodeError, ValueError):
        host_unicode = host
    return any(h in (host, host_unicode) or host.endswith('.' + h) or host_unicode.endswith('.' + h)
               for h in SERVICE_HOSTS)


def _clear_paragraph(p):
    for child in list(p):
        if child.tag != _q('w:pPr'):
            p.remove(child)


def _empty_paragraph():
    return etree.Element(_q('w:p'))


def _has_page_field(p):
    instructions = ' '.join((i.text or '') for i in p.iter(_q('w:instrText')))
    fields = ' '.join(f.get(_q('w:instr'), '') for f in p.iter(_q('w:fldSimple')))
    return bool(re.search(r'\b(?:NUM)?PAGES?\b', instructions + ' ' + fields))


class Cleaner:
    def __init__(self, archive):
        self.archive = archive
        self.stats = {'note_blocks': 0, 'service_paragraphs': 0, 'logo_drawings': 0,
                      'hyperlinks_unwrapped': 0, 'header_footer_paragraphs': 0,
                      'docprops_fields': 0, 'rels_removed': 0, 'media_removed': 0}
        self.partial = []

    def _rels(self, part):
        folder, name = part.rsplit('/', 1)
        rels_name = folder + '/_rels/' + name + '.rels'
        if rels_name not in self.archive.namelist():
            return rels_name, None
        return rels_name, etree.fromstring(self.archive.read(rels_name))

    def _logo_rel_ids(self, rels):
        ids = set()
        if rels is None:
            return ids
        for rel in rels:
            target = rel.get('Target', '')
            if rel.get('Type', '').endswith('/image') and rel.get('TargetMode') != 'External':
                path = 'word/' + target.lstrip('/') if not target.startswith('word/') else target
                if path in self.archive.namelist() and hashlib.sha256(self.archive.read(path)).hexdigest() in LOGO_SHA256:
                    ids.add(rel.get('Id'))
        return ids

    def _service_link_ids(self, rels):
        if rels is None:
            return set()
        return {rel.get('Id') for rel in rels if rel.get('TargetMode') == 'External' and _service_host(rel.get('Target', ''))}

    def _remove_logos(self, root, logo_ids):
        for drawing in list(root.iter(_q('w:drawing'), _q('w:pict'))):
            embeds = {v for el in drawing.iter() for k, v in el.attrib.items() if k in ('{%s}embed' % R, '{%s}id' % R, '{%s}link' % R)}
            if embeds & logo_ids:
                run = drawing.getparent()
                run.remove(drawing)
                self.stats['logo_drawings'] += 1
                if run.tag == _q('w:r') and not [c for c in run if c.tag != _q('w:rPr')]:
                    run.getparent().remove(run)

    def _unwrap_links(self, root, link_ids):
        for link in list(root.iter(_q('w:hyperlink'))):
            if link.get('{%s}id' % R) in link_ids:
                parent = link.getparent()
                index = parent.index(link)
                for child in list(link):
                    # Текст бывшей ссылки не должен выглядеть как ссылка.
                    for props in child.iter(_q('w:rPr')):
                        for mark in props.findall(_q('w:color')) + props.findall(_q('w:u')):
                            props.remove(mark)
                    parent.insert(index, child)
                    index += 1
                parent.remove(link)
                self.stats['hyperlinks_unwrapped'] += 1

    def _neutral_attributes(self, root):
        # Имена/описания объектов (формулы-картинки, подсказки ссылок) видны в Word.
        for el in root.iter():
            for key, value in list(el.attrib.items()):
                local = etree.QName(key).localname
                if local in ('name', 'descr', 'title', 'tooltip') and BRAND_CHECK.search(value):
                    if local == 'name':
                        el.set(key, 'Рисунок')
                    else:
                        del el.attrib[key]
                    self.stats['object_attributes'] = self.stats.get('object_attributes', 0) + 1

    def _clean_paragraphs(self, root, where):
        for p in root.iter(_q('w:p')):
            original = _text(p)
            if not original.strip():
                continue
            cleaned, removed = clean_text(original)
            if not removed:
                continue
            if not cleaned.strip(' \t '):
                _clear_paragraph(p)
                self.stats['service_paragraphs'] += 1
            else:
                self.partial.append((where, original[:200]))

    def _drop_empty_rows(self, table):
        for row in list(table.findall(_q('w:tr'))):
            if not _text(row).strip(' \t ') and not list(row.iter(_q('w:drawing'), _q('w:pict'), _q('w:object'))):
                table.remove(row)
        return len(table.findall(_q('w:tr')))

    def document(self, part='word/document.xml'):
        root = etree.fromstring(self.archive.read(part))
        rels_name, rels = self._rels(part)
        body = root.find(_q('w:body'))
        # 1. Редакционные примечания системы: блок заменяется пустым абзацем.
        for index, block in enumerate(list(body)):
            if block.tag in (_q('w:tbl'), _q('w:p')) and NOTE_BLOCK.match(_text(block)):
                body.replace(block, _empty_paragraph())
                self.stats['note_blocks'] += 1
        logo_ids = self._logo_rel_ids(rels)
        link_ids = self._service_link_ids(rels)
        title_tables = [b for b in list(body)[:3] if b.tag == _q('w:tbl') and BRAND_CHECK.search(_text(b))]
        self._remove_logos(root, logo_ids)
        self._unwrap_links(root, link_ids)
        self._neutral_attributes(root)
        self._clean_paragraphs(root, part)
        # 2. Титульная плашка: убрать опустевшие строки (логотип, «Документ предоставлен»).
        for table in title_tables:
            if not self._drop_empty_rows(table):
                body.replace(table, _empty_paragraph())
        self._finish_rels(rels_name, rels, root, logo_ids | link_ids)
        return part, root

    def header_footer(self, part):
        root = etree.fromstring(self.archive.read(part))
        rels_name, rels = self._rels(part)
        logo_ids = self._logo_rel_ids(rels)
        link_ids = self._service_link_ids(rels)
        self._remove_logos(root, logo_ids)
        self._unwrap_links(root, link_ids)
        self._neutral_attributes(root)
        is_header = part.rsplit('/', 1)[-1].startswith('header')
        branded = bool(BRAND_CHECK.search(_text(root)))
        for p in root.iter(_q('w:p')):
            text = _text(p)
            if not text.strip() or _has_page_field(p):
                continue
            # Колонтитул системы: бегущий заголовок и плашки удаляются, номера страниц остаются.
            if (is_header and branded) or not clean_text(text)[0].strip(' \t ') or BRAND_CHECK.search(text):
                _clear_paragraph(p)
                self.stats['header_footer_paragraphs'] += 1
        self._finish_rels(rels_name, rels, root, logo_ids | link_ids)
        return part, root

    def _finish_rels(self, rels_name, rels, root, candidate_ids):
        if rels is None:
            return
        used = {v for el in root.iter() for k, v in el.attrib.items() if k.startswith('{%s}' % R)}
        for rel in list(rels):
            if rel.get('Id') in candidate_ids and rel.get('Id') not in used:
                rels.remove(rel)
                self.stats['rels_removed'] += 1
        self.rels_out[rels_name] = rels

    def docprops(self, name):
        root = etree.fromstring(self.archive.read(name))
        for el in list(root.iter()):
            local = etree.QName(el).localname if isinstance(el.tag, str) else ''
            value = (el.text or '').strip()
            if local in ('Application', 'Company', 'creator', 'lastModifiedBy', 'Manager', 'HyperlinkBase') and value:
                if BRAND_CHECK.search(value) or local in ('creator', 'lastModifiedBy', 'Company', 'Manager', 'HyperlinkBase') or 'Консультант' in value:
                    el.getparent().remove(el)
                    self.stats['docprops_fields'] += 1
        return name, root

    def run(self):
        self.rels_out = {}
        parts = {}
        names = self.archive.namelist()
        name, root = self.document()
        parts[name] = root
        for n in names:
            if re.fullmatch(r'word/(?:header|footer)\d*\.xml', n):
                name, root = self.header_footer(n)
                parts[name] = root
        for n in ('docProps/app.xml', 'docProps/core.xml'):
            if n in names:
                name, root = self.docprops(n)
                parts[name] = root
        # Неиспользуемые изображения логотипов удаляются вместе со связями.
        referenced = set()
        for rels_name in [n for n in names if n.endswith('.rels')]:
            rels = self.rels_out.get(rels_name)
            if rels is None:
                rels = etree.fromstring(self.archive.read(rels_name))
            base = rels_name.replace('_rels/', '').rsplit('/', 1)[0]
            for rel in rels:
                if rel.get('TargetMode') != 'External':
                    referenced.add((base + '/' + rel.get('Target', '')).replace('//', '/'))
        dropped = set()
        for n in names:
            if n.startswith('word/media/') and not n.endswith('/'):
                if hashlib.sha256(self.archive.read(n)).hexdigest() in LOGO_SHA256 and n not in referenced:
                    dropped.add(n)
                    self.stats['media_removed'] += 1
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
            for info in self.archive.infolist():
                if info.filename in dropped:
                    continue
                if info.filename in parts:
                    data = etree.tostring(parts[info.filename], xml_declaration=True, encoding='UTF-8', standalone=True)
                elif info.filename in self.rels_out:
                    data = etree.tostring(self.rels_out[info.filename], xml_declaration=True, encoding='UTF-8', standalone=True)
                else:
                    data = self.archive.read(info.filename)
                entry = zipfile.ZipInfo(info.filename, FIXED_TIME)
                entry.compress_type = zipfile.ZIP_STORED if info.filename.endswith('/') else zipfile.ZIP_DEFLATED
                entry.external_attr = info.external_attr
                target.writestr(entry, data)
        return output.getvalue()


def residual_brand_text(data):
    """Все текстовые узлы и метаданные очищенного файла, где остался бренд."""
    found = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in archive.namelist():
            if name.endswith('.xml') or name.endswith('.rels'):
                raw = archive.read(name).decode('utf-8', errors='replace')
                if name.endswith('.rels'):
                    for target in re.findall(r'Target="([^"]+)"', raw):
                        if target.startswith('http') and _service_host(target):
                            found.append((name, target))
                    continue
                root = etree.fromstring(archive.read(name))
                values = [t.text or '' for t in root.iter() if isinstance(t.tag, str)]
                values += [v for el in root.iter() for v in el.attrib.values()]
                for value in values:
                    if BRAND_CHECK.search(value):
                        found.append((name, value[:160]))
    return found


def clean_file(source, target):
    with zipfile.ZipFile(source) as archive:
        cleaner = Cleaner(archive)
        data = cleaner.run()
    Path(target).write_bytes(data)
    return {'stats': cleaner.stats, 'partial': cleaner.partial, 'residual': residual_brand_text(data),
            'sha256': hashlib.sha256(data).hexdigest(),
            'original_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest()}


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    report = clean_file(sys.argv[1], sys.argv[2])
    print(report)
    sys.exit(1 if report['residual'] or report['partial'] else 0)
