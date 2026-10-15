"""Ferramentas: lembrete de contas (FLemb), registros excluidos (FDeleteDes), protecao de
dados (FLok), banco de dados (FConfig), configuracoes da conta controle (FConfigConta),
logomarca, importacao de extrato OFX (FConcilia / FConciliaCad), calculadora, sobre."""
import ast
import operator
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QDate, QIODevice, QSettings, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPlainTextEdit, QPushButton, QStackedWidget, QTabWidget, QTextBrowser, QVBoxLayout,
                               QWidget)

from ..core import finance as fin
from ..core.auth import COMPLETO
from . import estilo as E
from .base import (BitBtn, Campo, CampoData, CampoValor, ComboDados, ComboLookup, FormBase, Grade, RadioGrupo, SpeedButton,
                   confirmar, executar, icone, msg_aviso, msg_info, rotulo)
from .lancamentos import _bt_cancela, _bt_confirma, _por, _rot


# ---------- Calculadora (TRxCalculator) ----------

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.USub: operator.neg,
        ast.UAdd: operator.pos, ast.Mod: operator.mod, ast.Pow: operator.pow}


def avaliar(expr):
    """Avalia expressao aritmetica (so numeros e + - * / % ** parenteses), sem eval."""
    expr = expr.replace(',', '.').replace('x', '*').replace('÷', '/')

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            if isinstance(n.op, ast.Pow) and abs(ev(n.right)) > 100:
                raise ValueError('expoente muito grande')
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError('expressão inválida')
    return ev(ast.parse(expr, mode='eval'))


class Calculadora(FormBase):
    def __init__(self, parent, valor=None):
        super().__init__(parent, 'Calculadora', 260, 300)
        self.resultado = None
        v = QVBoxLayout(self)
        self.ed = QLineEdit(fin.moeda(valor, simbolo=False) if valor else '')
        self.ed.setFont(E.fonte('Segoe UI', 20, negrito=True))
        self.ed.setAlignment(Qt.AlignRight)
        self.ed.returnPressed.connect(self.igual)
        v.addWidget(self.ed)
        self.lb = rotulo('', px=12, nome='Segoe UI', cor='#555')
        v.addWidget(self.lb)
        g = QGridLayout()
        teclas = ['7', '8', '9', '/', '4', '5', '6', '*', '1', '2', '3', '-', '0', ',', '=', '+']
        for i, t in enumerate(teclas):
            b = QPushButton(t)
            b.setFixedHeight(38)
            b.setFont(E.fonte('Segoe UI', 16, negrito=True))
            b.clicked.connect(lambda _=False, t=t: self.igual() if t == '=' else self.ed.insert(t))
            g.addWidget(b, i // 4, i % 4)
        v.addLayout(g)
        h = QHBoxLayout()
        bc = QPushButton('C')
        bc.clicked.connect(self.ed.clear)
        ok = QPushButton('&Ok (usar valor)')
        ok.setDefault(False)
        ok.clicked.connect(self.ok)
        h.addWidget(bc)
        h.addWidget(ok)
        v.addLayout(h)

    def igual(self):
        try:
            t = self.ed.text().replace('.', '') if ',' in self.ed.text() else self.ed.text()
            r = round(avaliar(t), 2)
            self.ed.setText(fin.moeda(r, simbolo=False).replace('.', ''))
            self.lb.setText('')
            self.resultado = r
        except (ValueError, SyntaxError, ZeroDivisionError) as e:
            self.lb.setText(f'Erro: {e}')

    def ok(self):
        self.igual()
        if self.resultado is not None:
            self.accept()


# ---------- Lembrete de contas (FLemb) ----------

class FormLembretes(FormBase):
    ADIAR = [('Na próxima execução', 0), ('Amanhã', 1), ('Na próxima semana', 7), ('Daqui quinze dias', 15), ('Daqui um mês', 30), ('Nunca', -1)]

    def __init__(self, ferr):
        super().__init__(ferr.j, 'Lembrete de contas', 685, 521, cor=E.FUNDO_CADASTRO)
        self.ferr, self.s = ferr, ferr.s
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        topo = rotulo(f"  Contas vencidas e a vencer até {fin.br((date.today() + timedelta(days=7)).isoformat())}", px=13, nome='MS Sans Serif',
                      cor=E.NAVY, sublinhado=True)
        topo.setFixedHeight(41)
        v.addWidget(topo)
        self.abas = QTabWidget()
        self.abas.setFont(E.fonte('Verdana', 13, negrito=True))
        ls = self.s.lembretes(7)
        cols = [('vencimento', 'Vencimento', 85, 'data'), ('status', 'Situação', 80), ('descricao', 'Descrição', 170), ('pessoa', 'Nome', 150),
                ('documento', 'Doc.', 70), ('valor', 'Valor', 90, 'moeda')]
        cor = lambda l, c: '#c00000' if l['status'] == 'Vencida' else None
        self.grades = {}
        for tipo, titulo in (('D', 'Contas à Pagar'), ('R', 'Contas à Receber')):
            if self.s.nivel_tipo(tipo) < 1:
                continue
            g = Grade(cols, cor_linha=cor, px=13)
            g.setFont(E.fonte('Arial', 13))
            linhas = [l for l in ls if l['tipo'] == tipo]
            g.definir(linhas)
            g.ativada.connect(lambda l, tipo=tipo: self._abrir(tipo, l))
            self.grades[tipo] = g
            self.abas.addTab(g, f'{titulo} ({len(linhas)}) — {fin.moeda(sum(x["valor"] for x in linhas))}')
        v.addWidget(self.abas, 1)
        base = QFrame()
        base.setFixedHeight(49)
        h = QHBoxLayout(base)
        h.addSpacing(30)
        h.addWidget(rotulo('Ativar lembrete novamente', px=11, nome='Verdana', cor=E.NAVY))
        self.cb = ComboDados(px=11, opcoes=self.ADIAR)
        self.cb.setFixedWidth(175)
        self.cb.definir(1)
        h.addWidget(self.cb)
        h.addSpacing(40)
        bf = BitBtn('&Fechar', icone('fa6s.xmark', '#b02a2a'))
        bf.setFixedSize(105, 30)
        bf.clicked.connect(self.accept)
        h.addWidget(bf)
        h.addStretch()
        v.addWidget(base)

    def _abrir(self, tipo, l):
        self.ferr.j.form_lancamento(tipo, l['id'])

    def done(self, r):
        dias = self.cb.valor()
        cfg = QSettings('MCC', 'MCC')
        chave = f"lembrete/{self.s.u['id']}/{self.s.empresa_id}"
        if dias == -1:
            cfg.setValue(chave, '9999-12-31')
        elif dias == 0:
            cfg.remove(chave)
        else:
            cfg.setValue(chave, (date.today() + timedelta(days=dias)).isoformat())
        super().done(r)


# ---------- Registros excluidos (FDeleteDes) ----------

class FormExcluidos(FormBase):
    def __init__(self, ferr):
        super().__init__(ferr.j, 'Registros excluidos', 757, 420)
        self.ferr, self.s = ferr, ferr.s
        p = QFrame(self)
        p.setGeometry(0, 0, 757, 81)
        _rot('Data inicial:', p, 32, 16, px=12, nome='Tahoma')
        self.di = _por(CampoData(px=15), p, 32, 35, 130, 28)
        self.di.setDate(QDate.currentDate().addMonths(-3))
        _rot('Data final:', p, 178, 16, px=12, nome='Tahoma')
        self.df = _por(CampoData(px=15), p, 178, 35, 130, 28)
        _rot('Tipo de registro:', p, 338, 16, px=12, nome='Tahoma')
        opcoes = [(t, d) for t, d in (('Despesas', 'D'), ('Receitas', 'R')) if self.s.nivel_tipo(d)]
        self.cb = _por(ComboDados(px=16, opcoes=opcoes), p, 338, 35, 205, 32)
        b = _por(QPushButton('Filtrar'), p, 557, 30, 81, 35)
        b.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
        b.clicked.connect(self.filtrar)
        self.grade = Grade([('excluido_em', 'Excluído em', 130), ('data_mov', 'Data', 85, 'data'), ('documento', 'Doc.', 80),
                            ('descricao', 'Descrição', 180), ('pessoa', 'Pessoa', 150), ('valor', 'Valor', 90, 'moeda')], self, px=12, multi=True)
        self.grade.setGeometry(0, 81, 757, 274)
        base = QFrame(self)
        base.setGeometry(0, 355, 757, 65)
        br_ = _por(BitBtn('&Restaurar selecionados', icone('fa6s.trash-arrow-up', '#1a7f37')), base, 20, 14, 210, 38)
        br_.clicked.connect(self.restaurar)
        bf = _por(BitBtn('&Fechar', icone('fa6s.xmark', '#b02a2a')), base, 240, 14, 110, 38)
        bf.clicked.connect(self.accept)
        self.filtrar()

    def filtrar(self):
        de, ate, tipo = self.di.valor(), self.df.valor(), self.cb.valor()
        self.grade.definir([l for l in self.s.excluidos() if l['tipo'] == tipo and de <= l['excluido_em'][:10] <= ate], manter=False)

    def restaurar(self):
        sel = self.grade.selecionados()
        if not sel:
            msg_aviso(self, 'Selecione os registros a restaurar.')
            return
        n = 0
        for l in sel:
            if executar(self, lambda senha, l=l: self.s.restaurar(l['id'], senha=senha)):
                n += 1
        if n:
            msg_info(self, f'{n} lançamento(s) restaurado(s).')
        self.filtrar()


# ---------- Protecao de dados (FLok) ----------

class FormProtecao(FormBase):
    def __init__(self, ferr):
        super().__init__(ferr.j, 'Proteção de dados', 340, 395, cor=E.FUNDO_CADASTRO)
        self.s = ferr.s
        memo = QPlainTextEdit(self)
        memo.setGeometry(8, 8, 323, 169)
        memo.setReadOnly(True)
        memo.setFont(E.fonte('Segoe UI', 13))
        memo.setPlainText('Esta opção permite que você possa bloquear lançamentos até uma determinada data. Com isso, os lançamentos até a '
                          'data predefinida estarão protegidos contra alterações e não poderão ser excluídos, assim como não serão '
                          'permitidas inserções de movimentação no caixa até a data informada, garantindo a manutenção de saldos do caixa '
                          'de períodos anteriores.\n\nPara alterar algo no período bloqueado será pedida a senha de um administrador.')
        atual = self.s.limite_bloqueio()
        self.rg = RadioGrupo('Definir proteção', [('&Ativado', 1), ('&Desativado', 0)], self, px=13)
        self.rg.setGeometry(8, 192, 323, 46)
        self.rg.definir(1 if atual else 0)
        g = QGroupBox(self)
        g.setGeometry(8, 253, 323, 50)
        _rot('Bloqueado até', g, 15, 16, px=13)
        self.ed = _por(CampoData(px=13), g, 104, 12, 186, 26)
        self.ed.definir(atual)
        self.rg.mudou.connect(lambda v: self.ed.setEnabled(v == 1))
        self.ed.setEnabled(bool(atual))
        _por(_bt_cancela(None), self, 115, 342, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 218, 342, 113, 39).clicked.connect(self.confirmar)

    def confirmar(self):
        ativo = self.rg.valor() == 1
        r = executar(self, lambda senha: self.s.definir_protecao(ativo, self.ed.valor()) or 'ok')
        if r:
            msg_info(self, f'Lançamentos bloqueados até {fin.br(self.ed.valor())}.' if ativo else 'Proteção de dados desativada.')
            self.accept()


# ---------- Configuracoes da conta controle (FConfigConta) ----------

class FormConfigConta(FormBase):
    def __init__(self, parent, s):
        super().__init__(parent, 'Configurações da conta controle', 466, 475)
        self.s = s
        emp = s.empresa()
        cfg = s.config()
        p = QFrame(self)
        p.setGeometry(0, 0, 466, 49)
        _rot('Conta controle:', p, 3, 3, px=13, nome='Segoe UI')
        n = QLabel(emp['nome'], p)
        n.setFont(E.fonte('Segoe UI Semibold', 15, negrito=True))
        n.setStyleSheet('background: #ffffff;')
        n.setAlignment(Qt.AlignCenter)
        n.setGeometry(3, 24, 460, 22)
        _rot('Saldo inicial em caixa:\nValor disponível no Caixa Interno:', self, 8, 70, px=13, nome='Segoe UI')
        self.caixa = next((c for c in s.listar('contas') if c['tipo'] == 'C' and c['empresa_id'] == s.empresa_id), None)
        self.ed_cx = _por(CampoValor(px=13), self, 330, 79, 118, 25)
        self.ed_cx.definir(self.caixa['saldo_inicial'] if self.caixa else 0)
        self.ck_cen = QCheckBox('&Trabalhar com centros de custo', self)
        self.ck_cen.setGeometry(11, 119, 300, 18)
        self.ck_cen.setChecked(bool(emp['usa_centro_custo']))
        self.ck_sal = QCheckBox('&Exibir saldos na tela principal', self)
        self.ck_sal.setGeometry(11, 145, 300, 18)
        self.ck_sal.setChecked(cfg['exibir_saldos'] == '1')
        _rot('A listagem de ítens de despesas e\nreceitas são específicas dos lançamentos\nrealizados nesta conta controle?', self, 8, 191, px=13, nome='Segoe UI')
        self.rg1 = RadioGrupo('', [('Sim', '1'), ('Não', '0')], self, px=13)
        self.rg1.setGeometry(260, 191, 188, 44)
        self.rg1.definir(cfg['itens_proprios'])
        _rot('Ao incluir um novo lançamento de\ndespesa ou receita, o cursor deverá\nestar posicionado no seguinte campo:', self, 8, 265, px=13, nome='Segoe UI')
        self.rg2 = RadioGrupo('', [('Conta', 'conta'), ('Documento', 'documento'), ('Data Mov.', 'data'), ('Descrição', 'descricao')], self, colunas=2, px=13)
        self.rg2.setGeometry(260, 255, 188, 80)
        from .cadastros import FormPessoa
        FormPessoa._grid_radios(self.rg2, 2)
        self.rg2.definir(cfg['campo_inicial'])
        _rot('Conta bancária padrão para a\ninclusão de despesas e receitas:', self, 15, 358, px=13, nome='Segoe UI')
        self.cb_conta = _por(ComboDados(px=13, opcoes=[('(nenhuma)', '')] + [(c['descricao'], str(c['id'])) for c in s.listar('contas') if c['ativa']]),
                             self, 260, 366, 188, 26)
        self.cb_conta.definir(cfg['conta_padrao'])
        _por(_bt_cancela(None), self, 15, 422, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 118, 422, 113, 39).clicked.connect(self.confirmar)

    def confirmar(self):
        def salvar(senha):
            s = self.s
            s.salvar('empresas', {'usa_centro_custo': int(self.ck_cen.isChecked())}, s.empresa_id)
            if self.caixa:
                s.salvar('contas', {'saldo_inicial': self.ed_cx.valor() or 0}, self.caixa['id'], senha=senha)
            elif self.ed_cx.valor():
                s.salvar('contas', {'descricao': 'CAIXA INTERNO', 'tipo': 'C', 'saldo_inicial': self.ed_cx.valor()})
            s.salvar_config({'exibir_saldos': '1' if self.ck_sal.isChecked() else '0', 'itens_proprios': self.rg1.valor(),
                             'campo_inicial': self.rg2.valor(), 'conta_padrao': self.cb_conta.valor()})
            return True
        if executar(self, salvar):
            self.accept()


# ---------- Banco de dados (FConfig) ----------

class FormBancoDados(FormBase):
    def __init__(self, ferr):
        super().__init__(ferr.j, 'Configuração do banco de dados', 560, 230)
        self.cfg = QSettings('MCC', 'MCC')
        atual = self.cfg.value('caminho_db', ferr.j.ctx.caminho_db)
        _rot('O MCC guarda os dados num arquivo SQLite. Para usar em rede, coloque o arquivo numa pasta\n'
             'compartilhada e aponte todas as estações para ele. O mesmo arquivo pode ser aberto pelo\n'
             'clone web (mcc-clone), que usa o mesmo formato.', self, 16, 12, px=12, nome='Segoe UI')
        _rot('Arquivo do banco de dados', self, 16, 72, px=13, nome='Segoe UI')
        self.ed = _por(QLineEdit(atual), self, 16, 92, 440, 28)
        b = _por(QPushButton('Procurar…'), self, 462, 92, 82, 28)
        b.clicked.connect(self.procurar)
        self.lb = _rot(f'Em uso agora: {ferr.j.ctx.caminho_db}', self, 16, 128, px=11, nome='Segoe UI', cor='#555')
        bk = _por(BitBtn('Fazer cópia de segurança', icone('fa6s.floppy-disk', E.NAVY)), self, 16, 170, 200, 39)
        bk.clicked.connect(lambda: ferr.backup(self))
        _por(_bt_cancela(None), self, 330, 170, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 433, 170, 113, 39).clicked.connect(self.confirmar)

    def procurar(self):
        caminho, _ = QFileDialog.getSaveFileName(self, 'Arquivo do banco de dados', self.ed.text(), 'Banco SQLite (*.db *.sqlite);;Todos (*)',
                                                 options=QFileDialog.DontConfirmOverwrite)
        if caminho:
            self.ed.setText(caminho)

    def confirmar(self):
        self.cfg.setValue('caminho_db', self.ed.text().strip())
        msg_info(self, 'O novo banco será usado na próxima vez que o MCC for aberto.')
        self.accept()


# ---------- Importacao de extrato OFX (FConcilia / FConciliaCad) ----------

STATUS_OFX = {'novo': 'Novo', 'em_aberto': 'Em aberto no MCC', 'conciliado': 'Já lançado', 'importado': 'Já importado'}
ACOES_OFX = {'incluir': 'Cadastrar', 'baixar': 'Baixar', 'conciliar': 'Conciliar', 'ignorar': 'Ignorar'}


class FormValidarLinha(FormBase):
    """FConciliaCad: completar a linha do extrato antes de cadastrar."""

    def __init__(self, parent, s, linha, conta_nome):
        super().__init__(parent, 'Validar lançamento', 500, 520, cor='#8fb7cf' if linha['tipo'] == 'D' else '#c0dcc0')
        self.s, self.l = s, linha
        g = QFrame(self)
        g.setGeometry(25, 15, 451, 128)
        g.setStyleSheet('QFrame { background: #f0fbff; border: 1px solid #7f9db9; } QLabel { border: 0; background: transparent; }')
        _rot('Descrição no extrato:', g, 6, 4, px=15)
        _rot(linha['descricao'], g, 6, 26, px=15, negrito=True)
        _rot('Conta bancária', g, 6, 70, px=15)
        _rot(conta_nome, g, 6, 92, px=14, negrito=True)
        _rot('Data de pagamento', g, 160, 70, px=15)
        _rot(fin.br(linha['data']), g, 160, 92, px=15, negrito=True)
        _rot('Valor', g, 320, 70, px=15)
        _rot(fin.moeda(linha['valor']), g, 320, 92, px=15, negrito=True, cor='#b02a2a' if linha['tipo'] == 'D' else '#1a7f37')
        tip = _rot('Despesa' if linha['tipo'] == 'D' else 'Receita', self, 25, 185, px=27, sublinhado=True, cor='#808080')
        _rot('Documento', self, 363, 178, px=15)
        self.ed_doc = _por(Campo(px=15, opcional=True), self, 364, 201, 113, 25)
        self.ed_doc.definir(linha.get('documento'))
        _rot('Descrição', self, 23, 235, px=15)
        self.ed_des = _por(ComboLookup(px=16), self, 23, 253, 453, 27)
        self.ed_des.definir_itens(s.itens_descricoes(linha['tipo']))
        self.ed_des.definir(linha.get('descricao_mcc') or linha['descricao'])
        _rot('Fornecedor' if linha['tipo'] == 'D' else 'Cliente', self, 23, 286, px=15)
        self.ed_pes = _por(ComboLookup(px=16), self, 24, 309, 453, 27)
        self.ed_pes.definir_itens([p['nome'] for p in s.listar('pessoas', tipo='F' if linha['tipo'] == 'D' else 'C')])
        self.ed_pes.definir(linha.get('pessoa'))
        _rot('Observações(Cheque,banco, etc)', self, 23, 342, px=15)
        self.ed_obs = _por(Campo(px=15, opcional=True), self, 23, 365, 454, 26)
        self.ed_obs.definir(linha.get('observacao') or 'Importado do extrato OFX')
        _rot('Centro de custo', self, 23, 396, px=15)
        self.cb_cen = _por(ComboDados(px=15), self, 23, 415, 454, 27)
        self.cb_cen.adicionar('', None)
        for c in s.listar('centros'):
            self.cb_cen.adicionar(c['nome'], c['id'])
        self.cb_cen.definir(linha.get('centro_id'))
        self.cb_cen.setEnabled(bool(s.empresa()['usa_centro_custo']))
        self.ignorar = False
        bi = _por(BitBtn('&Ignorar lançamento', icone('fa6s.ban', '#555')), self, 19, 471, 206, 37)
        bi.clicked.connect(self._ignorar)
        _por(BitBtn('&Fechar', icone('fa6s.xmark', '#b02a2a')), self, 231, 471, 124, 37).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 361, 471, 120, 37).clicked.connect(self.accept)

    def _ignorar(self):
        self.ignorar = True
        self.accept()

    def aplicar(self):
        if self.ignorar:
            self.l['acao'] = 'ignorar'
            return
        self.l.update(acao='incluir', descricao_mcc=self.ed_des.valor(), pessoa=self.ed_pes.valor() or None, documento=self.ed_doc.valor(),
                      observacao=self.ed_obs.valor(), centro_id=self.cb_cen.valor(), validado=True)


class FormConciliacao(FormBase):
    def __init__(self, ferr):
        super().__init__(ferr.j, 'Extrato bancário', 984, 482)
        self.ferr, self.s = ferr, ferr.s
        self.linhas = []
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.passo_lb = rotulo('', px=14, nome='Arial', cor='#3090cf', negrito=True)
        self.passo_lb.setFixedHeight(30)
        v.addWidget(self.passo_lb)
        self.paginas = QStackedWidget()
        v.addWidget(self.paginas, 1)
        # 1: conta
        p1 = QWidget()
        info = QLabel('IMPORTAR EXTRATO BANCÁRIO\n\nO MCC lê o arquivo OFX exportado pelo internet banking e compara cada linha com os '
                      'lançamentos já cadastrados:\n• linhas que correspondem a lançamentos já pagos são conciliadas;\n• linhas que correspondem '
                      'a contas em aberto podem ser baixadas;\n• as demais podem ser validadas (descrição, pessoa, centro) e cadastradas.', p1)
        info.setWordWrap(True)
        info.setFont(E.fonte('Arial', 13))
        info.setGeometry(208, 20, 560, 170)
        box = QFrame(p1)
        box.setGeometry(208, 208, 473, 129)
        box.setStyleSheet(f'QFrame {{ background: {E.CONTA_CONTROLE}; }}')
        _rot('Selecione a conta bancária:', box, 20, 10, px=15)
        self.cb_conta = _por(ComboDados(px=13, opcoes=[(c['descricao'], c['id']) for c in self.s.listar('contas') if c['ativa']]), box, 20, 32, 433, 26)
        _por(SpeedButton('&Voltar', icone('fa6s.arrow-left', '#333')), box, 20, 66, 188, 50).clicked.connect(self.reject)
        _por(BitBtn('&Avançar', icone('fa6s.arrow-right', '#1a7f37')), box, 233, 66, 220, 50).clicked.connect(lambda: self.ir(1))
        self.paginas.addWidget(p1)
        # 2: arquivo
        p2 = QWidget()
        box2 = QFrame(p2)
        box2.setGeometry(184, 96, 520, 145)
        box2.setStyleSheet(f'QFrame {{ background: {E.CONTA_CONTROLE}; }}')
        _rot('Conta bancária:', box2, 15, 50, px=15)
        self.lb_conta = _rot('', box2, 130, 50, px=15, negrito=True)
        _por(SpeedButton('&Voltar', icone('fa6s.arrow-left', '#333')), box2, 15, 95, 130, 35).clicked.connect(lambda: self.ir(0))
        _por(BitBtn('&Importar Extrato bancário OFX', icone('fa6s.file-import', E.NAVY)), box2, 151, 95, 350, 35).clicked.connect(self.importar)
        self.paginas.addWidget(p2)
        # 3: identificar
        p3 = QWidget()
        v3 = QVBoxLayout(p3)
        self.rg_filt = RadioGrupo('Filtrar', [('Todos', 'todos'), ('Novos (a validar)', 'novo'), ('Validados', 'validado'), ('Em aberto no MCC', 'em_aberto'),
                                              ('Já lançados', 'conciliado'), ('Ignorados / já importados', 'ignorar')], px=12)
        self.rg_filt.definir('todos')
        self.rg_filt.mudou.connect(lambda _v: self._mostrar())
        v3.addWidget(self.rg_filt)
        cols = [('data', 'Data', 85, 'data'), ('descricao', 'Descrição no extrato', 230), ('documento', 'Doc.', 70), ('tipo_txt', 'Tipo', 70),
                ('valor', 'Valor', 90, 'moeda'), ('status_txt', 'Situação', 120), ('acao_txt', 'Ação', 90), ('mcc', 'Lançamento no MCC', 220)]
        self.grade = Grade(cols, px=12, multi=True, cor_linha=lambda l, c: ('#b02a2a' if l['tipo'] == 'D' else '#1a7f37') if c == 'valor' else None)
        self.grade.setFont(E.fonte('Arial', 13))
        self.grade.ativada.connect(lambda l: self.validar([l]))
        self.grade.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grade.customContextMenuRequested.connect(self._menu)
        v3.addWidget(self.grade, 1)
        h3 = QHBoxLayout()
        for texto, ic, fn in (('Validar registro', 'fa6s.pen-to-square', lambda: self.validar(self.grade.selecionados())),
                              ('Cadastrar os registros validados', 'fa6s.forward', lambda: self.ir(3)), ('&Voltar', 'fa6s.arrow-left', lambda: self.ir(1))):
            b = BitBtn(texto, icone(ic, E.NAVY))
            b.setFixedHeight(43)
            b.clicked.connect(fn)
            h3.addWidget(b)
        h3.addStretch()
        v3.addLayout(h3)
        self.paginas.addWidget(p3)
        # 4: realizar
        p4 = QWidget()
        v4 = QVBoxLayout(p4)
        h4 = QHBoxLayout()
        b = BitBtn('Registrar lançamentos', icone('fa6s.check-double', '#1a7f37'))
        b.setFixedSize(250, 47)
        b.clicked.connect(self.registrar)
        bv = BitBtn('&Voltar', icone('fa6s.arrow-left', '#333'))
        bv.setFixedSize(130, 47)
        bv.clicked.connect(lambda: self.ir(2))
        self.lb_res = rotulo('', px=14, nome='Arial', negrito=True)
        h4.addWidget(b)
        h4.addWidget(bv)
        h4.addWidget(self.lb_res)
        h4.addStretch()
        v4.addLayout(h4)
        self.grade4 = Grade(cols, px=12)
        self.grade4.setFont(E.fonte('Arial', 13))
        v4.addWidget(self.grade4, 1)
        self.paginas.addWidget(p4)
        self.ir(0)

    def ir(self, i):
        titulos = ['1 de 4: Selecionar conta', '2 de 4: Selecionar arquivo', '3 de 4: Identificar lançamentos', '4 de 4: Realizar importação']
        if i == 1:
            if self.cb_conta.valor() is None:
                msg_aviso(self, 'Cadastre uma conta bancária primeiro.')
                return
            self.lb_conta.setText(self.cb_conta.currentText())
            self.lb_conta.adjustSize()
        if i == 3:
            self.grade4.definir([l for l in self.linhas if l['acao'] != 'ignorar'], manter=False)
            n = {a: sum(1 for l in self.linhas if l['acao'] == a) for a in ACOES_OFX}
            self.lb_res.setText(f"  {n['incluir']} a cadastrar, {n['baixar']} a baixar, {n['conciliar']} a conciliar, {n['ignorar']} ignorado(s)")
        self.paginas.setCurrentIndex(i)
        self.passo_lb.setText('  ' + titulos[i])

    def importar(self):
        caminho, _ = QFileDialog.getOpenFileName(self, 'Extrato bancário OFX', str(Path.home()), 'Extrato OFX (*.ofx *.OFX);;Todos (*)')
        if not caminho:
            return
        bruto = Path(caminho).read_bytes()
        try:
            texto = bruto.decode('utf-8')
        except UnicodeDecodeError:
            texto = bruto.decode('cp1252', errors='replace')
        try:
            self.linhas = self.s.analisar_ofx(self.cb_conta.valor(), texto)
        except Exception as e:  # arquivo invalido
            msg_aviso(self, f'Não foi possível ler o arquivo: {e}')
            return
        if not self.linhas:
            msg_aviso(self, 'Nenhuma transação encontrada no arquivo.')
            return
        self._mostrar()
        self.ir(2)

    def _enriquecer(self, l):
        lanc = l.get('lancamento') or {}
        return {**l, 'tipo_txt': 'Débito' if l['tipo'] == 'D' else 'Crédito', 'status_txt': ('Validado' if l.get('validado') else STATUS_OFX[l['status']]),
                'acao_txt': ACOES_OFX[l['acao']], 'mcc': (f"{lanc.get('descricao', '')} {('- ' + lanc['pessoa']) if lanc.get('pessoa') else ''}" if lanc
                                                          else (l.get('descricao_mcc') or ''))}

    def _mostrar(self):
        f = self.rg_filt.valor()
        vis = [l for l in self.linhas if f == 'todos' or (f == 'validado' and l.get('validado')) or (f == 'ignorar' and l['acao'] == 'ignorar')
               or (f not in ('validado', 'ignorar') and l['status'] == f and not l.get('validado'))]
        for l in self.linhas:
            l.update(self._enriquecer(l))
        self.grade.definir(vis, manter=False)

    def validar(self, linhas):
        for l in linhas:
            if l['status'] in ('conciliado', 'importado'):
                continue
            f = FormValidarLinha(self, self.s, l, self.cb_conta.currentText())
            if f.exec() == QDialog.Accepted:
                f.aplicar()
            else:
                break
        self._mostrar()

    def _menu(self, pos):
        sel = self.grade.selecionados()
        if not sel:
            return
        m = QMenu(self)
        m.addAction('Validar lançamento selecionado', lambda: self.validar(sel[:1]))
        m.addAction('Validar todos os lançamentos a partir do lançamento selecionado',
                    lambda: self.validar(self.grade.modelo.linhas[self.grade.modelo.linhas.index(sel[0]):]))
        m.addAction('Validar todos os lançamentos', lambda: self.validar(list(self.grade.modelo.linhas)))
        m.addSeparator()
        for acao in ('incluir', 'baixar', 'conciliar', 'ignorar'):
            m.addAction(f'Marcar como: {ACOES_OFX[acao]}', lambda acao=acao: self._marcar(sel, acao))
        m.exec(self.grade.viewport().mapToGlobal(pos))

    def _marcar(self, sel, acao):
        for l in sel:
            if acao in ('baixar', 'conciliar') and not l.get('lancamento'):
                continue
            l['acao'] = acao
        self._mostrar()

    def registrar(self):
        linhas = []
        for l in self.linhas:
            x = dict(l)
            if x['acao'] == 'incluir' and x.get('descricao_mcc'):
                x['descricao'] = x['descricao_mcc']
            linhas.append(x)
        r = executar(self, lambda senha: self.s.aplicar_ofx(self.cb_conta.valor(), linhas, senha=senha))
        if r:
            msg_info(self, f"{r['incluidos']} cadastrado(s), {r['baixados']} baixado(s), {r['conciliados']} conciliado(s).")
            self.accept()


class Ferramentas:
    def __init__(self, janela):
        self.j = janela

    @property
    def s(self):
        return self.j.s

    def lembretes(self, automatico=False):
        if automatico:
            ate = QSettings('MCC', 'MCC').value(f"lembrete/{self.s.u['id']}/{self.s.empresa_id}")
            if ate and ate > date.today().isoformat():
                return
            if not self.s.lembretes(7):
                return
        FormLembretes(self).exec()
        self.j.atualizar()

    def excluidos(self):
        FormExcluidos(self).exec()
        self.j.atualizar()

    def protecao(self):
        FormProtecao(self).exec()
        self.j.atualizar()

    def config_conta(self):
        if FormConfigConta(self.j, self.s).exec() == QDialog.Accepted:
            self.j.usar_empresa(self.s.empresa_id)

    def banco_de_dados(self):
        FormBancoDados(self).exec()

    def backup(self, parent):
        destino, _ = QFileDialog.getSaveFileName(parent, 'Cópia de segurança', str(Path.home() / f'mcc-backup-{date.today().isoformat()}.db'),
                                                 'Banco SQLite (*.db)')
        if destino:
            import sqlite3
            alvo = sqlite3.connect(destino)
            self.s.db.backup(alvo)
            alvo.close()
            msg_info(parent, f'Cópia gravada em {destino}')

    def usuarios(self):
        from .acesso import NavUsuarios
        NavUsuarios(self.j, self.s).exec()
        self.j.s.recarregar_usuario()
        self.j.aplicar_usuario()

    def alterar_senha(self):
        from .acesso import FormAlterarSenha
        FormAlterarSenha(self.j, self.s).exec()

    def logomarca(self, incluir):
        if not incluir:
            if confirmar(self.j, 'Excluir a logomarca da empresa dos relatórios?'):
                executar(self.j, lambda senha: self.s.definir_logo(None) or True, 'Logomarca excluída.')
            return
        caminho, _ = QFileDialog.getOpenFileName(self.j, 'Logomarca da empresa', str(Path.home()), 'Imagens (*.png *.jpg *.jpeg *.bmp *.gif)')
        if not caminho:
            return
        img = QImage(caminho)
        if img.isNull():
            msg_aviso(self.j, 'Imagem inválida.')
            return
        img = img.scaled(600, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, 'PNG')
        executar(self.j, lambda senha: self.s.definir_logo(bytes(ba)) or True, 'Logomarca incluída. Ela aparecerá no cabeçalho dos relatórios.')

    def conciliacao(self):
        FormConciliacao(self).exec()
        self.j.atualizar()

    def sobre(self):
        msg_info(self.j, 'MCC — controle financeiro\n\nReimplementação em Python + PySide6 do sistema MCC original,\n'
                         'com o mesmo banco de dados do clone web.\n\nÍcones: Font Awesome (via QtAwesome).', 'Sobre o MCC')

    def atalhos(self):
        msg_info(self.j, 'Insert — incluir lançamento na aba atual\nEnter / duplo clique — alterar/consultar\nF5 — atualizar\n'
                         'Ctrl+F — busca rápida\nBotão direito na grade — baixar, estornar, excluir, transferir, repetir no mês seguinte\n'
                         'Esc — fechar a janela atual', 'Comandos de função')

    def manual(self):
        dlg = FormBase(self.j, 'Manual do usuário', 760, 560)
        v = QVBoxLayout(dlg)
        t = QTextBrowser()
        readme = Path(__file__).resolve().parents[2] / 'README.md'
        t.setMarkdown(readme.read_text(encoding='utf-8') if readme.exists() else 'Manual não encontrado.')
        v.addWidget(t)
        dlg.exec()
