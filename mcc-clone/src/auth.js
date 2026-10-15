// Usuarios, sessoes e permissoes por modulo (FUseCad / FLog do MCC original).
// Niveis por modulo, como nos TDBRadioGroup UsuPo1..UsuPo6: 2 completo, 1 consulta, 0 sem acesso.
import { randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';
import { tx } from './db.js';

export const MODULOS = {
  config: 'Configurações',                                    // UsuPo1 (somente 2 ou 0)
  despesas: 'Controle de despesas',                           // UsuPo2
  receitas: 'Controle de receitas',                           // UsuPo3
  centros: 'Controle de centros de custo',                    // UsuPo4
  bancos: 'Controle de contas bancárias e movimentações',     // UsuPo5
  fluxo: 'Fluxo de caixa',                                    // UsuPo6
};
export const COMPLETO = 2, CONSULTA = 1, SEM_ACESSO = 0;

const SESSAO_HORAS = 12;
const MAX_FALHAS = 5, BLOQUEIO_MS = 60_000;

export function criarTabelas(db) {
  db.exec(`
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
    );`);
}

// ---------- Senhas ----------
export function hashSenha(senha) {
  const sal = randomBytes(16);
  return `scrypt$${sal.toString('hex')}$${scryptSync(senha, sal, 64).toString('hex')}`;
}
function confere(senha, hash) {
  const [alg, sal, h] = String(hash).split('$');
  if (alg !== 'scrypt' || !sal || !h) return false;
  const esperado = Buffer.from(h, 'hex');
  const obtido = scryptSync(senha, Buffer.from(sal, 'hex'), esperado.length);
  return timingSafeEqual(esperado, obtido);
}
function validaSenha(senha) {
  if (typeof senha !== 'string' || senha.length < 6) throw new AuthError(400, 'A senha deve ter pelo menos 6 caracteres.');
}

export class AuthError extends Error {
  constructor(status, msg) { super(msg); this.status = status; }
}

// ---------- Usuario / permissoes ----------
export function existeUsuario(db) {
  return !!db.prepare('SELECT 1 FROM usuarios LIMIT 1').get();
}

// Nivel efetivo do usuario num modulo (administrador tem acesso completo a tudo).
export function nivel(u, modulo) {
  if (u.admin) return COMPLETO;
  return Number(u['perm_' + modulo]) || 0;
}

export function exigir(u, modulo, minimo) {
  if (nivel(u, modulo) < minimo)
    throw new AuthError(403, minimo === COMPLETO
      ? `Seu usuário tem acesso somente de consulta (ou nenhum) ao módulo "${MODULOS[modulo]}".`
      : `Seu usuário não tem acesso ao módulo "${MODULOS[modulo]}".`);
}

// Modulo que controla cada tipo de lancamento.
export const moduloDoTipo = (tipo) => (tipo === 'R' ? 'receitas' : 'despesas');

export function empresasPermitidas(db, u) {
  if (u.admin || u.todas_empresas) return null; // null = todas
  return db.prepare('SELECT empresa_id FROM usuario_empresas WHERE usuario_id=?').all(u.id).map((r) => r.empresa_id);
}

export function podeEmpresa(db, u, empresaId) {
  const lista = empresasPermitidas(db, u);
  return lista === null || lista.includes(Number(empresaId));
}

// Dados publicos do usuario (sem hash) com permissoes efetivas.
export function publico(db, u) {
  const perms = Object.fromEntries(Object.keys(MODULOS).map((m) => [m, nivel(u, m)]));
  return {
    id: u.id, nome: u.nome, email: u.email, admin: !!u.admin, ativo: !!u.ativo,
    todas_empresas: !!(u.admin || u.todas_empresas), empresas: empresasPermitidas(db, u) ?? [],
    perms, ultimo_acesso: u.ultimo_acesso,
  };
}

// ---------- Sessoes ----------
const falhas = new Map(); // email -> { n, ate }

export function login(db, email, senha) {
  const chave = String(email || '').trim().toLowerCase();
  const f = falhas.get(chave);
  if (f && f.ate > Date.now()) throw new AuthError(429, 'Muitas tentativas. Aguarde um minuto e tente novamente.');
  const u = db.prepare('SELECT * FROM usuarios WHERE email = ?').get(chave);
  if (!u || !confere(String(senha || ''), u.senha_hash)) {
    const n = (f?.n || 0) + 1;
    falhas.set(chave, { n, ate: n >= MAX_FALHAS ? Date.now() + BLOQUEIO_MS : 0 });
    throw new AuthError(401, 'E-mail ou senha incorretos.');
  }
  if (!u.ativo) throw new AuthError(403, 'Usuário desativado. Procure o administrador.');
  falhas.delete(chave);
  const token = randomBytes(32).toString('base64url');
  db.prepare('DELETE FROM sessoes WHERE expira_em < ?').run(Date.now());
  db.prepare('INSERT INTO sessoes (token, usuario_id, expira_em) VALUES (?,?,?)').run(token, u.id, Date.now() + SESSAO_HORAS * 3.6e6);
  const ultimo = u.ultimo_acesso;
  db.prepare("UPDATE usuarios SET ultimo_acesso = datetime('now','localtime') WHERE id=?").run(u.id);
  return { token, usuario: { ...publico(db, u), ultimo_acesso: ultimo } };
}

// Valida o token e renova a validade (expiracao deslizante).
export function sessao(db, token) {
  if (!token) return null;
  const s = db.prepare('SELECT * FROM sessoes WHERE token=?').get(token);
  if (!s || s.expira_em < Date.now()) return null;
  const u = db.prepare('SELECT * FROM usuarios WHERE id=?').get(s.usuario_id);
  if (!u || !u.ativo) return null;
  db.prepare('UPDATE sessoes SET expira_em=? WHERE token=?').run(Date.now() + SESSAO_HORAS * 3.6e6, token);
  return u;
}

export function logout(db, token) {
  db.prepare('DELETE FROM sessoes WHERE token=?').run(token);
}

// ---------- Cadastro de usuarios (FUseCad) ----------
const PERMS = Object.keys(MODULOS).map((m) => 'perm_' + m);

function normaliza(b, novo) {
  const o = {};
  if ('nome' in b || novo) { o.nome = String(b.nome || '').trim(); if (!o.nome) throw new AuthError(400, 'Informe o nome do usuário.'); }
  if ('email' in b || novo) {
    o.email = String(b.email || '').trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(o.email)) throw new AuthError(400, 'Informe um e-mail válido.');
  }
  for (const k of ['admin', 'ativo', 'todas_empresas']) if (k in b) o[k] = Number(b[k]) ? 1 : 0;
  for (const k of PERMS) if (k in b) {
    const v = Number(b[k]);
    if (![0, 1, 2].includes(v) || (k === 'perm_config' && v === 1)) throw new AuthError(400, 'Permissão inválida: ' + k);
    o[k] = v;
  }
  return o;
}

export function listarUsuarios(db) {
  return db.prepare('SELECT * FROM usuarios ORDER BY nome').all().map((u) => publico(db, u));
}

function admins(db) {
  return db.prepare('SELECT COUNT(*) n FROM usuarios WHERE admin=1 AND ativo=1').get().n;
}

export function salvarUsuario(db, b, id, autor) {
  const o = normaliza(b, !id);
  if (!id || b.senha) validaSenha(b.senha);
  return tx(db, () => {
    if (id) {
      const atual = db.prepare('SELECT * FROM usuarios WHERE id=?').get(id);
      if (!atual) throw new AuthError(404, 'Usuário não encontrado.');
      if (autor?.id === id && (o.ativo === 0 || o.admin === 0))
        throw new AuthError(400, 'Você não pode desativar nem remover a categoria de administrador do seu próprio usuário.');
      if (atual.admin && atual.ativo && (o.admin === 0 || o.ativo === 0) && admins(db) <= 1)
        throw new AuthError(400, 'É preciso manter pelo menos um administrador ativo.');
      if (b.senha) o.senha_hash = hashSenha(b.senha);
      const campos = Object.keys(o);
      if (campos.length) db.prepare(`UPDATE usuarios SET ${campos.map((c) => `${c}=?`).join(', ')} WHERE id=?`).run(...campos.map((c) => o[c]), id);
      // Desativar ou trocar a senha de outro usuario derruba as sessoes abertas dele.
      if (autor?.id !== id && (o.ativo === 0 || b.senha)) db.prepare('DELETE FROM sessoes WHERE usuario_id=?').run(id);
    } else {
      o.senha_hash = hashSenha(b.senha);
      const campos = Object.keys(o);
      try {
        id = Number(db.prepare(`INSERT INTO usuarios (${campos.join(', ')}) VALUES (${campos.map(() => '?').join(', ')})`).run(...campos.map((c) => o[c])).lastInsertRowid);
      } catch (e) {
        if (String(e.message).includes('UNIQUE')) throw new AuthError(409, 'Já existe um usuário com este e-mail.');
        throw e;
      }
    }
    if (Array.isArray(b.empresas)) {
      db.prepare('DELETE FROM usuario_empresas WHERE usuario_id=?').run(id);
      const ins = db.prepare('INSERT OR IGNORE INTO usuario_empresas (usuario_id, empresa_id) VALUES (?,?)');
      for (const e of b.empresas) ins.run(id, Number(e));
    }
    return id;
  });
}

export function excluirUsuario(db, id, autor) {
  if (autor.id === id) throw new AuthError(400, 'Você não pode excluir o seu próprio usuário.');
  const u = db.prepare('SELECT * FROM usuarios WHERE id=?').get(id);
  if (!u) throw new AuthError(404, 'Usuário não encontrado.');
  if (u.admin && u.ativo && admins(db) <= 1) throw new AuthError(400, 'É preciso manter pelo menos um administrador ativo.');
  db.prepare('DELETE FROM usuarios WHERE id=?').run(id);
}

// Senha de desbloqueio da protecao de dados (FLokSen: "Digite a senha do administrador").
// Aceita a senha de qualquer administrador ativo; erros contam para o bloqueio por tentativas.
export function senhaAdministrador(db, senha, chave) {
  const k = 'desbloqueio:' + chave;
  const f = falhas.get(k);
  if (f && f.ate > Date.now()) throw new AuthError(429, 'Muitas tentativas. Aguarde um minuto e tente novamente.');
  const ok = db.prepare('SELECT senha_hash FROM usuarios WHERE admin=1 AND ativo=1').all().some((a) => confere(String(senha || ''), a.senha_hash));
  if (ok) { falhas.delete(k); return true; }
  const n = (f?.n || 0) + 1;
  falhas.set(k, { n, ate: n >= MAX_FALHAS ? Date.now() + BLOQUEIO_MS : 0 });
  return false;
}

export function alterarSenha(db, u, atual, nova) {
  if (!confere(String(atual || ''), u.senha_hash)) throw new AuthError(400, 'A senha atual não confere.');
  validaSenha(nova);
  db.prepare('UPDATE usuarios SET senha_hash=? WHERE id=?').run(hashSenha(nova), u.id);
}

// Primeiro acesso: cria o administrador (o FCad original pede "Nome do usuario administrador").
export function criarAdministrador(db, b) {
  if (existeUsuario(db)) throw new AuthError(409, 'O administrador já foi criado.');
  return salvarUsuario(db, { ...b, admin: 1, ativo: 1, perm_config: 2, todas_empresas: 1 });
}
