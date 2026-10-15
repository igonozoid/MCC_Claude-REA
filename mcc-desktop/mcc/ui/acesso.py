"""Acesso: login (FLog), primeiro acesso (FCad), escolha da conta controle (FLogin),
usuarios e permissoes (FUseBrs / FUseCad) e redefinicao de senha (FAlterSenha)."""
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from ..core import auth
from ..core.auth import AcessoNegado
from . import estilo as E
from .base import (BitBtn, Campo, ComboDados, FormBase, Grade, RadioGrupo, SpeedButton, confirmar, executar, icone, msg_aviso,
                   msg_erro, msg_info, rotulo)
from .cadastros import FormEmpresa, Navegador
from .lancamentos import _bt_cancela, _bt_confirma, _por, _rot


def _campo_senha(parent, x, y, w, h=25):
    e = _por(QLineEdit(), parent, x, y, w, h)
    e.setEchoMode(QLineEdit.Password)
    e.setFont(E.fonte('Arial', 15))
    olho = SpeedButton('', icone('fa6s.eye', '#555'), parent, dica='Visualizar senha')
    olho.setGeometry(x + w + 4, y, 34, h)
    olho.setCheckable(True)
    olho.toggled.connect(lambda on: (e.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password),
                                     olho.setIcon(icone('fa6s.eye-slash' if on else 'fa6s.eye', '#555'))))
    return e


class FormLogin(FormBase):
    """FLog, aba 'Usuario': e-mail e senha."""

    def __init__(self, db):
        super().__init__(None, 'Login de acesso', 424, 310, cor='#c0c7e2')
        self.db = db
        self.usuario = None
        self.cfg = QSettings('MCC', 'MCC')
        logo = QLabel(self)
        logo.setPixmap(icone('fa6s.coins', E.FAIXA_MENU).pixmap(40, 40))
        logo.move(20, 18)
        t = rotulo('MCC — controle financeiro', self, px=17, nome='Segoe UI Semibold', cor=E.FAIXA_MENU, negrito=True)
        t.move(70, 26)
        caixa = QFrame(self)
        caixa.setGeometry(10, 70, 404, 230)
        caixa.setStyleSheet('QFrame#caixa { background: #f0f0f0; border: 1px solid #8c8c8c; }')
        caixa.setObjectName('caixa')
        _rot('E-mail do usuário', caixa, 56, 14, px=13, nome='Segoe UI', cor='#008000')
        self.ed_eml = _por(QComboBox(), caixa, 56, 34, 290, 28)
        self.ed_eml.setEditable(True)
        self.ed_eml.setFont(E.fonte('Segoe UI', 15))
        historico = self.cfg.value('logins', []) or []
        if isinstance(historico, str):
            historico = [historico]
        self.ed_eml.addItems(historico)
        _rot('Senha de acesso', caixa, 56, 70, px=13, nome='Segoe UI', cor='#008000')
        self.ed_sen = _campo_senha(caixa, 56, 90, 290, 28)
        self.ck_log = QCheckBox('Salvar login no histórico', caixa)
        self.ck_log.setGeometry(57, 128, 190, 20)
        self.ck_log.setChecked(bool(historico))
        self.ck_log.setToolTip('Ao marcar esta opção, o login utilizado será mostrado no histórico para os próximos acessos.')
        esq = rotulo('esqueci a senha', caixa, px=13, nome='Segoe UI', cor=E.NAVY, sublinhado=True)
        esq.move(253, 129)
        esq.setCursor(Qt.PointingHandCursor)
        esq.mousePressEvent = lambda _e: msg_info(self, 'Peça a um administrador do MCC para redefinir a sua senha em\n'
                                                        'Ferramentas › Configurações › Usuários.', 'Esqueci a senha')
        ln = QFrame(caixa)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(56, 158, 290, 2)
        b1 = _por(BitBtn('&Fechar', icone('fa6s.xmark', '#b02a2a')), caixa, 56, 168, 122, 47)
        b2 = _por(BitBtn('&Acessar', icone('fa6s.right-to-bracket', '#1a7f37')), caixa, 184, 168, 162, 47)
        b2.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
        b2.setDefault(True)
        b1.clicked.connect(self.reject)
        b2.clicked.connect(self.acessar)
        (self.ed_sen if historico else self.ed_eml).setFocus()

    def acessar(self):
        email = self.ed_eml.currentText().strip()
        try:
            self.usuario = auth.login(self.db, email, self.ed_sen.text())
        except AcessoNegado as e:
            msg_aviso(self, str(e))
            self.ed_sen.selectAll()
            self.ed_sen.setFocus()
            return
        hist = [x for x in (self.cfg.value('logins', []) or []) if isinstance(x, str) and x.lower() != email.lower()]
        self.cfg.setValue('logins', ([email] + hist)[:8] if self.ck_log.isChecked() else [])
        self.accept()


class FormPrimeiroAcesso(FormBase):
    """FCad: primeiro uso — cadastro da conta e do usuario administrador."""

    def __init__(self, db):
        super().__init__(None, 'Cadastro da conta — bem-vindo ao MCC', 470, 330, cor='#c0c7e2')
        self.db = db
        self.usuario = None
        _rot('Crie o usuário administrador do MCC. Ele tem acesso completo e cadastra os\n'
             'demais usuários e suas permissões.', self, 20, 14, px=13, nome='Segoe UI', cor=E.NAVY)
        _rot('Nome do usuário administrador', self, 20, 62, px=13, nome='Segoe UI')
        self.ed_nom = _por(Campo(px=15), self, 20, 80, 400, 28)
        _rot('E-mail (login)', self, 20, 114, px=13, nome='Segoe UI')
        self.ed_eml = _por(Campo(px=15), self, 20, 132, 400, 28)
        _rot('Senha de acesso (mín. 6)', self, 20, 166, px=13, nome='Segoe UI')
        self.ed_sen = _campo_senha(self, 20, 184, 160, 28)
        _rot('Confirme a senha', self, 230, 166, px=13, nome='Segoe UI')
        self.ed_cnf = _campo_senha(self, 230, 184, 150, 28)
        self.ck_termos = QCheckBox('Estou de acordo com os termos de uso e políticas de privacidade.', self)
        self.ck_termos.setGeometry(20, 224, 430, 20)
        self.ck_termos.setChecked(True)
        ln = QFrame(self)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(20, 252, 430, 2)
        _por(BitBtn('Cancelar', icone('fa6s.xmark', '#b02a2a')), self, 20, 266, 110, 42).clicked.connect(self.reject)
        b = _por(BitBtn('&Avançar', icone('fa6s.arrow-right', '#1a7f37')), self, 136, 266, 150, 42)
        b.setDefault(True)
        b.clicked.connect(self.confirmar)

    def confirmar(self):
        if self.ed_sen.text() != self.ed_cnf.text():
            msg_aviso(self, 'A confirmação não confere com a senha.')
            return
        if not self.ck_termos.isChecked():
            msg_aviso(self, 'É preciso concordar com os termos de uso.')
            return
        try:
            auth.criar_administrador(self.db, {'nome': self.ed_nom.valor(), 'email': self.ed_eml.valor(), 'senha': self.ed_sen.text()})
            self.usuario = auth.login(self.db, self.ed_eml.valor(), self.ed_sen.text())
        except (ValueError, AcessoNegado) as e:
            msg_aviso(self, str(e))
            return
        self.accept()


class FormEscolherEmpresa(FormBase):
    """FLogin: 'Conta controle:' + Acessar."""

    def __init__(self, parent, empresas, atual=None, pode_criar=False):
        super().__init__(parent, 'Conta controle', 350, 135, cor='#c0c7e2')
        _rot('Conta controle:', self, 8, 13, px=13, nome='Segoe UI')
        self.cb = _por(ComboDados(px=15, opcoes=[(e['nome'], e['id']) for e in empresas]), self, 8, 36, 332, 28)
        if atual:
            self.cb.definir(atual)
        self.nova = False
        if pode_criar:
            bn = _por(BitBtn('Nova', icone('fa6s.plus', '#1a7f37'), dica='Nova conta controle'), self, 8, 88, 100, 35)
            bn.clicked.connect(self._nova)
        _por(BitBtn('Ca&ncelar', icone('fa6s.xmark', '#b02a2a')), self, 113, 88, 100, 35).clicked.connect(self.reject)
        b = _por(BitBtn('&Acessar', icone('fa6s.right-to-bracket', '#1a7f37')), self, 215, 88, 125, 35)
        b.setFont(E.fonte('Segoe UI Semibold', 13, negrito=True))
        b.setDefault(True)
        b.clicked.connect(self.accept)

    def _nova(self):
        self.nova = True
        self.accept()


def escolher_empresa(parent, s, forcar=False, cfg=None):
    """Retorna o id da conta controle a usar (cria a primeira, se preciso)."""
    cfg = cfg or QSettings('MCC', 'MCC')
    empresas = s.empresas()
    pode_criar = s.nivel('config') >= 2
    if not empresas:
        if not pode_criar:
            msg_erro(parent, 'Seu usuário não tem acesso a nenhuma conta controle. Procure o administrador.')
            return None
        return criar_empresa(parent, s, primeira=True)
    salva = cfg.value(f"ultima_empresa/{s.u['id']}")
    ids = [e['id'] for e in empresas]
    if not forcar:
        if salva is not None and int(salva) in ids:
            return int(salva)
        if len(empresas) == 1:
            return empresas[0]['id']
    f = FormEscolherEmpresa(parent, empresas, s.empresa_id or (int(salva) if salva else None), pode_criar)
    if f.exec() != QDialog.Accepted:
        return None
    if f.nova:
        return criar_empresa(parent, s)
    return f.cb.valor()


def criar_empresa(parent, s, primeira=False):
    f = FormEmpresa(parent, s, None, primeira=primeira)
    if f.exec() != QDialog.Accepted:
        return None
    novo = f.novo_id
    s.usar_empresa(novo)
    if s.nivel('bancos') >= 2 and not s.listar('contas'):
        s.salvar('contas', {'descricao': 'CAIXA INTERNO', 'tipo': 'C', 'saldo_inicial': 0})
    return novo


# ---------- Usuarios (FUseBrs / FUseCad) ----------

MODULOS = [('config', 'Configurações', [('Acesso completo', 2), ('Sem acesso', 0)]),
           ('despesas', 'Controle de despesas', None), ('receitas', 'Controle de receitas', None), ('fluxo', 'Fluxo de caixa', None),
           ('centros', 'Controle de centros de custo', None), ('bancos', 'Controle de contas bancárias e movimentações', None)]
NIVEIS = [('Acesso completo', 2), ('Somente consulta', 1), ('Sem acesso', 0)]


class FormUsuario(FormBase):
    def __init__(self, parent, s, u=None):
        super().__init__(parent, 'Usuário', 422, 561)
        self.s, self.u = s, u or {}
        novo = not u
        self.abas = QTabWidget(self)
        self.abas.setGeometry(3, 3, 416, 555)
        t1 = QWidget()
        self.abas.addTab(t1, 'Dados do usuário')
        sou_admin = bool(s.u['admin'])
        if sou_admin:
            self.rg_cat = RadioGrupo('Categoria', [('Usuário', 0), ('Administrador', 1)], t1, px=13)
            self.rg_cat.setGeometry(20, 8, 215, 47)
            self.rg_cat.definir(int(self.u.get('admin', 0)))
        else:
            self.rg_cat = None
            _rot('Categoria', t1, 20, 10, px=13, nome='Segoe UI')
            c = _por(Campo(px=13), t1, 20, 30, 185, 25)
            c.setText('Administrador' if self.u.get('admin') else 'Usuário')
            c.setReadOnly(True)
        self.rg_sta = RadioGrupo('Status', [('Ativo', 1), ('Inativo', 0)], t1, px=13)
        self.rg_sta.setGeometry(240, 8, 150, 47)
        self.rg_sta.definir(int(self.u.get('ativo', 1)))
        ln = QFrame(t1)
        ln.setFrameShape(QFrame.HLine)
        ln.setGeometry(20, 69, 331, 2)
        _rot('Usuario', t1, 20, 96, px=13)
        self.ed_nom = _por(Campo(px=15), t1, 20, 115, 330, 26)
        self.ed_nom.definir(self.u.get('nome'))
        _rot('E-mail', t1, 20, 155, px=13)
        self.ed_eml = _por(Campo(px=15), t1, 20, 174, 330, 26)
        self.ed_eml.definir(self.u.get('email'))
        lb_s = _rot('Senha de acesso' if novo else 'Nova senha', t1, 20, 211, px=13)
        if not novo:
            lb_s.setToolTip('Deixe em branco para manter a senha atual')
        self.ed_sen = _campo_senha(t1, 20, 231, 146, 26)
        _rot('Confirmação', t1, 176 + 34, 211, px=13)
        self.ed_cnf = _por(QLineEdit(), t1, 176 + 34, 231, 140, 26)
        self.ed_cnf.setEchoMode(QLineEdit.Password)
        bp = _por(BitBtn('Permissões de acesso', icone('fa6s.user-shield', E.NAVY)), t1, 172, 283, 179, 41)
        bp.clicked.connect(lambda: self.abas.setCurrentIndex(1))
        ln2 = QFrame(t1)
        ln2.setFrameShape(QFrame.HLine)
        ln2.setGeometry(20, 346, 331, 2)
        _por(_bt_cancela(None), t1, 152, 361, 95, 41).clicked.connect(self.reject)
        _por(_bt_confirma(None), t1, 253, 361, 99, 41).clicked.connect(self.confirmar)
        # permissoes
        t2 = QWidget()
        self.abas.addTab(t2, 'Permissões de acesso')
        v = QVBoxLayout(t2)
        sub = QTabWidget()
        v.addWidget(sub)
        pm = QWidget()
        pv = QVBoxLayout(pm)
        self.aviso_admin = rotulo('Administradores têm acesso completo a todos os módulos e contas controle.', px=12, nome='Segoe UI', cor=E.NAVY)
        pv.addWidget(self.aviso_admin)
        self.rg_mod = {}
        for chave, titulo, op in MODULOS:
            rg = RadioGrupo(titulo, op or NIVEIS, px=12)
            rg.definir(int(self.u.get('perm_' + chave, 0 if chave == 'config' else 2)))
            pv.addWidget(rg)
            self.rg_mod[chave] = rg
        pv.addStretch()
        sub.addTab(pm, 'Acesso aos modulos')
        pc = QWidget()
        cv = QVBoxLayout(pc)
        self.rg_con = RadioGrupo('', [('Todas as contas', 1), ('Contas controle específicas:', 0)], px=12)
        self.rg_con.definir(1 if self.u.get('todas_empresas', 1) else 0)
        cv.addWidget(self.rg_con)
        cv.addWidget(rotulo('Marque as contas que deseja permitir o acesso:', px=13, nome='Segoe UI'))
        self.lista = QListWidget()
        for e in s.empresas():
            it = QListWidgetItem(e['nome'])
            it.setData(Qt.UserRole, e['id'])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if e['id'] in (self.u.get('empresas') or []) else Qt.Unchecked)
            self.lista.addItem(it)
        cv.addWidget(self.lista)
        sub.addTab(pc, 'Acesso a contas controle')
        h = QHBoxLayout()
        h.addStretch()
        bv = BitBtn('Voltar', icone('fa6s.arrow-left', '#333'))
        bv.clicked.connect(lambda: self.abas.setCurrentIndex(0))
        h.addWidget(bv)
        v.addLayout(h)
        if self.rg_cat:
            self.rg_cat.mudou.connect(lambda _v: self._sync())
        self.rg_con.mudou.connect(lambda _v: self._sync())
        self._sync()

    def _admin(self):
        return (self.rg_cat.valor() if self.rg_cat else int(self.u.get('admin', 0))) == 1

    def _sync(self):
        adm = self._admin()
        self.aviso_admin.setVisible(adm)
        for rg in self.rg_mod.values():
            rg.setEnabled(not adm)
        self.rg_con.setEnabled(not adm)
        self.lista.setEnabled(not adm and self.rg_con.valor() == 0)

    def confirmar(self):
        if self.ed_sen.text() != self.ed_cnf.text():
            msg_aviso(self, 'A confirmação não confere com a senha.')
            return
        d = {'nome': self.ed_nom.valor(), 'email': self.ed_eml.valor(), 'ativo': self.rg_sta.valor(), 'todas_empresas': self.rg_con.valor()}
        if self.rg_cat:
            d['admin'] = self.rg_cat.valor()
        if self.ed_sen.text():
            d['senha'] = self.ed_sen.text()
        for k, rg in self.rg_mod.items():
            d['perm_' + k] = rg.valor()
        d['empresas'] = [self.lista.item(i).data(Qt.UserRole) for i in range(self.lista.count()) if self.lista.item(i).checkState() == Qt.Checked]
        if not d['todas_empresas'] and not d['empresas'] and not d.get('admin'):
            msg_aviso(self, 'Marque ao menos uma conta controle ou escolha "Todas as contas".')
            return
        if executar(self, lambda senha: self.s.salvar_usuario(d, self.u.get('id'))):
            self.accept()


class NavUsuarios(Navegador):
    def __init__(self, parent, s):
        super().__init__(parent, 'Usuários', [('nome', 'Usuário', 160), ('email', 'E-mail', 180), ('cat', 'Categoria', 100),
                                              ('sta', 'Status', 70), ('ultimo_acesso', 'Último acesso', 130)], 680, 376, 'config', s)
        self.carregar()

    def buscar(self):
        return [{**u, 'cat': 'Administrador' if u['admin'] else 'Usuário', 'sta': 'Ativo' if u['ativo'] else 'Inativo'} for u in self.s.listar_usuarios()]

    def editar(self, r):
        return FormUsuario(self, self.s, r).exec() == QDialog.Accepted

    def remover(self, r, senha):
        self.s.excluir_usuario(r['id'])


class FormAlterarSenha(FormBase):
    """FAlterSenha (com a senha atual, para o proprio usuario)."""

    def __init__(self, parent, s):
        super().__init__(parent, 'Redefinir senha de acesso', 300, 250, cor='#e5e5e5')
        self.s = s
        _rot('Senha atual:', self, 16, 10, px=13, nome='Segoe UI')
        self.ed0 = _campo_senha(self, 16, 28, 196, 24)
        _rot('Digite a nova senha:', self, 16, 62, px=13, nome='Segoe UI')
        self.ed1 = _campo_senha(self, 16, 80, 196, 24)
        _rot('Confirme a senha:', self, 16, 114, px=13, nome='Segoe UI')
        self.ed2 = _por(QLineEdit(), self, 16, 132, 196, 24)
        self.ed2.setEchoMode(QLineEdit.Password)
        _por(_bt_cancela(None), self, 15, 190, 97, 39).clicked.connect(self.reject)
        _por(_bt_confirma(None), self, 118, 190, 113, 39).clicked.connect(self.confirmar)

    def confirmar(self):
        if self.ed1.text() != self.ed2.text():
            msg_aviso(self, 'A confirmação não confere com a nova senha.')
            return
        try:
            self.s.alterar_senha(self.ed0.text(), self.ed1.text())
        except ValueError as e:
            msg_aviso(self, str(e))
            return
        msg_info(self, 'Senha alterada.')
        self.accept()
