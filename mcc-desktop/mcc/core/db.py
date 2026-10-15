"""Banco SQLite do MCC.

O schema e identico ao do clone web (mcc-clone/src/db.js e auth.js), entao os dois
programas podem abrir o mesmo arquivo. Tabelas so do desktop ficam em tabelas
proprias (ex.: empresa_logos) para nao mudar o que o clone web le.
"""
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS empresas (            -- Con* (conta controle)
  id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  pessoa TEXT NOT NULL DEFAULT 'J' CHECK (pessoa IN ('F','J')),
  documento TEXT, documento2 TEXT,
  endereco TEXT, bairro TEXT, cidade TEXT, uf TEXT, cep TEXT,
  telefone TEXT, email TEXT, site TEXT,
  usa_centro_custo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS contas (              -- Ban* (conta bancaria / caixa)
  id INTEGER PRIMARY KEY,
  empresa_id INTEGER REFERENCES empresas(id),    -- NULL = compartilhada
  descricao TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'B' CHECK (tipo IN ('B','C')),
  saldo_inicial REAL NOT NULL DEFAULT 0,
  limite REAL NOT NULL DEFAULT 0,
  ativa INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS centros (             -- Cen* (centro de custo/lucro)
  id INTEGER PRIMARY KEY,
  empresa_id INTEGER NOT NULL REFERENCES empresas(id),
  nome TEXT NOT NULL,
  aplica_despesa INTEGER NOT NULL DEFAULT 1,
  aplica_receita INTEGER NOT NULL DEFAULT 0,
  orcamento REAL NOT NULL DEFAULT 0,
  projecao REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pessoas (             -- Pes* (cliente/fornecedor)
  id INTEGER PRIMARY KEY,
  empresa_id INTEGER REFERENCES empresas(id),    -- NULL = compartilhado
  tipo TEXT NOT NULL CHECK (tipo IN ('C','F')),
  pessoa TEXT NOT NULL DEFAULT 'J' CHECK (pessoa IN ('F','J')),
  nome TEXT NOT NULL,
  documento TEXT, documento2 TEXT,
  endereco TEXT, bairro TEXT, cidade TEXT, uf TEXT, cep TEXT,
  telefone TEXT, email TEXT, contato TEXT,
  banco TEXT, agencia TEXT, conta_bancaria TEXT,
  limite REAL NOT NULL DEFAULT 0,
  observacao TEXT
);
CREATE TABLE IF NOT EXISTS itens (               -- Ite* (itens de despesa/receita)
  id INTEGER PRIMARY KEY,
  empresa_id INTEGER NOT NULL REFERENCES empresas(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('D','R')),
  descricao TEXT NOT NULL,
  UNIQUE (empresa_id, tipo, descricao)
);
CREATE TABLE IF NOT EXISTS lancamentos (         -- Mov* (despesa/receita)
  id INTEGER PRIMARY KEY,
  empresa_id INTEGER NOT NULL REFERENCES empresas(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('D','R')),
  data_mov TEXT NOT NULL,
  documento TEXT,
  descricao TEXT NOT NULL,
  pessoa TEXT,
  valor REAL NOT NULL,
  situacao TEXT NOT NULL DEFAULT 'P' CHECK (situacao IN ('V','P')),
  vencimento TEXT NOT NULL,
  data_pagamento TEXT,
  observacao TEXT,
  conta_id INTEGER REFERENCES contas(id),
  centro_id INTEGER REFERENCES centros(id),
  grupo TEXT, parcela INTEGER, total_parcelas INTEGER,
  criado_em TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  alterado_em TEXT,
  excluido_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_lanc ON lancamentos (empresa_id, tipo, excluido_em);
CREATE TABLE IF NOT EXISTS movbancarias (        -- Tra* (movimentacao bancaria)
  id INTEGER PRIMARY KEY,
  empresa_id INTEGER NOT NULL REFERENCES empresas(id),
  tipo TEXT NOT NULL CHECK (tipo IN ('D','R','T')),
  situacao TEXT NOT NULL DEFAULT 'V' CHECK (situacao IN ('V','P')),
  data TEXT NOT NULL,
  origem_id INTEGER NOT NULL REFERENCES contas(id),
  destino_id INTEGER REFERENCES contas(id),
  valor REAL NOT NULL,
  observacao TEXT,
  excluido_em TEXT
);
CREATE TABLE IF NOT EXISTS ofx_importados (
  conta_id INTEGER NOT NULL,
  fitid TEXT NOT NULL,
  PRIMARY KEY (conta_id, fitid)
);
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  senha_hash TEXT NOT NULL,
  admin INTEGER NOT NULL DEFAULT 0,
  ativo INTEGER NOT NULL DEFAULT 1,
  perm_config INTEGER NOT NULL DEFAULT 0 CHECK (perm_config IN (0,2)),
  perm_despesas INTEGER NOT NULL DEFAULT 2 CHECK (perm_despesas IN (0,1,2)),
  perm_receitas INTEGER NOT NULL DEFAULT 2 CHECK (perm_receitas IN (0,1,2)),
  perm_centros INTEGER NOT NULL DEFAULT 2 CHECK (perm_centros IN (0,1,2)),
  perm_bancos INTEGER NOT NULL DEFAULT 2 CHECK (perm_bancos IN (0,1,2)),
  perm_fluxo INTEGER NOT NULL DEFAULT 2 CHECK (perm_fluxo IN (0,1,2)),
  todas_empresas INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  ultimo_acesso TEXT
);
CREATE TABLE IF NOT EXISTS usuario_empresas (
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
  PRIMARY KEY (usuario_id, empresa_id)
);
CREATE TABLE IF NOT EXISTS sessoes (
  token TEXT PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  expira_em INTEGER NOT NULL
);
-- So do desktop: logomarca da empresa impressa nos relatorios (menu "Logomarca da empresa").
-- So do desktop: campos do FPesCad que o clone web nao tem (contatos, perfil, referencias), em JSON.
CREATE TABLE IF NOT EXISTS pessoas_extra (
  pessoa_id INTEGER PRIMARY KEY REFERENCES pessoas(id) ON DELETE CASCADE,
  dados TEXT NOT NULL DEFAULT '{}',
  criado_em TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
-- So do desktop: opcoes do FConfigConta (exibir saldos, campo inicial, conta padrao...).
CREATE TABLE IF NOT EXISTS empresa_config (
  empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
  chave TEXT NOT NULL,
  valor TEXT,
  PRIMARY KEY (empresa_id, chave)
);
CREATE TABLE IF NOT EXISTS empresa_logos (
  empresa_id INTEGER PRIMARY KEY REFERENCES empresas(id) ON DELETE CASCADE,
  imagem BLOB NOT NULL
);
"""


def ordem_pt(t):
    """Chave de ordenacao em portugues: sem acentos e sem diferenciar maiusculas."""
    if t is None:
        return None
    s = unicodedata.normalize('NFD', str(t))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()


def abrir(caminho):
    """Abre (e cria/migra, se preciso) o banco. Linhas vem como sqlite3.Row."""
    if caminho != ':memory:':
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(caminho, isolation_level=None)  # autocommit; transacoes explicitas em tx()
    db.row_factory = sqlite3.Row
    db.create_function('ordem_pt', 1, ordem_pt, deterministic=True)
    db.execute('PRAGMA foreign_keys = ON')
    if caminho != ':memory:':
        db.execute('PRAGMA journal_mode = WAL')
    db.executescript(SCHEMA)
    _migrar(db)
    return db


def _migrar(db):
    cols = [r['name'] for r in db.execute('PRAGMA table_info(empresas)')]
    # Protecao de dados (FLok): lancamentos ate esta data ficam bloqueados.
    if 'bloqueio_ate' not in cols:
        db.execute('ALTER TABLE empresas ADD COLUMN bloqueio_ate TEXT')


@contextmanager
def tx(db):
    """Transacao: confirma no fim do bloco ou desfaz em caso de erro."""
    if db.in_transaction:  # transacao aninhada: participa da externa
        yield
        return
    db.execute('BEGIN')
    try:
        yield
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise


def dicts(cur):
    return [dict(r) for r in cur]


def um(cur):
    r = cur.fetchone()
    return dict(r) if r else None
