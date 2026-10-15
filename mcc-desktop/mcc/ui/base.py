"""Componentes no estilo VCL usados por todas as telas (SpeedButton, BitBtn, TDBGrid,
TRadioGroup, campos de data e valor) e utilitarios de mensagem."""
from datetime import date

import qtawesome as qta
from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QCompleter, QDateEdit, QDialog, QFrame, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QTableView,
                               QToolButton, QVBoxLayout, QWidget, QCheckBox, QPlainTextEdit, QInputDialog)

from ..core import finance as fin
from ..core.auth import AcessoNegado
from ..core.servico import Bloqueado
from .estilo import TEXTO_CAMPO, fonte


def icone(nome, cor='#1f3f73', **kw):
    return qta.icon(nome, color=cor, **kw)


def amp(texto):
    """'&' do Delphi vira atalho no Qt tambem; '&&' literal."""
    return texto


# ---------- botoes ----------

class SpeedButton(QToolButton):
    """TSpeedButton plano. topo=True: botao branco da faixa de menu."""

    def __init__(self, texto='', icone_=None, parent=None, glyph_top=False, tam_icone=16, topo=False, dica=None):
        super().__init__(parent)
        self.setText(texto)
        if icone_ is not None:
            self.setIcon(icone_)
            self.setIconSize(QSize(tam_icone, tam_icone))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon if glyph_top else
                                (Qt.ToolButtonTextBesideIcon if texto else Qt.ToolButtonIconOnly))
        self.setProperty('topo' if topo else 'speed', True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAutoRaise(True)
        if dica:
            self.setToolTip(dica)


class BitBtn(QPushButton):
    def __init__(self, texto, icone_=None, parent=None, dica=None, glyph_top=False):
        super().__init__(texto, parent)
        if icone_ is not None:
            self.setIcon(icone_)
            self.setIconSize(QSize(20 if glyph_top else 16, 20 if glyph_top else 16))
        if dica:
            self.setToolTip(dica)
        self._top = glyph_top
        self.setCursor(Qt.PointingHandCursor)


class BotaoTopo(QToolButton):
    """Botao com glifo em cima e texto embaixo (BitBtn Layout=blGlyphTop das telas de cadastro)."""

    def __init__(self, texto, icone_, parent=None, dica=None, w=79, h=65):
        super().__init__(parent)
        self.setText(texto)
        self.setIcon(icone_)
        self.setIconSize(QSize(26, 26))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setFixedSize(w, h)
        self.setFont(fonte('Segoe UI Semibold', 13, negrito=True))
        self.setStyleSheet('QToolButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fdfdfd, stop:1 #e3e3e3);'
                           ' border: 1px solid #adadad; border-radius: 2px; }'
                           'QToolButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #eaf6fd, stop:1 #bee6fd); border-color: #3c7fb1; }'
                           'QToolButton:pressed { background: #c4e5f6; } QToolButton:disabled { color: #a0a0a0; }')
        if dica:
            self.setToolTip(dica)
        self.setCursor(Qt.PointingHandCursor)


# ---------- campos ----------

def _fonte_campo(w, px=16):
    w.setFont(fonte('Segoe UI Semibold', px, negrito=True))
    pal = w.palette()
    pal.setColor(w.foregroundRole(), QColor(TEXTO_CAMPO))
    w.setPalette(pal)


class Campo(QLineEdit):
    """TDBEdit."""

    def __init__(self, parent=None, opcional=False, px=16, maximo=None):
        super().__init__(parent)
        _fonte_campo(self, px)
        if opcional:
            self.setProperty('opcional', True)
        if maximo:
            self.setMaxLength(maximo)

    def valor(self):
        return self.text().strip()

    def definir(self, v):
        self.setText('' if v is None else str(v))


class CampoValor(QLineEdit):
    """Valor monetario no formato brasileiro (1.234,56)."""

    def __init__(self, parent=None, px=16, negativo=False):
        super().__init__(parent)
        _fonte_campo(self, px)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.negativo = negativo
        self.editingFinished.connect(self._formatar)

    def valor(self):
        t = self.text().strip().replace('R$', '').replace(' ', '')
        if not t:
            return None
        if ',' in t:
            t = t.replace('.', '').replace(',', '.')
        try:
            return round(float(t), 2)
        except ValueError:
            return None

    def definir(self, v):
        self.setText('' if v in (None, '') else fin.moeda(v, simbolo=False))

    def _formatar(self):
        v = self.valor()
        if v is not None:
            self.definir(v)


class CampoData(QDateEdit):
    """TDBEdit de data com calendario (SbCalend). Aceita ficar vazio."""
    VAZIO = QDate(1900, 1, 1)

    def __init__(self, parent=None, px=16, vazio=False):
        super().__init__(parent)
        _fonte_campo(self, px)
        self.setDisplayFormat('dd/MM/yyyy')
        self.setCalendarPopup(True)
        self.setMinimumDate(self.VAZIO)
        if vazio:
            self.setSpecialValueText(' ')
            self.setDate(self.VAZIO)
        else:
            self.setDate(QDate.currentDate())

    def valor(self):
        d = self.date()
        if d == self.VAZIO:
            return None
        return d.toString('yyyy-MM-dd')

    def definir(self, iso):
        if not iso:
            self.setDate(self.VAZIO if self.specialValueText() else QDate.currentDate())
        else:
            self.setDate(QDate.fromString(str(iso)[:10], 'yyyy-MM-dd'))


class ComboLookup(QComboBox):
    """TRxLookupEdit: combo editavel com autocompletar por trecho."""

    def __init__(self, parent=None, px=16, itens=()):
        super().__init__(parent)
        _fonte_campo(self, px)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.definir_itens(itens)

    def definir_itens(self, itens):
        atual = self.currentText()
        self.clear()
        self.addItems(list(itens))
        comp = QCompleter(list(itens), self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.setCompleter(comp)
        self.setEditText(atual)

    def valor(self):
        return self.currentText().strip()

    def definir(self, v):
        self.setEditText(v or '')


class ComboDados(QComboBox):
    """Combo com um dado por item (ex.: id da conta)."""

    def __init__(self, parent=None, px=16, opcoes=()):
        super().__init__(parent)
        _fonte_campo(self, px)
        for texto, dado in opcoes:
            self.addItem(texto, dado)

    def adicionar(self, texto, dado):
        self.addItem(texto, dado)

    def valor(self):
        return self.currentData()

    def definir(self, dado):
        for i in range(self.count()):
            if self.itemData(i) == dado or (dado is not None and str(self.itemData(i)) == str(dado)):
                self.setCurrentIndex(i)
                return
        if self.count():
            self.setCurrentIndex(0)


class RadioGrupo(QGroupBox):
    """TRadioGroup / TDBRadioGroup: opcoes [(texto, valor)], em colunas."""
    mudou = Signal(object)

    def __init__(self, titulo, opcoes, parent=None, colunas=None, px=13):
        super().__init__(titulo, parent)
        self.setFont(fonte('Segoe UI Semibold', px, negrito=True))
        self.grupo = QButtonGroup(self)
        lay = QHBoxLayout(self) if (colunas or len(opcoes)) <= 3 and colunas != 1 else QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        self.valores = []
        for i, (texto, valor) in enumerate(opcoes):
            rb = QRadioButton(texto)
            rb.setFont(fonte('Segoe UI', 13))
            self.grupo.addButton(rb, i)
            lay.addWidget(rb)
            self.valores.append(valor)
        if isinstance(lay, QVBoxLayout):
            lay.addStretch()
        self.grupo.idToggled.connect(lambda i, on: on and self.mudou.emit(self.valores[i]))

    def valor(self):
        i = self.grupo.checkedId()
        return self.valores[i] if i >= 0 else None

    def definir(self, valor):
        for i, v in enumerate(self.valores):
            if str(v) == str(valor):
                self.grupo.button(i).setChecked(True)
                return


def rotulo(texto, parent=None, px=12, nome='Arial', cor='#000000', negrito=False, sublinhado=False):
    l = QLabel(texto, parent)
    l.setFont(fonte(nome, px, negrito, sublinhado))
    l.setStyleSheet(f'color: {cor}; background: transparent;')
    return l


def linha_h(parent=None):
    f = QFrame(parent)
    f.setFrameShape(QFrame.HLine)
    f.setFrameShadow(QFrame.Sunken)
    return f


# ---------- grade (TDBGrid) ----------

class ModeloTabela(QAbstractTableModel):
    """colunas: [(campo, titulo, largura, fmt)]; fmt em data|moeda|int|num|texto ou funcao."""

    def __init__(self, colunas, linhas=None, cor_linha=None):
        super().__init__()
        self.colunas = colunas
        self.linhas = linhas or []
        self.cor_linha = cor_linha

    def definir(self, linhas):
        self.beginResetModel()
        self.linhas = list(linhas)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.linhas)

    def columnCount(self, parent=QModelIndex()):
        return len(self.colunas)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return self.colunas[s][1]
        if o == Qt.Horizontal and role == Qt.TextAlignmentRole:
            fmt = self.colunas[s][3] if len(self.colunas[s]) > 3 else None
            return int((Qt.AlignRight if fmt in ('moeda', 'int', 'num') else Qt.AlignLeft) | Qt.AlignVCenter)
        return None

    @staticmethod
    def formatar(v, fmt):
        if v is None or v == '':
            return ''
        if callable(fmt):
            return fmt(v)
        if fmt == 'data':
            return fin.br(str(v))
        if fmt == 'moeda':
            return fin.moeda(v, simbolo=False)
        if fmt == 'num':
            return f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        if fmt == 'sn':
            return 'Sim' if v else 'Não'
        return str(v)

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None
        linha = self.linhas[idx.row()]
        col = self.colunas[idx.column()]
        fmt = col[3] if len(col) > 3 else None
        if role == Qt.DisplayRole:
            return self.formatar(linha.get(col[0]), fmt)
        if role == Qt.TextAlignmentRole:
            return int((Qt.AlignRight if fmt in ('moeda', 'int', 'num') else Qt.AlignLeft) | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and self.cor_linha:
            c = self.cor_linha(linha, col[0])
            return QBrush(QColor(c)) if c else None
        if role == Qt.FontRole and linha.get('_tipo'):
            return fonte('Segoe UI', 13, negrito=True)
        if role == Qt.BackgroundRole and linha.get('_tipo') == 'grupo':
            return QBrush(QColor('#e3e9f0'))
        return None

    def linha(self, i):
        return self.linhas[i] if 0 <= i < len(self.linhas) else None

    def sort(self, coluna, ordem=Qt.AscendingOrder):
        campo = self.colunas[coluna][0]
        self.layoutAboutToBeChanged.emit()
        self.linhas.sort(key=lambda r: (r.get(campo) is None, r.get(campo) if not isinstance(r.get(campo), str) else r.get(campo).lower()),
                         reverse=ordem == Qt.DescendingOrder)
        self.layoutChanged.emit()


class Grade(QTableView):
    """TDBGrid com dgRowSelect, dgTitleClick (ordena) e duplo clique."""
    ativada = Signal(dict)

    def __init__(self, colunas, parent=None, cor_linha=None, multi=False, px=13, cor_fundo=None, ordenar=True):
        super().__init__(parent)
        self.modelo = ModeloTabela(colunas, cor_linha=cor_linha)
        self.setModel(self.modelo)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection if multi else QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(px + 11)
        self.setFont(fonte('Segoe UI Semibold', px, negrito=True))
        self.horizontalHeader().setFont(fonte('Segoe UI', 13, negrito=True))
        self.horizontalHeader().setHighlightSections(False)
        self.setSortingEnabled(ordenar)
        self.setWordWrap(False)
        if cor_fundo:
            self.setStyleSheet(f'QTableView {{ background: {cor_fundo}; alternate-background-color: {cor_fundo}; }}')
        for i, c in enumerate(colunas):
            if len(c) > 2 and c[2]:
                self.setColumnWidth(i, c[2])
        self.horizontalHeader().setStretchLastSection(True)
        self.doubleClicked.connect(lambda idx: self.ativada.emit(self.modelo.linha(idx.row())))

    def definir(self, linhas, manter=True):
        ids = {r.get('id') for r in self.selecionados()} if manter else set()
        self.modelo.definir(linhas)
        if ids:
            for i, r in enumerate(self.modelo.linhas):
                if r.get('id') in ids:
                    self.selectRow(i)

    def atual(self):
        idx = self.currentIndex()
        sel = self.selectionModel().selectedRows()
        if sel:
            return self.modelo.linha(sel[0].row())
        return self.modelo.linha(idx.row()) if idx.isValid() else None

    def selecionados(self):
        return [self.modelo.linha(i.row()) for i in sorted(self.selectionModel().selectedRows(), key=lambda i: i.row())]

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and self.atual():
            self.ativada.emit(self.atual())
            return
        super().keyPressEvent(ev)


# ---------- dialogos ----------

def msg_info(parent, texto, titulo='MCC'):
    QMessageBox.information(parent, titulo, texto)


def msg_aviso(parent, texto, titulo='MCC'):
    QMessageBox.warning(parent, titulo, texto)


def msg_erro(parent, texto, titulo='MCC'):
    QMessageBox.critical(parent, titulo, texto)


def confirmar(parent, texto, titulo='Confirmação'):
    box = QMessageBox(QMessageBox.Question, titulo, texto, QMessageBox.Yes | QMessageBox.No, parent)
    box.button(QMessageBox.Yes).setText('&Sim')
    box.button(QMessageBox.No).setText('&Não')
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes


class FormBase(QDialog):
    """Janela modal de tamanho fixo, como as TForm do original (posicoes absolutas do DFM)."""

    def __init__(self, parent, titulo, largura, altura, cor=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setFixedSize(largura, altura)
        if cor:
            self.setStyleSheet(f'FormBase, QDialog {{ background: {cor}; }}')
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.reject)

    def por(self, w, x, y, larg=None, alt=None):
        w.setParent(self if w.parent() is None else w.parent())
        w.move(x, y)
        if larg and alt:
            w.resize(larg, alt)
        elif larg:
            w.resize(larg, w.sizeHint().height())
        w.show()
        return w


def pedir_senha_desbloqueio(parent, limite, incorreta=False):
    """FLokSen: 'Movimentacoes bloqueadas ate ... Deseja inserir a senha de desbloqueio?'"""
    if not incorreta and not confirmar(parent, f'Movimentações bloqueadas até {fin.br(limite)}.\nDeseja inserir a senha de desbloqueio?',
                                       'Proteção de dados'):
        return None
    dlg = QInputDialog(parent)
    dlg.setWindowTitle('Senha de desbloqueio')
    dlg.setLabelText(('Senha incorreta.\n' if incorreta else '') + 'Digite a senha do administrador:')
    dlg.setTextEchoMode(QLineEdit.Password)
    dlg.setOkButtonText('&Ok')
    dlg.setCancelButtonText('Ca&ncela')
    return dlg.textValue() if dlg.exec() else None


def executar(parent, fn, sucesso=None):
    """Executa uma operacao do servico tratando permissao, validacao e protecao de dados.
    fn recebe senha= (None na 1a tentativa). Retorna o resultado ou None se falhar/cancelar."""
    senha = None
    while True:
        try:
            r = fn(senha=senha)
            if sucesso:
                msg_info(parent, sucesso)
            return r if r is not None else True
        except Bloqueado as b:
            senha = pedir_senha_desbloqueio(parent, b.limite, b.incorreta)
            if senha is None:
                return None
        except (AcessoNegado, ValueError) as e:
            msg_aviso(parent, str(e))
            return None


def caber_na_tela(w, largura, altura):
    """Redimensiona uma janela respeitando a area util da tela (notebooks 1366x768 / 1280x720)."""
    from PySide6.QtGui import QGuiApplication
    tela = (w.screen() or QGuiApplication.primaryScreen()).availableGeometry()
    w.resize(min(largura, tela.width() - 20), min(altura, tela.height() - 50))


def hoje_qdate():
    d = date.today()
    return QDate(d.year, d.month, d.day)
