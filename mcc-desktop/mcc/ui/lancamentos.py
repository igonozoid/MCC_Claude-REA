"""Telas de lancamento: FMovCad (incluir/alterar), FMulCad (parcelamento), FBaixa,
FBaixaMult, FMultDelMov (exclusao de parcelas), FPesM (localizar), transferir para
outra conta controle e repetir no mes seguinte."""
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QVBoxLayout, QWidget)

from ..core import finance as fin
from ..core.auth import COMPLETO
from . import estilo as E
from .base import (BitBtn, Campo, CampoData, CampoValor, ComboDados, ComboLookup, FormBase, Grade, RadioGrupo, SpeedButton,
                   confirmar, executar, icone, msg_aviso, msg_info, rotulo)

PERIODICIDADES = [('Diária', 'diaria'), ('Semanal', 'semanal'), ('Quinzenal', 'quinzenal'), ('Mensal', 'mensal'),
                  ('Bimestral', 'bimestral'), ('Trimestral', 'trimestral'), ('Semestral', 'semestral'), ('Anual', 'anual')]


def _bt_confirma(parent, texto='&Confirma'):
    b = BitBtn(texto, icone('fa6s.check', '#1a7f37'), parent, dica='Grava os dados acima digitados')
    b.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
    b.setDefault(True)
    return b


def _bt_cancela(parent, dica='Cancela as inserções/ alterações'):
    b = BitBtn('Ca&ncela', icone('fa6s.xmark', '#b02a2a'), parent, dica=dica)
    b.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
    return b


def _rot(texto, parent, x, y, px=12, nome='Arial', negrito=False, cor='#000000'):
    l = rotulo(texto, parent, px=px, nome=nome, cor=cor, negrito=negrito)
    l.move(x, y)
    l.adjustSize()
    return l


def _por(w, parent, x, y, larg, alt):
    w.setParent(parent)
    w.setGeometry(x, y, larg, alt)
    return w


class FormLancamento(FormBase):
    """FMovCad: inclusao/alteracao de despesa ou receita."""

    def __init__(self, ctrl, tipo, lanc=None):
        s = ctrl.s
        emp = s.empresa()
        self.usa_centro = bool(emp['usa_centro_custo'])
        dy = 47 if self.usa_centro else 0
        super().__init__(ctrl.j, 'Despesa' if tipo == 'D' else 'Receita', 506, 509 + dy)
        self.ctrl, self.s, self.tipo, self.lanc = ctrl, s, tipo, lanc or {}
        self.leitura = s.nivel_tipo(tipo) < COMPLETO
        tit = QLabel('Despesas' if tipo == 'D' else 'Receitas', self)
        tit.setFont(E.fonte('Segoe UI Semibold', 27, negrito=True))
        tit.setStyleSheet(f'color: {E.NAVY};')
        tit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tit.setGeometry(3, 3, 495, 40)
        ic = QLabel(self)
        ic.setPixmap(icone('fa6s.arrow-trend-down' if tipo == 'D' else 'fa6s.arrow-trend-up', '#b02a2a' if tipo == 'D' else '#1a7f37').pixmap(30, 30))
        ic.move(12, 8)
        p = QFrame(self)
        p.setGeometry(8, 51, 490, 450 + dy)
        p.setStyleSheet(f'QFrame#fundo2 {{ background: {E.CONTA_CONTROLE}; border: 1px solid #7f9db9; }}')
        p.setObjectName('fundo2')
        # linha 1: conta / documento / data
        _rot('Conta', p, 25, 15)
        self.cb_conta = _por(ComboDados(px=15), p, 26, 31, 153, 27)
        self.cb_conta.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cb_conta.customContextMenuRequested.connect(self._menu_conta)
        self.cb_conta.setToolTip('Clique com o botão direito para criar nova conta bancária')
        _rot('Documento', p, 196, 16)
        self.ed_doc = _por(Campo(opcional=True), p, 200, 30, 121, 29)
        self.ed_doc.setToolTip(' *  Campo opcional para cadastro de nota fiscal,\n     número de ordem de serviço, número de pedido, etc.')
        _rot('Data movimento', p, 333, 17)
        self.ed_dat = _por(CampoData(), p, 327, 30, 136, 29)
        self.ed_dat.setToolTip(' *  Data de processamento do movimento')
        bt_upd = SpeedButton('', icone('fa6s.clock-rotate-left', '#333'), p, dica='Controle de atualizações')
        bt_upd.setGeometry(463, 1, 24, 24)
        bt_upd.clicked.connect(self._controle_atualizacoes)
        # descricao / pessoa / centro
        _rot('Descrição', p, 25, 66)
        self.ed_des = _por(ComboLookup(), p, 26, 82, 437, 29)
        _rot('Fornecedor' if tipo == 'D' else 'Cliente', p, 26, 113)
        self.ed_pes = _por(ComboLookup(), p, 25, 129, 437, 29)
        if self.usa_centro:
            _rot('Centro de custo' if tipo == 'D' else 'Centro de lucro', p, 26, 162)
            self.cb_cen = _por(ComboDados(px=15), p, 25, 176, 409, 29)
            bt_cen = SpeedButton('', icone('fa6s.plus', '#1a7f37'), p, dica='Incluir novo centro de custo')
            bt_cen.setGeometry(439, 178, 24, 25)
            bt_cen.clicked.connect(self._novo_centro)
        else:
            self.cb_cen = None
        # valor / situacao
        _rot('Valor', p, 26, 162 + dy)
        self.ed_val = _por(CampoValor(), p, 25, 176 + dy, 111, 29)
        bt_calc = SpeedButton('', icone('fa6s.calculator', '#333'), p, dica='Calculadora')
        bt_calc.setGeometry(142, 178 + dy, 28, 25)
        bt_calc.clicked.connect(self._calculadora)
        self.rg_sit = RadioGrupo('Situação', [('Pago' if tipo == 'D' else 'Recebido', 'V'), ('À pagar' if tipo == 'D' else 'À receber', 'P')], p)
        self.rg_sit.setStyleSheet(f'QGroupBox {{ color: {E.NAVY}; }}')
        self.rg_sit.setGeometry(224, 162 + dy, 239, 50)
        # vencimento/pgto
        self.lb_ven = _rot('Vencimento/Pgto.', p, 25, 211 + dy)
        self.ed_ven = _por(CampoData(), p, 25, 228 + dy, 136, 29)
        self.lb_ven2 = _rot('Vencimento', p, 224, 211 + dy)
        self.ed_ven2 = _por(CampoData(px=15), p, 224, 230 + dy, 136, 27)
        _rot('Observações(Cheque,banco, etc)', p, 25, 263 + dy)
        self.ed_obs = _por(Campo(opcional=True), p, 25, 278 + dy, 438, 29)
        if self.lanc.get('grupo'):
            _rot(f"Parcela {self.lanc['parcela']} de {self.lanc['total_parcelas']}", p, 25, 313 + dy, px=12, cor='#102a43', negrito=True)
        ln = QFrame(p)
        ln.setFrameShape(QFrame.HLine)
        ln.setFrameShadow(QFrame.Sunken)
        ln.setGeometry(26, 337 + dy, 437, 2)
        self.bt_can = _por(_bt_cancela(None), p, 26, 361 + dy, 97, 39)
        self.bt_ok = _por(_bt_confirma(None), p, 129, 361 + dy, 154, 39)
        if self.leitura:
            self.bt_ok.hide()
            self.bt_can.setText('&Fechar')
            self.setWindowTitle(self.windowTitle() + ' — somente consulta')
        self.bt_can.clicked.connect(self.reject)
        self.bt_ok.clicked.connect(self.confirmar)
        self.rg_sit.mudou.connect(self._sit_mudou)
        self.ed_dat.dateChanged.connect(self._dat_mudou)
        self._carregar()
        if self.leitura:
            for w in (self.cb_conta, self.ed_doc, self.ed_dat, self.ed_des, self.ed_pes, self.ed_val, self.ed_ven, self.ed_ven2, self.ed_obs, self.cb_cen, self.rg_sit):
                if w is not None:
                    w.setEnabled(False)

    def _carregar(self):
        s, l = self.s, self.lanc
        self.cb_conta.clear()
        self.cb_conta.adicionar('', None)
        for c in s.listar('contas'):
            if c['ativa'] or c['id'] == l.get('conta_id'):
                self.cb_conta.adicionar(c['descricao'], c['id'])
        self.ed_des.definir_itens(s.itens_descricoes(self.tipo))
        self.ed_pes.definir_itens([p['nome'] for p in s.listar('pessoas', tipo='F' if self.tipo == 'D' else 'C')])
        if self.cb_cen is not None:
            self._carregar_centros()
        if l:
            self.cb_conta.definir(l.get('conta_id'))
            self.ed_doc.definir(l.get('documento'))
            self.ed_dat.definir(l.get('data_mov'))
            self.ed_des.definir(l.get('descricao'))
            self.ed_pes.definir(l.get('pessoa'))
            self.ed_val.definir(l.get('valor'))
            self.ed_obs.definir(l.get('observacao'))
            self.rg_sit.definir(l.get('situacao'))
            if l.get('situacao') == 'V':
                self.ed_ven.definir(l.get('data_pagamento') or l.get('vencimento'))
                self.ed_ven2.definir(l.get('vencimento'))
            else:
                self.ed_ven.definir(l.get('vencimento'))
                self.ed_ven2.definir(l.get('vencimento'))
            if self.cb_cen is not None:
                self.cb_cen.definir(l.get('centro_id'))
        else:
            self.rg_sit.definir('P')
            cfg = s.config()
            contas = [self.cb_conta.itemData(i) for i in range(1, self.cb_conta.count())]
            if cfg['conta_padrao'] and int(cfg['conta_padrao']) in contas:
                self.cb_conta.definir(int(cfg['conta_padrao']))
            elif len(contas) == 1:
                self.cb_conta.setCurrentIndex(1)
        self._sit_mudou(self.rg_sit.valor())
        foco = {'conta': self.cb_conta, 'documento': self.ed_doc, 'data': self.ed_dat}.get(s.config('campo_inicial'), self.ed_des)
        foco.setFocus()

    def _carregar_centros(self, selecionar=None):
        self.cb_cen.clear()
        self.cb_cen.adicionar('', None)
        for c in self.s.listar('centros'):
            if (c['aplica_despesa'] if self.tipo == 'D' else c['aplica_receita']) or c['id'] == self.lanc.get('centro_id'):
                self.cb_cen.adicionar(c['nome'], c['id'])
        if selecionar:
            self.cb_cen.definir(selecionar)

    def _sit_mudou(self, sit):
        pago = sit == 'V'
        self.lb_ven.setText('Data do pagamento' if pago and self.tipo == 'D' else 'Data do recebimento' if pago else 'Vencimento')
        self.lb_ven.adjustSize()
        self.lb_ven2.setVisible(pago)
        self.ed_ven2.setVisible(pago)
        if pago and not self.lanc.get('data_pagamento'):
            self.ed_ven2.setDate(self.ed_ven.date())
            self.ed_ven.setDate(QDate.currentDate())

    def _dat_mudou(self, d):
        if not self.lanc and self.rg_sit.valor() == 'P' and self.ed_ven.date() < d:
            self.ed_ven.setDate(d)

    def _menu_conta(self, pos):
        m = QMenu(self)
        m.addAction(icone('fa6s.building-columns'), 'Criar nova conta bancária', self._nova_conta)
        m.exec(self.cb_conta.mapToGlobal(pos))

    def _nova_conta(self):
        novo = self.ctrl.j.cad.form_conta()
        if novo:
            self._carregar()
            self.cb_conta.definir(novo)

    def _novo_centro(self):
        novo = self.ctrl.j.cad.form_centro()
        if novo:
            self._carregar_centros(novo)

    def _calculadora(self):
        from .ferramentas import Calculadora
        c = Calculadora(self, self.ed_val.valor())
        if c.exec() and c.resultado is not None:
            self.ed_val.definir(abs(c.resultado))

    def _controle_atualizacoes(self):
        l = self.lanc
        if not l:
            msg_info(self, 'Lançamento ainda não gravado.', 'Controle de atualizações')
            return
        msg_info(self, f"Incluído em: {fin.br(l['criado_em'][:10])} {l['criado_em'][11:16]}\n"
                       f"Última alteração: {(fin.br(l['alterado_em'][:10]) + ' ' + l['alterado_em'][11:16]) if l.get('alterado_em') else '—'}",
                 'Controle de atualizações')

    def dados(self):
        sit = self.rg_sit.valor()
        d = {'tipo': self.tipo, 'data_mov': self.ed_dat.valor(), 'documento': self.ed_doc.valor(), 'descricao': self.ed_des.valor(),
             'pessoa': self.ed_pes.valor() or None, 'valor': self.ed_val.valor(), 'situacao': sit, 'observacao': self.ed_obs.valor(),
             'conta_id': self.cb_conta.valor(), 'centro_id': self.cb_cen.valor() if self.cb_cen is not None else self.lanc.get('centro_id')}
        if sit == 'V':
            d['data_pagamento'] = self.ed_ven.valor()
            d['vencimento'] = self.ed_ven2.valor() or self.ed_ven.valor()
        else:
            d['vencimento'] = self.ed_ven.valor()
        return d

    def confirmar(self):
        d = self.dados()
        if executar(self, lambda senha: self.s.salvar_lancamento(d, self.lanc.get('id'), senha=senha)):
            self.accept()


class FormParcelamento(FormBase):
    """FMulCad: inserir multiplas despesas/receitas (parcelamento)."""

    def __init__(self, ctrl, tipo):
        s = ctrl.s
        self.usa_centro = bool(s.empresa()['usa_centro_custo'])
        dy = 47 if self.usa_centro else 0
        super().__init__(ctrl.j, f"Inserir múltiplas {'despesas' if tipo == 'D' else 'receitas'} (parcelamento)", 503, 438 + dy)
        self.ctrl, self.s, self.tipo = ctrl, s, tipo
        tit = QLabel('Despesas' if tipo == 'D' else 'Receitas', self)
        tit.setFont(E.fonte('Arial Rounded MT Bold', 27))
        tit.setStyleSheet(f'color: {E.NAVY};')
        tit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tit.setGeometry(3, 3, 492, 36)
        p = QFrame(self)
        p.setGeometry(8, 46, 487, 384 + dy)
        p.setStyleSheet('QFrame#fundo2 { border: 1px solid #a0a0a0; }')
        p.setObjectName('fundo2')
        rb = lambda t, x, y: _rot(t, p, x, y, negrito=True)
        rb('Conta', 25, 17)
        self.cb_conta = _por(ComboDados(px=15), p, 26, 30, 146, 26)
        rb('Documento', 199, 17)
        self.ed_doc = _por(Campo(opcional=True, px=15), p, 199, 30, 116, 26)
        rb('Data movimento', 336, 17)
        self.ed_dat = _por(CampoData(px=15), p, 330, 30, 133, 26)
        rb('Descrição', 25, 68)
        self.ed_des = _por(ComboLookup(px=15), p, 25, 84, 437, 26)
        rb('Fornecedor' if tipo == 'D' else 'Cliente', 25, 116)
        self.ed_pes = _por(ComboLookup(px=15), p, 25, 132, 437, 26)
        if self.usa_centro:
            rb('Centro de custo' if tipo == 'D' else 'Centro de lucro', 26, 164)
            self.cb_cen = _por(ComboDados(px=15), p, 25, 178, 410, 26)
            bc = SpeedButton('', icone('fa6s.plus', '#1a7f37'), p, dica='Incluir novo centro de custo')
            bc.setGeometry(440, 179, 23, 23)
            bc.clicked.connect(lambda: (lambda n: n and self._centros(n))(ctrl.j.cad.form_centro()))
        else:
            self.cb_cen = None
        rb('Valor da parcela', 25, 164 + dy)
        self.ed_val = _por(CampoValor(px=15), p, 25, 178 + dy, 114, 26)
        rb('1º Vencimento', 200, 164 + dy)
        self.ed_ven = _por(CampoData(px=15), p, 197, 178 + dy, 150, 26)
        rb('Nº Parcelas', 372, 164 + dy)
        self.ed_par = _por(Campo(px=15), p, 373, 178 + dy, 91, 26)
        self.ed_par.setText('2')
        rb('Observações', 25, 216 + dy)
        self.ed_obs = _por(Campo(opcional=True, px=15), p, 26, 231 + dy, 438, 26)
        rb('Periodicidade', 25, 259 + dy)
        self.cb_per = _por(ComboDados(px=15, opcoes=PERIODICIDADES), p, 25, 273 + dy, 161, 26)
        self.cb_per.definir('mensal')
        self.ck_mov = QCheckBox('Data de movimento igual a data de vencimento', p)
        self.ck_mov.setFont(E.fonte('Arial', 12))
        self.ck_mov.setStyleSheet(f'color: {E.NAVY};')
        self.ck_mov.setGeometry(192, 272 + dy, 284, 22)
        ln = QFrame(p)
        ln.setFrameShape(QFrame.HLine)
        ln.setFrameShadow(QFrame.Sunken)
        ln.setGeometry(25, 306 + dy, 438, 2)
        self.lb_resumo = _rot('', p, 260, 325 + dy, px=12, nome='Segoe UI', cor='#102a43', negrito=True)
        _por(_bt_cancela(None, 'Cancela tudo o que foi inserido/alterado'), p, 25, 315 + dy, 110, 35).clicked.connect(self.reject)
        _por(_bt_confirma(None), p, 141, 314 + dy, 110, 35).clicked.connect(self.confirmar)
        self.cb_conta.adicionar('', None)
        for c in s.listar('contas'):
            if c['ativa']:
                self.cb_conta.adicionar(c['descricao'], c['id'])
        self.ed_des.definir_itens(s.itens_descricoes(tipo))
        self.ed_pes.definir_itens([x['nome'] for x in s.listar('pessoas', tipo='F' if tipo == 'D' else 'C')])
        if self.cb_cen is not None:
            self._centros()
        for w in (self.ed_val, self.ed_par):
            w.textChanged.connect(self._resumo)
        self._resumo()

    def _centros(self, sel=None):
        self.cb_cen.clear()
        self.cb_cen.adicionar('', None)
        for c in self.s.listar('centros'):
            if c['aplica_despesa'] if self.tipo == 'D' else c['aplica_receita']:
                self.cb_cen.adicionar(c['nome'], c['id'])
        if sel:
            self.cb_cen.definir(sel)

    def _resumo(self):
        try:
            n = int(self.ed_par.text() or 0)
        except ValueError:
            n = 0
        v = self.ed_val.valor() or 0
        self.lb_resumo.setText(f'Total: {fin.moeda(n * v)}' if n and v else '')
        self.lb_resumo.adjustSize()

    def confirmar(self):
        d = {'tipo': self.tipo, 'data_mov': self.ed_dat.valor(), 'documento': self.ed_doc.valor(), 'descricao': self.ed_des.valor(),
             'pessoa': self.ed_pes.valor() or None, 'valor': self.ed_val.valor(), 'vencimento': self.ed_ven.valor(),
             'parcelas': self.ed_par.text(), 'periodicidade': self.cb_per.valor(), 'mov_igual_vencimento': self.ck_mov.isChecked(),
             'observacao': self.ed_obs.valor(), 'conta_id': self.cb_conta.valor(), 'centro_id': self.cb_cen.valor() if self.cb_cen is not None else None}
        ids = executar(self, lambda senha: self.s.parcelar(d, senha=senha))
        if ids:
            msg_info(self, f'{len(ids)} parcela(s) incluída(s).')
            self.accept()


class FormBaixa(FormBase):
    """FBaixa: baixa de um lancamento em aberto."""

    def __init__(self, ctrl, l):
        super().__init__(ctrl.j, 'Baixar pagamento' if l['tipo'] == 'D' else 'Baixar recebimento', 345, 320, cor=E.FUNDO_CADASTRO)
        self.s, self.l = ctrl.s, l
        _rot('Descrição', self, 15, 6, px=11, nome='Verdana')
        t1 = QLabel(l['descricao'], self)
        t1.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True, sublinhado=True))
        t1.setAlignment(Qt.AlignCenter)
        t1.setGeometry(15, 20, 316, 18)
        _rot('Pessoa', self, 15, 43, px=11, nome='Verdana')
        t2 = QLabel(l.get('pessoa') or '—', self)
        t2.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True, sublinhado=True))
        t2.setAlignment(Qt.AlignCenter)
        t2.setGeometry(15, 57, 316, 18)
        ln = QFrame(self)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(15, 83, 311, 2)
        _rot('Conta', self, 15, 91, px=13, nome='Segoe UI')
        self.cb_conta = _por(ComboDados(px=15), self, 15, 111, 180, 26)
        for c in self.s.listar('contas'):
            if c['ativa'] or c['id'] == l.get('conta_id'):
                self.cb_conta.adicionar(c['descricao'], c['id'])
        self.cb_conta.definir(l.get('conta_id'))
        venc = QLabel(f"Vencimento: {fin.br(l['vencimento'])}", self)
        venc.setFont(E.fonte('Segoe UI', 12))
        venc.setGeometry(205, 115, 125, 18)
        _rot('Valor', self, 15, 142, px=13, nome='Segoe UI')
        self.ed_val = _por(CampoValor(px=15), self, 15, 161, 104, 28)
        self.ed_val.definir(l['valor'])
        bc = SpeedButton('', icone('fa6s.calculator', '#333'), self, dica='Calculadora')
        bc.setGeometry(120, 162, 24, 26)
        bc.clicked.connect(self._calc)
        _rot('Pagamento' if l['tipo'] == 'D' else 'Recebimento', self, 241, 142, px=13, nome='Segoe UI')
        self.ed_dt = _por(CampoData(px=15), self, 205, 160, 122, 28)
        _rot('Observações(Cheque,banco, etc)', self, 15, 200, px=13, nome='Segoe UI')
        self.ed_obs = _por(Campo(opcional=True, px=15), self, 15, 219, 311, 28)
        self.ed_obs.definir(l.get('observacao'))
        ln2 = QFrame(self)
        ln2.setFrameShape(QFrame.HLine)
        ln2.setGeometry(15, 255, 311, 2)
        _por(_bt_cancela(None), self, 15, 269, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 118, 269, 113, 39).clicked.connect(self.confirmar)

    def _calc(self):
        from .ferramentas import Calculadora
        c = Calculadora(self, self.ed_val.valor())
        if c.exec() and c.resultado is not None:
            self.ed_val.definir(abs(c.resultado))

    def confirmar(self):
        d = {'data_pagamento': self.ed_dt.valor(), 'valor': self.ed_val.valor(), 'conta_id': self.cb_conta.valor(), 'observacao': self.ed_obs.valor()}
        if executar(self, lambda senha: self.s.baixar([self.l['id']], d, senha=senha)):
            self.accept()


class FormBaixaMultipla(FormBase):
    """FBaixaMult: baixa de todos os lancamentos em aberto exibidos (filtro por pessoa e vencimento)."""

    def __init__(self, ctrl, tipo, ids=None):
        super().__init__(ctrl.j, 'Baixa múltipla', 421, 574, cor=E.FUNDO_CADASTRO)
        self.s, self.tipo, self.ids = ctrl.s, tipo, ids
        _rot('Fornecedor' if tipo == 'D' else 'Cliente', self, 16, 21, px=12, nome='MS Sans Serif')
        self.cb_pes = _por(QComboBox(), self, 16, 38, 369, 24)
        self.cb_pes.addItem('(Todos)', None)
        for nome in sorted({l['pessoa'] for l in self._abertos() if l.get('pessoa')}, key=str.lower):
            self.cb_pes.addItem(nome, nome)
        g = QGroupBox(' Vencimento: ', self)
        g.setGeometry(16, 72, 368, 60)
        _rot('Entre', g, 8, 27, px=12, nome='MS Sans Serif')
        self.ed_i = _por(CampoData(px=12), g, 44, 22, 110, 24)
        _rot('a', g, 160, 27, px=12, nome='MS Sans Serif')
        self.ed_f = _por(CampoData(px=12), g, 176, 22, 110, 24)
        self.ed_i.setDate(QDate(2000, 1, 1))
        self.ed_f.setDate(QDate.currentDate().addMonths(1))
        if ids:
            self.cb_pes.setEnabled(False)
            g.setEnabled(False)
            _rot(f'{len(ids)} lançamento(s) selecionado(s) na tela principal', self, 16, 4, px=12, nome='Segoe UI', cor=E.NAVY, negrito=True)
        cols = [('vencimento', 'Vencimento', 80, 'data'), ('descricao', 'Descrição', 120), ('pessoa', 'Nome', 100),
                ('documento', 'Doc.', 60), ('valor', 'Valor', 80, 'moeda')]
        self.grade = Grade(cols, self, px=12, multi=True)
        self.grade.setFont(E.fonte('Arial', 12))
        self.grade.setGeometry(0, 146, 421, 300)
        self.grade.setToolTip('Selecione linhas e pressione Delete para retirá-las da baixa')
        base = QFrame(self)
        base.setGeometry(0, 446, 421, 128)
        _rot('Total a ser baixado:', base, 80, 6, px=12, negrito=True)
        self.lb_tot = _rot('', base, 217, 7, px=12, negrito=True, cor='#ff0000')
        _rot('Conta a ser movimentada', base, 80, 27, px=12, nome='MS Sans Serif')
        self.cb_conta = _por(ComboDados(px=14), base, 80, 43, 200, 26)
        self.cb_conta.adicionar('(manter a conta de cada lançamento)', None)
        for c in self.s.listar('contas'):
            if c['ativa']:
                self.cb_conta.adicionar(c['descricao'], c['id'])
        _rot('Data da baixa:', base, 293, 27, px=12, nome='MS Sans Serif')
        self.ed_dt = _por(CampoData(px=14), base, 290, 42, 118, 26)
        ln = QFrame(base)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(80, 75, 330, 1)
        bt = SpeedButton('Bai&xar todas', icone('fa6s.list-check', E.NAVY), base, dica='Baixa todos os lançamentos que estão sendo exibidos')
        bt.setFont(E.fonte('Tahoma', 12, negrito=True))
        bt.setStyleSheet(f'QToolButton {{ color: {E.NAVY}; border: 1px solid #adadad; background: #f3f3f3; }}')
        bt.setGeometry(275, 82, 135, 32)
        bt.clicked.connect(self.confirmar)
        fechar = SpeedButton('&Fechar', icone('fa6s.xmark', '#b02a2a'), base)
        fechar.setGeometry(150, 82, 110, 32)
        fechar.clicked.connect(self.reject)
        for w in (self.ed_i, self.ed_f):
            w.dateChanged.connect(lambda _d: self.filtrar())
        self.cb_pes.currentIndexChanged.connect(lambda _i: self.filtrar())
        self.grade.keyPressEvent = self._tecla
        self.removidos = set()
        self.filtrar()

    def _abertos(self):
        return self.s.listar_lancamentos(tipo=self.tipo, situacao='P', ordem='vencimento')

    def filtrar(self):
        ls = self._abertos()
        if self.ids:
            ls = [l for l in ls if l['id'] in self.ids]
        else:
            pes = self.cb_pes.currentData()
            de, ate = self.ed_i.valor(), self.ed_f.valor()
            ls = [l for l in ls if (not pes or l.get('pessoa') == pes) and de <= l['vencimento'] <= ate]
        ls = [l for l in ls if l['id'] not in self.removidos]
        self.grade.definir(ls, manter=False)
        self.lb_tot.setText(f"{fin.moeda(sum(l['valor'] for l in ls))}  ({len(ls)})")
        self.lb_tot.adjustSize()

    def _tecla(self, ev):
        if ev.key() == Qt.Key_Delete:
            for l in self.grade.selecionados():
                self.removidos.add(l['id'])
            self.filtrar()
        else:
            Grade.keyPressEvent(self.grade, ev)

    def confirmar(self):
        ls = self.grade.modelo.linhas
        if not ls:
            msg_aviso(self, 'Nenhum lançamento em aberto a baixar.')
            return
        if not confirmar(self, f"Baixar {len(ls)} lançamento(s), total {fin.moeda(sum(l['valor'] for l in ls))}?"):
            return
        d = {'data_pagamento': self.ed_dt.valor(), 'conta_id': self.cb_conta.valor()}
        n = executar(self, lambda senha: self.s.baixar([l['id'] for l in ls], d, senha=senha))
        if n:
            msg_info(self, f'{n} lançamento(s) baixado(s).')
            self.accept()


class FormExcluirParcelas(FormBase):
    """FMultDelMov: exclusao de lancamento parcelado."""

    def __init__(self, ctrl, l):
        super().__init__(ctrl.j, 'Excluir lançamento', 647, 471)
        self.s, self.l = ctrl.s, l
        v = QVBoxLayout(self)
        lb = QLabel(f"<b>{l['descricao']}</b>{' — ' + l['pessoa'] if l.get('pessoa') else ''}<br>"
                    f"Este lançamento é a parcela {l['parcela']} de {l['total_parcelas']}. Demais parcelas do grupo:")
        lb.setFont(E.fonte('Arial', 15))
        lb.setFixedHeight(56)
        v.addWidget(lb)
        grade = Grade([('parcela', 'Parc.', 50), ('vencimento', 'Vencimento', 100, 'data'), ('valor', 'Valor', 100, 'moeda'),
                       ('situacao_desc', 'Situação', 100), ('documento', 'Documento', 120), ('observacao', 'Observação', 150)], px=13, ordenar=False)
        grade.setFont(E.fonte('Arial', 14))
        grade.definir([x for x in self.s.listar_lancamentos(tipo=l['tipo'], ordem='vencimento') if x.get('grupo') == l['grupo']])
        v.addWidget(grade, 1)
        self.rg = RadioGrupo('Escolha uma opção abaixo:', [('Excluir somente o registro anteriormente selecionado', 'esta'),
                                                          ('Excluir esta e as parcelas seguintes', 'seguintes'),
                                                          ('Excluir todas a parcelas em aberto', 'abertas'),
                                                          ('Excluir todos os registros em aberto ou pagos.', 'todas')], colunas=1, px=15)
        self.rg.definir('esta')
        v.addWidget(self.rg)
        h = QHBoxLayout()
        h.addStretch()
        b1 = _bt_cancela(None)
        b2 = BitBtn('Excluir', icone('fa6s.trash-can', '#b02a2a'), dica='Excluir os registros conforme a opção escolhida')
        b2.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
        for b in (b1, b2):
            b.setFixedSize(105, 33)
            h.addWidget(b)
        v.addLayout(h)
        b1.clicked.connect(self.reject)
        b2.clicked.connect(self.confirmar)

    def confirmar(self):
        modo = self.rg.valor()
        n = executar(self, lambda senha: self.s.excluir(self.l['id'], modo, senha=senha))
        if n:
            msg_info(self, f'{n} lançamento(s) excluído(s). Podem ser restaurados em Ferramentas › Registros excluídos.')
            self.accept()


class FormLocalizar(FormBase):
    """FPesM: localizar movimento."""

    def __init__(self, ctrl, tipo):
        super().__init__(ctrl.j, f"Localizar {'despesas' if tipo == 'D' else 'receitas'}", 620, 470, cor=E.FUNDO_CADASTRO)
        self.ctrl, self.s, self.tipo = ctrl, ctrl.s, tipo
        g = QGroupBox('Localizar', self)
        g.setFont(E.fonte('Verdana', 12))
        g.setGeometry(0, 0, 620, 265)
        _rot('Digite uma palavra ou expressão à pesquisar:', g, 16, 24, px=12, nome='Verdana')
        self.ed = _por(QLineEdit(), g, 16, 40, 422, 24)
        self.ed.setFont(E.fonte('Verdana', 12, negrito=True))
        self.ed.setStyleSheet(f'color: {E.NAVY};')
        self.rg = RadioGrupo('Localizar em', [('Todos os Campos', 'todos'), ('Somente pela Descrição', 'descricao'),
                                              ('Somente pelo Nome', 'pessoa'), ('Pelo Valor', 'valor')], g, colunas=1, px=12)
        self.rg.setGeometry(21, 68, 345, 78)
        self.rg.definir('todos')
        per = QGroupBox('Período (Data de movimento)', g)
        per.setGeometry(372, 68, 232, 71)
        self.di = _por(CampoData(px=12, vazio=True), per, 7, 27, 104, 24)
        _rot('a', per, 114, 31, px=12, nome='Verdana')
        self.df = _por(CampoData(px=12, vazio=True), per, 124, 27, 104, 24)
        _rot('Ordenar por:', g, 16, 151, px=12, nome='Verdana')
        self.cb_ord = _por(ComboDados(px=12, opcoes=[('Data de Movimento', 'data'), ('Data de Vencimento/Pagamento', 'vencimento'),
                                                     ('Documento', 'documento'), ('Descrição', 'descricao'), ('Nome', 'pessoa'),
                                                     ('Valor', 'valor'), ('Observação', 'observacao')]), g, 16, 168, 223, 24)
        _rot('Situação:', g, 245, 151, px=12, nome='Verdana')
        self.cb_sit = _por(ComboDados(px=12, opcoes=[('Pagos e em aberto', ''), ('Somente pagos', 'V'), ('Somente em aberto', 'P')]), g, 245, 168, 153, 24)
        _rot('Centro de custo', g, 404, 151, px=12, nome='Verdana')
        self.cb_cen = _por(ComboDados(px=12), g, 404, 168, 200, 24)
        self.cb_cen.adicionar('(Todos)', None)
        for c in self.s.listar('centros'):
            self.cb_cen.adicionar(c['nome'], c['id'])
        ln = QFrame(g)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(16, 205, 588, 2)
        for texto, ic, x, w, fn in (('Li&mpar', 'fa6s.eraser', 18, 130, self.limpar), ('&Fechar', 'fa6s.xmark', 154, 113, self.reject),
                                    ('&Localizar', 'fa6s.magnifying-glass', 273, 165, self.localizar)):
            b = BitBtn(texto, icone(ic, E.NAVY), g)
            b.setFont(E.fonte('Verdana', 12, negrito=True))
            b.setGeometry(x, 218, w, 34)
            b.clicked.connect(fn)
            if texto == '&Localizar':
                b.setDefault(True)
        res = QGroupBox('Resultados da pesquisa', self)
        res.setGeometry(0, 265, 620, 205)
        vl = QVBoxLayout(res)
        self.grade = Grade([('data_mov', 'Data', 80, 'data'), ('documento', 'Documento', 80), ('descricao', 'Descrição', 160),
                            ('pessoa', 'Nome', 130), ('valor', 'Valor', 80, 'moeda'), ('situacao_desc', 'Situação', 80)], px=12)
        self.grade.setFont(E.fonte('Verdana', 11))
        self.grade.ativada.connect(self.abrir)
        vl.addWidget(self.grade)
        hb = QHBoxLayout()
        b = BitBtn('&Abrir', icone('fa6s.folder-open', E.NAVY))
        b.clicked.connect(lambda: self.abrir(self.grade.atual()))
        b2 = BitBtn('Gerar Relatório', icone('fa6s.print', E.NAVY))
        b2.clicked.connect(self.relatorio)
        self.lb_n = rotulo('', px=12, nome='Segoe UI')
        for w in (b, b2):
            w.setFont(E.fonte('Verdana', 11, negrito=True))
            hb.addWidget(w)
        hb.addWidget(self.lb_n)
        hb.addStretch()
        vl.addLayout(hb)

    def limpar(self):
        self.ed.clear()
        self.di.definir(None)
        self.df.definir(None)
        self.grade.definir([], manter=False)
        self.lb_n.setText('')

    def localizar(self):
        texto = self.ed.text().strip()
        campo = self.rg.valor()
        q = {'tipo': self.tipo, 'ordem': self.cb_ord.valor(), 'situacao': self.cb_sit.valor()}
        if self.di.valor() and self.df.valor():
            q['de'], q['ate'] = self.di.valor(), self.df.valor()
        if texto:
            if campo == 'todos':
                q['busca'] = texto
            elif campo == 'valor':
                v = CampoValor()
                v.setText(texto)
                if v.valor() is None:
                    msg_aviso(self, 'Informe um valor válido.')
                    return
                q['busca_campo'], q['busca_valor'] = 'valor', v.valor()
            else:
                q['busca_campo'], q['busca_valor'] = campo, texto
        ls = self.s.listar_lancamentos(**q)
        cen = self.cb_cen.valor()
        if cen:
            ls = [l for l in ls if l.get('centro_id') == cen]
        self.resultado = ls
        self.grade.definir(ls, manter=False)
        self.lb_n.setText(f'  {len(ls)} lançamento(s) encontrado(s) — total {fin.moeda(sum(l["valor"] for l in ls))}')

    def abrir(self, l):
        if l:
            self.ctrl.j.form_lancamento(self.tipo, l['id'])
            self.localizar()

    def relatorio(self):
        ls = self.grade.modelo.linhas
        if not ls:
            msg_aviso(self, 'Faça uma pesquisa primeiro.')
            return
        rel = fin.tabela(f"Localizar {'despesas' if self.tipo == 'D' else 'receitas'}: {self.ed.text().strip() or 'todos'}",
                         f'{len(ls)} lançamento(s)',
                         [('data_mov', 'Data', 'data'), ('documento', 'Documento'), ('descricao', 'Descrição'), ('pessoa', 'Nome'),
                          ('ven_pgto', 'Vcto/Pgto', 'data'), ('situacao_desc', 'Situação'), ('observacao', 'Observação'), ('valor', 'Valor', 'moeda')],
                         ls, ['valor'])
        self.ctrl.j.relatorios.mostrar(rel)


class FormTransferirEmpresa(FormBase):
    """PPCopy: transferir lancamento para outra conta controle."""

    def __init__(self, ctrl, linhas, empresas):
        super().__init__(ctrl.j, 'Transferir lançamento para outra conta', 460, 190, cor=E.FUNDO_CADASTRO)
        self.s, self.linhas = ctrl.s, linhas
        _rot(f'{len(linhas)} lançamento(s) selecionado(s) serão movidos para:', self, 20, 18, px=13, nome='Segoe UI')
        _rot('Conta controle de destino', self, 20, 50, px=13, nome='Segoe UI')
        self.cb = _por(ComboDados(px=15, opcoes=[(e['nome'], e['id']) for e in empresas]), self, 20, 70, 420, 28)
        _por(_bt_cancela(None), self, 20, 130, 105, 39).clicked.connect(self.reject)
        b = _por(_bt_confirma(None, '&Transferir'), self, 131, 130, 140, 39)
        b.clicked.connect(self.confirmar)

    def confirmar(self):
        n = executar(self, lambda senha: self.s.transferir_empresa([l['id'] for l in self.linhas], self.cb.valor(), senha=senha))
        if n:
            msg_info(self, f'{n} lançamento(s) transferido(s).')
            self.accept()


class Lancamentos:
    """Controlador das telas de lancamento (chamado pela janela principal)."""

    def __init__(self, janela):
        self.j = janela

    @property
    def s(self):
        return self.j.s

    def formulario(self, tipo, id_=None):
        lanc = self.s.lancamento(id_) if id_ else None
        if not id_ and self.s.nivel_tipo(tipo) < COMPLETO:
            msg_aviso(self.j, 'Seu usuário tem acesso somente de consulta a este módulo.')
            return False
        return FormLancamento(self, tipo, lanc).exec() == QDialog.Accepted

    def parcelamento(self, tipo):
        return FormParcelamento(self, tipo).exec() == QDialog.Accepted

    def baixa(self, l):
        if l['situacao'] == 'V':
            msg_aviso(self.j, 'Este lançamento já está baixado.')
            return False
        return FormBaixa(self, self.s.lancamento(l['id'])).exec() == QDialog.Accepted

    def baixa_multipla(self, tipo, ids=None):
        return FormBaixaMultipla(self, tipo, ids).exec() == QDialog.Accepted

    def excluir(self, l):
        l = self.s.lancamento(l['id'])
        if l.get('grupo'):
            return FormExcluirParcelas(self, l).exec() == QDialog.Accepted
        if not confirmar(self.j, f"Confirma a exclusão de \"{l['descricao']}\" no valor de {fin.moeda(l['valor'])}?"):
            return False
        return bool(executar(self.j, lambda senha: self.s.excluir(l['id'], 'esta', senha=senha)))

    def localizar(self, tipo):
        FormLocalizar(self, tipo).exec()
        self.j.atualizar()

    def transferir_empresa(self, linhas):
        if not linhas:
            msg_aviso(self.j, 'Selecione os lançamentos.')
            return False
        outras = [e for e in self.s.empresas() if e['id'] != self.s.empresa_id]
        if not outras:
            msg_aviso(self.j, 'Cadastre outra conta controle primeiro.')
            return False
        return FormTransferirEmpresa(self, linhas, outras).exec() == QDialog.Accepted

    def repetir_mes_seguinte(self, linhas):
        """PPCopy: 'Repetir lancamento no mes seguinte' (copia em aberto, datas + 1 mes)."""
        if not linhas:
            msg_aviso(self.j, 'Selecione os lançamentos.')
            return False
        if not confirmar(self.j, f'Repetir {len(linhas)} lançamento(s) no mês seguinte (em aberto)?'):
            return False
        n = 0
        for l in linhas:
            l = self.s.lancamento(l['id'])
            novo = {k: l[k] for k in ('tipo', 'documento', 'descricao', 'pessoa', 'valor', 'observacao', 'conta_id', 'centro_id')}
            novo.update(situacao='P', data_mov=fin.soma_periodo(l['data_mov'], 1, 'mensal'), vencimento=fin.soma_periodo(l['vencimento'], 1, 'mensal'))
            if executar(self.j, lambda senha, novo=novo: self.s.salvar_lancamento(novo, senha=senha)):
                n += 1
        if n:
            msg_info(self.j, f'{n} lançamento(s) repetido(s) no mês seguinte.')
        return n > 0
