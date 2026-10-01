"""Каталог нормативных карточек и фактически полученных локальных файлов."""
import json
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog
from learning_ui import _WorkerTab, _text, _set_text
from regulations import NormativeCatalog
from knowledge import KnowledgeBase


LOCAL_LABELS = {
    'card_only': 'Только карточка',
    'not_seeded': 'Карточка не импортирована',
    'official_file_partial': 'Официальный файл — текст извлечён частично',
    'official_file_error': 'Ошибка извлечения официального файла',
    'official_file_indexed': 'Официальный файл получен — редакцию проверить',
    'user_copy_indexed': 'Пользовательская копия — редакцию проверить',
    'needs_revision_check': 'Локальная копия — редакцию проверить',
    'local_material_indexed': 'Локальный материал — полноту проверить',
    'download_failed': 'Ошибка загрузки',
}


class RegulationsTab(_WorkerTab):
    def __init__(self, parent, store, open_file):
        super().__init__(parent)
        # seed() выполняется приложением до создания вкладки; здесь нет повторного импорта.
        self.catalog = NormativeCatalog(store.root)
        self.kb = KnowledgeBase(store.root)
        self.open_file = open_file
        self._records = []
        self._shown = {}
        self.query = tk.StringVar()
        self.filter_status = tk.StringVar(value='Все локальные статусы')
        self.ocr_lang = tk.StringVar(value='rus+eng')
        self.counts = tk.StringVar(value='Каталог загружается…')
        ttk.Label(self, text='Нормативный каталог: карточка содержит реквизиты и описание, а не полный текст документа. '
                  'Даже загруженный официальный файл может быть исходной публикацией без последующих изменений. '
                  'Действующую редакцию, полноту и применимость необходимо проверить отдельно.', wraplength=1150).pack(anchor='w')
        ttk.Label(self, text='Загрузка с официальных сайтов требует интернета на этапе подготовки. '
                  'Работа агентов с сохранёнными файлами выполняется локально. Пользовательские копии не подтверждаются автоматически.',
                  wraplength=1150).pack(anchor='w', pady=4)
        bar = ttk.Frame(self); bar.pack(fill='x', pady=3)
        self.entry(bar, 'Поиск: название / номер / область', self.query, 50)
        self.status_filter = self.control(ttk.Combobox(bar, textvariable=self.filter_status,
                       values=['Все локальные статусы'], state='readonly', width=43), 'readonly')
        self.status_filter.pack(side='left', padx=4)
        self.button(bar, 'Применить фильтр', self.apply_filter)
        self.query.trace_add('write', lambda *_: self.apply_filter())
        self.status_filter.bind('<<ComboboxSelected>>', lambda _: self.apply_filter())
        bar = ttk.Frame(self); bar.pack(fill='x')
        self.entry(bar, 'Язык OCR', self.ocr_lang, 12)
        self.button(bar, 'Обновить каталог', self.refresh)
        self.button(bar, 'Официальная страница', self.open_official)
        self.button(bar, 'Открыть локальный файл', self.open_local)
        self.button(bar, 'Экспорт каталога JSON', self.export_catalog)
        bar = ttk.Frame(self); bar.pack(fill='x')
        self.button(bar, 'Загрузить выбранный официальный файл', self.download_selected)
        self.button(bar, 'Загрузить все с прямой ссылкой на файл', self.download_all)
        self.stop_button = ttk.Button(bar, text='Остановить массовую загрузку', command=self.cancel_download, state='disabled')
        self.stop_button.pack(side='left', padx=4)
        ttk.Label(self, textvariable=self.counts, wraplength=1150).pack(anchor='w', pady=5)
        split = ttk.Panedwindow(self, orient='vertical'); split.pack(fill='both', expand=True)
        table_frame = ttk.Frame(split); details_frame = ttk.Frame(split)
        split.add(table_frame, weight=2); split.add(details_frame, weight=3)
        self.tree = self.control(ttk.Treeview(table_frame, columns=('number','title','domain','local'),
                                  show='headings', selectmode='browse', height=9))
        for key, label, width in [('number','Номер / дата',170), ('title','Документ',450),
                                  ('domain','Область',200), ('local','Локальные материалы',330)]:
            self.tree.heading(key,text=label); self.tree.column(key,width=width,minwidth=90)
        sy = ttk.Scrollbar(table_frame, orient='vertical', command=self.tree.yview)
        sx = ttk.Scrollbar(table_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0,column=0,sticky='nsew'); sy.grid(row=0,column=1,sticky='ns'); sx.grid(row=1,column=0,sticky='ew')
        table_frame.rowconfigure(0,weight=1); table_frame.columnconfigure(0,weight=1)
        self.tree.bind('<<TreeviewSelect>>', self.show_record)
        ttk.Label(details_frame,text='Реквизиты, происхождение, ограничения и ошибки').pack(anchor='w')
        self.details = _text(details_frame, height=12, readonly=True)
        # _WorkerTab использует log для сообщений фоновой загрузки.
        self.log = _text(self, height=3, readonly=True)
        ttk.Label(self,textvariable=self.status,wraplength=1150).pack(anchor='w',pady=4)
        self.refresh()

    @staticmethod
    def _string(value):
        if isinstance(value,(list,tuple)):
            return '; '.join(str(item) for item in value)
        if isinstance(value,dict):
            return json.dumps(value,ensure_ascii=False)
        return '' if value is None else str(value)

    @staticmethod
    def _act_id(record):
        return str(record.get('act_id') or record.get('id') or '')

    @staticmethod
    def _local_label(record):
        raw=record.get('local_status','not_seeded')
        return LOCAL_LABELS.get(raw,raw)

    def refresh(self):
        if self._busy:return
        self._launch(self.catalog.records,self._load_records,'Чтение локального каталога…')

    def _load_records(self,rows):
        self._records=[dict(row) for row in rows]
        options=['Все локальные статусы']+sorted({self._local_label(row) for row in self._records})
        self.status_filter.configure(values=options)
        if self.filter_status.get() not in options:self.filter_status.set(options[0])
        self.apply_filter()
        self.status.set('Каталог обновлён. Реквизиты карточек не подтверждают действующую редакцию.')

    def apply_filter(self):
        if self._busy or self._closed:return
        query=self.query.get().strip().casefold(); status=self.filter_status.get()
        selected=self.tree.selection()
        previous=selected[0] if selected else None
        self.tree.delete(*self.tree.get_children());self._shown={}
        for row in self._records:
            search=' '.join(self._string(row.get(key,'')) for key in
                           ('title','number','issuer','domain','category','applicability','status','local_status')).casefold()
            if query and query not in search:continue
            if status!='Все локальные статусы' and self._local_label(row)!=status:continue
            key=self._act_id(row);self._shown[key]=row
            self.tree.insert('','end',iid=key,values=(f"{row.get('number','')} / {row.get('date','')}",row.get('title',''),
                         self._string(row.get('domain') or row.get('category') or row.get('applicability','')),self._local_label(row)))
        official=sum(bool(r.get('downloaded_source_id')) for r in self._records)
        imported=sum(bool(r.get('imported_text_source_id')) and not r.get('downloaded_source_id') for r in self._records)
        cards_only=sum(bool(r.get('source_id')) and not r.get('downloaded_source_id') and not r.get('imported_text_source_id') for r in self._records)
        available=sum(bool(r.get('file_url')) for r in self._records)
        self.counts.set(f'Записей: {len(self._records)} • показано: {len(self._shown)} • получено официальных файлов: {official} '
                       f'• импортировано локальных материалов: {imported} • только карточки: {cards_only} '
                       f'• прямых ссылок на файлы: {available}. Наличие файла не подтверждает полноту или актуальность редакции.')
        if previous in self._shown:
            self.tree.selection_set(previous);self.show_record()
        else:_set_text(self.details,'Выберите запись каталога для просмотра реквизитов и локального состояния.')

    def selected_record(self):
        if self._busy:return None
        selected=self.tree.selection()
        if not selected:
            self.status.set('Выберите запись каталога.');return None
        return self._shown.get(selected[0])

    def show_record(self,event=None):
        row=self.selected_record()
        if row is None:return
        labels=[('Идентификатор','id'),('Наименование','title'),('Исходное имя файла','original_filename'),('Редакция из заголовка','revision_from_document'),('Дата сохранения из документа','saved_on_from_document'),('Орган','issuer'),('Номер','number'),('Дата документа','date'),
                ('Официальная страница','official_url'),('Прямая ссылка на файл','file_url'),('Область','domain'),
                ('Применимость из перечня','applicability'),('Описание из перечня','summary'),
                ('Примечания проверки','verification_note'),('Дополнительные примечания','verification_notes'),('Заявленный статус записи','status'),('Сведения о сроке из перечня','known_validity'),
                ('Дата проверки записи составителем','verified_on'),('Дата локальной загрузки / проверки backend','checked'),
                ('Происхождение локального материала','provenance'),('Ошибка последней операции','last_error')]
        lines=['РЕКВИЗИТЫ КАТАЛОГА — НЕ ПОЛНЫЙ ТЕКСТ И НЕ ЗАКЛЮЧЕНИЕ О ДЕЙСТВУЮЩЕЙ РЕДАКЦИИ',
               'Локальное состояние: '+self._local_label(row),'']
        lines.extend(label+': '+(self._string(row.get(key)) or 'Не указано') for label,key in labels)
        if row.get('downloaded_source_id'):
            lines.append('\nОфициальный файл получен и проиндексирован. Это может быть исходная публикация; консолидация изменений не подтверждена.')
        elif row.get('imported_text_source_id'):
            lines.append('\nЛокальный материал присутствует. Его происхождение, полнота и редакция требуют проверки. Автоматического подтверждения нет.')
        else:
            lines.append('\nПолного локального текста по этой записи нет. Открывается только карточка с реквизитами, если она импортирована.')
        _set_text(self.details,'\n'.join(lines))

    def open_official(self):
        row=self.selected_record()
        if row is None:return
        url=row.get('official_url') or ''
        if not url:
            self.status.set('В карточке отсутствует официальная ссылка.');return
        # Это браузер пользователя на его ПК при запуске локальной программы.
        if webbrowser.open(url):self.status.set('Официальная страница открыта в браузере. Требуется интернет.')
        else:self.status.set('Браузер не удалось открыть. Скопируйте URL из реквизитов.')

    def open_local(self):
        row=self.selected_record()
        if row is None:return
        sid=row.get('downloaded_source_id') or row.get('imported_text_source_id') or row.get('source_id')
        if not sid:
            self.status.set('Локальный файл или карточка отсутствует.');return
        card=not row.get('downloaded_source_id') and not row.get('imported_text_source_id')
        def done(path):
            self.open_file(path)
            self.status.set('Открыта только карточка с реквизитами; полного текста нет.' if card else
                            'Открыт локальный материал. Полнота и действующая редакция требуют проверки.')
        self._launch(lambda:self.kb.open_path(sid),done,'Открытие сохранённого локального материала…')

    def download_selected(self):
        row=self.selected_record()
        if row is None:return
        act_id=self._act_id(row);lang=self.ocr_lang.get().strip() or 'rus+eng'
        def done(result):
            self._show_json('Загрузка официального файла: фактический результат',result)
            self.refresh()
        self._launch(lambda:self.catalog.download_official(act_id,ocr_lang=lang),done,'Загрузка выбранного официального файла и индексирование…')

    def download_all(self):
        if self._busy:return
        candidates=[row for row in self._records if row.get('file_url')]
        if not candidates:
            self.status.set('В каталоге нет прямых ссылок на файлы. Массовая загрузка не запущена.');return
        lang=self.ocr_lang.get().strip() or 'rus+eng';events=self._queue;cancel=self._cancel
        _set_text(self.log,'')
        def progress(index,total,result):
            events.put(('log',f"{index}/{total}: {result.get('act_id','')} — {result.get('status','')} {result.get('error','')}",''))
        def done(result):
            self._show_json('Массовая загрузка: фактический результат',result)
            self.refresh()
        self._launch(lambda:self.catalog.download_all(ocr_lang=lang,progress=progress,cancel_event=cancel),done,
                     f'Загрузка файлов по {len(candidates)} прямым ссылкам. Требуется интернет…')

    def cancel_download(self):
        if self._busy:
            self._cancel.set();self.stop_button.configure(state='disabled')
            self.status.set('Запрошена остановка массовой загрузки после текущего файла.')

    def export_catalog(self):
        if self._busy:return
        path=filedialog.asksaveasfilename(parent=self,title='Экспорт нормативного каталога',defaultextension='.json',
                 initialfile='PromControl_regulations_catalog.json',filetypes=[('JSON','*.json')])
        if not path:return
        records=[dict(row) for row in self._records]
        def operation():
            payload={'notice':'Карточки и локальные состояния. Полнота текстов и действующая редакция не подтверждены автоматически.',
                     'records':records}
            with open(path,'w',encoding='utf-8') as out:json.dump(payload,out,ensure_ascii=False,indent=2,default=str)
            return path
        self._launch(operation,lambda _:self.status.set('Каталог экспортирован.'),'Экспорт каталога…')
