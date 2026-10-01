"""Русскоязычный интерфейс локальных агентов. SQLite и Tk — только главный поток."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from local_agents import AgentService, ROLES
from knowledge import KnowledgeBase


class AgentsTab(ttk.Frame):
    def __init__(self, parent, store):
        super().__init__(parent, padding=12)
        self.store = store
        self.service = AgentService(store)
        self.knowledge = KnowledgeBase(store.root)
        self._closed = False
        self._busy = False
        self._queue = queue.Queue()
        self._after_id = None
        self._controls = []
        self._runs = {}
        self._result = ''
        self._snapshot = None
        settings = self.service.settings()
        self.endpoint = tk.StringVar(value=settings.get('endpoint') or 'http://127.0.0.1:11434')
        self._preferred_model = settings.get('model') or ''
        self.model = tk.StringVar(value='')
        self.status = tk.StringVar(value='Модель не подключена — проверьте подключение.')
        top = ttk.Frame(self)
        top.pack(fill='x')
        ttk.Label(top, text='Адрес локального Ollama').grid(row=0, column=0, sticky='w')
        self.url_entry = ttk.Entry(top, textvariable=self.endpoint, width=38)
        self.url_entry.grid(row=0, column=1, padx=6, sticky='ew')
        self.models = ttk.Combobox(top, textvariable=self.model, values=[], state='readonly', width=28)
        self.models.grid(row=0, column=2, padx=6)
        check = ttk.Button(top, text='Проверить подключение / модели', command=self.check_connection)
        check.grid(row=0, column=3, padx=6)
        save = ttk.Button(top, text='Сохранить настройки', command=self.save_settings)
        save.grid(row=0, column=4)
        top.columnconfigure(1, weight=1)
        self._controls.extend([(self.url_entry, 'normal'), (self.models, 'readonly'), (check, 'normal'), (save, 'normal')])
        ttk.Label(self, textvariable=self.status, wraplength=1100).pack(anchor='w', pady=6)
        ttk.Label(self, text='Для работы на этом ПК нужны запущенный Ollama и загруженные веса модели. '
                  'Модель получает данные реестра и найденные фрагменты из вкладки «База знаний». '
                  'Выводы модели предварительные и требуют проверки специалистом.',
                  wraplength=1100).pack(anchor='w', pady=(0, 8))
        choices = ttk.Frame(self)
        choices.pack(fill='x')
        self._role_ids = list(ROLES)
        role_names = [ROLES[r]['name'] for r in self._role_ids] + ['Команда всех агентов']
        ttk.Label(choices, text='Исполнитель').pack(side='left')
        self.role = ttk.Combobox(choices, values=role_names, state='readonly', width=34)
        self.role.pack(side='left', padx=6)
        self.role.current(0)
        assets = list(store.assets())
        self._asset_ids = [None] + [a['seq'] for a in assets]
        asset_names = ['Весь реестр ОПО'] + [f"{a['reg_no']} — {a['name']}" for a in assets]
        ttk.Label(choices, text='Контекст').pack(side='left', padx=(12, 0))
        self.asset = ttk.Combobox(choices, values=asset_names, state='readonly', width=65)
        self.asset.pack(side='left', padx=6, fill='x', expand=True)
        self.asset.current(0)
        self._controls.extend([(self.role, 'readonly'), (self.asset, 'readonly')])
        rag_options = ttk.Frame(self)
        rag_options.pack(fill='x', pady=4)
        self.use_knowledge = tk.BooleanVar(value=True)
        self.use_authorized = tk.BooleanVar(value=True)
        use_nd = ttk.Checkbutton(rag_options, text='Использовать предоставленный архив НД', variable=self.use_authorized)
        use_nd.pack(side='left', padx=8)
        self._controls.append((use_nd, 'normal'))
        self.use_unreviewed = tk.BooleanVar(value=False)
        use_rag = ttk.Checkbutton(rag_options, text='Искать в локальной базе знаний', variable=self.use_knowledge)
        use_rag.pack(side='left')
        use_raw = ttk.Checkbutton(rag_options, text='Включать непроверенные тексты (предварительный разбор)', variable=self.use_unreviewed)
        use_raw.pack(side='left', padx=12)
        self._controls.extend([(use_rag, 'normal'), (use_raw, 'normal')])
        ttk.Label(self, text='Задача агенту').pack(anchor='w', pady=(8, 3))
        self.task = tk.Text(self, height=4, wrap='word')
        self.task.pack(fill='x')
        self._controls.append((self.task, 'normal'))
        bar = ttk.Frame(self)
        bar.pack(fill='x', pady=6)
        run = ttk.Button(bar, text='Запустить', command=self.start_run)
        run.pack(side='left')
        export = ttk.Button(bar, text='Экспорт результата (.txt)', command=self.export_result)
        export.pack(side='left', padx=8)
        self._controls.extend([(run, 'normal'), (export, 'normal')])
        split = ttk.Panedwindow(self, orient='horizontal')
        split.pack(fill='both', expand=True)
        output_frame = ttk.Frame(split)
        history_frame = ttk.Frame(split)
        split.add(output_frame, weight=3)
        split.add(history_frame, weight=1)
        ttk.Label(output_frame, text='Результат / сведения об ошибке').pack(anchor='w')
        self.output = tk.Text(output_frame, wrap='word', state='disabled', height=14)
        scroll = ttk.Scrollbar(output_frame, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.output.pack(fill='both', expand=True)
        ttk.Label(history_frame, text='Последние запуски — выберите для просмотра').pack(anchor='w')
        self.history_tree = ttk.Treeview(history_frame, columns=('created', 'role', 'model'), show='headings', height=12)
        self.history_tree.heading('created', text='Дата / время')
        self.history_tree.column('created', width=145)
        self.history_tree.heading('role', text='Исполнитель')
        self.history_tree.heading('model', text='Модель')
        self.history_tree.column('role', width=160)
        self.history_tree.column('model', width=120)
        self.history_tree.pack(fill='both', expand=True)
        self.history_tree.bind('<<TreeviewSelect>>', self.show_history)
        self._controls.append((self.history_tree, 'normal'))
        self.bind('<Destroy>', self._on_destroy, add='+')
        self.refresh_history()
        self._after_id = self.after(100, self._poll)

    def _on_destroy(self, event):
        if event.widget is self:
            self.shutdown()

    def shutdown(self):
        self._closed = True
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _set_busy(self, busy):
        self._busy = busy
        for widget, normal_state in self._controls:
            if widget is self.history_tree:
                widget.state(['disabled'] if busy else ['!disabled'])
            else:
                widget.configure(state='disabled' if busy else normal_state)

    def _display(self, text):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', text)
        self.output.configure(state='disabled')

    def save_settings(self):
        if self._busy:
            return
        try:
            self.service.save_settings(self.endpoint.get().strip(), self.model.get().strip())
            self.status.set('Настройки сохранены. Подключение модели проверяется отдельной кнопкой.')
        except Exception as ex:
            self.status.set(f'Ошибка настроек: {ex}')

    def check_connection(self):
        if self._busy:
            return
        endpoint = self.endpoint.get().strip()
        self._set_busy(True)
        self.status.set('Проверка локального Ollama…')
        service, results = self.service, self._queue
        def worker():
            try:
                results.put(('models', service.list_models(endpoint), ''))
            except Exception as ex:
                results.put(('models', [], str(ex)))
        threading.Thread(target=worker, daemon=True).start()

    def start_run(self):
        if self._busy:
            return
        task = self.task.get('1.0', 'end-1c').strip()
        model = self.model.get().strip()
        if not task or not model:
            self.status.set('Укажите задачу и выберите загруженную модель после проверки подключения.')
            return
        try:
            self.service.save_settings(self.endpoint.get().strip(), model)
            asset_id = self._asset_ids[self.asset.current()]
            context = self.service.build_context(asset_id)
            if self.use_knowledge.get():
                found = self.knowledge.context(task, asset_id=asset_id, limit=4, include_unreviewed=self.use_unreviewed.get(), include_authorized=self.use_authorized.get())
                context = found + '\n\nУЧЕТНЫЕ ЗАПИСИ (не нормативный источник):\n' + context
            else:
                context = 'Поиск источников отключен пользователем. Нормативные выводы не подтверждены.\n' + context
            team = self.role.current() == len(self._role_ids)
            role = self._role_ids[0] if team else self._role_ids[self.role.current()]
        except Exception as ex:
            self.status.set(f'Не удалось подготовить запуск: {ex}')
            return
        self._snapshot = dict(role=role, task=task, model=model, context=context, team=team)
        self._result = ''
        self._display('')
        self._set_busy(True)
        self.status.set('Команда работает…' if team else 'Агент работает…')
        service, results = self.service, self._queue
        def worker():
            try:
                result = service.run(role, task, context, team=team)
                results.put(('run', result, ''))
            except Exception as ex:
                results.put(('run', '', str(ex)))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        if self._closed:
            return
        self._after_id = None
        try:
            while True:
                kind, value, error = self._queue.get_nowait()
                self._set_busy(False)
                if kind == 'models':
                    self.models.configure(values=value)
                    if self.model.get() not in value:
                        self.model.set(self._preferred_model if self._preferred_model in value else (value[0] if value else ''))
                    self.status.set(f'Модель не подключена: {error}' if error else
                                    (f'Ollama доступен. Найдено моделей: {len(value)}.' if value else
                                     'Модель не подключена: Ollama доступен, но веса моделей не найдены.'))
                else:
                    snapshot = self._snapshot
                    self._result = value if not error else ''
                    self._display(f'Ошибка запуска: {error}' if error else value)
                    self.status.set('Ошибка запуска — результат не получен.' if error else 'Запуск завершён.')
                    try:
                        self.service.save_run('team' if snapshot['team'] else snapshot['role'], snapshot['task'], snapshot['model'],
                                              snapshot['context'], value if not error else '', error=error)
                        self.refresh_history()
                    except Exception as ex:
                        self.status.set(f'Запуск завершён, но история не сохранена: {ex}')
                    self._snapshot = None
        except queue.Empty:
            pass
        if not self._closed:
            self._after_id = self.after(100, self._poll)

    def refresh_history(self):
        try:
            rows = self.service.history()
            self.history_tree.delete(*self.history_tree.get_children())
            self._runs = {}
            for i, row in enumerate(rows[:100]):
                record = dict(row)
                key = str(i)
                self._runs[key] = record
                role = record.get('role', '')
                role_name = 'Команда всех агентов' if role == 'team' else ROLES.get(role, {}).get('name', role)
                if record.get('error'):
                    role_name += ' (ошибка)'
                self.history_tree.insert('', 'end', iid=key, values=(record.get('created', '').replace('T', ' '), role_name, record.get('model', '')))
        except Exception as ex:
            self.status.set(f'Не удалось загрузить историю: {ex}')

    def show_history(self, event=None):
        if self._busy:
            return
        selected = self.history_tree.selection()
        if not selected:
            return
        row = self._runs[selected[0]]
        error = row.get('error') or ''
        self._result = '' if error else row.get('result', '')
        text = f"Задача: {row.get('task', '')}\nМодель: {row.get('model', '')}\n\n"
        text += f'Ошибка запуска: {error}' if error else self._result
        self._display(text)

    def export_result(self):
        if self._busy:
            return
        if not self._result:
            self.status.set('Нет успешного результата для экспорта.')
            return
        path = filedialog.asksaveasfilename(parent=self, title='Экспорт результата',
                                          defaultextension='.txt', initialfile='PromControl_agent_result.txt',
                                          filetypes=[('Текстовый файл', '*.txt')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as out:
                    out.write(self._result)
                self.status.set('Результат экспортирован.')
            except OSError as ex:
                messagebox.showerror('Экспорт результата', str(ex), parent=self)
