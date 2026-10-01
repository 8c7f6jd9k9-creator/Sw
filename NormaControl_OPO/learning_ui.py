"""Локальные документы, RAG и обучение. Все обращения к Tk — главный поток."""
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from knowledge import KnowledgeBase
from training import TrainingStore


def _text(parent, height=5, readonly=False):
    frame = ttk.Frame(parent)
    frame.pack(fill='both', expand=True, pady=3)
    widget = tk.Text(frame, height=height, wrap='word', state='disabled' if readonly else 'normal')
    scroll = ttk.Scrollbar(frame, command=widget.yview)
    widget.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    widget.pack(fill='both', expand=True)
    return widget


def _set_text(widget, value, readonly=True):
    widget.configure(state='normal')
    widget.delete('1.0', 'end')
    widget.insert('1.0', str(value))
    if readonly:
        widget.configure(state='disabled')


class _WorkerTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self._queue = queue.Queue()
        self._busy = False
        self._closed = False
        self._after_id = None
        self._controls = []
        self._done = None
        self._cancel = threading.Event()
        self.status = tk.StringVar(value='Готово.')
        self.bind('<Destroy>', self._destroyed, add='+')
        self._after_id = self.after(100, self._poll)

    def control(self, widget, state='normal'):
        self._controls.append((widget, state))
        return widget

    def button(self, parent, label, command):
        widget = self.control(ttk.Button(parent, text=label, command=command))
        widget.pack(side='left', padx=3, pady=3)
        return widget

    def entry(self, parent, label, variable, width=30):
        ttk.Label(parent, text=label).pack(side='left', padx=3)
        widget = self.control(ttk.Entry(parent, textvariable=variable, width=width))
        widget.pack(side='left', padx=3, fill='x', expand=True)
        return widget

    def _destroyed(self, event):
        if event.widget is self:
            self.shutdown()

    def shutdown(self):
        self._closed = True
        self._cancel.set()
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _set_busy(self, busy):
        self._busy = busy
        for widget, state in self._controls:
            if isinstance(widget, ttk.Treeview):
                widget.state(['disabled'] if busy else ['!disabled'])
            else:
                widget.configure(state='disabled' if busy else state)
        if hasattr(self, 'stop_button'):
            self.stop_button.configure(state='normal' if busy else 'disabled')

    def _launch(self, operation, done, label):
        if self._busy or self._closed:
            return
        self._cancel.clear()
        self._done = done
        self._set_busy(True)
        self.status.set(label)
        events = self._queue
        def worker():
            try:
                events.put(('done', operation(), ''))
            except Exception as ex:
                events.put(('done', None, str(ex)))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        if self._closed:
            return
        self._after_id = None
        try:
            while True:
                kind, value, error = self._queue.get_nowait()
                if kind == 'log':
                    if hasattr(self, 'log'):
                        self.log.configure(state='normal')
                        self.log.insert('end', str(value) + '\n')
                        self.log.see('end')
                        self.log.configure(state='disabled')
                    continue
                callback = self._done
                self._done = None
                self._set_busy(False)
                if error:
                    self.status.set('Ошибка: ' + error)
                    messagebox.showerror('Локальная обработка', error, parent=self)
                elif callback:
                    try:
                        callback(value)
                    except Exception as ex:
                        self.status.set('Ошибка отображения: ' + str(ex))
        except queue.Empty:
            pass
        if not self._closed:
            self._after_id = self.after(100, self._poll)

    def _show_json(self, title, data):
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry('780x520')
        _set_text(_text(window, height=25, readonly=True), json.dumps(data, ensure_ascii=False, indent=2, default=str))


class KnowledgeTab(_WorkerTab):
    def __init__(self, parent, store, open_file):
        super().__init__(parent)
        self.kb = KnowledgeBase(store.root)
        self.open_file = open_file
        self._sources = {}
        self._hits = {}
        self._selected_id = None
        self.title = tk.StringVar()
        self.source_url = tk.StringVar()
        self.edition = tk.StringVar()
        self.valid_from = tk.StringVar()
        self.valid_to = tk.StringVar()
        self.ocr_lang = tk.StringVar(value='rus+eng')
        self.reviewed = tk.BooleanVar(value=False)
        self.active = tk.BooleanVar(value=True)
        self.force_ocr = tk.BooleanVar(value=False)
        self.include_unreviewed = tk.BooleanVar(value=False)
        ttk.Label(self, text='База знаний: извлечение текста / OCR и поиск фрагментов. '
                  'Индексирование не подтверждает правильность OCR, актуальность или применимость нормы. '
                  'Подтверждайте источник после проверки его текста и реквизитов.', wraplength=1150).pack(anchor='w')
        bar = ttk.Frame(self); bar.pack(fill='x', pady=4)
        assets = list(store.assets())
        self._asset_ids = [None] + [a['seq'] for a in assets]
        ttk.Label(bar, text='ОПО / область источника').pack(side='left')
        self.asset = self.control(ttk.Combobox(bar, state='readonly', width=70,
                                  values=['Общие источники / весь реестр'] +
                                  [f"{a['reg_no']} — {a['name']}" for a in assets]), 'readonly')
        self.asset.pack(side='left', padx=5, fill='x', expand=True)
        self.asset.current(0)
        self.button(bar, 'Диагностика OCR', self.diagnostics)
        notebook = ttk.Notebook(self); notebook.pack(fill='both', expand=True)
        sources_page = ttk.Frame(notebook, padding=6)
        search_page = ttk.Frame(notebook, padding=6)
        notebook.add(sources_page, text='Источники и OCR')
        notebook.add(search_page, text='Поиск фрагментов')
        fields = ttk.Frame(sources_page); fields.pack(fill='x')
        row = ttk.Frame(fields); row.pack(fill='x')
        self.entry(row, 'Название', self.title, 42)
        self.entry(row, 'Редакция', self.edition, 22)
        row = ttk.Frame(fields); row.pack(fill='x')
        self.entry(row, 'URL первоисточника', self.source_url, 60)
        row = ttk.Frame(fields); row.pack(fill='x')
        self.entry(row, 'Действует с (ГГГГ-ММ-ДД)', self.valid_from, 14)
        self.entry(row, 'Действует до (ГГГГ-ММ-ДД)', self.valid_to, 14)
        self.entry(row, 'Язык OCR', self.ocr_lang, 14)
        row = ttk.Frame(fields); row.pack(fill='x')
        for label, var in [('Текст и реквизиты проверены мной', self.reviewed),
                           ('Активный источник', self.active), ('Принудительный OCR', self.force_ocr)]:
            self.control(ttk.Checkbutton(row, text=label, variable=var)).pack(side='left', padx=4)
        bar = ttk.Frame(fields); bar.pack(fill='x')
        self.button(bar, 'Новый источник', self.new_source)
        self.button(bar, 'Импорт файла / OCR', self.import_source)
        self.button(bar, 'Индексировать документы реестра', self.index_documents)
        self.button(bar, 'Сохранить реквизиты выбранного', self.update_source)
        bar = ttk.Frame(fields); bar.pack(fill='x')
        self.button(bar, 'Открыть выбранный файл', self.open_source)
        self.button(bar, 'Исключить из поиска', self.deactivate_source)
        self.button(bar, 'Обновить список', self.refresh_sources)
        self.source_tree = self.control(ttk.Treeview(sources_page, columns=('title', 'edition', 'review', 'active', 'status'),
                                                       show='headings', height=12), 'normal')
        for key, label, width in [('title','Источник',350), ('edition','Редакция',110), ('review','Проверка',160),
                                  ('active','Активен',65), ('status','Индекс / ошибка',260)]:
            self.source_tree.heading(key, text=label)
            self.source_tree.column(key, width=width)
        sy = ttk.Scrollbar(sources_page, command=self.source_tree.yview)
        self.source_tree.configure(yscrollcommand=sy.set)
        sy.pack(side='right', fill='y'); self.source_tree.pack(fill='both', expand=True)
        self.source_tree.bind('<<TreeviewSelect>>', self.select_source)
        self.source_tree.bind('<Double-1>', lambda _: self.open_source())
        ttk.Label(search_page, text='Запрос (выбор ОПО выше также ограничивает поиск)').pack(anchor='w')
        self.query = self.control(_text(search_page, 3))
        self.include_nd = tk.BooleanVar(value=True)
        bar = ttk.Frame(search_page); bar.pack(fill='x')
        self.control(ttk.Checkbutton(bar, text='Предоставленный архив НД', variable=self.include_nd)).pack(side='left')
        self.control(ttk.Checkbutton(bar, text='Включить непроверенные источники', variable=self.include_unreviewed)).pack(side='left')
        self.button(bar, 'Найти фрагменты', self.search)
        self.hit_tree = self.control(ttk.Treeview(search_page, columns=('title','location','review'), show='headings', height=6))
        for key, label, width in [('title','Источник',440),('location','Точное место',260),('review','Проверен',120)]:
            self.hit_tree.heading(key, text=label); self.hit_tree.column(key, width=width)
        self.hit_tree.pack(fill='x', pady=5)
        self.hit_tree.bind('<<TreeviewSelect>>', self.show_hit)
        self.hit_text = _text(search_page, 12, readonly=True)
        ttk.Label(self, textvariable=self.status, wraplength=1150).pack(anchor='w', pady=5)
        self.refresh_sources()

    def _asset_id(self):
        return self._asset_ids[max(0, self.asset.current())]

    def new_source(self):
        if self._busy: return
        self._selected_id = None
        self.source_tree.selection_remove(*self.source_tree.selection())
        for var in (self.title, self.edition, self.source_url, self.valid_from, self.valid_to): var.set('')
        self.reviewed.set(False); self.active.set(True)
        self.status.set('Новый источник. Проверка пользователем не подтверждена.')

    def refresh_sources(self):
        if self._busy: return
        self._launch(self.kb.sources, self._render_sources, 'Чтение списка источников…')

    def _render_sources(self, rows):
        self.source_tree.delete(*self.source_tree.get_children()); self._sources = {}
        for source in rows:
            record = dict(source); key = str(record['id']); self._sources[key] = record
            reviewed = bool(record.get('reviewed')); active = bool(record.get('active', True))
            status = record.get('error') or {'indexed':'Проиндексирован', 'partial':'Частичный индекс — проверить', 'error':'Ошибка извлечения', 'pending':'Ожидает обработки'}.get(record.get('status'), record.get('status',''))
            status = f"{status} • фрагментов: {record.get('chunk_count', 0)}"
            self.source_tree.insert('', 'end', iid=key, values=(record.get('title',''), record.get('edition',''),
                                    'Проверен' if reviewed else 'Требует проверки', 'Да' if active else 'Нет', status))
        self.status.set(f'Источников: {len(rows)}. Непроверенные источники требуют проверки пользователем.')

    def select_source(self, event=None):
        if self._busy: return
        selected = self.source_tree.selection()
        if not selected: return
        record = self._sources[selected[0]]; self._selected_id = record['id']
        for variable, key in [(self.title,'title'),(self.edition,'edition'),(self.source_url,'source_url'),
                               (self.valid_from,'valid_from'),(self.valid_to,'valid_to')]:
            variable.set(record.get(key) or '')
        self.reviewed.set(bool(record.get('reviewed'))); self.active.set(bool(record.get('active', True)))
        aid = record.get('asset_id')
        if aid in self._asset_ids: self.asset.current(self._asset_ids.index(aid))

    def _selected(self):
        if self._selected_id is None:
            self.status.set('Выберите источник в таблице.'); return None
        return self._selected_id

    def import_source(self):
        if self._busy: return
        path = filedialog.askopenfilename(parent=self, title='Импорт локального источника',
                 filetypes=[('Документы', '*.pdf *.docx *.txt *.md *.png *.jpg *.jpeg *.tif *.tiff'),('Все файлы','*.*')])
        if not path: return
        # Каждый новый импорт получает отдельное подтверждение; флажок не переносится автоматически.
        reviewed = self.reviewed.get()
        if reviewed and not messagebox.askyesno('Подтверждение источника',
                'Вы проверили текст именно этого файла, его редакцию и реквизиты?\nПодтвердить источник для поиска?', parent=self):
            reviewed = False
        values = dict(title=self.title.get().strip(), asset_id=self._asset_id(), source_url=self.source_url.get().strip(),
                      edition=self.edition.get().strip(), valid_from=self.valid_from.get().strip(), valid_to=self.valid_to.get().strip(),
                      reviewed=reviewed, force_ocr=self.force_ocr.get(), ocr_lang=self.ocr_lang.get().strip() or 'rus+eng')
        self.reviewed.set(False)
        def done(source_id):
            self.refresh_sources()
            self.status.set(f'Источник {source_id} проиндексирован. ' + ('Подтверждён пользователем.' if reviewed else 'Требуется проверка текста OCR и реквизитов.'))
        self._launch(lambda: self.kb.import_file(path, **values), done, 'Извлечение текста и OCR…')

    def index_documents(self):
        self.index_asset(self._asset_id())

    def index_asset(self, asset_id=None):
        """Вызывается приложением из главного потока после добавления документа."""
        if self._busy:
            self.status.set('База знаний занята; нажмите «Индексировать документы» после завершения.')
            return
        aid, lang = asset_id, self.ocr_lang.get().strip() or 'rus+eng'
        def done(result):
            self._show_json('Индексирование документов: результат', result)
            self.refresh_sources()
        self._launch(lambda: self.kb.index_registered_documents(asset_id=aid, ocr_lang=lang), done,
                     'Индексирование документов реестра. Новые источники требуют проверки…')

    def update_source(self):
        source_id = self._selected()
        if source_id is None or self._busy: return
        values = dict(reviewed=self.reviewed.get(), active=self.active.get(), edition=self.edition.get().strip(),
                      source_url=self.source_url.get().strip(), valid_from=self.valid_from.get().strip(), valid_to=self.valid_to.get().strip())
        self._launch(lambda: self.kb.update_source(source_id, **values), lambda _: self.refresh_sources(), 'Сохранение реквизитов…')

    def deactivate_source(self):
        source_id = self._selected()
        if source_id is None or self._busy: return
        record = self._sources[str(source_id)]
        values = {k: record.get(k) or '' for k in ('edition','source_url','valid_from','valid_to')}
        self._launch(lambda: self.kb.update_source(source_id, reviewed=bool(record.get('reviewed')), active=False, **values),
                     lambda _: self.refresh_sources(), 'Исключение источника из поиска…')

    def open_source(self):
        source_id = self._selected()
        if source_id is None or self._busy: return
        self._launch(lambda: self.kb.open_path(source_id), lambda path: self.open_file(path), 'Поиск локального файла…')

    def diagnostics(self):
        self._launch(self.kb.diagnostics, lambda result: self._show_json('Диагностика извлечения / OCR', result), 'Проверка компонентов OCR…')

    def search(self):
        query = self.query.get('1.0','end-1c').strip()
        if not query:
            self.status.set('Введите запрос.'); return
        aid, include = self._asset_id(), self.include_unreviewed.get()
        authorized = self.include_nd.get()
        def done(hits):
            self.hit_tree.delete(*self.hit_tree.get_children()); self._hits = {}
            _set_text(self.hit_text, '')
            for n, hit in enumerate(hits):
                record = dict(hit); key = str(n); self._hits[key] = record
                # location от backend; номера страниц DOCX не выдумываются.
                self.hit_tree.insert('', 'end', iid=key, values=(record.get('title',''), record.get('location',''),
                                'Да' if record.get('reviewed') else 'Нет — требует проверки'))
            self.status.set(f'Найдено фрагментов: {len(hits)}.')
        self._launch(lambda: self.kb.search(query, asset_id=aid, limit=10, include_unreviewed=include, include_authorized=authorized), done, 'Поиск по локальному индексу…')

    def show_hit(self, event=None):
        if self._busy: return
        selected = self.hit_tree.selection()
        if not selected: return
        hit = self._hits[selected[0]]
        details = '\n'.join(f'{label}: {hit.get(key) or "—"}' for label, key in
                        [('Источник','title'),('Место','location'),('Редакция','edition'),('URL','source_url'),('ID источника','source_id')])
        _set_text(self.hit_text, details + '\n\n' + hit.get('text',''))


class TrainingTab(_WorkerTab):
    def __init__(self, parent, store):
        super().__init__(parent)
        self.training = TrainingStore(store.root)
        self._examples = {}; self._example_id = None
        self.reviewed = tk.BooleanVar(value=False)
        self.split = tk.StringVar(value='train')
        self.model_dir = tk.StringVar(); self.output_dir = tk.StringVar()
        self.import_dir = tk.StringVar(); self.import_name = tk.StringVar()
        self.epochs = tk.StringVar(value='1'); self.max_length = tk.StringVar(value='512')
        ttk.Label(self, text='Локальное обучение на вручную проверенных примерах. Ответ модели или извлечённый документ '
                  'не становится проверенным примером автоматически. Обучение не заменяет проверку нормативных источников.',
                  wraplength=1150).pack(anchor='w')
        notebook = ttk.Notebook(self); notebook.pack(fill='both', expand=True, pady=5)
        examples_page = ttk.Frame(notebook, padding=6)
        train_page = ttk.Frame(notebook, padding=6)
        notebook.add(examples_page, text='Проверенные примеры')
        notebook.add(train_page, text='Обучение и импорт модели')
        left = ttk.Frame(examples_page); left.pack(side='left', fill='y', padx=(0,10))
        self.examples_tree = self.control(ttk.Treeview(left, columns=('task','split','reviewed'), show='headings', height=16))
        for key,label,width in [('task','Задача',200),('split','Выборка',80),('reviewed','Проверен',85)]:
            self.examples_tree.heading(key,text=label); self.examples_tree.column(key,width=width)
        self.examples_tree.pack(fill='both', expand=True)
        self.examples_tree.bind('<<TreeviewSelect>>', self.select_example)
        bar=ttk.Frame(left); bar.pack(fill='x')
        self.button(bar,'Новый',self.new_example)
        self.button(bar,'Обновить',self.refresh_examples)
        right = ttk.Frame(examples_page); right.pack(side='left',fill='both',expand=True)
        ttk.Label(right,text='Задача').pack(anchor='w'); self.task=self.control(_text(right,3))
        ttk.Label(right,text='Контекст / исходные данные').pack(anchor='w'); self.context=self.control(_text(right,4))
        ttk.Label(right,text='Проверенный ответ').pack(anchor='w'); self.answer=self.control(_text(right,6))
        ttk.Label(right,text='Ссылки на источники / точные пункты').pack(anchor='w'); self.refs=self.control(_text(right,2))
        bar=ttk.Frame(right); bar.pack(fill='x')
        self.control(ttk.Checkbutton(bar,text='Я проверил этот пример и его источники',variable=self.reviewed)).pack(side='left')
        self.control(ttk.Combobox(bar,textvariable=self.split,values=['train','validation'],state='readonly',width=12),'readonly').pack(side='left',padx=5)
        self.button(bar,'Сохранить пример',self.save_example)
        bar=ttk.Frame(right); bar.pack(fill='x')
        self.button(bar,'Экспорт набора',self.export_dataset)
        self.button(bar,'Диагностика обучения',self.diagnostics)
        row=ttk.Frame(train_page); row.pack(fill='x')
        self.entry(row,'Локальная базовая модель Hugging Face',self.model_dir,55)
        self.button(row,'Выбрать каталог',lambda:self.pick_directory(self.model_dir))
        row=ttk.Frame(train_page); row.pack(fill='x')
        self.entry(row,'Каталог результатов обучения',self.output_dir,55)
        self.button(row,'Выбрать каталог',lambda:self.pick_directory(self.output_dir))
        row=ttk.Frame(train_page); row.pack(fill='x')
        self.entry(row,'Эпохи',self.epochs,5); self.entry(row,'Макс. длина токенов',self.max_length,8)
        self.button(row,'Диагностика зависимостей / оборудования',self.diagnostics)
        self.button(row,'Начать локальное обучение',self.start_training)
        self.stop_button=ttk.Button(row,text='Остановить',command=self.cancel_training,state='disabled')
        self.stop_button.pack(side='left',padx=3)
        ttk.Label(train_page,text='Используются подтверждённые примеры; базовые веса должны уже находиться на ПК. '
                  'Отмена выполняется при ближайшей контрольной точке backend. Метрики отображаются только после фактического расчёта.',
                  wraplength=1100).pack(anchor='w',pady=5)
        self.log=_text(train_page,13,readonly=True)
        import_box=ttk.LabelFrame(train_page,text='Импорт подготовленной локальной модели в Ollama',padding=5)
        import_box.pack(fill='x',pady=4)
        row=ttk.Frame(import_box); row.pack(fill='x')
        self.entry(row,'Каталог объединённых весов или файл GGUF',self.import_dir,50)
        self.button(row,'Каталог',lambda:self.pick_directory(self.import_dir))
        self.button(row,'GGUF',self.pick_gguf)
        row=ttk.Frame(import_box); row.pack(fill='x')
        self.entry(row,'Новое имя модели',self.import_name,28)
        self.button(row,'Импортировать локальную модель',self.import_model)
        ttk.Label(self,textvariable=self.status,wraplength=1150).pack(anchor='w',pady=5)
        self.refresh_examples()

    def refresh_examples(self):
        if self._busy: return
        def done(rows):
            self.examples_tree.delete(*self.examples_tree.get_children()); self._examples={}
            for row in rows:
                record=dict(row); key=str(record['id']); self._examples[key]=record
                self.examples_tree.insert('','end',iid=key,values=(record.get('task','')[:90],record.get('split','train'),
                                                       'Да' if record.get('reviewed') else 'Нет'))
            self.status.set(f'Примеров: {len(rows)}. Для обучения используются только подтверждённые.')
        self._launch(self.training.examples,done,'Загрузка примеров…')

    def new_example(self):
        if self._busy: return
        self._example_id=None; self.reviewed.set(False); self.split.set('train')
        self.examples_tree.selection_remove(*self.examples_tree.selection())
        for widget in (self.task,self.context,self.answer,self.refs): _set_text(widget,'',False)
        self.status.set('Новый пример. Подтверждение проверки обязательно отдельное.')

    def select_example(self,event=None):
        if self._busy: return
        selected=self.examples_tree.selection()
        if not selected:return
        record=self._examples[selected[0]]; self._example_id=record['id']
        for widget,key in [(self.task,'task'),(self.context,'context'),(self.answer,'answer'),(self.refs,'source_refs')]:
            _set_text(widget,record.get(key,'') or '',False)
        # Любое повторное сохранение требует явного подтверждения редактируемого примера.
        self.reviewed.set(False); self.split.set(record.get('split','train'))
        self.status.set('Пример открыт. Для сохранения подтверждённым заново отметьте проверку.')

    def save_example(self):
        if self._busy:return
        values={key:widget.get('1.0','end-1c').strip() for key,widget in
                [('task',self.task),('context',self.context),('answer',self.answer),('source_refs',self.refs)]}
        if not values['task'] or not values['answer']:
            self.status.set('Заполните задачу и ответ.');return
        values.update(reviewed=self.reviewed.get(),split=self.split.get())
        example_id=self._example_id
        self.reviewed.set(False)
        operation=(lambda:self.training.add_example(**values)) if example_id is None else \
                  (lambda:self.training.update_example(example_id,**values))
        self._launch(operation,lambda _:self.refresh_examples(),'Сохранение примера…')

    def pick_directory(self,variable):
        if self._busy:return
        path=filedialog.askdirectory(parent=self)
        if path:variable.set(path)

    def pick_gguf(self):
        if self._busy:return
        path=filedialog.askopenfilename(parent=self,title='Выберите локальный GGUF',filetypes=[('GGUF','*.gguf')])
        if path:self.import_dir.set(path)

    def export_dataset(self):
        if self._busy:return
        path=filedialog.askdirectory(parent=self,title='Каталог экспорта обучающего набора')
        if not path:return
        def done(result):
            self._show_json('Экспорт набора: результат',result);self.status.set('Набор экспортирован.')
        self._launch(lambda:self.training.export_dataset(path),done,'Экспорт подтверждённых примеров…')

    def diagnostics(self):
        self._launch(self.training.diagnostics,lambda result:self._show_json('Диагностика обучения',result),
                     'Проверка зависимостей и оборудования…')

    def start_training(self):
        if self._busy:return
        model_dir=self.model_dir.get().strip();output_dir=self.output_dir.get().strip()
        try:
            epochs=int(self.epochs.get());max_length=int(self.max_length.get())
            if epochs<1 or max_length<1:raise ValueError()
        except ValueError:
            self.status.set('Эпохи и максимальная длина должны быть положительными целыми числами.');return
        if not model_dir or not output_dir:
            self.status.set('Укажите локальную базовую модель и каталог результатов.');return
        _set_text(self.log,'')
        events=self._queue;cancel=self._cancel
        def progress(value):events.put(('log',value,''))
        def done(result):
            rendered=json.dumps(result,ensure_ascii=False,indent=2,default=str)
            self.log.configure(state='normal');self.log.insert('end','\nРезультат фактического запуска:\n'+rendered+'\n');self.log.configure(state='disabled')
            status = result.get('status', 'unknown') if isinstance(result, dict) else 'unknown'
            labels = {'completed':'Обучение завершено', 'failed':'Обучение завершилось ошибкой', 'cancelled':'Обучение остановлено', 'timeout':'Превышено время обучения'}
            self.status.set(labels.get(status, 'Локальный запуск завершён') + '. См. фактический результат и метрики.')
        self._launch(lambda:self.training.run_training(model_dir,output_dir,epochs=epochs,max_length=max_length,
                     progress=progress,cancel_event=cancel),done,'Локальное обучение выполняется…')

    def cancel_training(self):
        if self._busy:
            self._cancel.set();self.stop_button.configure(state='disabled')
            self.status.set('Запрошена остановка. Ожидание контрольной точки обучения…')

    def import_model(self):
        if self._busy:return
        name=self.import_name.get().strip();path=self.import_dir.get().strip()
        if not name or not path:
            self.status.set('Укажите новое имя и локальные веса модели.');return
        def done(result):
            self._show_json('Импорт локальной модели: результат',result)
            self.status.set('Импорт завершён. Проверьте модель во вкладке «Локальные агенты».')
        self._launch(lambda:self.training.import_model(name,path),done,'Импорт локальной модели в Ollama…')
