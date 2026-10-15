"""Inicializacao: banco, login (ou primeiro acesso), conta controle e janela principal."""
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QLocale
from PySide6.QtWidgets import QApplication, QDialog, QStyleFactory

from .core import auth, db as dbm
from .core.servico import Sessao
from .ui import estilo as E
from .ui.base import icone


@dataclass
class Contexto:
    caminho_db: str
    db: object


def caminho_padrao():
    return str(Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'MCC' / 'mcc.db')


def criar_app(argv=None):
    QApplication.setAttribute(Qt.AA_DontShowIconsInMenus, False)
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName('MCC')
    app.setOrganizationName('MCC')
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    app.setStyle(QStyleFactory.create('Fusion'))
    E.instalar_fontes()
    app.setFont(E.fonte('Segoe UI', 12))  # fonte padrao (a folha de estilo nao define fonte para nao anular as dos componentes)
    app.setStyleSheet(E.QSS)
    app.setWindowIcon(icone('fa6s.coins', E.FAIXA_MENU))
    return app


def abrir_banco():
    cfg = QSettings('MCC', 'MCC')
    caminho = os.environ.get('MCC_DB') or cfg.value('caminho_db') or caminho_padrao()
    return Contexto(caminho, dbm.abrir(caminho))


def main():
    from .ui.acesso import FormLogin, FormPrimeiroAcesso, escolher_empresa
    from .ui.principal import JanelaPrincipal
    app = criar_app()
    ctx = abrir_banco()
    if not auth.existe_usuario(ctx.db):
        f = FormPrimeiroAcesso(ctx.db)
    else:
        f = FormLogin(ctx.db)
    if f.exec() != QDialog.Accepted or not f.usuario:
        return 0
    s = Sessao(ctx.db, f.usuario)
    s.u['ultimo_acesso_anterior'] = f.usuario.get('ultimo_acesso_anterior')
    emp = escolher_empresa(None, s)
    if not emp:
        return 0
    s.usar_empresa(emp)
    j = JanelaPrincipal(ctx, s)
    j.usar_empresa(emp)
    j.showMaximized()
    return app.exec()
