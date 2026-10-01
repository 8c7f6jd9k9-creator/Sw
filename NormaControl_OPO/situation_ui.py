"""Native desktop views for NormaKontrol inspections and curated requirements."""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from learning_ui import _WorkerTab, _text, _set_text
from situations import SituationStore, CATEGORIES, RISKS, STATES


class SituationsTab(_WorkerTab):
    def __init__(self, parent, store, open_file, send_to_agent):
        super().__init__(parent)
        self.backend = SituationStore(store.root)
        self.open_file = open_file
        self.send_to_agent = send_to_agent
        self.current = None
        self._matches = {}
        self._material_rows = {}
        self.title = tk.StringVar()
        self.location = tk.StringVar()
        self.category = tk.StringVar(value=CATEGORIES[0])
        self.risk = tk.StringVar(value=RISKS['unknown'])
        self.reviewer = tk.StringVar()
        self.include_nd = tk.BooleanVar(value=True)
        self.include_other = tk.BooleanVar(value=False)
        self.summary = tk.StringVar()
        ttk.Label(self, text='Ситуационные проверки: описание → источники → решение специалиста → отчёт. '
                  'Локальный ИИ может подготовить разбор; оценку риска и решение фиксирует специалист.', wraplength=1200).pack(anchor='w')
        bar = ttk.Frame(self); bar.pack(fill='x')
        for label, command in [('Новая', self.new), ('Сохранить', self.save), ('Обновить', self.refresh),
                               ('Подобрать источники', self.analyze), ('Передать локальному ИИ', self.to_agent),
                               ('Отчёт PDF / HTML', self.export)]:
            self.button(bar, label, command)
        split = ttk.Panedwindow(self, orient='horizontal'); split.pack(fill='both', expand=True)
        left = ttk.Frame(split); right = ttk.Frame(split); split.add(left, weight=1); split.add(right, weight=3)
        self.tree = ttk.Treeview(left, columns=('number', 'title', 'status'), show='headings', height=16)
        for col, name, width in [('number', 'Номер', 140), ('title', 'Ситуация', 180), ('status', 'Статус', 140)]:
            self.tree.heading(col, text=name); self.tree.column(col, width=width)
        self.tree.pack(fill='both', expand=True); self.tree.bind('<<TreeviewSelect>>', self.select)
        self.editor = ttk.Notebook(right); self.editor.pack(fill='both', expand=True)
        card = ttk.Frame(self.editor, padding=8); found = ttk.Frame(self.editor, padding=8); decision = ttk.Frame(self.editor, padding=8)
        self.editor.add(card, text='Описание и материалы'); self.editor.add(found, text='Найденные источники'); self.editor.add(decision, text='Решение специалиста')
        row = ttk.Frame(card); row.pack(fill='x'); self.entry(row, 'Наименование', self.title, 60)
        row = ttk.Frame(card); row.pack(fill='x')
        assets = list(store.assets()); self.asset_ids = [None] + [a['seq'] for a in assets]
        self.asset = self.control(ttk.Combobox(row, state='readonly', values=['Общий вопрос'] + [a['reg_no'] + ' — ' + a['name'] for a in assets], width=80), 'readonly')
        ttk.Label(row, text='ОПО').pack(side='left'); self.asset.pack(side='left', fill='x', expand=True); self.asset.current(0)
        row = ttk.Frame(card); row.pack(fill='x')
        cb = self.control(ttk.Combobox(row, textvariable=self.category, values=CATEGORIES, state='readonly', width=45), 'readonly'); cb.pack(side='left')
        self.entry(row, 'Место', self.location, 25)
        ttk.Label(card, text='Описание наблюдения / работ / отклонения').pack(anchor='w')
        self.description = self.control(_text(card, 6))
        row = ttk.Frame(card); row.pack(fill='x')
        self.button(row, 'Добавить документ / фото', self.attach)
        self.button(row, 'Открыть материал', self.open_material)
        self.materials_tree = ttk.Treeview(card, columns=('name',), show='headings', height=3)
        self.materials_tree.heading('name', text='Материалы ситуации'); self.materials_tree.pack(fill='x')
        row = ttk.Frame(found); row.pack(fill='x')
        self.control(ttk.Checkbutton(row, text='Архив НД, предоставленный пользователем', variable=self.include_nd)).pack(side='left')
        self.control(ttk.Checkbutton(row, text='Другие непроверенные источники', variable=self.include_other)).pack(side='left', padx=8)
        self.button(row, 'Открыть оригинал', self.open_source)
        self.matches_tree = ttk.Treeview(found, columns=('source', 'edition'), show='headings', height=5)
        self.matches_tree.heading('source', text='Источник / ссылка'); self.matches_tree.heading('edition', text='Редакция из файла')
        self.matches_tree.column('source', width=500); self.matches_tree.column('edition', width=250)
        self.matches_tree.pack(fill='x'); self.matches_tree.bind('<<TreeviewSelect>>', self.select_match)
        self.fragment = _text(found, 10, readonly=True)
        row = ttk.Frame(decision); row.pack(fill='x')
        self.entry(row, 'Специалист', self.reviewer, 35)
        self.control(ttk.Combobox(row, textvariable=self.risk, values=list(RISKS.values()), state='readonly', width=20), 'readonly').pack(side='left')
        ttk.Label(decision, text='Обоснование, выявленные замечания, мероприятия / вывод').pack(anchor='w')
        self.decision = self.control(_text(decision, 12))
        row = ttk.Frame(decision); row.pack(fill='x')
        self.button(row, 'Сохранить решение', lambda: self.decide(False))
        self.button(row, 'Закрыть ситуацию', lambda: self.decide(True))
        ttk.Label(self, textvariable=self.summary).pack(anchor='w')
        ttk.Label(self, textvariable=self.status, wraplength=1200).pack(anchor='w')
        self.refresh()

    def refresh(self):
        if self._busy: return
        self.tree.delete(*self.tree.get_children())
        for r in self.backend.list():
            self.tree.insert('', 'end', iid=str(r['id']), values=(r['number'], r['title'], STATES[r['status']]))
        if self.current and self.tree.exists(str(self.current)):
            self.tree.selection_set(str(self.current))

    def new(self):
        if self._busy: return
        self.current = None; self.title.set(''); self.location.set(''); self.asset.current(0)
        self.reviewer.set(''); self.risk.set(RISKS['unknown'])
        _set_text(self.description, '', False); _set_text(self.decision, '', False)
        _set_text(self.fragment, '')
        self.matches_tree.delete(*self.matches_tree.get_children()); self.materials_tree.delete(*self.materials_tree.get_children())
        self.summary.set('Новая ситуация. Заполните описание и сохраните.')

    def save(self):
        if self._busy: return False
        try:
            self.current = self.backend.save(self.title.get(), self.asset_ids[self.asset.current()], self.category.get(),
                                             self.location.get(), self.description.get('1.0', 'end-1c'), self.current)
            self.refresh(); self.load(); self.status.set('Ситуация сохранена.')
            return True
        except Exception as exc:
            self.status.set(str(exc)); return False

    def select(self, event=None):
        if self._busy: return
        selected = self.tree.selection()
        if selected:
            sid = int(selected[0])
            if self.current != sid:
                self.current = sid; self.load()

    def load(self):
        if self.current is None: return
        r = self.backend.get(self.current)
        self.title.set(r['title']); self.location.set(r['location']); self.category.set(r['category'])
        self.asset.current(self.asset_ids.index(r['asset_id'])); self.reviewer.set(r['reviewer']); self.risk.set(RISKS[r['risk']])
        _set_text(self.description, r['description'], False); _set_text(self.decision, r['decision'], False)
        self.summary.set(r['number'] + ' • ' + STATES[r['status']] + ' • Риск: ' + RISKS[r['risk']])
        self._matches = {}; self.matches_tree.delete(*self.matches_tree.get_children())
        for i, m in enumerate(r['matches']):
            key = str(i); self._matches[key] = m
            self.matches_tree.insert('', 'end', iid=key, values=(f'[К{m["source_id"]}-Ф{m["id"]}] ' + m['title'], m['edition']))
        self._material_rows = {}; self.materials_tree.delete(*self.materials_tree.get_children())
        for m in self.backend.materials(self.current):
            key = str(m['id']); self._material_rows[key] = m
            self.materials_tree.insert('', 'end', iid=key, values=(m['original_name'],))
        _set_text(self.fragment, 'Выберите найденный фрагмент.' if r['matches'] else 'Источники ещё не подобраны либо совпадения не найдены.')

    def analyze(self):
        if not self.save(): return
        sid = self.current; raw = self.include_other.get(); nd = self.include_nd.get()
        def done(matches):
            self.refresh(); self.load(); self.editor.select(1)
            self.status.set(f'Подобрано источников: {len(matches)}. Применимость требует проверки; риск не назначен автоматически.')
        self._launch(lambda: self.backend.analyze(sid, raw, nd), done, 'Поиск по локальной базе…')

    def select_match(self, event=None):
        selected = self.matches_tree.selection()
        if selected:
            m = self._matches[selected[0]]
            _set_text(self.fragment, f'{m["title"]}\n{m["edition"]}\n{m.get("clause", "")}\n{m.get("reason", "")}\n\n{m["text"]}')

    def open_source(self):
        selected = self.matches_tree.selection()
        if not selected: return
        try: self.open_file(self.backend.kb.open_path(self._matches[selected[0]]['source_id']))
        except Exception as exc: self.status.set(str(exc))

    def attach(self):
        if not self.save(): return
        paths = filedialog.askopenfilenames(parent=self, title='Материалы ситуации')
        try:
            for p in paths: self.backend.attach(self.current, p)
            self.load(); self.status.set(f'Добавлено материалов: {len(paths)}.')
        except Exception as exc: self.status.set(str(exc))

    def open_material(self):
        selected = self.materials_tree.selection()
        if selected:
            try: self.open_file(self.backend.material_path(int(selected[0])))
            except Exception as exc: self.status.set(str(exc))

    def decide(self, close):
        if self.current is None:
            self.status.set('Сначала сохраните ситуацию.'); return
        try:
            risk = next(k for k, v in RISKS.items() if v == self.risk.get())
            reviewer, decision = self.reviewer.get(), self.decision.get('1.0', 'end-1c')
            if not self.save(): return
            self.backend.decide(self.current, risk, reviewer, decision, close)
            self.refresh(); self.load(); self.status.set('Решение сохранено.')
        except Exception as exc: self.status.set(str(exc))

    def to_agent(self):
        if not self.save(): return
        r = self.backend.get(self.current)
        self.send_to_agent(r)

    def export(self):
        if self.current is None:
            self.status.set('Выберите ситуацию.'); return
        path = filedialog.asksaveasfilename(parent=self, title='Отчёт', defaultextension='.pdf',
                    initialfile=f'NormaControl_{self.current}.pdf', filetypes=[('PDF', '*.pdf'), ('HTML', '*.html')])
        if path:
            sid = self.current
            self._launch(lambda: self.backend.export_report(sid, path),
                         lambda p: self.status.set('Отчёт сохранён: ' + str(p)), 'Формирование отчёта…')


class RequirementsTab(_WorkerTab):
    def __init__(self, parent, store, open_file):
        super().__init__(parent)
        self.backend = SituationStore(store.root)
        self.open_file = open_file
        self.current = None
        self.title = tk.StringVar(); self.clause = tk.StringVar(); self.source = tk.StringVar(); self.chunk = tk.StringVar()
        self.category = tk.StringVar(value=CATEGORIES[-1]); self.keywords = tk.StringVar(); self.action = tk.StringVar()
        self.reviewed = tk.BooleanVar(); self.active = tk.BooleanVar(value=True)
        ttk.Label(self, text='Проверенные требования: каждая запись связана с реальным источником и фрагментом. '
                  'Демонстрационные нормы из старого MVP не импортированы. Реквизиты К/Ф видны в поиске базы знаний.', wraplength=1200).pack(anchor='w')
        bar = ttk.Frame(self); bar.pack(fill='x')
        self.button(bar, 'Новая запись', self.new); self.button(bar, 'Сохранить', self.save)
        self.button(bar, 'Импорт CSV', self.import_csv); self.button(bar, 'Экспорт CSV', self.export_csv)
        self.button(bar, 'Открыть источник', self.open_source)
        self.tree = ttk.Treeview(self, columns=('title', 'clause', 'review'), show='headings', height=6)
        for key, label in [('title', 'Документ'), ('clause', 'Пункт'), ('review', 'Проверка / активность')]: self.tree.heading(key, text=label)
        self.tree.pack(fill='x'); self.tree.bind('<<TreeviewSelect>>', self.select)
        row = ttk.Frame(self); row.pack(fill='x'); self.entry(row, 'Документ', self.title, 45); self.entry(row, 'Пункт', self.clause, 15)
        row = ttk.Frame(self); row.pack(fill='x')
        self.control(ttk.Combobox(row, values=CATEGORIES, textvariable=self.category, state='readonly', width=45), 'readonly').pack(side='left')
        self.entry(row, 'К — источник', self.source, 8); self.entry(row, 'Ф — фрагмент', self.chunk, 8)
        self.control(ttk.Checkbutton(row, text='Проверено специалистом', variable=self.reviewed)).pack(side='left')
        self.control(ttk.Checkbutton(row, text='Активно', variable=self.active)).pack(side='left')
        ttk.Label(self, text='Текст требования (проверить по оригиналу)').pack(anchor='w'); self.text = self.control(_text(self, 8))
        row = ttk.Frame(self); row.pack(fill='x'); self.entry(row, 'Ключевые слова', self.keywords, 40)
        row = ttk.Frame(self); row.pack(fill='x'); self.entry(row, 'Мероприятие', self.action, 80)
        ttk.Label(self, textvariable=self.status, wraplength=1200).pack(anchor='w')
        self.rows = {}; self.refresh()

    def refresh(self):
        self.rows = {}; self.tree.delete(*self.tree.get_children())
        for r in self.backend.requirements():
            key = str(r['id']); self.rows[key] = r
            self.tree.insert('', 'end', iid=key, values=(r['title'], r['clause'],
                             ('Проверено' if r['reviewed'] else 'Черновик') + (' / активно' if r['active'] else ' / архив')))

    def new(self):
        self.current = None
        for v in (self.title, self.clause, self.source, self.chunk, self.keywords, self.action): v.set('')
        self.reviewed.set(False); self.active.set(True); _set_text(self.text, '', False)

    def select(self, event=None):
        if self._busy: return
        selected = self.tree.selection()
        if not selected: return
        r = self.rows[selected[0]]; self.current = r['id']
        for key, v in [('title', self.title), ('clause', self.clause), ('source_id', self.source), ('chunk_id', self.chunk),
                       ('category', self.category), ('keywords', self.keywords), ('action', self.action)]: v.set(r[key])
        self.reviewed.set(False); self.active.set(bool(r['active'])); _set_text(self.text, r['text'], False)
        self.status.set('При редактировании отметьте проверку повторно; существующая запись меняется только после сохранения.')

    def save(self):
        try:
            self.current = self.backend.save_requirement(self.title.get(), self.category.get(), self.clause.get(),
                    self.text.get('1.0', 'end-1c'), self.source.get(), self.chunk.get(), self.keywords.get(), self.action.get(),
                    self.reviewed.get(), self.active.get(), self.current)
            self.refresh(); self.status.set('Требование сохранено.')
        except Exception as exc: self.status.set(str(exc))

    def open_source(self):
        try: self.open_file(self.backend.kb.open_path(int(self.source.get())))
        except Exception as exc: self.status.set(str(exc))

    def import_csv(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('CSV UTF-8', '*.csv')])
        if path:
            def done(n): self.refresh(); self.status.set(f'Импортировано черновиков: {n}. Проверка человеком обязательна.')
            self._launch(lambda: self.backend.import_requirements_csv(path), done, 'Импорт требований…')

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.csv', initialfile='NormaControl_requirements.csv')
        if not path: return
        import csv
        try:
            fields = ['title', 'category', 'clause', 'text', 'source_id', 'chunk_id', 'keywords', 'action']
            with Path(path).open('w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fields, extrasaction='ignore'); writer.writeheader()
                for r in self.backend.requirements():
                    # Export text safely for spreadsheet viewers without executing formulas.
                    writer.writerow({k: ("'" + str(r[k]) if str(r[k]).startswith(('=', '+', '-', '@')) else r[k]) for k in fields})
            self.status.set('CSV сохранён.')
        except Exception as exc: self.status.set(str(exc))
