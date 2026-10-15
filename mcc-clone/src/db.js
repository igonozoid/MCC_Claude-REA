// Banco local SQLite. Modelo derivado dos TFDMemTable do MCC original
// (ver analise/MCC-funcionalidades.md para o mapeamento de nomes).
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { criarTabelas as criarTabelasAuth } from './auth.js';

const SCHEMA = `
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
  orcamento REAL NOT NULL DEFAULT 0,             -- mensal (despesas)
  projecao REAL NOT NULL DEFAULT 0               -- mensal (receitas)
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
  situacao TEXT NOT NULL DEFAULT 'P' CHECK (situacao IN ('V','P')), -- V pago, P em aberto
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
  tipo TEXT NOT NULL CHECK (tipo IN ('D','R','T')), -- deposito, retirada, transferencia
  situacao TEXT NOT NULL DEFAULT 'V' CHECK (situacao IN ('V','P')), -- realizado, previsto
  data TEXT NOT NULL,
  origem_id INTEGER NOT NULL REFERENCES contas(id),
  destino_id INTEGER REFERENCES contas(id),
  valor REAL NOT NULL,
  observacao TEXT,
  excluido_em TEXT
);
CREATE TABLE IF NOT EXISTS ofx_importados (      -- evita importar a mesma linha duas vezes
  conta_id INTEGER NOT NULL,
  fitid TEXT NOT NULL,
  PRIMARY KEY (conta_id, fitid)
);
`;

export function openDb(file) {
  if (file !== ':memory:') mkdirSync(dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec('PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL;');
  // Chave de ordenacao em portugues: sem acentos e sem diferenciar maiusculas ("Água" junto de "agua").
  db.function('ordem_pt', { deterministic: true }, (t) => (t == null ? null : String(t).normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()));
  db.exec(SCHEMA);
  criarTabelasAuth(db);
  migrar(db);
  return db;
}

// Colunas acrescentadas depois da primeira versao do banco.
function migrar(db) {
  const cols = db.prepare('PRAGMA table_info(empresas)').all().map((c) => c.name);
  // Protecao de dados (FLok): lancamentos ate esta data ficam bloqueados.
  if (!cols.includes('bloqueio_ate')) db.exec('ALTER TABLE empresas ADD COLUMN bloqueio_ate TEXT');
}

// Executa fn dentro de uma transacao.
export function tx(db, fn) {
  db.exec('BEGIN');
  try {
    const r = fn();
    db.exec('COMMIT');
    return r;
  } catch (e) {
    db.exec('ROLLBACK');
    throw e;
  }
}
