"""Janela principal (FPrin): faixa de menus, usuario, conta controle, filtros,
quadro de saldos, abas Despesas / Receitas / Dashboard e busca rapida."""
import shutil
import subprocess
from datetime import date

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QRadioButton,
                               QStackedWidget, QTabWidget, QVBoxLayout, QWidget, QButtonGroup, QSizePolicy, QApplication)

from ..core import finance as fin
from ..core.auth import COMPLETO, CONSULTA
from . import estilo as E
from .base import (BitBtn, Grade, SpeedButton, confirmar, executar, icone, msg_aviso, msg_info, rotulo)
from .graficos import Grafico

PERIODOS_MES = [(m, str(i + 1)) for i, m in enumerate(fin.MESES_LONGOS)] + [
    ('1º Tri', 'T1'), ('2º Tri', 'T2'), ('3º Tri', 'T3'), ('4º Tri', 'T4'), ('1º Sem', 'S1'), ('2º Sem', 'S2'),
    ('Ano todo', 'ANO'), ('Todo periodo', 'TODOS')]
ORDENS = [('Data de movimento', 'data'), ('Data de Pgto/Vcto', 'vencimento'), ('Documento', 'documento'), ('Descrição', 'descricao'),
          ('Cliente/Fornecedor', 'pessoa'), ('Valor', 'valor'), ('Situação', 'situacao'), ('Observação', 'observacao')]


def _faixa(cor, altura=None):
    w = QFrame()
    w.setAutoFillBackground(True)
    w.setStyleSheet(f'QFrame#faixa {{ background: {cor}; }}')
    w.setObjectName('faixa')
    if altura:
        w.setFixedHeight(altura)
    return w


def _combo_filtro(itens, largura):
    c = QComboBox()
    c.setFont(E.fonte('Segoe UI Semibold', 11, negrito=True))
    c.setStyleSheet(f'QComboBox {{ color: {E.TEXTO_COMBO}; background: #ffffff; }}')
    for texto, dado in itens:
        c.addItem(texto, dado)
    c.setFixedHeight(24)
    c.setMinimumWidth(int(largura * 0.7))
    c.setMaximumWidth(int(largura * 1.12))
    c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    c.setMinimumContentsLength(4)
    c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    return c


def cor_situacao(linha, campo):
    if campo != 'situacao_desc':
        return None
    return {'Pago': '#006400', 'Recebido': '#006400', 'Vencido': '#c00000'}.get(linha.get('situacao_desc'), '#000080')


class AbaLancamentos(QWidget):
    """TabDespesas / TabReceitas: barra de botoes + grade."""

    def __init__(self, janela, tipo):
        super().__init__()
        self.j = janela
        self.tipo = tipo
        nome = 'despesa' if tipo == 'D' else 'receita'
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        barra = _faixa(E.CONTA_CONTROLE if tipo == 'D' else E.GRADE, 41)
        b = QHBoxLayout(barra)
        b.setContentsMargins(3, 3, 3, 3)
        b.setSpacing(4)
        fb = E.fonte('Tahoma', 12, negrito=True)
        self.bt_inc = BitBtn(f'&Incluir nova {nome}', icone('fa6s.circle-plus', '#1a7f37'), dica=f'Inclui nova {nome}')
        self.bt_inc.setFont(E.fonte('Verdana', 12, negrito=True))
        self.bt_inc.setStyleSheet(self.bt_inc.styleSheet() + f'QPushButton {{ color: {E.NAVY}; }}')
        self.bt_inc.setFixedSize(185, 35)
        self.bt_mul = SpeedButton('', icone('fa6s.caret-down', E.NAVY), dica='Incluir múltiplos lançamentos')
        self.bt_mul.setFixedSize(15, 35)
        menu_mul = QMenu(self)
        menu_mul.addAction(icone('fa6s.layer-group'), 'Incluir múltiplos lançamentos', lambda: self.j.parcelamento(self.tipo))
        self.bt_mul.setMenu(menu_mul)
        self.bt_mul.setPopupMode(SpeedButton.InstantPopup)
        self.bt_alt = SpeedButton('&Alterar', icone('fa6s.pen-to-square', E.NAVY), dica=f'Altera/Consulta {nome} selecionada')
        self.bt_exc = SpeedButton('&Excluir', icone('fa6s.trash-can', '#b02a2a'), dica=f'Exclui {nome} selecionada')
        self.bt_loc = SpeedButton('&Localizar', icone('fa6s.magnifying-glass', E.NAVY), dica='Localizar Movimento')
        self.bt_bai = SpeedButton('Bai&xar', icone('fa6s.circle-check', '#1a7f37'), dica='Baixa conta em aberto')
        menu_bai = QMenu(self)
        menu_bai.addAction(icone('fa6s.circle-check'), 'Baixar lançamento selecionado', self.baixar)
        menu_bai.addAction(icone('fa6s.list-check'), 'Baixa múltipla', lambda: self.j.baixa_multipla(self.tipo))
        self.bt_bai.setMenu(menu_bai)
        self.bt_bai.setPopupMode(SpeedButton.MenuButtonPopup)
        self.bt_rec = SpeedButton('Recib&o' if tipo == 'D' else '&Recibo', icone('fa6s.receipt', E.NAVY),
                                  dica='Emitir Recibo' if tipo == 'D' else 'Emitir Recibo / Duplicata')
        for w, larg in ((self.bt_alt, 84), (self.bt_exc, 83), (self.bt_loc, 93), (self.bt_bai, 95), (self.bt_rec, 83)):
            w.setFont(fb)
            w.setStyleSheet(f'QToolButton {{ color: {E.NAVY}; }}')
            w.setFixedSize(larg, 35)
        nav = QWidget()
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(4, 0, 4, 0)
        nl.setSpacing(0)
        for ic, dica, fn in (('fa6s.backward-step', 'Primeiro', lambda: self.mover('primeiro')), ('fa6s.caret-left', 'Anterior', lambda: self.mover(-1)),
                             ('fa6s.caret-right', 'Próximo', lambda: self.mover(1)), ('fa6s.forward-step', 'Último', lambda: self.mover('ultimo'))):
            sb = SpeedButton('', icone(ic, '#333'), dica=dica)
            sb.setFixedSize(34, 35)
            sb.clicked.connect(fn)
            nl.addWidget(sb)
        self.bt_upd = SpeedButton('', icone('fa6s.rotate', E.NAVY), dica='Atualizar (F5)')
        self.bt_upd.setFixedSize(33, 35)
        self.bt_upd.clicked.connect(self.j.atualizar)
        for w in (self.bt_inc, self.bt_mul, self.bt_alt, self.bt_exc, self.bt_loc, self.bt_bai, self.bt_rec, nav, self.bt_upd):
            b.addWidget(w)
        b.addStretch()
        self.lb_tot = QLabel()
        self.lb_tot.setFont(E.fonte('Segoe UI', 12, negrito=True))
        self.lb_tot.setStyleSheet(f'color: #102a43; background: {E.CONTA_CONTROLE if tipo == "D" else E.GRADE}; padding: 2px 8px;')
        self.lb_tot.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(barra)
        cols = [('data_mov', ' Data', 90, 'data'), ('ven_pgto', ' Pgto/Vcto.', 90, 'data'), ('documento', ' Documento', 90),
                ('descricao', f' Descrição da {nome}', 260), ('pessoa', ' Fornecedor' if tipo == 'D' else ' Cliente', 260),
                ('valor', ' Valor', 120, 'moeda'), ('situacao_desc', ' Situação', 135), ('centro', ' Centro de custo', 170), ('observacao', ' Observação', 200)]
        self.grade = Grade(cols, cor_linha=cor_situacao, multi=True, cor_fundo=None)
        self.grade.setStyleSheet(f'QTableView {{ background: #ffffff; alternate-background-color: #eef4f4; color: #646464; }}')
        self.grade.ativada.connect(lambda l: self.alterar())
        self.grade.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grade.customContextMenuRequested.connect(self.menu_contexto)
        lay.addWidget(self.grade)
        lay.addWidget(self.lb_tot)
        self.bt_inc.clicked.connect(lambda: self.j.form_lancamento(self.tipo))
        self.bt_alt.clicked.connect(self.alterar)
        self.bt_exc.clicked.connect(self.excluir)
        self.bt_loc.clicked.connect(lambda: self.j.localizar(self.tipo))
        self.bt_bai.clicked.connect(self.baixar)
        self.bt_rec.clicked.connect(self.recibo)

    def aplicar_permissao(self, nivel):
        edita = nivel >= COMPLETO
        for w in (self.bt_inc, self.bt_mul, self.bt_exc, self.bt_bai):
            w.setEnabled(edita)
        self.bt_alt.setText('&Alterar' if edita else '&Consultar')

    def carregar(self, linhas):
        self.grade.definir(linhas)
        pago = sum(l['valor'] for l in linhas if l['situacao'] == 'V')
        aberto = sum(l['valor'] for l in linhas if l['situacao'] == 'P')
        rot = 'Pago' if self.tipo == 'D' else 'Recebido'
        self.lb_tot.setText(f'{len(linhas)} lançamento(s)     {rot}: {fin.moeda(pago)}   Em aberto: {fin.moeda(aberto)}   Total: {fin.moeda(pago + aberto)}')

    def mover(self, passo):
        n = self.grade.modelo.rowCount()
        if not n:
            return
        atual = self.grade.currentIndex().row()
        i = 0 if passo == 'primeiro' else n - 1 if passo == 'ultimo' else max(0, min(n - 1, atual + passo))
        self.grade.selectRow(i)

    def atual(self, avisar=True):
        l = self.grade.atual()
        if not l and avisar:
            msg_aviso(self, 'Selecione um lançamento.')
        return l

    def alterar(self):
        l = self.atual()
        if l:
            self.j.form_lancamento(self.tipo, l['id'])

    def excluir(self):
        l = self.atual()
        if l:
            self.j.excluir_lancamento(l)

    def baixar(self):
        sel = self.grade.selecionados()
        if len(sel) > 1:
            self.j.baixa_multipla(self.tipo, [l['id'] for l in sel])
        elif sel:
            self.j.form_baixa(sel[0])
        else:
            msg_aviso(self, 'Selecione um lançamento.')

    def recibo(self):
        l = self.atual()
        if l:
            self.j.recibo(l)

    def menu_contexto(self, pos):
        l = self.grade.atual()
        m = QMenu(self)
        edita = self.j.s.nivel_tipo(self.tipo) >= COMPLETO
        a = m.addAction(icone('fa6s.circle-plus'), f"Incluir nova {'despesa' if self.tipo == 'D' else 'receita'}", lambda: self.j.form_lancamento(self.tipo))
        a.setEnabled(edita)
        if l:
            m.addAction(icone('fa6s.pen-to-square'), 'Alterar/Consultar', self.alterar)
            m.addSeparator()
            for texto, ic, fn in (('Baixar lançamento selecionado', 'fa6s.circle-check', self.baixar),
                                  ('Estornar baixa', 'fa6s.rotate-left', lambda: self.j.estornar(l)),
                                  ('Excluir', 'fa6s.trash-can', self.excluir),
                                  ('Transferir lançamento para outra conta', 'fa6s.right-left', lambda: self.j.transferir_empresa(self.grade.selecionados())),
                                  ('Repetir lançamento no mês seguinte', 'fa6s.repeat', lambda: self.j.repetir_mes_seguinte(self.grade.selecionados()))):
                a = m.addAction(icone(ic), texto, fn)
                a.setEnabled(edita)
            m.addSeparator()
            m.addAction(icone('fa6s.receipt'), 'Emitir recibo', self.recibo)
        m.exec(self.grade.viewport().mapToGlobal(pos))


class Dashboard(QWidget):
    """TabDashboard: botoes laterais Caixa / Competencia / Linear e as tres analises."""

    def __init__(self, janela):
        super().__init__()
        self.j = janela
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lateral = QFrame()
        lateral.setFixedWidth(96)
        lateral.setStyleSheet(f'QFrame {{ background: {E.DASH_LATERAL}; }}')
        ll = QVBoxLayout(lateral)
        ll.setContentsMargins(3, 3, 3, 3)
        ll.setSpacing(6)
        self.paginas = QStackedWidget()
        self.botoes = []
        for i, (texto, ic) in enumerate((('Caixa', 'fa6s.cash-register'), ('Competência', 'fa6s.scale-balanced'), ('Linear', 'fa6s.chart-line'))):
            b = SpeedButton(texto, icone(ic, '#ffffff'), glyph_top=True, tam_icone=30)
            b.setFixedSize(90, 80)
            b.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
            b.clicked.connect(lambda _=False, i=i: self.mostrar(i))
            ll.addWidget(b)
            self.botoes.append(b)
        ll.addStretch()
        lay.addWidget(lateral)
        lay.addWidget(self.paginas, 1)
        self.paginas.addWidget(self._pagina_caixa())
        self.paginas.addWidget(self._pagina_comp())
        self.paginas.addWidget(self._pagina_linear())
        self.mostrar(0, carregar=False)

    def mostrar(self, i, carregar=True):
        self.paginas.setCurrentIndex(i)
        for k, b in enumerate(self.botoes):
            cor = E.DASH_BOTAO_ATIVO if k == i else E.DASH_BOTAO
            b.setStyleSheet(f'QToolButton {{ background: {cor}; color: #ffffff; border: 0; }} QToolButton:hover {{ background: #5b8fcf; }}')
        if carregar:
            self.atualizar()

    def _barra_analise(self, titulo):
        w = QFrame()
        w.setStyleSheet(f'QFrame {{ background: {E.CONTA_CONTROLE}; }}')
        w.setFixedHeight(38)
        h = QHBoxLayout(w)
        h.setContentsMargins(3, 3, 3, 3)
        t = rotulo(titulo, px=15, nome='Segoe UI Semibold', negrito=True)
        h.addWidget(t)
        h.addSpacing(16)
        h.addWidget(rotulo('Analisar: ', px=13, nome='Segoe UI'))
        combo = QComboBox()
        combo.setFont(E.fonte('Segoe UI', 15))
        for texto, dado in (('Hoje', 'hoje'), ('Esta Semana', 'semana'), ('Este Mês', 'mes'), ('Período específico', 'periodo')):
            combo.addItem(texto, dado)
        combo.setFixedWidth(220)
        h.addWidget(combo)
        return w, h, combo

    def _card(self, titulo, cor, ic):
        c = QFrame()
        c.setFixedSize(180, 76)
        c.setStyleSheet(f'QFrame {{ background: {cor}; }} QLabel {{ color: #ffffff; background: transparent; }}')
        g = QLabel(c)
        g.setPixmap(icone(ic, '#ffffff').pixmap(38, 38))
        g.move(8, 6)
        t = QLabel(titulo, c)
        t.setFont(E.fonte('Segoe UI', 13, negrito=True))
        t.setAlignment(Qt.AlignRight)
        t.setGeometry(50, 4, 124, 18)
        sep = QFrame(c)
        sep.setStyleSheet('background: #ffffff;')
        sep.setGeometry(51, 27, 123, 1)
        v = QLabel('R$ 0,00', c)
        v.setFont(E.fonte('Segoe UI', 21, negrito=True))
        v.setAlignment(Qt.AlignCenter)
        v.setGeometry(4, 40, 172, 32)
        c.valor = v
        return c

    def _pagina_caixa(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setContentsMargins(0, 0, 0, 0)
        barra, h, self.combo_caixa = self._barra_analise('Análise em Regime de Caixa')
        self.ck_vencidos = QCheckBox('Considerar os vencidos')
        self.ck_vencidos.setToolTip('Considerar os vencidos anteriores ao período analisado.')
        h.addWidget(self.ck_vencidos)
        self.per_caixa = self._periodo_especifico(h)
        h.addStretch()
        v.addWidget(barra)
        cards = QHBoxLayout()
        cards.setContentsMargins(3, 3, 3, 3)
        self.c_pago = self._card('Pago', E.CARD_PAGO, 'fa6s.arrow-trend-down')
        self.c_rec = self._card('Recebido', E.CARD_RECEBIDO, 'fa6s.arrow-trend-up')
        self.c_apagar = self._card('À pagar', E.CARD_APAGAR, 'fa6s.file-invoice-dollar')
        self.c_areceber = self._card('À receber', E.CARD_ARECEBER, 'fa6s.hand-holding-dollar')
        for c in (self.c_pago, self.c_rec, self.c_apagar, self.c_areceber):
            cards.addWidget(c)
        cards.addStretch()
        v.addLayout(cards)
        self.g_caixa = Grafico()
        v.addWidget(self.g_caixa, 1)
        self.combo_caixa.currentIndexChanged.connect(self.atualizar)
        self.ck_vencidos.toggled.connect(self.atualizar)
        return p

    def _periodo_especifico(self, h):
        from .base import CampoData
        de, ate = CampoData(px=13), CampoData(px=13)
        de.setDate(de.date().addDays(-(de.date().day() - 1)))
        for w in (de, ate):
            w.setFixedWidth(115)
            w.hide()
            w.dateChanged.connect(lambda _d: self.atualizar())
        a = rotulo(' a ', px=13, nome='Segoe UI')
        a.hide()
        h.addWidget(de)
        h.addWidget(a)
        h.addWidget(ate)
        return de, a, ate

    def _pagina_comp(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setContentsMargins(0, 0, 0, 0)
        barra, h, self.combo_comp = self._barra_analise('Análise em Regime de Competência')
        self.per_comp = self._periodo_especifico(h)
        h.addStretch()
        v.addWidget(barra)
        cards = QHBoxLayout()
        cards.setContentsMargins(3, 3, 3, 3)
        self.c_desp = self._card('Despesas', E.CARD_PAGO, 'fa6s.arrow-trend-down')
        self.c_rece = self._card('Receitas', E.CARD_RECEBIDO, 'fa6s.arrow-trend-up')
        self.c_marg = self._card('Margem Bruta', E.CARD_ARECEBER, 'fa6s.scale-balanced')
        for c in (self.c_desp, self.c_rece, self.c_marg):
            cards.addWidget(c)
        cards.addStretch()
        v.addLayout(cards)
        gh = QHBoxLayout()
        self.g_comp = Grafico()
        self.g_margem = Grafico()
        self.g_margem.setFixedWidth(300)
        gh.addWidget(self.g_comp, 1)
        gh.addWidget(self.g_margem)
        v.addLayout(gh, 1)
        self.combo_comp.currentIndexChanged.connect(self.atualizar)
        return p

    def _pagina_linear(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setContentsMargins(0, 0, 0, 0)
        w = QFrame()
        w.setStyleSheet(f'QFrame {{ background: {E.CONTA_CONTROLE}; }}')
        w.setFixedHeight(34)
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 3, 3, 3)
        h.addWidget(rotulo('Análise linear', px=15, nome='Segoe UI Semibold', negrito=True))
        h.addSpacing(16)
        h.addWidget(rotulo('Análise:', px=13, nome='Segoe UI Semibold', negrito=True))
        self.grp_lin = QButtonGroup(self)
        for i, (t, d) in enumerate((('Diária', 'dia'), ('Semanal', 'semana'), ('Mensal', 'mes'))):
            rb = QRadioButton(t)
            rb.setFont(E.fonte('Segoe UI', 13))
            rb.dado = d
            self.grp_lin.addButton(rb, i)
            h.addWidget(rb)
            if d == 'mes':
                rb.setChecked(True)
        h.addSpacing(10)
        self.ck_des, self.ck_rec, self.ck_sal = QCheckBox('Pagamentos'), QCheckBox('Recebimentos'), QCheckBox('Margem')
        for c in (self.ck_des, self.ck_rec, self.ck_sal):
            c.setChecked(True)
            c.setFont(E.fonte('Segoe UI', 13))
            h.addWidget(c)
            c.toggled.connect(self.atualizar)
        h.addStretch()
        self.grp_lin.idToggled.connect(lambda i, on: on and self.atualizar())
        v.addWidget(w)
        self.g_linear = Grafico()
        v.addWidget(self.g_linear, 1)
        return p

    def _periodo(self, combo, widgets):
        tipo = combo.currentData()
        de, a, ate = widgets
        for x in widgets:
            x.setVisible(tipo == 'periodo')
        return {'periodo_tipo': tipo, 'de': de.valor(), 'ate': ate.valor()}

    def atualizar(self):
        s = self.j.s
        if s.nivel('fluxo') < CONSULTA or not s.empresa_id:
            return
        i = self.paginas.currentIndex()
        if i == 0:
            d = s.dashboard(**self._periodo(self.combo_caixa, self.per_caixa), vencidos=self.ck_vencidos.isChecked())
            c = d['caixa']
            for card, k in ((self.c_pago, 'pago'), (self.c_rec, 'recebido'), (self.c_apagar, 'a_pagar'), (self.c_areceber, 'a_receber')):
                card.valor.setText(fin.moeda(c[k]))
            self.g_caixa.colunas(['Pago', 'Recebido', 'À pagar', 'À receber'],
                                 [('Valor', E.SERIE['R'], [c['pago'], c['recebido'], c['a_pagar'], c['a_receber']])],
                                 titulo=f"Regime de caixa — {fin.br(d['de'])} a {fin.br(d['ate'])}")
        elif i == 1:
            d = s.dashboard(**self._periodo(self.combo_comp, self.per_comp))
            c = d['competencia']
            self.c_desp.valor.setText(fin.moeda(c['despesas']))
            self.c_rece.valor.setText(fin.moeda(c['receitas']))
            self.c_marg.valor.setText(fin.moeda(c['margem']))
            itens = s.dashboard_itens(de=d['de'], ate=d['ate'], tipo='D')[:10]
            self.g_comp.ranking([{'rotulo': x['descricao'], 'valor': x['valor'],
                                  'perc': round(x['valor'] / (c['despesas'] or 1) * 100, 1)} for x in itens], E.SERIE['D'],
                                titulo=f"Despesas por ítem — {fin.br(d['de'])} a {fin.br(d['ate'])}")
            self.g_margem.pizza([('Despesas', c['despesas'], E.SERIE['D']), ('Margem', max(0, c['margem']), E.SERIE['M'])], titulo='Receitas')
        else:
            ag = self.grp_lin.checkedButton().dado
            dados = s.linear(agrupamento=ag, ano=self.j.cb_ano.currentData())
            cats = [(fin.MESES[int(p['periodo'][5:7]) - 1] if ag == 'mes' else p['periodo'][5:] if ag == 'dia' else p['periodo'][5:]) for p in dados]
            series = []
            if self.ck_rec.isChecked():
                series.append(('Recebimentos', E.SERIE['R'], [p['recebimentos'] for p in dados]))
            if self.ck_des.isChecked():
                series.append(('Pagamentos', E.SERIE['D'], [p['pagamentos'] for p in dados]))
            if self.ck_sal.isChecked():
                series.append(('Margem', E.SERIE['M'], [p['margem'] for p in dados]))
            self.g_linear.linhas(cats, series, titulo='Pagamentos e recebimentos realizados')


class QuadroSaldos(QFrame):
    """ScrollSaldo: quadro azul no canto superior direito com a aba "Saldos"."""

    def __init__(self, janela):
        super().__init__(janela)
        self.j = janela
        self.setFixedSize(290, 190)
        self.setMinimumSize(200, 100)
        self.setStyleSheet(f'QuadroSaldos {{ background: {E.FAIXA_MENU}; }}')
        v = QVBoxLayout(self)
        v.setContentsMargins(3, 6, 3, 3)
        abas = QTabWidget()
        abas.setFont(E.fonte('Arial', 13))
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setContentsMargins(2, 4, 2, 2)
        self.grade = Grade([('descricao', 'Conta', 150), ('saldo', 'Saldo', 100, 'moeda')], px=12, ordenar=False,
                           cor_linha=lambda l, c: '#c00000' if c == 'saldo' and (l.get('saldo') or 0) < 0 else None)
        self.grade.setFont(E.fonte('Segoe UI', 12))
        self.grade.verticalHeader().setDefaultSectionSize(20)
        self.grade.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.grade.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.grade.horizontalHeader().setStretchLastSection(False)
        self.grade.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grade.setToolTip('Duplo clique: extrato da conta')
        self.grade.ativada.connect(lambda l: self.j.relatorios.extrato(l['id']) if l.get('id') else None)
        wl.addWidget(self.grade)
        self.total = QLabel()
        self.total.setFont(E.fonte('Segoe UI', 12, negrito=True))
        self.total.setAlignment(Qt.AlignRight)
        wl.addWidget(self.total)
        abas.addTab(w, 'Saldos')
        v.addWidget(abas)

    def atualizar(self):
        s = self.j.s
        if not s.empresa_id or (s.nivel('bancos') < CONSULTA and s.nivel('fluxo') < CONSULTA) or s.config('exibir_saldos') != '1':
            self.hide()
            return
        self.show()
        contas = [c for c in s.saldos() if c['ativa']]
        self.grade.definir(contas, manter=False)
        self.total.setText(f"Total: {fin.moeda(sum(c['saldo'] for c in contas))}")


class JanelaPrincipal(QMainWindow):
    def __init__(self, app_ctx, sessao):
        super().__init__()
        from .lancamentos import Lancamentos
        from .cadastros import Cadastros
        from .relatorios import Relatorios
        from .ferramentas import Ferramentas
        self.ctx = app_ctx
        self.s = sessao
        self.cfg = QSettings('MCC', 'MCC')
        self.setWindowTitle('MCC')
        self.setWindowIcon(icone('fa6s.coins', E.FAIXA_MENU))
        self.resize(1106, 693)
        self.setMinimumSize(960, 560)
        self.lanc = Lancamentos(self)
        self.cad = Cadastros(self)
        self.relatorios = Relatorios(self)
        self.ferr = Ferramentas(self)
        central = QWidget()
        central.setStyleSheet('QWidget#central { background: #ffffff; }')
        central.setObjectName('central')
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(3, 3, 3, 0)
        v.setSpacing(0)
        v.addWidget(self._faixa_menu())
        v.addWidget(self._linha_usuario())
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet('background: #c8c8c8;')
        v.addWidget(sep)
        v.addWidget(self._faixa_conta())
        v.addWidget(self._faixa_filtros())
        v.addSpacing(9)
        self.abas = QTabWidget()
        self.abas.setFont(E.fonte('Verdana', 17, sublinhado=True))
        self.abas.tabBar().setStyleSheet('QTabBar::tab { min-width: 220px; padding: 5px 14px; }')
        self.aba_d = AbaLancamentos(self, 'D')
        self.aba_r = AbaLancamentos(self, 'R')
        self.dash = Dashboard(self)
        self.abas.addTab(self.aba_d, icone('fa6s.arrow-trend-down', '#b02a2a'), ' Despesas ')
        self.abas.addTab(self.aba_r, icone('fa6s.arrow-trend-up', '#1a7f37'), ' Receitas ')
        self.abas.addTab(self.dash, icone('fa6s.chart-pie', E.FAIXA_MENU), 'Dashboard')
        self.abas.currentChanged.connect(lambda _i: self.atualizar())
        v.addWidget(self.abas, 1)
        v.addWidget(self._rodape())
        self.saldos = QuadroSaldos(self)
        self.saldos.raise_()
        QShortcut(QKeySequence(Qt.Key_F5), self, activated=self.atualizar)
        QShortcut(QKeySequence(Qt.Key_Insert), self, activated=lambda: self.aba_atual() and self.form_lancamento(self.aba_atual().tipo))
        QShortcut(QKeySequence('Ctrl+F'), self, activated=lambda: self.ed_busca.setFocus())
        self.aplicar_usuario()

    # ---------- montagem ----------
    def _faixa_menu(self):
        f = _faixa(E.FAIXA_MENU, 59)
        h = QHBoxLayout(f)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(3)
        self.bt_topo = {}
        for chave, texto, ic in (('cad', '&Cadastros', 'fa6s.folder-open'), ('fer', '&Ferramentas', 'fa6s.screwdriver-wrench'),
                                 ('ban', '&Bancos', 'fa6s.building-columns'), ('rel', '&Relatórios', 'fa6s.chart-column'),
                                 ('sup', '&Suporte', 'fa6s.headset'), ('ace', 'Acesso fácil', 'fa6s.star')):
            b = SpeedButton(texto, icone(ic, '#ffffff'), glyph_top=True, tam_icone=26, topo=True)
            b.setFont(E.fonte('Arial', 12))
            b.setFixedSize(120, 53)
            b.setPopupMode(SpeedButton.InstantPopup)
            h.addWidget(b)
            self.bt_topo[chave] = b
        h.addStretch()
        self._montar_menus()
        return f

    def _menu(self, chave):
        m = QMenu(self)
        m.setFont(E.fonte('Segoe UI', 12))
        self.bt_topo[chave].setMenu(m)
        return m

    def _acao(self, menu, texto, fn, ic=None, perm=None, dica=None):
        a = menu.addAction(icone(ic) if ic else QIcon(), texto, fn)
        a.perm = perm
        if dica:
            a.setToolTip(dica)
        self._acoes.append(a)
        return a

    def _montar_menus(self):
        self._acoes = []
        R = lambda *a, **k: (lambda: self.relatorios.abrir(*a, **k))
        # PPCad
        m = self._menu('cad')
        self._acao(m, 'CADASTRO DE CONTAS CONTROLE', lambda: self.cad.empresas(), 'fa6s.building', 'config:2',
                   'Cadastro de Conta Pessoa Física / Conta Empresa')
        m.addSeparator()
        self._acao(m, 'CADASTRO DE CENTROS DE CUSTO', lambda: self.cad.centros(), 'fa6s.sitemap', 'centros')
        m.addSeparator()
        self._acao(m, 'CADASTRO DE CLIENTES', lambda: self.cad.pessoas('C'), 'fa6s.user-tie', 'receitas')
        m.addSeparator()
        self._acao(m, 'CADASTRO DE FORNECEDORES', lambda: self.cad.pessoas('F'), 'fa6s.truck', 'despesas')
        m.addSeparator()
        self._acao(m, 'LEMBRETES DE CONTAS', lambda: self.ferr.lembretes(), 'fa6s.bell', 'despesas|receitas')
        m.addSeparator()
        self._acao(m, 'IR PARA OUTRA CONTA', self.trocar_empresa, 'fa6s.right-left', None, 'Ir para outra Conta Pessoa Física ou Empresa')
        m.addSeparator()
        self._acao(m, 'SAIR DO SISTEMA', self.close, 'fa6s.power-off', None, 'Fechar o Sistema')
        # ppCnf (Ferramentas)
        m = self._menu('fer')
        sub = m.addMenu(icone('fa6s.gear'), 'CONFIGURAÇÕES')
        self._acao(sub, 'ALTERAR SENHA DE ACESSO', lambda: self.ferr.alterar_senha(), 'fa6s.key')
        sub.addSeparator()
        self._acao(sub, 'USUÁRIOS', lambda: self.ferr.usuarios(), 'fa6s.users-gear', 'config:2')
        sub.addSeparator()
        self._acao(sub, 'PROTEÇÃO DE DADOS', lambda: self.ferr.protecao(), 'fa6s.lock', 'config:2')
        sub.addSeparator()
        self._acao(sub, 'BANCO DE DADOS', lambda: self.ferr.banco_de_dados(), 'fa6s.database', 'config:2', 'Configura o banco de dados local/rede')
        sub.addSeparator()
        cores = sub.addMenu(icone('fa6s.palette'), 'COR DOS RELATÓRIOS')
        cores.setToolTip('Selecione a cor de fundo dos cabeçalhos e rodapés dos relatórios')
        self.acoes_cor = []
        for chave, (nome, hexa) in E.CORES_RELATORIO.items():
            a = cores.addAction(nome.upper(), lambda chave=chave: self._definir_cfg('cor_relatorio', chave))
            a.setCheckable(True)
            a.chave = chave
            self.acoes_cor.append(a)
        sub.addSeparator()
        ger = sub.addMenu(icone('fa6s.print'), 'GERAÇÃO DOS RELATÓRIOS')
        self.acoes_ger = []
        for chave, texto in (('tela', 'GERADO NA TELA DO SISTEMA'), ('pdf', 'GERADO EM ARQUIVO PDF'), ('preview', 'GERADO PELO REPORT PREVIEW'),
                             ('html', 'GERADO EM ARQUIVO HTML')):
            a = ger.addAction(texto, lambda chave=chave: self._definir_cfg('geracao_relatorio', chave))
            a.setCheckable(True)
            a.chave = chave
            self.acoes_ger.append(a)
        sub.addSeparator()
        logo = sub.addMenu(icone('fa6s.image'), 'LOGOMARCA DA EMPRESA')
        self._acao(logo, 'INCLUIR', lambda: self.ferr.logomarca(True), 'fa6s.file-image', 'config:2')
        logo.addSeparator()
        self._acao(logo, 'EXCLUIR', lambda: self.ferr.logomarca(False), 'fa6s.trash-can', 'config:2')
        m.addSeparator()
        self._acao(m, 'CONFIGURAÇÕES DA CONTA CONTROLE', lambda: self.ferr.config_conta(), 'fa6s.sliders', 'config:2')
        m.addSeparator()
        tab = m.addMenu(icone('fa6s.table-list'), 'TABELAS')
        self._acao(tab, 'ÍTENS DE DESPESAS', lambda: self.cad.itens('D'), 'fa6s.list', 'despesas')
        tab.addSeparator()
        self._acao(tab, 'ÍTENS DE RECEITAS', lambda: self.cad.itens('R'), 'fa6s.list', 'receitas')
        m.addSeparator()
        self._acao(m, 'REGISTROS EXCLUÍDOS', lambda: self.ferr.excluidos(), 'fa6s.trash-arrow-up', 'despesas|receitas')
        self._acao(m, 'EXPORTAR LANÇAMENTOS (CSV)', self.exportar_csv, 'fa6s.file-csv', 'despesas|receitas')
        # PPBan
        m = self._menu('ban')
        self._acao(m, 'CADASTRO DE CONTAS BANCÁRIAS', lambda: self.cad.contas(), 'fa6s.building-columns', 'bancos',
                   'Cadastro de contas bancárias da Empresa/Pessoa Física')
        m.addSeparator()
        self._acao(m, 'CONTROLE DE MOVIMENTAÇÕES BANCÁRIAS', lambda: self.cad.movbancarias(), 'fa6s.money-bill-transfer', 'bancos',
                   'Movimentações bancárias com as contas da Empresa/Pessoa Física')
        m.addSeparator()
        self._acao(m, 'IMPORTAR EXTRATO BANCÁRIO (OFX)', lambda: self.ferr.conciliacao(), 'fa6s.file-import', 'bancos:2')
        # PPRel
        m = self._menu('rel')
        self._acao(m, 'RELATÓRIO DE DESPESAS', R('lancamentos', tipo='D'), 'fa6s.file-lines', 'despesas')
        self._acao(m, 'RELATÓRIO DE DESPESAS TOTAIS', R('totais_item', tipo='D'), 'fa6s.file-lines', 'despesas')
        m.addSeparator()
        self._acao(m, 'RELATÓRIO DE RECEITAS', R('lancamentos', tipo='R'), 'fa6s.file-lines', 'receitas')
        self._acao(m, 'RELATÓRIO DE RECEITAS TOTAIS', R('totais_item', tipo='R'), 'fa6s.file-lines', 'receitas')
        m.addSeparator()
        sub = m.addMenu(icone('fa6s.file-invoice-dollar'), 'CONTAS A PAGAR')
        self._acao(sub, 'CONTAS EM ABERTO', R('lancamentos', tipo='D', situacao='P', campo_data='vencimento', titulo='Contas a pagar em aberto'), None, 'despesas')
        self._acao(sub, 'CONTAS PAGAS', R('lancamentos', tipo='D', situacao='V', campo_data='vencimento', titulo='Contas pagas'), None, 'despesas')
        self._acao(sub, 'TODAS AS CONTAS', R('lancamentos', tipo='D', campo_data='vencimento', titulo='Contas a pagar'), None, 'despesas')
        self._acao(sub, 'CONTAS A PAGAR POR FORNECEDOR', R('por_pessoa', tipo='D', situacao='P'), None, 'despesas')
        self._acao(sub, 'ANALISE DE PONTUALIDADE  DE PAGAMENTOS', R('pontualidade', tipo='D'), None, 'despesas')
        sub = m.addMenu(icone('fa6s.hand-holding-dollar'), 'CONTAS A RECEBER')
        self._acao(sub, 'CONTAS EM ABERTO', R('lancamentos', tipo='R', situacao='P', campo_data='vencimento', titulo='Contas a receber em aberto'), None, 'receitas')
        self._acao(sub, 'CONTAS RECEBIDAS', R('lancamentos', tipo='R', situacao='V', campo_data='vencimento', titulo='Contas recebidas'), None, 'receitas')
        self._acao(sub, 'TODAS AS CONTAS', R('lancamentos', tipo='R', campo_data='vencimento', titulo='Contas a receber'), None, 'receitas')
        self._acao(sub, 'CONTAS A RECEBER POR CLIENTE', R('por_pessoa', tipo='R', situacao='P'), None, 'receitas')
        self._acao(sub, 'ANALISE DE PONTUALIDADE DE RECEBIMENTOS', R('pontualidade', tipo='R'), None, 'receitas')
        m.addSeparator()
        G = lambda *a, **k: (lambda: self.relatorios.grafico(*a, **k))
        sub = m.addMenu(icone('fa6s.chart-column'), 'GRÁFICOS GERENCIAIS')
        self._acao(sub, 'GRÁFICO DESPESAS x RECEITAS', G('desp_rec'), None, 'despesas&receitas')
        self._acao(sub, 'GRÁFICO DE DESPESAS', G('composicao', tipo='D', agrupar='item'), None, 'despesas')
        self._acao(sub, 'GRÁFICO DE RECEITAS', G('composicao', tipo='R', agrupar='item'), None, 'receitas')
        self._acao(sub, 'GRÁFICO DE EVOLUÇÃO DE DESPESAS POR ÍTEM', G('evolucao', tipo='D', agrupar='item'), None, 'despesas')
        self._acao(sub, 'GRÁFICO DE EVOLUÇÃO DE DESPESAS POR FORNECEDOR', G('evolucao', tipo='D', agrupar='pessoa'), None, 'despesas')
        self._acao(sub, 'GRÁFICO DE EVOLUÇÃO DE RECEITAS POR ÍTEM', G('evolucao', tipo='R', agrupar='item'), None, 'receitas')
        self._acao(sub, 'GRÁFICO DE EVOLUÇÃO DE RECEITAS POR CLIENTE', G('evolucao', tipo='R', agrupar='pessoa'), None, 'receitas')
        sub = m.addMenu(icone('fa6s.sitemap'), 'ANÁLISE POR CENTRO DE CUSTO')
        self._acao(sub, 'ORÇAMENTO POR CENTRO DE CUSTO', R('centros', tipo='D'), None, 'centros&despesas')
        self._acao(sub, 'PROJEÇÃO POR CENTRO DE LUCRO', R('centros', tipo='R'), None, 'centros&receitas')
        self._acao(sub, 'RELATÓRIO DE DESPESAS', R('centro_itens', tipo='D'), None, 'centros&despesas')
        self._acao(sub, 'RELATÓRIO DE RECEITAS', R('centro_itens', tipo='R'), None, 'centros&receitas')
        self._acao(sub, 'RELATÓRIO DE DESPESAS TOTAIS POR CENTRO', R('centro_itens', tipo='D', totais='1'), None, 'centros&despesas')
        self._acao(sub, 'RELATÓRIO DE RECEITAS TOTAIS POR CENTRO', R('centro_itens', tipo='R', totais='1'), None, 'centros&receitas')
        self._acao(sub, 'RELATÓRIO DE FLUXO DE CAIXA POR CENTRO', R('fluxo_centros'), None, 'centros')
        self._acao(sub, 'GRÁFICO DE DESPESAS TOTAIS POR CENTRO', G('composicao', tipo='D', agrupar='centro'), None, 'centros&despesas')
        self._acao(sub, 'GRÁFICO DE RECEITAS TOTAIS POR CENTRO', G('composicao', tipo='R', agrupar='centro'), None, 'centros&receitas')
        self._acao(sub, 'GRÁFICO DE DESPESAS', G('composicao', tipo='D', agrupar='item'), None, 'centros&despesas')
        self._acao(sub, 'GRÁFICO DE RECEITAS', G('composicao', tipo='R', agrupar='item'), None, 'centros&receitas')
        sub = m.addMenu(icone('fa6s.cash-register'), 'FLUXO DE CAIXA')
        self._acao(sub, 'EXTRATO DE FECHAMENTO DE CAIXA', R('fechamento'), None, 'fluxo')
        self._acao(sub, 'FLUXO DE CAIXA (REALIZADO)', R('fluxo'), None, 'fluxo')
        self._acao(sub, 'FLUXO DE CAIXA POR DIA', R('fluxo_dia'), None, 'fluxo')
        self._acao(sub, 'PREVISÃO DE CAIXA', R('fluxo', previsao='1'), None, 'fluxo')
        self._acao(sub, 'PREVISÃO DE CAIXA POR DIA', R('fluxo_dia', previsao='1'), None, 'fluxo')
        sub = m.addMenu(icone('fa6s.building-columns'), 'BANCOS')
        self._acao(sub, 'EXTRATO DE CONTA BANCÁRIA', R('extrato', tipo_conta='B'), None, 'bancos')
        self._acao(sub, 'EXTRATO DE PREVISÃO BANCÁRIA', R('extrato', previsao='1'), None, 'bancos')
        self._acao(sub, 'EXTRATO DO CAIXA INTERNO', R('extrato', tipo_conta='C'), None, 'bancos')
        self._acao(sub, 'RELATÓRIO DE SALDO DE CONTAS', R('saldos'), None, 'bancos')
        self._acao(sub, 'RELATÓRIO COMPARATIVO DE SALDOS', R('comparativo_saldos'), None, 'bancos')
        m.addSeparator()
        self._acao(m, 'RELATÓRIO DE CLIENTES', R('pessoas', pessoa_tipo='C'), 'fa6s.user-tie', 'receitas')
        self._acao(m, 'RELATÓRIO DE FORNECEDORES', R('pessoas', pessoa_tipo='F'), 'fa6s.truck', 'despesas')
        m.addSeparator()
        self._acao(m, 'RELATÓRIO ANALÍTICO', lambda: self.relatorios.analitico(), 'fa6s.magnifying-glass-chart', 'despesas|receitas')
        sub = m.addMenu(icone('fa6s.table'), 'RELATÓRIO DEMONSTRATIVO')
        sd = sub.addMenu('DEMONSTRATIVO ANUAL DE DESPESAS')
        for texto, agr, extra in (('POR ÍTEM', 'item', ''), ('POR FORNECEDOR', 'pessoa', ''), ('POR CENTRO DE CUSTO', 'centro', '&centros'),
                                  ('POR CONTA BANCÁRIA/CAIXA INTERNO', 'conta', '')):
            self._acao(sd, texto, R('demonstrativo', tipo='D', agrupar=agr), None, 'despesas' + extra)
        sr = sub.addMenu('DEMONSTRATIVO ANUAL DE RECEITAS')
        for texto, agr, extra in (('POR ITEM', 'item', ''), ('POR CLIENTE', 'pessoa', ''), ('POR CENTRO DE LUCRO', 'centro', '&centros'),
                                  ('POR CONTA BANCÁRIA / CAIXA INTERNO', 'conta', '')):
            self._acao(sr, texto, R('demonstrativo', tipo='R', agrupar=agr), None, 'receitas' + extra)
        sub.addSeparator()
        self._acao(sub, 'DEMONSTRATIVO DE RESULTADOS', R('dre'), None, 'fluxo')
        # PPSup
        m = self._menu('sup')
        self._acao(m, 'MANUAL DO USUÁRIO', lambda: self.ferr.manual(), 'fa6s.book')
        self._acao(m, 'COMANDOS DE FUNÇÃO', lambda: self.ferr.atalhos(), 'fa6s.keyboard')
        m.addSeparator()
        self._acao(m, 'SOBRE...', lambda: self.ferr.sobre(), 'fa6s.circle-info')
        # PPAce (Acesso facil)
        m = self._menu('ace')
        self._acao(m, 'Alterar dados Cadastrais', lambda: self.cad.editar_empresa_atual(), 'fa6s.id-card', 'config:2',
                   'Altera as suas informações cadastradas no sistema')
        self.acao_centros = self._acao(m, 'Ativar/Desativar controle por centros de custo/lucro', self.alternar_centros, 'fa6s.toggle-on', 'config:2')
        m.addSeparator()
        self._acao(m, 'Inserir multiplas despesas (parcelamento)', lambda: self.parcelamento('D'), 'fa6s.layer-group', 'despesas:2')
        self._acao(m, 'Inserir multiplas receitas (parcelamento)', lambda: self.parcelamento('R'), 'fa6s.layer-group', 'receitas:2')
        self._acao(m, 'Incluir uma conta a pagar', lambda: self.form_lancamento('D'), 'fa6s.file-invoice-dollar', 'despesas:2')
        self._acao(m, 'Incluir uma conta a receber', lambda: self.form_lancamento('R'), 'fa6s.hand-holding-dollar', 'receitas:2')
        m.addSeparator()
        self._acao(m, 'Calculadora', self.calculadora, 'fa6s.calculator')

    def _linha_usuario(self):
        f = QFrame()
        f.setFixedHeight(26)
        h = QHBoxLayout(f)
        h.setContentsMargins(3, 3, 3, 3)
        self.lb_login = rotulo('', px=14, nome='Segoe UI Semibold', cor=E.TEXTO_LOGIN, negrito=True)
        self.lb_usuario = rotulo('', px=13, nome='Segoe UI', cor=E.TEXTO_LOGIN)
        self.lb_acesso = rotulo('', px=11, nome='Segoe UI', cor=E.TEXTO_LOGIN)
        for w in (self.lb_login, self.lb_usuario, self.lb_acesso):
            h.addWidget(w)
        h.addStretch()
        return f

    def _faixa_conta(self):
        f = _faixa(E.CONTA_CONTROLE, 57)
        h = QHBoxLayout(f)
        h.setContentsMargins(3, 16, 3, 16)
        h.setSpacing(3)
        rot = QLabel(' Conta controle:  ')
        rot.setFont(E.fonte('Arial', 16))
        rot.setStyleSheet(f'color: #ffffff; background: {E.MED_GRAY}; padding: 0 2px;')
        self.lb_con = QLabel()
        self.lb_con.setFont(E.fonte('Arial', 19, sublinhado=True))
        self.lb_con.setStyleSheet(f'color: #ffffff; background: {E.MED_GRAY}; padding: 0 6px;')
        self.lb_con.setCursor(Qt.PointingHandCursor)
        self.lb_con.setToolTip('Clique para ir para outra conta controle')
        self.lb_con.mousePressEvent = lambda _e: self.trocar_empresa()
        self.lb_protecao = QLabel()
        self.lb_protecao.setFont(E.fonte('Arial', 13, negrito=True))
        self.lb_protecao.setStyleSheet('color: #7a0000; background: transparent; padding-left: 12px;')
        h.addWidget(rot)
        h.addWidget(self.lb_con)
        h.addWidget(self.lb_protecao)
        h.addStretch()
        return f

    def _faixa_filtros(self):
        f = _faixa(E.FILTRO, 40)
        h = QHBoxLayout(f)
        h.setContentsMargins(0, 4, 3, 3)
        self._lay_filtros = h
        h.setSpacing(3)
        ic = QLabel()
        ic.setPixmap(icone('fa6s.filter', E.TEXTO_FILTRO).pixmap(26, 26))
        ic.setFixedSize(40, 33)
        ic.setAlignment(Qt.AlignCenter)
        h.addWidget(ic)
        lf = rotulo('Filtrar:', px=13, nome='Segoe UI Semibold', cor=E.TEXTO_FILTRO)
        h.addWidget(lf)
        self.cb_mes = _combo_filtro(PERIODOS_MES, 98)
        self.cb_mes.setToolTip('Selecione o mês ou período a ser filtrado.')
        self.cb_ano = _combo_filtro([(str(a), a) for a in range(2001, 2041)], 65)
        self.cb_ano.setToolTip('Selecione o ano de filtragem dos lançamentos.')
        self.cb_data = _combo_filtro([('Filtrar por data de movimento', 'data_mov'), ('Filtrar por data de vcto/pagto.', 'vencimento'),
                                      ('Filtrar por data Mov/Ven/Pgo.', 'ambos')], 192)
        self.cb_data.setToolTip('Filtrar por campo Data movimento ou Vcto/Pagto.')
        self.cb_conta = _combo_filtro([('Todas as contas', None)], 128)
        self.cb_conta.setToolTip('Filtrar por conta bancária ou caixa interno')
        self.cb_sit = _combo_filtro([('Contas pagas', 'V'), ('Contas em aberto', 'P'), ('Pagas ou em aberto', '')], 140)
        self.cb_sit.setToolTip('Filtrar por situação (Pago ou em aberto)')
        lo = rotulo('Ordem:', px=13, nome='Segoe UI Semibold', cor=E.TEXTO_FILTRO)
        self.cb_ordem = _combo_filtro(ORDENS, 135)
        self.cb_ordem.setToolTip('Ordenação')
        self.ck_dec = QCheckBox('Decrescente')
        self.ck_dec.setFont(E.fonte('Segoe UI', 12))
        for w in (self.cb_mes, self.cb_ano, self.cb_data, self.cb_conta, self.cb_sit, lo, self.cb_ordem, self.ck_dec):
            h.addWidget(w, 1 if isinstance(w, QComboBox) else 0)  # combos crescem ate a largura original
        h.addStretch(1)
        hoje = date.today()
        self.cb_ano.setCurrentIndex(self.cb_ano.findData(hoje.year))
        self.cb_mes.setCurrentIndex(hoje.month - 1)
        self.cb_sit.setCurrentIndex(2)
        for c in (self.cb_mes, self.cb_ano, self.cb_data, self.cb_conta, self.cb_sit, self.cb_ordem):
            c.currentIndexChanged.connect(lambda _i: self.atualizar())
        self.ck_dec.toggled.connect(lambda _b: self.atualizar())
        return f

    def _rodape(self):
        f = QFrame()
        f.setFixedHeight(28)
        h = QHBoxLayout(f)
        h.setContentsMargins(3, 2, 3, 2)
        b = SpeedButton('', icone('fa6s.magnifying-glass', '#808080'), dica='Busca rápida por campo')
        b.setFixedSize(22, 22)
        h.addWidget(b)
        self.ed_busca = QLineEdit()
        self.ed_busca.setPlaceholderText('Busca rápida: descrição, pessoa, documento, observação ou valor   (Ctrl+F)')
        self.ed_busca.setFont(E.fonte('Verdana', 12))
        self.ed_busca.setClearButtonEnabled(True)
        self.ed_busca.setFixedWidth(420)
        h.addWidget(self.ed_busca)
        h.addStretch()
        self.lb_status = rotulo('', px=11, nome='Segoe UI', cor='#555')
        h.addWidget(self.lb_status)
        self._timer_busca = QTimer(self, singleShot=True, interval=300, timeout=self.atualizar)
        self.ed_busca.textChanged.connect(lambda _t: self._timer_busca.start())
        b.clicked.connect(self.ed_busca.setFocus)
        return f

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # quadro de saldos ancorado no canto superior direito, como no original
        self.saldos.move(self.width() - self.saldos.width() - 3, 5)
        # em telas estreitas (1366/1280) o quadro encolhe para caber acima da faixa de filtros
        topo_filtros = self.cb_mes.parentWidget().mapTo(self, self.cb_mes.parentWidget().rect().topLeft()).y()
        estreita = self.width() < 1500
        livre = self.width() - (self.bt_topo['ace'].geometry().right() + 30)
        self.saldos.setFixedSize(max(250, min(430, livre)) if estreita else 290, max(110, topo_filtros - 8) if estreita else 190)
        self.saldos.move(self.width() - self.saldos.width() - 3, 5)

    # ---------- estado ----------
    def aba_atual(self):
        w = self.abas.currentWidget()
        return w if isinstance(w, AbaLancamentos) else None

    def pode(self, regra):
        """'modulo[:nivel]' com | (ou) e & (e)."""
        if not regra:
            return True
        if '&' in regra:
            return all(self.pode(p) for p in regra.split('&'))
        for p in regra.split('|'):
            mod, _, n = p.partition(':')
            if self.s.nivel(mod) >= int(n or 1):
                return True
        return False

    def aplicar_usuario(self):
        u = self.s.u
        self.lb_login.setText(u['email'])
        self.lb_usuario.setText(f"  {u['nome']}{'  (administrador)' if u['admin'] else ''}")
        ult = u.get('ultimo_acesso_anterior')
        self.lb_acesso.setText(f'   Último acesso: {fin.br(ult[:10])} {ult[11:16]}' if ult else '')
        for a in self._acoes:
            a.setVisible(self.pode(getattr(a, 'perm', None)))
        for chave, b in self.bt_topo.items():
            b.setVisible(any(a.isVisible() for a in self._acoes_de(b.menu())))
        self.abas.setTabVisible(0, self.s.nivel('despesas') > 0)
        self.abas.setTabVisible(1, self.s.nivel('receitas') > 0)
        self.abas.setTabVisible(2, self.s.nivel('fluxo') > 0)
        self.aba_d.aplicar_permissao(self.s.nivel('despesas'))
        self.aba_r.aplicar_permissao(self.s.nivel('receitas'))
        cor = self.cfg.value('cor_relatorio', 'cinza_claro')
        for a in self.acoes_cor:
            a.setChecked(a.chave == cor)
        ger = self.cfg.value('geracao_relatorio', 'tela')
        for a in self.acoes_ger:
            a.setChecked(a.chave == ger)
        for i in range(3):
            if self.abas.isTabVisible(i):
                if not self.abas.isTabVisible(self.abas.currentIndex()):
                    self.abas.setCurrentIndex(i)
                break

    def _acoes_de(self, menu):
        for a in menu.actions():
            if a.menu():
                yield from self._acoes_de(a.menu())
            elif not a.isSeparator():
                yield a

    def _definir_cfg(self, chave, valor):
        self.cfg.setValue(chave, valor)
        self.aplicar_usuario()

    def usar_empresa(self, empresa_id):
        self.s.usar_empresa(empresa_id)
        self.cfg.setValue(f"ultima_empresa/{self.s.u['id']}", empresa_id)
        emp = self.s.empresa()
        self.lb_con.setText(emp['nome'])
        self.setWindowTitle(f"MCC - {emp['nome']}")
        self.acao_centros.setText(('Desativar' if emp['usa_centro_custo'] else 'Ativar') + ' controle por centros de custo/lucro')
        self._carregar_contas()
        self.atualizar()
        lemb = self.s.lembretes(3)
        if lemb:
            QTimer.singleShot(400, lambda: self.ferr.lembretes(automatico=True))

    def _carregar_contas(self):
        atual = self.cb_conta.currentData()
        self.cb_conta.blockSignals(True)
        self.cb_conta.clear()
        self.cb_conta.addItem('Todas as contas', None)
        for c in self.s.listar('contas'):
            if c['ativa']:
                self.cb_conta.addItem(c['descricao'], c['id'])
        i = self.cb_conta.findData(atual)
        self.cb_conta.setCurrentIndex(max(0, i))
        self.cb_conta.blockSignals(False)

    def filtros(self):
        return {'situacao': self.cb_sit.currentData(), 'conta_id': self.cb_conta.currentData(), 'campo_data': self.cb_data.currentData(),
                'ano': self.cb_ano.currentData(), 'mes': self.cb_mes.currentData(), 'ordem': self.cb_ordem.currentData(),
                'decrescente': self.ck_dec.isChecked(), 'busca': self.ed_busca.text().strip()}

    def atualizar(self):
        if not self.s.empresa_id:
            return
        emp = self.s.empresa()
        lim = emp.get('bloqueio_ate')
        self.lb_protecao.setText(f'🔒 Movimentações bloqueadas até {fin.br(lim)}' if lim else '')
        self.aba_d.grade.setColumnHidden(7, not emp['usa_centro_custo'])
        self.aba_r.grade.setColumnHidden(7, not emp['usa_centro_custo'])
        aba = self.aba_atual()
        if aba and self.s.nivel_tipo(aba.tipo) >= CONSULTA:
            linhas = self.s.listar_lancamentos(tipo=aba.tipo, **self.filtros())
            aba.carregar(linhas)
            self.lb_status.setText(f'Atualizado às {date.today().strftime("%d/%m/%Y")} {__import__("datetime").datetime.now().strftime("%H:%M:%S")}')
        elif self.abas.currentWidget() is self.dash:
            self.dash.atualizar()
        self.saldos.atualizar()

    # ---------- acoes delegadas ----------
    def form_lancamento(self, tipo, id_=None):
        if self.lanc.formulario(tipo, id_):
            self.atualizar()

    def parcelamento(self, tipo):
        if self.lanc.parcelamento(tipo):
            self.atualizar()

    def form_baixa(self, l):
        if self.lanc.baixa(l):
            self.atualizar()

    def baixa_multipla(self, tipo, ids=None):
        if self.lanc.baixa_multipla(tipo, ids):
            self.atualizar()

    def excluir_lancamento(self, l):
        if self.lanc.excluir(l):
            self.atualizar()

    def estornar(self, l):
        if l['situacao'] != 'V':
            msg_aviso(self, 'Este lançamento não está baixado.')
            return
        if confirmar(self, f"Estornar a baixa de \"{l['descricao']}\"?") and executar(self, lambda senha: self.s.estornar(l['id'], senha=senha)):
            self.atualizar()

    def localizar(self, tipo):
        self.lanc.localizar(tipo)

    def recibo(self, l):
        self.relatorios.recibo(l)

    def transferir_empresa(self, linhas):
        if self.lanc.transferir_empresa(linhas):
            self.atualizar()

    def repetir_mes_seguinte(self, linhas):
        if self.lanc.repetir_mes_seguinte(linhas):
            self.atualizar()

    def trocar_empresa(self):
        from .acesso import escolher_empresa
        emp = escolher_empresa(self, self.s, forcar=True)
        if emp:
            self.usar_empresa(emp)

    def alternar_centros(self):
        emp = self.s.empresa()
        novo = 0 if emp['usa_centro_custo'] else 1
        if executar(self, lambda senha: self.s.salvar('empresas', {'usa_centro_custo': novo}, emp['id'])):
            self.usar_empresa(emp['id'])
            msg_info(self, f"Controle por centros de custo/lucro {'ativado' if novo else 'desativado'}.")

    def calculadora(self):
        for prog in ('gnome-calculator', 'kcalc', 'galculator', 'mate-calc', 'xcalc'):
            if shutil.which(prog):
                subprocess.Popen([prog])
                return
        from .ferramentas import Calculadora
        Calculadora(self).show()

    def exportar_csv(self):
        aba = self.aba_atual()
        if not aba:
            msg_aviso(self, 'Abra a aba Despesas ou Receitas para exportar.')
            return
        self.relatorios.exportar_grade(aba.grade, 'Despesas' if aba.tipo == 'D' else 'Receitas')
