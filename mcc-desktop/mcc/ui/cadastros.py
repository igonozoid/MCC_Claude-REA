"""Cadastros: telas de navegacao (FBanBrs, FCenBrs, FConBrs, FPesBrs, FIteBrs, FTraBrs)
e de edicao (FBanCad, FCenCad, FConCad, FPesCad, FIteCad, FTraCad)."""
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QStatusBar, QTabWidget, QVBoxLayout, QWidget)

from ..core import finance as fin
from ..core.auth import COMPLETO
from . import estilo as E
from .base import (BitBtn, BotaoTopo, Campo, CampoData, CampoValor, ComboDados, FormBase, Grade, RadioGrupo, SpeedButton,
                   confirmar, executar, icone, msg_aviso, msg_info, rotulo)
from .lancamentos import _bt_cancela, _bt_confirma, _por, _rot

UFS = 'AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO'.split()
BANCOS = ['BANCO DO BRASIL', 'BRADESCO', 'CAIXA ECONOMICA FEDERAL', 'BANCO ITAÚ', 'BANCO SANTANDER', 'BANRISUL', 'BANCO INTER', 'NUBANK',
          'C6 BANK', 'BTG PACTUAL', 'SICOOB', 'SICREDI', 'UNICRED', 'BANCO SAFRA', 'BANESTES', 'BANCO DO NORDESTE', 'BANCO ORIGINAL',
          'MERCADOPAGO', 'PAGSEGURO', 'PICPAY', 'PAYPAL', 'NEON', 'PAN', 'XP', 'CIELO', 'ASAAS', 'CAIXA INTERNO', 'OUTROS']


class Navegador(FormBase):
    """Tela de navegacao: Incluir / Alterar / Excluir (+Localizar) com glifo em cima, navegador + Voltar, grade e barra de status."""

    def __init__(self, parent, titulo, colunas, largura=520, altura=400, modulo=None, s=None, localizar=False, extra_rodape=None):
        super().__init__(parent, titulo, largura, altura, cor=E.FUNDO_CADASTRO)
        self.setMinimumSize(largura, altura)
        self.setMaximumSize(16777215, 16777215)
        self.s = s
        self.edita = s.nivel(modulo) >= COMPLETO if modulo else True
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        topo = QFrame()
        topo.setFixedHeight(71)
        h = QHBoxLayout(topo)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(3)
        self.bt_inc = BotaoTopo('&Incluir', icone('fa6s.file-circle-plus', '#1a7f37'), dica='Incluir novo registro')
        self.bt_alt = BotaoTopo('&Alterar' if self.edita else '&Consultar', icone('fa6s.pen-to-square', E.NAVY), dica='Altera/Consulta o registro selecionado')
        self.bt_exc = BotaoTopo('&Excluir', icone('fa6s.trash-can', '#b02a2a'), dica='Exclui o registro selecionado')
        for b in (self.bt_inc, self.bt_alt, self.bt_exc):
            h.addWidget(b)
        self.bt_inc.setEnabled(self.edita)
        self.bt_exc.setEnabled(self.edita)
        if localizar:
            self.bt_loc = BotaoTopo('&Localizar', icone('fa6s.magnifying-glass', E.NAVY), dica='Localizar pelo nome')
            h.addWidget(self.bt_loc)
            self.bt_loc.clicked.connect(lambda: self.busca.setFocus())
        nav = QWidget()
        nav.setFixedWidth(250)
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(3, 0, 0, 0)
        nv.setSpacing(3)
        nh = QHBoxLayout()
        nh.setSpacing(0)
        for ic, dica, fn in (('fa6s.backward-step', 'Primeiro', lambda: self.mover('p')), ('fa6s.caret-left', 'Anterior', lambda: self.mover(-1)),
                             ('fa6s.caret-right', 'Próximo', lambda: self.mover(1)), ('fa6s.forward-step', 'Último', lambda: self.mover('u')),
                             ('fa6s.rotate', 'Atualizar', self.carregar)):
            sb = SpeedButton('', icone(ic, '#333'), dica=dica)
            sb.setFixedHeight(29)
            sb.setStyleSheet('QToolButton { border: 1px solid #adadad; background: #f3f3f3; }')
            sb.clicked.connect(fn)
            nh.addWidget(sb)
        nv.addLayout(nh)
        voltar = SpeedButton('&Voltar', icone('fa6s.arrow-left', '#333'), dica='Voltar para a tela principal')
        voltar.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
        voltar.setStyleSheet('QToolButton { border: 1px solid #adadad; background: #f3f3f3; }')
        voltar.setFixedHeight(32)
        voltar.clicked.connect(self.reject)
        nv.addWidget(voltar)
        h.addWidget(nav)
        h.addStretch()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText('Localizar…')
        self.busca.setClearButtonEnabled(True)
        self.busca.setFixedWidth(180)
        self.busca.textChanged.connect(self._filtrar)
        h.addWidget(self.busca, 0, Qt.AlignBottom)
        v.addWidget(topo)
        self.grade = Grade(colunas, px=12)
        self.grade.setFont(E.fonte('Arial', 13))
        self.grade.ativada.connect(lambda _l: self.alterar())
        v.addWidget(self.grade, 1)
        if extra_rodape:
            v.addWidget(extra_rodape)
        self.bar = QStatusBar()
        self.bar.setSizeGripEnabled(False)
        v.addWidget(self.bar)
        self.bt_inc.clicked.connect(self.incluir)
        self.bt_alt.clicked.connect(self.alterar)
        self.bt_exc.clicked.connect(self.excluir)
        self.todos = []

    def mover(self, passo):
        n = self.grade.modelo.rowCount()
        if n:
            i = 0 if passo == 'p' else n - 1 if passo == 'u' else max(0, min(n - 1, self.grade.currentIndex().row() + passo))
            self.grade.selectRow(i)

    def _filtrar(self, t=''):
        t = (t or self.busca.text()).lower()
        linhas = [r for r in self.todos if not t or any(t in str(v).lower() for v in r.values() if isinstance(v, str))]
        self.grade.definir(linhas)
        self.bar.showMessage(f'{len(linhas)} registro(s)')

    def carregar(self):
        self.todos = self.buscar()
        self._filtrar()

    def atual(self):
        r = self.grade.atual()
        if not r:
            msg_aviso(self, 'Selecione um registro.')
        return r

    # a implementar nas subclasses
    def buscar(self):
        return []

    def incluir(self):
        if self.editar(None):
            self.carregar()

    def alterar(self):
        r = self.atual()
        if r and self.editar(r):
            self.carregar()

    def excluir(self):
        r = self.atual()
        if r and confirmar(self, 'Confirma a exclusão do registro selecionado?') and executar(self, lambda senha: self.remover(r, senha)):
            self.carregar()

    def editar(self, r):
        return False

    def remover(self, r, senha):
        pass


# ---------- Contas bancarias (FBanBrs / FBanCad) ----------

class FormConta(FormBase):
    def __init__(self, parent, s, r=None):
        super().__init__(parent, 'Conta bancária', 490, 392, cor=E.FUNDO_CADASTRO)
        self.s, self.r = s, r or {}
        _rot('Banco e Conta', self, 25, 22, px=13, nome='Segoe UI')
        self.ed_nom = _por(QComboBox(), self, 25, 40, 288, 29)
        self.ed_nom.setEditable(True)
        self.ed_nom.addItems(BANCOS)
        self.ed_nom.setEditText(self.r.get('descricao', ''))
        self.ed_nom.setFont(E.fonte('Segoe UI', 16, negrito=True))
        self.rg_tipo = RadioGrupo('Tipo', [('Conta bancária', 'B'), ('Caixa interno', 'C')], self)
        self.rg_tipo.setGeometry(320, 26, 150, 46)
        self.rg_tipo.definir(self.r.get('tipo', 'B'))
        _rot('Saldo inicial', self, 25, 78, px=13, nome='Segoe UI')
        self.ed_sal = _por(CampoValor(), self, 25, 96, 144, 29)
        self.ed_sal.definir(self.r.get('saldo_inicial', 0))
        _rot('Limite', self, 190, 78, px=13, nome='Segoe UI')
        self.ed_lim = _por(CampoValor(), self, 190, 96, 144, 29)
        self.ed_lim.definir(self.r.get('limite', 0))
        self.ck_ativa = QCheckBox('Conta ativa', self)
        self.ck_ativa.setFont(E.fonte('Segoe UI Semibold', 15, negrito=True))
        self.ck_ativa.setGeometry(25, 150, 200, 22)
        self.ck_ativa.setChecked(bool(self.r.get('ativa', 1)))
        emp = s.empresa_id
        self.rg_uso = RadioGrupo('Utilização', [('Compartilhada em todas as contas controle (empresas)', None),
                                                ('Somente para conta controle (empresa) atual', emp)], self, colunas=1, px=15)
        self.rg_uso.setGeometry(25, 190, 440, 96)
        self.rg_uso.definir(self.r['empresa_id'] if self.r else emp)
        ln = QFrame(self)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(25, 324, 440, 1)
        _por(_bt_cancela(None), self, 25, 341, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 128, 341, 113, 39).clicked.connect(self.confirmar)
        if s.nivel('bancos') < COMPLETO:
            for w in (self.ed_nom, self.rg_tipo, self.ed_sal, self.ed_lim, self.ck_ativa, self.rg_uso):
                w.setEnabled(False)
        self.novo_id = None

    def confirmar(self):
        d = {'descricao': self.ed_nom.currentText().strip().upper(), 'tipo': self.rg_tipo.valor(), 'saldo_inicial': self.ed_sal.valor() or 0,
             'limite': self.ed_lim.valor() or 0, 'ativa': 1 if self.ck_ativa.isChecked() else 0,
             'empresa_id': self.rg_uso.valor() if self.rg_uso.valor() else ''}
        if d['empresa_id'] == '':
            d['empresa_id'] = None
        r = executar(self, lambda senha: self.s.salvar('contas', d, self.r.get('id'), senha=senha))
        if r:
            self.novo_id = r
            self.accept()


class NavContas(Navegador):
    def __init__(self, parent, s):
        super().__init__(parent, 'Contas Bancárias', [('descricao', 'Banco e conta', 190), ('tipo_txt', 'Tipo', 100),
                                                     ('saldo_inicial', 'Saldo inicial', 100, 'moeda'), ('saldo', 'Saldo atual', 100, 'moeda'),
                                                     ('ativa', 'Ativa', 50, 'sn'), ('uso', 'Utilização', 150)],
                         720, 420, 'bancos', s)
        self.carregar()

    def buscar(self):
        saldos = {c['id']: c['saldo'] for c in self.s.saldos()} if self.s.nivel('bancos') or self.s.nivel('fluxo') else {}
        out = []
        for c in self.s.listar('contas'):
            out.append({**c, 'tipo_txt': 'Caixa interno' if c['tipo'] == 'C' else 'Conta bancária', 'saldo': saldos.get(c['id']),
                        'uso': 'Esta conta controle' if c['empresa_id'] else 'Compartilhada'})
        return out

    def editar(self, r):
        return FormConta(self, self.s, r).exec() == QDialog.Accepted

    def remover(self, r, senha):
        self.s.remover('contas', r['id'], senha=senha)


# ---------- Centros de custo (FCenBrs / FCenCad) ----------

class FormCentro(FormBase):
    def __init__(self, parent, s, r=None):
        super().__init__(parent, 'Centro de custo', 325, 380, cor=E.FUNDO_CADASTRO)
        self.s, self.r = s, r or {}
        _rot('Código:', self, 35, 32, px=13, nome='Segoe UI')
        _rot(str(self.r.get('id', '(novo)')), self, 88, 32, px=13, nome='Segoe UI', negrito=True)
        _rot('Descrição do Centro de Custo', self, 35, 61, px=13, nome='Segoe UI')
        self.ed_nom = _por(Campo(px=13), self, 35, 77, 250, 25)
        self.ed_nom.definir(self.r.get('nome'))
        g1 = QGroupBox('', self)
        g1.setGeometry(39, 119, 245, 83)
        self.ck_des = QCheckBox('Aplicar a Despesas', g1)
        self.ck_des.setGeometry(6, -1, 160, 18)
        self.ck_des.setChecked(bool(self.r.get('aplica_despesa', 1)))
        _rot('Orçamento', g1, 19, 24, px=13, nome='Segoe UI')
        _rot('(Mensal)', g1, 90, 27, px=11, nome='Verdana')
        self.ed_orc = _por(CampoValor(px=13), g1, 90, 46, 107, 25)
        self.ed_orc.definir(self.r.get('orcamento', 0))
        g2 = QGroupBox('', self)
        g2.setGeometry(39, 221, 246, 83)
        self.ck_rec = QCheckBox('Aplicar a Receitas (centro de lucro)', g2)
        self.ck_rec.setGeometry(6, 0, 230, 18)
        self.ck_rec.setChecked(bool(self.r.get('aplica_receita', 0)))
        _rot('Projeção', g2, 19, 19, px=13, nome='Segoe UI')
        _rot('(Mensal)', g2, 90, 23, px=11, nome='Verdana')
        self.ed_pro = _por(CampoValor(px=13), g2, 90, 42, 107, 25)
        self.ed_pro.definir(self.r.get('projecao', 0))
        ln = QFrame(self)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(39, 310, 246, 2)
        _por(_bt_cancela(None), self, 39, 325, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 142, 325, 113, 39).clicked.connect(self.confirmar)
        self.ck_des.toggled.connect(self.ed_orc.setEnabled)
        self.ck_rec.toggled.connect(self.ed_pro.setEnabled)
        self.ed_orc.setEnabled(self.ck_des.isChecked())
        self.ed_pro.setEnabled(self.ck_rec.isChecked())
        self.novo_id = None

    def confirmar(self):
        d = {'nome': self.ed_nom.valor(), 'aplica_despesa': int(self.ck_des.isChecked()), 'aplica_receita': int(self.ck_rec.isChecked()),
             'orcamento': self.ed_orc.valor() or 0, 'projecao': self.ed_pro.valor() or 0}
        r = executar(self, lambda senha: self.s.salvar('centros', d, self.r.get('id')))
        if r:
            self.novo_id = r
            self.accept()


class NavCentros(Navegador):
    def __init__(self, parent, s):
        super().__init__(parent, 'Cadastro de Centros de Custo', [('id', 'Código', 60), ('nome', 'Centro de custo', 220),
                                                                  ('aplica_d', 'Despesas', 70), ('orcamento', 'Orçamento', 100, 'moeda'),
                                                                  ('aplica_r', 'Receitas', 70), ('projecao', 'Projeção', 100, 'moeda')],
                         680, 420, 'centros', s)
        self.carregar()

    def buscar(self):
        return [{**c, 'aplica_d': 'Sim' if c['aplica_despesa'] else 'Não', 'aplica_r': 'Sim' if c['aplica_receita'] else 'Não'}
                for c in self.s.listar('centros')]

    def editar(self, r):
        return FormCentro(self, self.s, r).exec() == QDialog.Accepted

    def remover(self, r, senha):
        self.s.remover('centros', r['id'])


# ---------- Itens de despesas / receitas (FIteBrs / FIteCad) ----------

class NavItens(Navegador):
    def __init__(self, parent, s, tipo):
        self.tipo = tipo
        super().__init__(parent, f"Ítens de {'despesas' if tipo == 'D' else 'receitas'}", [('descricao', 'Descrição', 300), ('uso', 'Lançamentos', 90)],
                         420, 480, 'despesas' if tipo == 'D' else 'receitas', s)
        self.carregar()

    def buscar(self):
        usos = dict(self.s.db.execute('SELECT descricao, COUNT(*) FROM lancamentos WHERE empresa_id=? AND tipo=? AND excluido_em IS NULL GROUP BY 1',
                                      (self.s.empresa_id, self.tipo)).fetchall())
        return [{**i, 'uso': usos.get(i['descricao'], 0)} for i in self.s.listar('itens', tipo=self.tipo)]

    def editar(self, r):
        dlg = FormBase(self, 'Alterando ítem' if r else 'Incluindo ítem', 410, 130)
        _rot('Descrição', dlg, 25, 13, px=13, nome='Segoe UI')
        ed = _por(Campo(px=13), dlg, 25, 33, 360, 25)
        ed.definir((r or {}).get('descricao'))
        ln = QFrame(dlg)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(25, 74, 360, 2)
        _por(_bt_cancela(None), dlg, 25, 84, 97, 34).clicked.connect(dlg.reject)
        ok = _por(_bt_confirma(None), dlg, 128, 84, 113, 34)
        renomear = [False]

        def salvar():
            nova = ed.valor()
            if r and r['descricao'] != nova and r.get('uso') and confirmar(dlg, f"Atualizar também os {r['uso']} lançamento(s) com a descrição \"{r['descricao']}\"?"):
                renomear[0] = True
            if executar(dlg, lambda senha: self.s.salvar('itens', {'tipo': self.tipo, 'descricao': nova}, (r or {}).get('id'))):
                if renomear[0]:
                    self.s.db.execute('UPDATE lancamentos SET descricao=? WHERE empresa_id=? AND tipo=? AND descricao=?',
                                      (nova, self.s.empresa_id, self.tipo, r['descricao']))
                dlg.accept()
        ok.clicked.connect(salvar)
        return dlg.exec() == QDialog.Accepted

    def remover(self, r, senha):
        self.s.remover('itens', r['id'])


# ---------- Pessoas (FPesBrs / FPesCad) ----------

class FormPessoa(FormBase):
    """FPesCad: Dados Cadastrais / Perfil do cliente / Dados Bancarios / Observacoes."""

    def __init__(self, parent, s, tipo, r=None):
        super().__init__(parent, 'Cliente' if tipo == 'C' else 'Fornecedor', 580, 583, cor=E.FUNDO_CADASTRO)
        self.s, self.tipo, self.r = s, tipo, r or {}
        self.x = s.pessoa_extra(self.r['id']) if self.r else {}
        abas = QTabWidget(self)
        abas.setGeometry(0, 0, 580, 521)
        abas.setFont(E.fonte('Segoe UI', 13))
        self.c = {}

        def ed(pai, chave, x, y, w, h=25, opcional=True, valor=None, extra=False):
            e = _por(Campo(px=13, opcional=opcional), pai, x, y, w, h)
            e.definir(valor if valor is not None else (self.x.get(chave) if extra else self.r.get(chave)))
            self.c[('x:' if extra else '') + chave] = e
            return e
        L = lambda pai, t, x, y: _rot(t, pai, x, y, px=13, nome='Segoe UI')
        # aba 1
        t1 = QWidget()
        abas.addTab(t1, 'Dados Cadastrais')
        L(t1, 'Nome', 32, 9)
        ed(t1, 'nome', 32, 30, 349, opcional=False)
        L(t1, 'Data Cadastro', 389, 9)
        dc = _por(Campo(px=13), t1, 389, 30, 100, 25)
        dc.setReadOnly(True)
        dc.setText(fin.br((self.x.get('_criado_em') or date.today().isoformat())[:10]))
        bt_upd = SpeedButton('', icone('fa6s.clock-rotate-left', '#333'), t1, dica='Controle de atualizações')
        bt_upd.setGeometry(535, 3, 28, 28)
        bt_upd.clicked.connect(lambda: msg_info(self, f"Cadastrado em: {fin.br((self.x.get('_criado_em') or '')[:10]) or '—'}", 'Controle de atualizações'))
        self.rg_pes = RadioGrupo('Pessoa', [('Física', 'F'), ('Jurídica', 'J')], t1)
        self.rg_pes.setGeometry(32, 60, 168, 42)
        self.rg_pes.definir(self.r.get('pessoa', 'J'))
        self.lb_doc = L(t1, 'CNPJ/CPF', 215, 54)
        ed(t1, 'documento', 215, 75, 166)
        self.lb_doc2 = L(t1, 'I.E/R.G', 387, 54)
        ed(t1, 'documento2', 387, 75, 153)
        L(t1, 'Endereço', 32, 98)
        ed(t1, 'endereco', 32, 119, 349)
        L(t1, 'Bairro', 388, 99)
        ed(t1, 'bairro', 388, 119, 153)
        L(t1, 'CEP', 32, 144)
        ed(t1, 'cep', 32, 164, 109)
        L(t1, 'Cidade', 147, 143)
        ed(t1, 'cidade', 147, 164, 234)
        L(t1, 'UF', 388, 143)
        self.cb_uf = _por(QComboBox(), t1, 388, 164, 60, 25)
        self.cb_uf.addItems([''] + UFS)
        self.cb_uf.setCurrentText(self.r.get('uf') or '')
        L(t1, 'Telefone(s)', 32, 189)
        ed(t1, 'telefone', 32, 209, 350)
        L(t1, 'E-mail', 32, 234)
        ed(t1, 'email', 35, 254, 350)
        L(t1, 'Contatos:', 32, 285)
        ln = QFrame(t1)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(32, 302, 508, 3)
        L(t1, 'Depto. Compras/Vendas', 32, 307)
        ed(t1, 'contato', 32, 327, 252)
        L(t1, 'Depto.Financeiro', 287, 306)
        ed(t1, 'contato_financeiro', 287, 327, 253, extra=True)
        L(t1, 'Depto. Administrativo', 32, 351)
        ed(t1, 'contato_administrativo', 32, 373, 252, extra=True)
        L(t1, 'Depto. Técnico/Operacional', 287, 353)
        ed(t1, 'contato_tecnico', 287, 373, 253, extra=True)
        self.rg_uso = RadioGrupo('Uso do cadastro:', [('Compartilhado com as outras contas', None), ('Somente para esta conta controle', s.empresa_id)], t1, px=12)
        self.rg_uso.setGeometry(32, 409, 508, 46)
        self.rg_uso.definir(self.r['empresa_id'] if self.r else s.empresa_id)
        # aba 2
        t2 = QWidget()
        abas.addTab(t2, 'Perfil do cliente' if tipo == 'C' else 'Perfil do fornecedor')
        L(t2, 'Data de Fundação', 32, 6)
        ed(t2, 'fundacao', 32, 25, 110, extra=True)
        L(t2, 'Limite de crédito', 32, 47)
        self.ed_lim = _por(CampoValor(px=13), t2, 32, 66, 110, 25)
        self.ed_lim.definir(self.r.get('limite', 0))
        self.rg_freq = RadioGrupo('Frequência de compra', [('Diária', 'D'), ('Mensal', 'M'), ('Semestral', 'S'), ('Semanal', 'W'),
                                                          ('Trimestral', 'T'), ('Anual', 'A')], t2, colunas=1, px=13)
        self.rg_freq.setGeometry(164, 6, 195, 92)
        self._grid_radios(self.rg_freq, 2)
        self.rg_freq.definir(self.x.get('frequencia'))
        self.rg_cla = RadioGrupo('Classificação', [('Classe A', 'A'), ('Classe B', 'B'), ('Classe C', 'C')], t2, colunas=1, px=13)
        self.rg_cla.setGeometry(383, 6, 165, 92)
        self.rg_cla.definir(self.x.get('classe'))
        L(t2, 'Referências Comerciais', 32, 100)
        ln2 = QFrame(t2)
        ln2.setFrameShape(QFrame.HLine)
        ln2.setGeometry(32, 116, 517, 3)
        for i, y in enumerate((122, 166, 211)):
            L(t2, f'Referências Comerciais {i + 1}', 32, y)
            ed(t2, f'ref_comercial{i + 1}', 32, y + 19, 340, extra=True)
            L(t2, 'Telefone', 383, y)
            ed(t2, f'ref_comercial{i + 1}_tel', 383, y + 19, 158, extra=True)
        L(t2, 'Referências Bancárias', 33, 256)
        ln3 = QFrame(t2)
        ln3.setFrameShape(QFrame.HLine)
        ln3.setGeometry(32, 274, 509, 3)
        L(t2, 'Banco', 32, 279)
        ed(t2, 'ref_banco', 32, 298, 122, extra=True)
        L(t2, 'Agência', 171, 279)
        ed(t2, 'ref_agencia', 171, 298, 84, extra=True)
        L(t2, 'Conta', 272, 279)
        ed(t2, 'ref_conta', 272, 298, 92, extra=True)
        L(t2, 'Telefone', 383, 279)
        ed(t2, 'ref_telefone', 383, 298, 158, extra=True)
        self.rg_con = RadioGrupo('Crédito consultado', [('Sim', 'S'), ('Não', 'N')], t2, px=13)
        self.rg_con.setGeometry(32, 330, 153, 42)
        self.rg_con.definir(self.x.get('credito_consultado', 'N'))
        self.rg_pen = RadioGrupo('Possui pendência de crédito', [('Sim', 'S'), ('Não', 'N')], t2, px=13)
        self.rg_pen.setGeometry(193, 330, 244, 42)
        self.rg_pen.definir(self.x.get('pendencia', 'N'))
        self.w_pend = []
        self.w_pend.append(L(t2, 'Data Consulta', 33, 376))
        self.w_pend.append(ed(t2, 'data_consulta', 33, 395, 98, extra=True))
        self.w_pend.append(L(t2, 'Local Pendência', 142, 376))
        self.w_pend.append(ed(t2, 'local_pendencia', 142, 395, 294, extra=True))
        self.w_pend.append(L(t2, 'Nome da Mãe', 32, 421))
        self.w_pend.append(ed(t2, 'nome_mae', 32, 440, 405, extra=True))
        self.rg_pen.mudou.connect(lambda v: [w.setVisible(v == 'S') for w in self.w_pend])
        for w in self.w_pend:
            w.setVisible(self.rg_pen.valor() == 'S')
        # aba 3
        t3 = QWidget()
        abas.addTab(t3, 'Dados Bancários')
        _rot(self.r.get('nome', ''), t3, 32, 25, px=13, nome='Segoe UI Semibold', negrito=True)
        L(t3, 'Banco', 32, 61)
        ed(t3, 'banco', 32, 79, 150)
        L(t3, 'Agência', 32, 105)
        ed(t3, 'agencia', 32, 123, 120)
        L(t3, 'Conta', 31, 150)
        ed(t3, 'conta_bancaria', 31, 168, 120)
        L(t3, 'Titular da Conta', 31, 195)
        ed(t3, 'titular', 31, 213, 258, extra=True)
        L(t3, 'Chave PIX', 31, 240)
        ed(t3, 'pix', 31, 258, 258, extra=True)
        # aba 4
        t4 = QWidget()
        abas.addTab(t4, 'Observações')
        _rot(self.r.get('nome', ''), t4, 32, 28, px=11, nome='Segoe UI Semibold', negrito=True, cor=E.NAVY)
        L(t4, 'Observações', 32, 49)
        self.ed_obs = _por(QPlainTextEdit(), t4, 32, 72, 505, 336)
        self.ed_obs.setStyleSheet(f'background: {E.INFO_BK};')
        self.ed_obs.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
        self.ed_obs.setPlainText(self.r.get('observacao') or '')
        rod = QFrame(self)
        rod.setGeometry(0, 521, 580, 62)
        _por(_bt_cancela(None), rod, 39, 12, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), rod, 142, 12, 113, 39).clicked.connect(self.confirmar)
        self.rg_pes.mudou.connect(self._docs)
        self._docs(self.rg_pes.valor())
        self.edita = s.nivel('receitas' if tipo == 'C' else 'despesas') >= COMPLETO
        if not self.edita:
            for w in self.c.values():
                w.setReadOnly(True)
            self.setWindowTitle(self.windowTitle() + ' — somente consulta')
        self.novo_id = None

    @staticmethod
    def _grid_radios(grupo, colunas):
        from PySide6.QtWidgets import QGridLayout
        bts = grupo.grupo.buttons()
        old = grupo.layout()
        for b in bts:
            old.removeWidget(b)
        QWidget().setLayout(old)
        g = QGridLayout(grupo)
        g.setContentsMargins(8, 2, 4, 2)
        for i, b in enumerate(bts):
            g.addWidget(b, i % 3, i // 3)

    def _docs(self, pessoa):
        self.lb_doc.setText('CPF' if pessoa == 'F' else 'CNPJ')
        self.lb_doc2.setText('R.G' if pessoa == 'F' else 'I.E')

    def confirmar(self):
        if not self.edita:
            self.reject()
            return
        d = {k: w.valor() for k, w in self.c.items() if not k.startswith('x:')}
        d.update(tipo=self.tipo, pessoa=self.rg_pes.valor(), uf=self.cb_uf.currentText(), limite=self.ed_lim.valor() or 0,
                 observacao=self.ed_obs.toPlainText(), empresa_id=self.rg_uso.valor())
        extra = {k[2:]: w.valor() for k, w in self.c.items() if k.startswith('x:')}
        extra.update(frequencia=self.rg_freq.valor(), classe=self.rg_cla.valor(), credito_consultado=self.rg_con.valor(), pendencia=self.rg_pen.valor())
        r = executar(self, lambda senha: self.s.salvar('pessoas', d, self.r.get('id')))
        if r:
            self.s.salvar_pessoa_extra(r, extra)
            self.novo_id = r
            self.accept()


class NavPessoas(Navegador):
    def __init__(self, parent, s, tipo):
        self.tipo = tipo
        super().__init__(parent, 'Cadastro de clientes' if tipo == 'C' else 'Cadastro de fornecedores',
                         [('nome', 'Nome', 220), ('documento', 'CPF/CNPJ', 120), ('cidade_uf', 'Cidade/UF', 140), ('telefone', 'Telefone', 120),
                          ('email', 'E-mail', 160), ('uso', 'Uso', 90)],
                         820, 483, 'receitas' if tipo == 'C' else 'despesas', s, localizar=True)
        self.carregar()

    def buscar(self):
        return [{**p, 'cidade_uf': ' - '.join(x for x in (p['cidade'], p['uf']) if x), 'uso': 'Esta conta' if p['empresa_id'] else 'Compartilhado'}
                for p in self.s.listar('pessoas', tipo=self.tipo)]

    def editar(self, r):
        return FormPessoa(self, self.s, self.tipo, r).exec() == QDialog.Accepted

    def remover(self, r, senha):
        if self.s.db.execute('SELECT 1 FROM lancamentos WHERE pessoa=? AND empresa_id=? AND excluido_em IS NULL LIMIT 1', (r['nome'], self.s.empresa_id)).fetchone():
            if not confirmar(self, 'Esta pessoa possui lançamentos. Os lançamentos serão mantidos com o nome. Excluir o cadastro mesmo assim?'):
                return None
        self.s.remover('pessoas', r['id'])
        return True


# ---------- Contas controle (FConBrs / FConCad) ----------

class FormEmpresa(FormBase):
    def __init__(self, parent, s, r=None, primeira=False):
        super().__init__(parent, 'Conta controle', 440, 575, cor=E.FUNDO_CADASTRO)
        self.s, self.r, self.primeira = s, r or {}, primeira
        if primeira:
            _rot('Cadastre a primeira conta controle (sua empresa ou você como pessoa física).', self, 19, 4, px=12, nome='Segoe UI', cor=E.NAVY, negrito=True)
        self.rg_pes = RadioGrupo('Pessoa', [('Física', 'F'), ('Jurídica', 'J')], self)
        self.rg_pes.setGeometry(234, 23, 184, 46)
        self.rg_pes.definir(self.r.get('pessoa', 'J'))
        star = lambda x, y: _rot('*', self, x, y, px=24, nome='Segoe UI')
        star(5, 72)
        self.lb_nome = _rot('Nome ou razão social', self, 19, 58, px=13, nome='Segoe UI')
        self.c = {}

        def ed(chave, x, y, w, opc=True):
            e = _por(Campo(px=15, opcional=opc), self, x, y, w, 28)
            e.definir(self.r.get(chave))
            self.c[chave] = e
            return e
        ed('nome', 21, 77, 398, opc=False)
        _rot('Endereço completo', self, 19, 109, px=13, nome='Segoe UI')
        ed('endereco', 19, 130, 398)
        _rot('Bairro', self, 19, 160, px=13, nome='Segoe UI')
        ed('bairro', 19, 181, 261)
        _rot('Cidade', self, 19, 211, px=13, nome='Segoe UI')
        ed('cidade', 19, 232, 228)
        _rot('UF', self, 258, 214, px=13, nome='Segoe UI')
        self.cb_uf = _por(QComboBox(), self, 255, 232, 54, 28)
        self.cb_uf.addItems([''] + UFS)
        self.cb_uf.setCurrentText(self.r.get('uf') or '')
        _rot('CEP', self, 318, 214, px=13, nome='Segoe UI')
        ed('cep', 315, 232, 103)
        star(4, 294)
        _rot('Telefone(s)', self, 19, 263, px=13, nome='Segoe UI')
        ed('telefone', 19, 283, 398)
        _rot('E-mail', self, 19, 314, px=13, nome='Segoe UI')
        ed('email', 19, 334, 398, opc=False)
        self.lb_d1 = _rot('CNPJ', self, 19, 364, px=13, nome='Segoe UI')
        ed('documento', 19, 385, 197)
        self.lb_d2 = _rot('Inscrição estadual', self, 220, 364, px=13, nome='Segoe UI')
        ed('documento2', 220, 385, 198)
        _rot('Web Site', self, 19, 416, px=13, nome='Segoe UI')
        ed('site', 19, 436, 398)
        _rot('* campo de preenchimento obrigatório', self, 19, 475, px=13, nome='Segoe UI', cor=E.NAVY)
        self.ck_cen = QCheckBox('Trabalhar com centros de custo', self)
        self.ck_cen.setGeometry(240, 475, 200, 20)
        self.ck_cen.setChecked(bool(self.r.get('usa_centro_custo', 1)))
        ln = QFrame(self)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(19, 503, 399, 2)
        if not primeira:
            _por(_bt_cancela(None), self, 19, 520, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 122 if not primeira else 19, 520, 113, 39).clicked.connect(self.confirmar)
        if self.r and not primeira:
            bc = _por(BitBtn('Configurações', icone('fa6s.sliders', E.NAVY), dica='Configurações da conta controle'), self, 241, 520, 140, 39)
            bc.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
            bc.clicked.connect(lambda: parent_cfg(self))
        self.rg_pes.mudou.connect(self._docs)
        self._docs(self.rg_pes.valor())
        self.novo_id = None

        def parent_cfg(w):
            from .ferramentas import FormConfigConta
            FormConfigConta(w, s).exec()

    def _docs(self, p):
        self.lb_nome.setText('Nome completo' if p == 'F' else 'Nome ou razão social')
        self.lb_d1.setText('CPF' if p == 'F' else 'CNPJ')
        self.lb_d2.setText('RG' if p == 'F' else 'Inscrição estadual')
        for l in (self.lb_nome, self.lb_d1, self.lb_d2):
            l.adjustSize()

    def dados(self):
        d = {k: w.valor() for k, w in self.c.items()}
        d.update(pessoa=self.rg_pes.valor(), uf=self.cb_uf.currentText(), usa_centro_custo=int(self.ck_cen.isChecked()))
        return d

    def confirmar(self):
        d = self.dados()
        if not d['nome'] or not d['telefone']:
            msg_aviso(self, 'Preencha os campos obrigatórios (*): nome e telefone.')
            return
        r = executar(self, lambda senha: self.s.salvar('empresas', d, self.r.get('id')))
        if r:
            self.novo_id = r
            self.accept()


class NavEmpresas(Navegador):
    def __init__(self, parent, s):
        super().__init__(parent, 'Cadastro de Contas Controle', [('nome', 'Conta controle', 230), ('pessoa_txt', 'Pessoa', 80),
                                                                 ('documento', 'CPF/CNPJ', 130), ('cidade', 'Cidade', 120), ('telefone', 'Telefone', 120)],
                         720, 400, 'config', s)
        self.carregar()

    def buscar(self):
        return [{**e, 'pessoa_txt': 'Física' if e['pessoa'] == 'F' else 'Jurídica'} for e in self.s.empresas()]

    def editar(self, r):
        return FormEmpresa(self, self.s, r).exec() == QDialog.Accepted

    def remover(self, r, senha):
        if r['id'] == self.s.empresa_id:
            raise ValueError('Não é possível excluir a conta controle em uso. Vá para outra conta antes.')
        self.s.remover('empresas', r['id'])


# ---------- Movimentacoes bancarias (FTraBrs / FTraCad) ----------

class FormMovBancaria(FormBase):
    def __init__(self, parent, s, r=None):
        super().__init__(parent, 'Movimentação bancária', 377, 400, cor=E.FUNDO_CADASTRO)
        self.s, self.r = s, r or {}
        self.rg_tipo = RadioGrupo('Movimento', [('&Depósito', 'D'), ('&Retirada', 'R'), ('&Transferência', 'T')], self)
        self.rg_tipo.setGeometry(20, 30, 337, 46)
        self.rg_tipo.definir(self.r.get('tipo', 'T'))
        contas = [(c['descricao'], c['id']) for c in s.listar('contas') if c['ativa'] or c['id'] in (self.r.get('origem_id'), self.r.get('destino_id'))]
        _rot('Conta', self, 20, 85, px=13, nome='Segoe UI')
        self.cb_ori = _por(ComboDados(px=13, opcoes=contas), self, 19, 102, 170, 26)
        self.cb_ori.definir(self.r.get('origem_id'))
        self.lb_des = _rot('Conta Destino', self, 199, 85, px=13, nome='Segoe UI')
        self.cb_des = _por(ComboDados(px=13, opcoes=[('', None)] + contas), self, 199, 102, 158, 26)
        self.cb_des.definir(self.r.get('destino_id'))
        _rot('Data', self, 20, 135, px=13, nome='Segoe UI')
        self.ed_dat = _por(CampoData(px=13), self, 20, 152, 136, 27)
        self.ed_dat.definir(self.r.get('data'))
        _rot('Valor', self, 199, 135, px=13, nome='Segoe UI')
        self.ed_val = _por(CampoValor(px=13), self, 199, 152, 107, 27)
        self.ed_val.definir(self.r.get('valor'))
        self.rg_sit = RadioGrupo('Situação', [('Realizado', 'V'), ('Previsto', 'P')], self, colunas=1)
        self.rg_sit.setGeometry(20, 189, 110, 70)
        self.rg_sit.definir(self.r.get('situacao', 'V'))
        self.lb_txt = QLabel(self)
        self.lb_txt.setWordWrap(True)
        self.lb_txt.setFont(E.fonte('Segoe UI', 12))
        self.lb_txt.setGeometry(140, 193, 216, 67)
        _rot('Observações (Cheque)', self, 20, 269, px=13, nome='Segoe UI')
        self.ed_obs = _por(Campo(px=13, opcional=True), self, 20, 288, 337, 26)
        self.ed_obs.definir(self.r.get('observacao'))
        ln = QFrame(self)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(20, 332, 337, 1)
        _por(_bt_cancela(None), self, 20, 345, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 123, 345, 113, 39).clicked.connect(self.confirmar)
        self.rg_tipo.mudou.connect(self._tipo)
        self._tipo(self.rg_tipo.valor())
        if s.nivel('bancos') < COMPLETO:
            for w in (self.rg_tipo, self.cb_ori, self.cb_des, self.ed_dat, self.ed_val, self.rg_sit, self.ed_obs):
                w.setEnabled(False)

    def _tipo(self, t):
        self.lb_des.setVisible(t == 'T')
        self.cb_des.setVisible(t == 'T')
        self.lb_txt.setText({'D': 'Depósito: entrada de dinheiro na conta (sem lançamento de receita).',
                             'R': 'Retirada: saída de dinheiro da conta (sem lançamento de despesa).',
                             'T': 'Transferência: sai da conta de origem e entra na conta destino.'}[t])

    def confirmar(self):
        t = self.rg_tipo.valor()
        d = {'tipo': t, 'situacao': self.rg_sit.valor(), 'data': self.ed_dat.valor(), 'origem_id': self.cb_ori.valor(),
             'destino_id': self.cb_des.valor() if t == 'T' else None, 'valor': self.ed_val.valor(), 'observacao': self.ed_obs.valor()}
        if executar(self, lambda senha: self.s.salvar('movbancarias', d, self.r.get('id'), senha=senha)):
            self.accept()


class NavMovBancarias(Navegador):
    def __init__(self, parent, s):
        rod = QFrame()
        rod.setFixedHeight(32)
        h = QHBoxLayout(rod)
        h.setContentsMargins(3, 3, 3, 3)
        h.addWidget(rotulo('Exibir:', px=12, negrito=True))
        from .principal import PERIODOS_MES
        self.cb_mes = ComboDados(px=12, opcoes=PERIODOS_MES)
        self.cb_ano = ComboDados(px=12, opcoes=[(str(a), a) for a in range(2001, 2041)])
        hoje = date.today()
        self.cb_mes.definir(str(hoje.month))
        self.cb_ano.definir(hoje.year)
        h.addWidget(self.cb_mes)
        h.addWidget(self.cb_ano)
        h.addStretch()
        super().__init__(parent, 'Controle de Movimentações Bancárias', [('data', 'Data', 85, 'data'), ('tipo_txt', 'Movimento', 100),
                                                                          ('conta', 'Conta', 150), ('destino', 'Conta destino', 150),
                                                                          ('valor', 'Valor', 100, 'moeda'), ('sit_txt', 'Situação', 80),
                                                                          ('observacao', 'Observação', 150)],
                         860, 451, 'bancos', s, extra_rodape=rod)
        self.cb_mes.currentIndexChanged.connect(lambda _i: self.carregar())
        self.cb_ano.currentIndexChanged.connect(lambda _i: self.carregar())
        self.carregar()

    def buscar(self):
        nomes = {c['id']: c['descricao'] for c in self.s.listar('contas')}
        per = fin.periodo(self.cb_ano.valor(), self.cb_mes.valor())
        out = []
        for m in self.s.listar('movbancarias'):
            if per and not per[0] <= m['data'] <= per[1]:
                continue
            out.append({**m, 'tipo_txt': {'D': 'Depósito', 'R': 'Retirada', 'T': 'Transferência'}[m['tipo']], 'conta': nomes.get(m['origem_id'], ''),
                        'destino': nomes.get(m['destino_id'], ''), 'sit_txt': 'Realizado' if m['situacao'] == 'V' else 'Previsto'})
        return out

    def editar(self, r):
        return FormMovBancaria(self, self.s, r).exec() == QDialog.Accepted

    def remover(self, r, senha):
        self.s.remover('movbancarias', r['id'], senha=senha)


class Cadastros:
    """Controlador dos cadastros (chamado pelos menus)."""

    def __init__(self, janela):
        self.j = janela

    @property
    def s(self):
        return self.j.s

    def _depois(self):
        self.j._carregar_contas()
        self.j.atualizar()

    def contas(self):
        NavContas(self.j, self.s).exec()
        self._depois()

    def centros(self):
        NavCentros(self.j, self.s).exec()
        self._depois()

    def itens(self, tipo):
        NavItens(self.j, self.s, tipo).exec()
        self._depois()

    def pessoas(self, tipo):
        NavPessoas(self.j, self.s, tipo).exec()
        self._depois()

    def empresas(self):
        NavEmpresas(self.j, self.s).exec()
        self.j.usar_empresa(self.s.empresa_id)

    def movbancarias(self):
        NavMovBancarias(self.j, self.s).exec()
        self._depois()

    def editar_empresa_atual(self):
        if FormEmpresa(self.j, self.s, self.s.empresa()).exec() == QDialog.Accepted:
            self.j.usar_empresa(self.s.empresa_id)

    def form_conta(self):
        f = FormConta(self.j, self.s)
        return f.novo_id if f.exec() == QDialog.Accepted else None

    def form_centro(self):
        f = FormCentro(self.j, self.s)
        return f.novo_id if f.exec() == QDialog.Accepted else None
