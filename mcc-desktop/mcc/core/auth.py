"""Usuarios e permissoes por modulo (FUseCad / FLog do MCC original).

Niveis por modulo, como nos TDBRadioGroup UsuPo1..UsuPo6: 2 completo, 1 consulta, 0 sem acesso.
O hash de senha (scrypt N=16384, r=8, p=1, 64 bytes) e o mesmo do clone web.
"""
import hashlib
import hmac
import os
import re
import time

from .db import dicts, tx, um

MODULOS = {
    'config': 'Configurações',                                   # UsuPo1 (somente 2 ou 0)
    'despesas': 'Controle de despesas',                          # UsuPo2
    'receitas': 'Controle de receitas',                          # UsuPo3
    'centros': 'Controle de centros de custo',                   # UsuPo4
    'bancos': 'Controle de contas bancárias e movimentações',    # UsuPo5
    'fluxo': 'Fluxo de caixa',                                   # UsuPo6
}
COMPLETO, CONSULTA, SEM_ACESSO = 2, 1, 0
MAX_FALHAS, BLOQUEIO_S = 5, 60


class AcessoNegado(Exception):
    pass


def hash_senha(senha):
    sal = os.urandom(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=16384, r=8, p=1, dklen=64)
    return f'scrypt${sal.hex()}${h.hex()}'


def confere(senha, hash_):
    try:
        alg, sal, h = str(hash_).split('$')
    except ValueError:
        return False
    if alg != 'scrypt':
        return False
    esperado = bytes.fromhex(h)
    obtido = hashlib.scrypt(str(senha or '').encode(), salt=bytes.fromhex(sal), n=16384, r=8, p=1, dklen=len(esperado))
    return hmac.compare_digest(esperado, obtido)


def valida_senha(senha):
    if not isinstance(senha, str) or len(senha) < 6:
        raise ValueError('A senha deve ter pelo menos 6 caracteres.')


def existe_usuario(db):
    return db.execute('SELECT 1 FROM usuarios LIMIT 1').fetchone() is not None


def nivel(u, modulo):
    """Nivel efetivo (administrador tem acesso completo a tudo)."""
    if u['admin']:
        return COMPLETO
    return int(u.get('perm_' + modulo) or 0)


def exigir(u, modulo, minimo):
    if nivel(u, modulo) < minimo:
        if minimo == COMPLETO:
            raise AcessoNegado(f'Seu usuário tem acesso somente de consulta (ou nenhum) ao módulo "{MODULOS[modulo]}".')
        raise AcessoNegado(f'Seu usuário não tem acesso ao módulo "{MODULOS[modulo]}".')


def modulo_do_tipo(tipo):
    return 'receitas' if tipo == 'R' else 'despesas'


def empresas_permitidas(db, u):
    """None = todas."""
    if u['admin'] or u['todas_empresas']:
        return None
    return [r[0] for r in db.execute('SELECT empresa_id FROM usuario_empresas WHERE usuario_id=?', (u['id'],))]


def pode_empresa(db, u, empresa_id):
    lista = empresas_permitidas(db, u)
    return lista is None or int(empresa_id) in lista


# ---------- Login ----------
_falhas = {}


def login(db, email, senha):
    chave = str(email or '').strip().lower()
    f = _falhas.get(chave)
    if f and f['ate'] > time.time():
        raise AcessoNegado('Muitas tentativas. Aguarde um minuto e tente novamente.')
    u = um(db.execute('SELECT * FROM usuarios WHERE email = ?', (chave,)))
    if not u or not confere(senha, u['senha_hash']):
        n = (f['n'] if f else 0) + 1
        _falhas[chave] = {'n': n, 'ate': time.time() + BLOQUEIO_S if n >= MAX_FALHAS else 0}
        raise AcessoNegado('E-mail ou senha incorretos.')
    if not u['ativo']:
        raise AcessoNegado('Usuário desativado. Procure o administrador.')
    _falhas.pop(chave, None)
    ultimo = u['ultimo_acesso']
    db.execute("UPDATE usuarios SET ultimo_acesso = datetime('now','localtime') WHERE id=?", (u['id'],))
    u['ultimo_acesso_anterior'] = ultimo
    return u


def recarregar(db, u):
    return um(db.execute('SELECT * FROM usuarios WHERE id=?', (u['id'],)))


def senha_administrador(db, senha, chave):
    """Senha de desbloqueio da protecao de dados (FLokSen): qualquer administrador ativo."""
    k = f'desbloqueio:{chave}'
    f = _falhas.get(k)
    if f and f['ate'] > time.time():
        raise AcessoNegado('Muitas tentativas. Aguarde um minuto e tente novamente.')
    ok = any(confere(senha, r[0]) for r in db.execute('SELECT senha_hash FROM usuarios WHERE admin=1 AND ativo=1'))
    if ok:
        _falhas.pop(k, None)
        return True
    n = (f['n'] if f else 0) + 1
    _falhas[k] = {'n': n, 'ate': time.time() + BLOQUEIO_S if n >= MAX_FALHAS else 0}
    return False


# ---------- Cadastro de usuarios (FUseCad) ----------
PERMS = ['perm_' + m for m in MODULOS]


def _normaliza(b, novo):
    o = {}
    if 'nome' in b or novo:
        o['nome'] = str(b.get('nome') or '').strip()
        if not o['nome']:
            raise ValueError('Informe o nome do usuário.')
    if 'email' in b or novo:
        o['email'] = str(b.get('email') or '').strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', o['email']):
            raise ValueError('Informe um e-mail válido.')
    for k in ('admin', 'ativo', 'todas_empresas'):
        if k in b:
            o[k] = 1 if int(b[k] or 0) else 0
    for k in PERMS:
        if k in b:
            v = int(b[k])
            if v not in (0, 1, 2) or (k == 'perm_config' and v == 1):
                raise ValueError('Permissão inválida: ' + k)
            o[k] = v
    return o


def listar_usuarios(db):
    return dicts(db.execute('SELECT * FROM usuarios ORDER BY ordem_pt(nome)'))


def empresas_do_usuario(db, usuario_id):
    return [r[0] for r in db.execute('SELECT empresa_id FROM usuario_empresas WHERE usuario_id=?', (usuario_id,))]


def _admins(db):
    return db.execute('SELECT COUNT(*) FROM usuarios WHERE admin=1 AND ativo=1').fetchone()[0]


def salvar_usuario(db, b, id_=None, autor=None):
    o = _normaliza(b, not id_)
    if not id_ or b.get('senha'):
        valida_senha(b.get('senha'))
    with tx(db):
        if id_:
            atual = um(db.execute('SELECT * FROM usuarios WHERE id=?', (id_,)))
            if not atual:
                raise ValueError('Usuário não encontrado.')
            if autor and autor['id'] == id_ and (o.get('ativo') == 0 or o.get('admin') == 0):
                raise ValueError('Você não pode desativar nem remover a categoria de administrador do seu próprio usuário.')
            if atual['admin'] and atual['ativo'] and (o.get('admin') == 0 or o.get('ativo') == 0) and _admins(db) <= 1:
                raise ValueError('É preciso manter pelo menos um administrador ativo.')
            if b.get('senha'):
                o['senha_hash'] = hash_senha(b['senha'])
            if o:
                db.execute(f"UPDATE usuarios SET {', '.join(f'{k}=?' for k in o)} WHERE id=?", (*o.values(), id_))
            if autor and autor['id'] != id_ and (o.get('ativo') == 0 or b.get('senha')):
                db.execute('DELETE FROM sessoes WHERE usuario_id=?', (id_,))  # encerra sessoes no clone web
        else:
            o['senha_hash'] = hash_senha(b['senha'])
            try:
                id_ = db.execute(f"INSERT INTO usuarios ({', '.join(o)}) VALUES ({', '.join('?' * len(o))})", tuple(o.values())).lastrowid
            except Exception as e:
                if 'UNIQUE' in str(e):
                    raise ValueError('Já existe um usuário com este e-mail.') from e
                raise
        if isinstance(b.get('empresas'), list):
            db.execute('DELETE FROM usuario_empresas WHERE usuario_id=?', (id_,))
            for e in b['empresas']:
                db.execute('INSERT OR IGNORE INTO usuario_empresas (usuario_id, empresa_id) VALUES (?,?)', (id_, int(e)))
    return id_


def excluir_usuario(db, id_, autor):
    if autor['id'] == id_:
        raise ValueError('Você não pode excluir o seu próprio usuário.')
    u = um(db.execute('SELECT * FROM usuarios WHERE id=?', (id_,)))
    if not u:
        raise ValueError('Usuário não encontrado.')
    if u['admin'] and u['ativo'] and _admins(db) <= 1:
        raise ValueError('É preciso manter pelo menos um administrador ativo.')
    db.execute('DELETE FROM usuarios WHERE id=?', (id_,))


def alterar_senha(db, u, atual, nova):
    if not confere(atual, u['senha_hash']):
        raise ValueError('A senha atual não confere.')
    valida_senha(nova)
    db.execute('UPDATE usuarios SET senha_hash=? WHERE id=?', (hash_senha(nova), u['id']))


def criar_administrador(db, b):
    if existe_usuario(db):
        raise ValueError('O administrador já foi criado.')
    return salvar_usuario(db, {**b, 'admin': 1, 'ativo': 1, 'perm_config': 2, 'todas_empresas': 1})
