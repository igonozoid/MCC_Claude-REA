"""Cores, fontes e folha de estilo que reproduzem o visual do MCC original (VCL).

Cores vindas dos DFMs (TColor BGR convertido para RGB) e das cores de sistema
do Windows que o original usa (clBtnFace, clActiveCaption...).
"""
from PySide6.QtGui import QColor, QFont

# ---- cores do original ----
FAIXA_MENU = '#025780'          # ScrollMenu (barra dos botoes grandes)
CONTA_CONTROLE = '#99b4d1'      # clActiveCaption (faixa "Conta controle:")
FILTRO = '#b9d1ea'              # clGradientActiveCaption (faixa de filtros)
BTN_FACE = '#f0f0f0'            # clBtnFace
FUNDO_CADASTRO = '#c0c7e2'      # fundo das telas de cadastro (FBanBrs, FLog...)
GRADE = '#afc7c7'               # fundo da grade de lancamentos (Color=13092783)
INFO_BK = '#ffffe1'             # clInfoBk (campos opcionais)
TEXTO_FILTRO = '#2b6095'        # rotulos "Filtrar:", "Ordem:"
TEXTO_COMBO = '#204871'         # combos da faixa de filtros
TEXTO_CAMPO = '#484848'         # campos de edicao
TEXTO_LOGIN = '#00537b'         # nome do usuario / ultimo acesso
NAVY = '#000080'
MED_GRAY = '#a0a0a4'            # clMedGray

# cartoes do dashboard
CARD_PAGO = '#0074e8'
CARD_RECEBIDO = '#00aa55'
CARD_APAGAR = '#208fff'
CARD_ARECEBER = '#00c161'
DASH_LATERAL = '#e9eff8'
DASH_BOTAO = '#d2d2d2'
DASH_BOTAO_ATIVO = '#457aba'

# cores dos relatorios (menu Configuracoes > Cor dos relatorios)
CORES_RELATORIO = {
    'cinza_claro': ('Cinza claro', '#d4d0c8'),
    'branco': ('Branco', '#ffffff'),
    'cinza_escuro': ('Cinza escuro', '#808080'),
    'cream': ('Cream', '#fffbf0'),
    'azul_claro': ('Azul claro', '#a6caf0'),
    'verde_claro': ('Verde claro', '#c0dcc0'),
}

# serie dos graficos (paleta categorica validada: receitas, despesas, margem)
SERIE = {'R': '#2a78d6', 'D': '#eb6834', 'M': '#1baf7a'}

# ---- fontes ----
# Fontes do Windows usadas no original -> equivalentes disponiveis no Linux.
SUBSTITUTOS = {
    'Segoe UI': ['Segoe UI', 'Noto Sans', 'Inter', 'DejaVu Sans'],
    'Tahoma': ['Tahoma', 'DejaVu Sans', 'Verdana'],
    'MS Sans Serif': ['Microsoft Sans Serif', 'Liberation Sans', 'Arial'],
    'Arial Rounded MT Bold': ['Arial Rounded MT Bold', 'Arial'],
}


def instalar_fontes():
    for nome, subs in SUBSTITUTOS.items():
        QFont.insertSubstitutions(nome, subs)


def fonte(nome='Segoe UI', px=13, negrito=False, sublinhado=False, italico=False):
    """Font.Name/Font.Height do DFM: Height negativo = tamanho em pixels."""
    semibold = nome.endswith(' Semibold')
    f = QFont(nome.replace(' Semibold', ''))
    f.setPixelSize(px)
    if negrito:
        f.setWeight(QFont.Weight.Bold)
    elif semibold:
        f.setWeight(QFont.Weight.DemiBold)
    f.setUnderline(sublinhado)
    f.setItalic(italico)
    return f


def qcor(hexa):
    return QColor(hexa)


QSS = f"""
QDialog, QMainWindow {{ background: {BTN_FACE}; }}
QToolTip {{ background: #ffffe1; color: #000; border: 1px solid #767676; padding: 2px; }}

QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
  background: #ffffff; border: 1px solid #7a7a7a; padding: 1px 3px; selection-background-color: #0078d7;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {{ border: 1px solid #0078d7; }}
QLineEdit:read-only {{ background: #f7f7f7; }}
QLineEdit[opcional="true"] {{ background: {INFO_BK}; }}

QPushButton {{
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #fdfdfd, stop:1 #e3e3e3);
  border: 1px solid #adadad; border-radius: 2px; padding: 3px 10px;
}}
QPushButton:hover {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #eaf6fd, stop:1 #bee6fd); border-color: #3c7fb1; }}
QPushButton:pressed {{ background: #c4e5f6; border-color: #2c628b; }}
QPushButton:disabled {{ color: #a0a0a0; }}
QPushButton:default {{ border: 1px solid #3399ff; }}

QToolButton[speed="true"] {{ border: 1px solid transparent; border-radius: 2px; background: transparent; }}
QToolButton[speed="true"]:hover {{ border: 1px solid #7eb4ea; background: rgba(229, 243, 255, 0.85); }}
QToolButton[speed="true"]:pressed {{ background: #cce4f7; border-color: #569de5; }}
QToolButton[speed="true"]:disabled {{ color: #a0a0a0; }}
QToolButton[topo="true"] {{ color: #ffffff; border: 1px solid transparent; background: transparent; }}
QToolButton[topo="true"]:hover {{ border: 1px solid rgba(255,255,255,0.55); background: rgba(255,255,255,0.12); }}
QToolButton[topo="true"]:pressed, QToolButton[topo="true"]:checked {{ background: rgba(0,0,0,0.18); }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QTableView {{
  background: #ffffff; alternate-background-color: #f4f8f8; gridline-color: #d8d8d8;
  selection-background-color: #0078d7; selection-color: #ffffff; border: 1px solid #a0a0a0;
}}
QHeaderView::section {{
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #dfe6ee);
  border: 0; border-right: 1px solid #c5ccd5; border-bottom: 1px solid #a9b2bd; padding: 3px 4px;
  font-weight: bold; color: #000000;
}}
QHeaderView::section:hover {{ background: #e5f3ff; }}

QTabWidget::pane {{ border: 1px solid #8c8c8c; background: #ffffff; top: -1px; }}
QTabBar::tab {{
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f6f6f6, stop:1 #e1e1e1);
  border: 1px solid #8c8c8c; border-bottom: 0; padding: 4px 14px; margin-right: 1px;
}}
QTabBar::tab:selected {{ background: #ffffff; }}
QTabBar::tab:!selected {{ margin-top: 2px; }}

QGroupBox {{ border: 1px solid #c8c8c8; border-radius: 2px; margin-top: 9px; padding-top: 4px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 3px; }}
QMenu {{ background: #f2f2f2; border: 1px solid #979797; padding: 2px; }}
QMenu::item {{ padding: 5px 28px 5px 30px; }}
QMenu::item:selected {{ background: #91c9f7; color: #000; }}
QMenu::separator {{ height: 1px; background: #d7d7d7; margin: 3px 4px; }}
QStatusBar {{ background: {BTN_FACE}; border-top: 1px solid #d0d0d0; }}
QScrollArea {{ border: 0; }}
"""
