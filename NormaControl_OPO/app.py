"""PromControl Stage 1: native Tk desktop UI. Python 3.11+."""
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from core import Store, LABELS, document_status
from inspection_ui import InspectionTab
from agent_ui import AgentsTab
from learning_ui import KnowledgeTab, TrainingTab
from regulations import NormativeCatalog
from regulations_ui import RegulationsTab
from situation_ui import SituationsTab, RequirementsTab
from ui_scale import fit_window, px, responsive_wraplength, scale_treeview_columns

VERSION='1.0 RC2'

BASE=Path(__file__).resolve().parent

def data_root():
    override=os.environ.get('PROMCONTROL_DATA_DIR')
    if override: return Path(override)
    if sys.platform=='win32':
        base=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))
        legacy=base/'PromControlStage1'
        return legacy if (legacy/'promcontrol.sqlite3').is_file() else base/'NormaControlOPO'
    return Path.home()/'PromControlStage1'

def open_file(path):
    if not Path(path).is_file(): raise ValueError('Файл отсутствует.')
    if sys.platform=='win32': os.startfile(str(path))
    elif sys.platform=='darwin': subprocess.Popen(['open',str(path)])
    else: subprocess.Popen(['xdg-open',str(path)])

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'НормаКонтроль ОПО • Windows • {VERSION}')
        scale_treeview_columns(self)
        self.window_state=fit_window(self,1380,850,1000,680,maximize_if_small=True)
        self.store=Store(data_root(),BASE/'registry.json'); self.current=None
        self.normative_catalog=NormativeCatalog(self.store.root)
        # Подготовка базы идёт до построения вкладок; окно обновляется, чтобы Windows не считала его зависшим.
        self.protocol('WM_DELETE_WINDOW',lambda:None)
        self.splash=ttk.Label(self,text="НормаКонтроль ОПО: подготовка базы знаний… Первый запуск может занять несколько минут.",padding=30,justify='left')
        self.splash.pack(fill="both",expand=True); self.update()
        self.normative_seed=self.normative_catalog.seed(progress=self._seed_progress)
        self.normative_catalog.authorize_uploaded_corpus()
        self.splash.destroy()
        self.protocol('WM_DELETE_WINDOW',self.quit_app)
        style=ttk.Style(self); style.theme_use('clam')
        style.configure('Treeview',rowheight=px(self,30),font=('Segoe UI',10))
        style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'))
        style.configure('TButton',padding=6); style.configure('TLabel',font=('Segoe UI',10))
        header=ttk.Frame(self,padding=16); header.pack(fill='x')
        ttk.Label(header,text='НОРМАКОНТРОЛЬ ОПО',font=('Segoe UI',19,'bold')).pack(side='left')
        ttk.Button(header,text='Резервная копия',command=lambda:self.guard(self.backup)).pack(side='right',padx=5)
        ttk.Button(header,text='Сводный отчёт',command=lambda:self.guard(self.export)).pack(side='right')
        ttk.Label(self,text='Документы и ЦАУК • Локальная база знаний, OCR, агенты и подготовка дообучения.',padding=(16,5)).pack(fill='x')
        sections=ttk.Notebook(self); self.sections=sections; sections.pack(fill='both',expand=True,padx=8,pady=5)
        registry_tab=ttk.Frame(sections); sections.add(registry_tab,text='Реестр ОПО и документы')
        main=ttk.Panedwindow(registry_tab,orient='horizontal'); main.pack(fill='both',expand=True,padx=16,pady=8)
        left=ttk.Frame(main,width=470); right=ttk.Frame(main); main.add(left,weight=2); main.add(right,weight=3)
        self.search=tk.StringVar(); self.search.trace_add('write',lambda *_:self.refresh_assets())
        ttk.Label(left,text='Реестр ОПО • поиск по номеру / названию').pack(anchor='w')
        ttk.Entry(left,textvariable=self.search).pack(fill='x',pady=6)
        self.assets=self.table(left,('reg','name','class'),('Рег. номер','Наименование','Класс'),(155,290,55))
        self.assets.bind('<<TreeviewSelect>>',self.select_asset)
        self.asset_count=ttk.Label(left); self.asset_count.pack(anchor='w',pady=6)
        self.title_label=ttk.Label(right,text='Выберите ОПО',font=('Segoe UI',13,'bold'),wraplength=750)
        self.title_label.pack(anchor='w',pady=6)
        self.meta=ttk.Label(right,wraplength=750); self.meta.pack(anchor='w')
        notebook=ttk.Notebook(right); notebook.pack(fill='both',expand=True,pady=10)
        card=ttk.Frame(notebook,padding=12); docs=ttk.Frame(notebook,padding=12); reqs=ttk.Frame(notebook,padding=12)
        notebook.add(card,text='Карточка'); notebook.add(docs,text='Документы'); notebook.add(reqs,text='Перечень и полнота')
        self.owner=tk.StringVar(); self.verified=tk.BooleanVar()
        ttk.Label(card,text='Ответственный').pack(anchor='w'); ttk.Entry(card,textvariable=self.owner).pack(fill='x',pady=5)
        ttk.Checkbutton(card,text='Карточка сверена с оригиналом пользователем',variable=self.verified).pack(anchor='w',pady=8)
        ttk.Label(card,text='Примечания / состав оборудования / уточнения').pack(anchor='w')
        self.notes=tk.Text(card,height=8,wrap='word',font=('Segoe UI',10)); self.notes.pack(fill='both',expand=True,pady=6)
        ttk.Button(card,text='Сохранить карточку',command=lambda:self.guard(self.save_card)).pack(anchor='w',pady=5)
        ttk.Button(card,text='Открыть фотографию-источник',command=lambda:self.guard(self.source)).pack(anchor='w')
        bar=ttk.Frame(docs); bar.pack(fill='x')
        for text,fn in [('Добавить файл',self.add_document),('Открыть файл',self.open_document),('В архив',self.archive)]:
            ttk.Button(bar,text=text,command=lambda fn=fn:self.guard(fn)).pack(side='left',padx=3)
        ttk.Label(docs,text='Даты и реквизиты вводятся вручную. Исправление: добавьте новую запись, старую переведите в архив.',wraplength=720).pack(anchor='w',pady=10)
        self.docs=self.table(docs,('title','date','status','review'),('Документ','Окончание','Статус','Проверка'),(230,90,185,115))
        ttk.Button(reqs,text='Добавить вид документа в перечень',command=lambda:self.guard(self.add_requirement)).pack(anchor='w')
        self.completeness_label=ttk.Label(reqs,wraplength=720); self.completeness_label.pack(anchor='w',pady=10)
        self.reqs=self.table(reqs,('title','basis','state'),('Вид документа','Основание пользователя','Состояние'),(195,195,260))
        ttk.Label(reqs,text='Перечень задаёт пользователь. Проверка по нему не является проверкой соблюдения законодательства.',wraplength=720).pack(anchor='w',pady=8)
        self.inspections=InspectionTab(sections,self.store,open_file,BASE/'sources')
        sections.add(self.inspections,text='Проверки ЦАУК')
        self.knowledge=KnowledgeTab(sections,self.store,open_file)
        sections.add(self.knowledge,text='База знаний / OCR')
        self.regulations=RegulationsTab(sections,self.store,open_file)
        sections.add(self.regulations,text='Нормативный каталог')
        self.training=TrainingTab(sections,self.store)
        sections.add(self.training,text='Обучение ИИ')
        self.agents=AgentsTab(sections,self.store)
        sections.add(self.agents,text='Локальные агенты')
        self.situations=SituationsTab(sections,self.store,open_file,self.send_situation_to_agent)
        sections.add(self.situations,text='Ситуационные проверки')
        self.norm_requirements=RequirementsTab(sections,self.store,open_file)
        sections.add(self.norm_requirements,text='Проверенные требования')
        self.status=ttk.Label(self,text=f'Данные: {self.store.root}',padding=(16,8)); self.status.pack(fill='x',side='bottom',before=sections)
        upgraded=self.normative_seed.get('local_texts_upgraded') or 0
        cleanup=self.normative_seed.get('service_text_cleanup') or {}
        if upgraded or cleanup.get('sources'):
            self.status.configure(text=f'Данные: {self.store.root} • Обновление базы: очищенных текстов НД {upgraded}, источников с удалёнными служебными надписями {cleanup.get("sources",0)}. Ссылки и отметки сохранены.')
        if self.normative_seed.get('errors'):
            self.status.configure(text=self.status.cget('text')+' • Ошибки каталога: '+str(len(self.normative_seed['errors']))+' (вкладка «Нормативный каталог»).')
        responsive_wraplength(self)
        self.refresh_assets()
    def _seed_progress(self,index,total,title):
        self.splash.configure(text=f'НормаКонтроль ОПО: подготовка базы знаний… {index} из {total}\n{title[:120]}\n\nПервый запуск или обновление может занять несколько минут. Не закрывайте окно.')
        self.update()
    def send_situation_to_agent(self,record):
        self.sections.select(self.agents)
        self.agents.role.current(self.agents._role_ids.index('regulatory'))
        aid=record['asset_id']
        self.agents.asset.current(self.agents._asset_ids.index(aid))
        self.agents.task.delete('1.0','end')
        self.agents.task.insert('1.0','Разбери производственную ситуацию по предоставленным нормативным источникам. Укажи документы, редакции, пункты и необходимые уточнения. Не устанавливай соответствие без доказательств.\n\n'+record['title']+'\nКатегория: '+record['category']+'\nМесто: '+record['location']+'\nОписание: '+record['description'])
        self.agents.status.set('Ситуация передана. Проверьте модель и нажмите «Запустить». Фото не анализируется автоматически.')

    def table(self,parent,columns,headings,widths):
        frame=ttk.Frame(parent); frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse')
        for col,heading,width in zip(columns,headings,widths):
            tree.heading(col,text=heading); tree.column(col,width=width,minwidth=60)
        sy=ttk.Scrollbar(frame,orient='vertical',command=tree.yview); sx=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
        tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        tree.grid(row=0,column=0,sticky='nsew'); sy.grid(row=0,column=1,sticky='ns'); sx.grid(row=1,column=0,sticky='ew')
        frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        return tree
    def guard(self,fn):
        try: fn()
        except Exception as ex: messagebox.showerror('НормаКонтроль ОПО',str(ex),parent=self)
    def require_current(self):
        if self.current is None: raise ValueError('Выберите ОПО в реестре.')
        return self.current
    def refresh_assets(self):
        if not hasattr(self,'assets'): return
        selected=self.current
        self.assets.delete(*self.assets.get_children()); q=self.search.get().casefold().strip(); count=0
        for asset in self.store.assets():
            if q and q not in (asset['reg_no']+' '+asset['name']).casefold(): continue
            self.assets.insert('', 'end', iid=str(asset['seq']),values=(asset['reg_no'],asset['name'],asset['danger_class'])); count+=1
        self.asset_count.configure(text=f'Показано {count} из 33 • I: 4 / II: 9 / III: 18 / IV: 2')
        if selected is not None and self.assets.exists(str(selected)): self.assets.selection_set(str(selected))
    def select_asset(self,event=None):
        sel=self.assets.selection()
        if not sel: return
        self.current=int(sel[0]); self.refresh_card()
    def refresh_card(self):
        asset=self.store.asset(self.current)
        self.title_label.configure(text=f'{asset["reg_no"]}\n{asset["name"]}')
        self.meta.configure(text=f'Класс {asset["danger_class"]} • Признаки {asset["signs"]} • Регистрация {asset["registered"]}\nПризнаки: уточнение пользователя 01.10.2026. Название и класс: {asset["source"]}.')
        self.owner.set(asset['owner']); self.verified.set(bool(asset['verified']))
        self.notes.delete('1.0','end'); self.notes.insert('1.0',asset['notes'])
        self.docs.delete(*self.docs.get_children())
        for d in self.store.documents(self.current):
            state='Архив' if d['superseded'] else LABELS[document_status(d['expiry'],d['permanent'])]
            if not self.store.document_path(d['id']).is_file(): state+=' / ФАЙЛ ОТСУТСТВУЕТ'
            self.docs.insert('','end',iid=str(d['id']),values=(d['title'],d['expiry'],state,'Пользователь' if d['reviewed'] else 'Не проверен'))
        self.reqs.delete(*self.reqs.get_children()); checks=self.store.completeness(self.current)
        for r,state in checks: self.reqs.insert('','end',values=(r['title'],r['basis'],state))
        missing=sum(s=='Не загружен' for _,s in checks)
        self.completeness_label.configure(text=f'В перечне: {len(checks)}. Не загружено: {missing}. Оценка только по перечню пользователя.' if checks else 'Перечень не настроен. Полнота не оценена.')
    def save_card(self):
        asset_id=self.require_current()
        self.store.update_asset(asset_id,self.owner.get().strip(),self.notes.get('1.0','end').strip(),self.verified.get())
        self.status.configure(text=f'Карточка сохранена. Данные: {self.store.root}')
    def source(self):
        asset=self.store.asset(self.require_current()); open_file(BASE/'sources'/asset['source'])
    def dialog(self,title):
        win=tk.Toplevel(self); win.title(title); win.transient(self); win.grab_set(); fit_window(win,650,550)
        frame=ttk.Frame(win,padding=18); frame.pack(fill='both',expand=True)
        return win,frame
    def field(self,frame,label,initial=''):
        ttk.Label(frame,text=label).pack(anchor='w',pady=(6,0)); v=tk.StringVar(value=initial)
        ttk.Entry(frame,textvariable=v).pack(fill='x'); return v
    def add_requirement(self):
        asset_id=self.require_current(); win,frame=self.dialog('Перечень документов пользователя')
        title=self.field(frame,'Вид документа')
        basis=self.field(frame,'Основание: документ, пункт, применимость к этому ОПО')
        ttk.Label(frame,text='Можно указать внутренний перечень или точную нормативную ссылку. Автоматическая проверка основания пока не выполняется.',wraplength=600).pack(anchor='w',pady=15)
        def save():
            self.store.add_requirement(asset_id,title.get(),basis.get()); win.destroy(); self.refresh_card()
        ttk.Button(frame,text='Добавить',command=lambda:self.guard(save)).pack(anchor='w',pady=10)
    def add_document(self):
        asset_id=self.require_current()
        path=filedialog.askopenfilename(parent=self,title='Выберите документ для локального хранения')
        if not path: return
        win,frame=self.dialog('Добавить документ'); fit_window(win,650,730)
        ttk.Label(frame,text=Path(path).name,wraplength=600).pack(anchor='w')
        title=self.field(frame,'Название документа',Path(path).stem); number=self.field(frame,'Номер')
        issued=self.field(frame,'Дата документа • ДД.ММ.ГГГГ'); expiry=self.field(frame,'Окончание срока • ДД.ММ.ГГГГ (пусто = неизвестно)')
        permanent=tk.BooleanVar(); reviewed=tk.BooleanVar()
        ttk.Checkbutton(frame,text='Срок не ограничен — подтверждено пользователем',variable=permanent).pack(anchor='w',pady=8)
        ttk.Checkbutton(frame,text='Содержание проверено пользователем',variable=reviewed).pack(anchor='w',pady=8)
        reqs=self.store.requirements(asset_id); options=['Без привязки к перечню']+[f'{r["id"]}: {r["title"]}' for r in reqs]
        ttk.Label(frame,text='Связать с видом документа из перечня').pack(anchor='w',pady=(8,0))
        choice=ttk.Combobox(frame,values=options,state='readonly'); choice.current(0); choice.pack(fill='x')
        ttk.Label(frame,text='Файл будет сохранён и направлен в базу знаний для извлечения текста/OCR. Ошибки извлечения видны на вкладке базы знаний. Правильность срока подтверждает пользователь.',wraplength=600).pack(anchor='w',pady=15)
        def save():
            index=choice.current(); req_id=reqs[index-1]['id'] if index>0 else None
            self.store.add_document(asset_id,path,title.get(),number.get(),issued.get(),expiry.get(),permanent.get(),reviewed.get(),req_id)
            win.destroy(); self.refresh_card()
            self.knowledge.index_asset(asset_id)
        ttk.Button(frame,text='Сохранить файл и реквизиты',command=lambda:self.guard(save)).pack(anchor='w',pady=10)
    def selected_document(self):
        selected=self.docs.selection()
        if not selected: raise ValueError('Выберите документ.')
        return int(selected[0])
    def open_document(self): open_file(self.store.document_path(self.selected_document()))
    def archive(self):
        doc_id=self.selected_document()
        self.store.supersede(doc_id); self.refresh_card()
    def export(self):
        path=filedialog.asksaveasfilename(parent=self,title='Сохранить статус документов',defaultextension='.html',initialfile='PromControl_status.html',filetypes=[('HTML','*.html')])
        if path:
            self.store.report(path); self.status.configure(text=f'Отчёт сохранён: {path}')
    def backup(self):
        path=filedialog.asksaveasfilename(parent=self,title='Сохранить резервную копию вне папки данных',defaultextension='.zip',initialfile='PromControl_backup.zip',filetypes=[('ZIP','*.zip')])
        if path:
            result=self.store.backup(path)
            missing=f'; отсутствуют файлы: {len(result["missing_files"])}' if result['missing_files'] else ''
            self.status.configure(text=f'Резервная копия сохранена и проверена (integrity {result["integrity"]}, файлов {result["files"]}{missing}): {path}')
    def quit_app(self):
        self.agents.shutdown()
        self.knowledge.shutdown()
        self.training.shutdown()
        self.regulations.shutdown()
        self.situations.shutdown()
        self.norm_requirements.shutdown()
        self.store.close()
        self.destroy()

if __name__=='__main__': App().mainloop()
