import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from inspections import APPLICABILITY, WORK_STATUS

class InspectionTab(ttk.Frame):
    def __init__(self,parent,store,opener,source_root):
        super().__init__(parent,padding=12)
        self.store=store; self.opener=opener; self.source_root=source_root; self.current=None
        toolbar=ttk.Frame(self); toolbar.pack(fill='x')
        ttk.Label(toolbar,text='Проверка').pack(side='left')
        self.plans=store.cauk_plans(); self.plan=ttk.Combobox(toolbar,state='readonly',values=[p['name'] for p in self.plans],width=22)
        self.plan.pack(side='left',padx=8); self.plan.current(0); self.plan.bind('<<ComboboxSelected>>',lambda _:self.refresh_tree())
        self.filter=ttk.Combobox(toolbar,state='readonly',values=['Все вопросы','Применимые (вкл. предварительные)','Требуют решения','Не применимые'],width=33)
        self.filter.current(0); self.filter.pack(side='left',padx=8); self.filter.bind('<<ComboboxSelected>>',lambda _:self.refresh_tree())
        ttk.Button(toolbar,text='Отчёт по проверке',command=lambda:self.guard(self.report)).pack(side='right')
        self.summary=ttk.Label(self,wraplength=1300); self.summary.pack(fill='x',pady=8)
        split=ttk.Panedwindow(self,orient='horizontal'); split.pack(fill='both',expand=True)
        left=ttk.Frame(split); right=ttk.Frame(split); split.add(left,weight=1); split.add(right,weight=1)
        self.tree=ttk.Treeview(left,columns=('app','state'),show='tree headings',selectmode='browse')
        self.tree.heading('#0',text='Проверка → ОПО → вопрос'); self.tree.column('#0',width=440,minwidth=200)
        self.tree.heading('app',text='Применимость'); self.tree.column('app',width=145,minwidth=80)
        self.tree.heading('state',text='Подготовка'); self.tree.column('state',width=100,minwidth=80)
        sy=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview); sx=ttk.Scrollbar(left,orient='horizontal',command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.tree.grid(row=0,column=0,sticky='nsew'); sy.grid(row=0,column=1,sticky='ns'); sx.grid(row=1,column=0,sticky='ew')
        left.rowconfigure(0,weight=1); left.columnconfigure(0,weight=1)
        self.tree.bind('<<TreeviewSelect>>',self.select_check)
        canvas=tk.Canvas(right,highlightthickness=0); scroll=ttk.Scrollbar(right,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
        editor=ttk.Frame(canvas,padding=(12,0,8,12)); item=canvas.create_window((0,0),window=editor,anchor='nw')
        editor.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=event.width))
        self.heading=ttk.Label(editor,text='Раскройте ОПО и выберите вопрос',font=('Segoe UI',12,'bold'),wraplength=610); self.heading.pack(anchor='w',pady=5)
        self.question=tk.Text(editor,height=7,wrap='word',font=('Segoe UI',10),state='disabled'); self.question.pack(fill='x')
        self.worker=ttk.Label(editor,wraplength=610); self.worker.pack(anchor='w',pady=5)
        self.guidance=tk.Text(editor,height=7,wrap='word',font=('Segoe UI',10),state='disabled'); self.guidance.pack(fill='x',pady=6)
        row=ttk.Frame(editor); row.pack(fill='x')
        ttk.Label(row,text='Применимость').pack(side='left'); self.applicability=ttk.Combobox(row,values=APPLICABILITY,state='readonly',width=16); self.applicability.pack(side='left',padx=8)
        self.confirmed=tk.BooleanVar(); ttk.Checkbutton(editor,text='Решение о применимости подтверждено пользователем',variable=self.confirmed).pack(anchor='w',pady=6)
        ttk.Label(editor,text='Основание применимости / неприменимости').pack(anchor='w')
        self.reason=tk.Text(editor,height=3,wrap='word',font=('Segoe UI',10)); self.reason.pack(fill='x')
        row=ttk.Frame(editor); row.pack(fill='x',pady=8)
        ttk.Label(row,text='Подготовка').pack(side='left'); self.work=ttk.Combobox(row,values=WORK_STATUS,state='readonly',width=20); self.work.pack(side='left',padx=8)
        self.owner=tk.StringVar(); self.deadline=tk.StringVar()
        ttk.Label(editor,text='Исполнитель подготовки (ваш сотрудник)').pack(anchor='w'); ttk.Entry(editor,textvariable=self.owner).pack(fill='x')
        ttk.Label(editor,text='Срок подготовки • ДД.ММ.ГГГГ').pack(anchor='w',pady=(5,0)); ttk.Entry(editor,textvariable=self.deadline).pack(fill='x')
        ttk.Label(editor,text='Результат / замечания / действия').pack(anchor='w',pady=(5,0)); self.answer=tk.Text(editor,height=4,wrap='word',font=('Segoe UI',10)); self.answer.pack(fill='x')
        self.save_button=ttk.Button(editor,text='Сохранить решение и результат',command=lambda:self.guard(self.save),state='disabled'); self.save_button.pack(anchor='w',pady=8)
        ttk.Label(editor,text='Подтверждающие материалы (файлы)').pack(anchor='w')
        self.evidence=ttk.Treeview(editor,columns=('name','type'),show='headings',height=4,selectmode='browse')
        self.evidence.heading('name',text='Имя файла'); self.evidence.column('name',width=340)
        self.evidence.heading('type',text='Источник / наличие'); self.evidence.column('type',width=190)
        self.evidence.pack(fill='x'); self.evidence.bind('<Double-1>',lambda _:self.guard(self.open_evidence))
        bar=ttk.Frame(editor); bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='Добавить файл',command=lambda:self.guard(self.add_evidence)).pack(side='left',padx=2)
        ttk.Button(bar,text='Связать документ',command=lambda:self.guard(self.link_document)).pack(side='left',padx=2)
        ttk.Button(bar,text='Открыть файл',command=lambda:self.guard(self.open_evidence)).pack(side='left',padx=2)
        ttk.Button(editor,text='Открыть фотографию вопроса',command=lambda:self.guard(self.source)).pack(anchor='w')
        ttk.Label(editor,text='Подсказки по материалам подготовлены для работы с программой. Они не являются обязательным нормативным перечнем. Сохраняйте изменения перед выбором другого вопроса.',wraplength=610).pack(anchor='w',pady=8)
        self.message=ttk.Label(self); self.message.pack(fill='x',pady=(8,0))
        self.refresh_tree()
    def guard(self,fn):
        try: fn()
        except Exception as ex: messagebox.showerror('Проверки ЦАУК',str(ex),parent=self)
    def plan_id(self): return self.plans[self.plan.current()]['id']
    def require_check(self):
        if self.current is None: raise ValueError('Раскройте ОПО и выберите конкретный вопрос.')
        return self.current
    def refresh_tree(self):
        current=self.current; opened={node for node in self.tree.get_children('') for node in self.tree.get_children(node) if self.tree.item(node,'open')}
        self.tree.delete(*self.tree.get_children()); plan_id=self.plan_id(); plan=self.plans[self.plan.current()]
        root=f'p{plan_id}'; self.tree.insert('','end',iid=root,text=plan['name'],open=True)
        filt=self.filter.current(); checks=self.store.cauk_checks(plan_id)
        by_asset={}
        for c in checks: by_asset.setdefault(c['asset_id'],[]).append(c)
        for member in self.store.cauk_members(plan_id):
            aid=f'a{member["asset_id"]}'; self.tree.insert(root,'end',iid=aid,text=f'{member["reg_no"]} — {member["name"]}',open=aid in opened)
            for c in by_asset.get(member['asset_id'],[]):
                if filt==1 and c['applicability']!='Применим': continue
                if filt==2 and c['confirmed'] and c['applicability']!='Уточнить': continue
                if filt==3 and c['applicability']!='Не применим': continue
                app=c['applicability']+(' *' if not c['confirmed'] else '')
                self.tree.insert(aid,'end',iid=f'q{c["id"]}',text=f'№{c["question_no"]}. {c["text"].splitlines()[0]}',values=(app,c['work_status']))
        summary=self.store.cauk_summary(plan_id)
        self.summary.configure(text=f'33 ОПО • {summary["total"]} вопросов • Подтверждено применимых: {summary["applicable"]} • Требуют решения: {summary["unresolved"]} • Не применимы: {summary["excluded"]} • Подготовлено: {summary["prepared"]} • Замечания: {summary["issues"]}. Звёздочка: предварительное решение.')
        if current is not None and self.tree.exists(f'q{current}'):
            self.tree.selection_set(f'q{current}'); self.tree.focus(f'q{current}')
        else:
            self.current=None; self.save_button.configure(state='disabled')
    def set_text(self,widget,value,readonly=False):
        widget.configure(state='normal'); widget.delete('1.0','end'); widget.insert('1.0',value)
        if readonly: widget.configure(state='disabled')
    def select_check(self,event=None):
        selection=self.tree.selection()
        if not selection: return
        iid=selection[0]
        if not iid.startswith('q'):
            self.current=None; self.save_button.configure(state='disabled')
            self.heading.configure(text='Раскройте ОПО и выберите вложенный вопрос')
            for widget in (self.question,self.guidance): self.set_text(widget,'',True)
            self.worker.configure(text=''); self.set_text(self.reason,''); self.set_text(self.answer,'')
            self.applicability.set(''); self.work.set(''); self.owner.set(''); self.deadline.set(''); self.confirmed.set(False)
            self.evidence.delete(*self.evidence.get_children()); return
        self.current=int(iid[1:]); c=self.store.cauk_check(self.current)
        self.save_button.configure(state='normal'); self.heading.configure(text=f'{c["reg_no"]} • Вопрос №{c["question_no"]}')
        self.set_text(self.question,c['text'],True)
        self.worker.configure(text=f'Ответственный работник по программе: {c["program_worker"]}\nИсточник: {c["source"]}')
        self.set_text(self.guidance,'Условие применимости:\n'+c['condition']+'\n\n'+c['preparation'],True)
        self.applicability.set(c['applicability']); self.confirmed.set(bool(c['confirmed']))
        self.set_text(self.reason,c['reason']); self.work.set(c['work_status']); self.owner.set(c['owner']); self.deadline.set(c['deadline']); self.set_text(self.answer,c['answer'])
        self.refresh_evidence()
    def refresh_evidence(self):
        self.evidence.delete(*self.evidence.get_children())
        if self.current is None: return
        for item in self.store.cauk_evidence(self.current):
            exists=self.store.cauk_evidence_path(item['id']).is_file()
            origin='Из реестра' if item['document_id'] is not None else 'Файл проверки'
            self.evidence.insert('','end',iid=str(item['id']),values=(item['original_name'],origin+(' / есть' if exists else ' / отсутствует')))
    def save(self):
        check_id=self.require_check()
        self.store.update_cauk_check(check_id,self.applicability.get(),self.confirmed.get(),self.reason.get('1.0','end').strip(),self.work.get(),self.answer.get('1.0','end').strip(),self.owner.get(),self.deadline.get())
        self.refresh_tree(); self.message.configure(text='Решение и результат сохранены. Применимость и подготовка подтверждаются пользователем.')
    def add_evidence(self):
        check_id=self.require_check(); path=filedialog.askopenfilename(parent=self,title='Подтверждение по вопросу проверки')
        if path:
            self.store.add_cauk_evidence(check_id,path); self.refresh_evidence(); self.message.configure(text='Файл скопирован и привязан к выбранному вопросу.')
    def link_document(self):
        check_id=self.require_check(); docs=self.store.cauk_linkable_documents(check_id)
        if not docs: raise ValueError('Нет доступных документов. Добавьте файл здесь или в реестре ОПО.')
        win=tk.Toplevel(self); win.title('Связать существующий документ'); win.transient(self.winfo_toplevel()); win.grab_set(); win.geometry('850x220')
        frame=ttk.Frame(win,padding=16); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='Общие вопросы №4, 7, 8 допускают документ из другого ОПО. Файл не копируется повторно.',wraplength=800).pack(anchor='w')
        choice=ttk.Combobox(frame,state='readonly',values=[f'{d["id"]} / {d["reg_no"]} / {d["title"]}' for d in docs]); choice.current(0); choice.pack(fill='x',pady=15)
        def save():
            self.store.link_cauk_document(check_id,docs[choice.current()]['id']); win.destroy(); self.refresh_evidence()
        ttk.Button(frame,text='Связать',command=lambda:self.guard(save)).pack(anchor='w')
    def open_evidence(self):
        self.require_check(); selected=self.evidence.selection()
        if not selected: raise ValueError('Выберите подтверждающий файл.')
        self.opener(self.store.cauk_evidence_path(int(selected[0])))
    def source(self):
        c=self.store.cauk_check(self.require_check()); self.opener(self.source_root/c['source'])
    def report(self):
        path=filedialog.asksaveasfilename(parent=self,title='Отчёт по проверке ЦАУК',initialfile='CAUK_October_2026.html',defaultextension='.html',filetypes=[('HTML','*.html')])
        if path:
            self.store.cauk_report(self.plan_id(),path); self.message.configure(text=f'Отчёт сохранён: {path}')
