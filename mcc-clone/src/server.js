// Servidor HTTP do clone do MCC. Sem dependencias externas: node:http + node:sqlite.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { openDb } from './db.js';
import * as fin from './finance.js';
import * as auth from './auth.js';

const { COMPLETO, CONSULTA, exigir, nivel, moduloDoTipo } = auth;
const PUBLIC = fileURLToPath(new URL('../public/', import.meta.url));
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml' };
const COOKIE = 'mcc_sessao';

// Cadastros simples: tabela -> campos editaveis, se pertencem a uma empresa e qual modulo
// controla a escrita (modulo pode depender do tipo do registro).
const CADASTROS = {
  empresas: { campos: ['nome', 'pessoa', 'documento', 'documento2', 'endereco', 'bairro', 'cidade', 'uf', 'cep', 'telefone', 'email', 'site', 'usa_centro_custo'], global: true, ordem: 'nome', modulo: () => 'config' },
  contas: { campos: ['empresa_id', 'descricao', 'tipo', 'saldo_inicial', 'limite', 'ativa'], compartilhavel: true, ordem: 'descricao', modulo: () => 'bancos' },
  centros: { campos: ['nome', 'aplica_despesa', 'aplica_receita', 'orcamento', 'projecao'], ordem: 'nome', modulo: () => 'centros' },
  pessoas: { campos: ['empresa_id', 'tipo', 'pessoa', 'nome', 'documento', 'documento2', 'endereco', 'bairro', 'cidade', 'uf', 'cep', 'telefone', 'email', 'contato', 'banco', 'agencia', 'conta_bancaria', 'limite', 'observacao'], compartilhavel: true, ordem: 'nome', modulo: (t) => (t === 'C' ? 'receitas' : 'despesas') },
  itens: { campos: ['tipo', 'descricao'], ordem: 'descricao', modulo: moduloDoTipo },
  movbancarias: { campos: ['tipo', 'situacao', 'data', 'origem_id', 'destino_id', 'valor', 'observacao'], ordem: 'data DESC, id DESC', softDelete: true, modulo: () => 'bancos', leitura: 'bancos' },
};

// Modulo exigido (para leitura) por relatorio; tipo D/R decide entre despesas e receitas.
const MODULO_RELATORIO = {
  lancamentos: 'tipo', totais_item: 'tipo', por_pessoa: 'tipo', pontualidade: 'tipo', demonstrativo: 'tipo',
  fluxo_dia: 'fluxo', dre: 'fluxo', extrato: 'bancos', saldos: 'bancos', centros: 'centros',
};

class HttpError extends Error {
  constructor(status, msg, extra) { super(msg); this.status = status; this.extra = extra; }
}
const br = (d) => (d ? d.split('-').reverse().join('/') : '');

const cookies = (req) => Object.fromEntries(String(req.headers.cookie || '').split(';').map((c) => c.trim().split('=')).filter(([k]) => k).map(([k, ...v]) => [k, decodeURIComponent(v.join('='))]));

export function criarApp(db) {
  function empresaDe(req, url, u) {
    const id = Number(req.headers['x-empresa'] || url.searchParams.get('empresa'));
    if (!id || !db.prepare('SELECT 1 FROM empresas WHERE id=?').get(id)) throw new HttpError(400, 'Selecione uma conta controle.');
    if (!auth.podeEmpresa(db, u, id)) throw new HttpError(403, 'Seu usuário não tem acesso a esta conta controle.');
    return id;
  }

  // ---------- Protecao de dados (FLok) ----------
  // Ate a data de bloqueio da conta controle, lancamentos nao podem ser incluidos, alterados,
  // baixados ou excluidos, nem o caixa movimentado, sem a senha de um administrador
  // (enviada no cabecalho x-desbloqueio e valida so para aquela requisicao).
  const limiteBloqueio = (emp) => db.prepare('SELECT bloqueio_ate FROM empresas WHERE id=?').get(emp)?.bloqueio_ate || null;

  // O lancamento pertence ao periodo protegido pela data de movimento ou, se pago, pela data do pagamento.
  function lancNoPeriodo(l, lim) {
    const mov = l.data_mov || fin.hoje();
    if (mov <= lim) return true;
    return l.situacao === 'V' && (l.data_pagamento || l.vencimento || mov) <= lim;
  }

  function exigeDesbloqueio(req, u, emp, afetado) {
    const lim = limiteBloqueio(emp);
    if (!lim || !afetado(lim)) return;
    const senha = req.headers['x-desbloqueio'];
    if (senha !== undefined) {
      let txt = '';
      try { txt = decodeURIComponent(senha); } catch { /* senha mal codificada = incorreta */ }
      if (auth.senhaAdministrador(db, txt, u.id)) return;
      throw new HttpError(423, 'Senha de desbloqueio incorreta.', { bloqueio_ate: lim, senha_incorreta: true });
    }
    throw new HttpError(423, `Movimentações bloqueadas até ${br(lim)}.`, { bloqueio_ate: lim });
  }

  // Tipos de lancamento (D/R) que o usuario pode ver.
  const tiposVisiveis = (u) => ['D', 'R'].filter((t) => nivel(u, moduloDoTipo(t)) >= CONSULTA);

  function listar(tabela, empresaId, q, u) {
    const cfg = CADASTROS[tabela];
    if (cfg.leitura) exigir(u, cfg.leitura, CONSULTA);
    const where = [], args = [];
    if (tabela === 'empresas') {
      const permitidas = auth.empresasPermitidas(db, u);
      if (permitidas) where.push(`id IN (${permitidas.map(Number).join(',') || 'NULL'})`);
    } else {
      where.push(cfg.compartilhavel ? '(empresa_id = ? OR empresa_id IS NULL)' : 'empresa_id = ?');
      args.push(empresaId);
    }
    if (cfg.softDelete) where.push('excluido_em IS NULL');
    if (q.get('tipo')) { where.push('tipo = ?'); args.push(q.get('tipo')); }
    if (tabela === 'itens') where.push(`tipo IN (${tiposVisiveis(u).map((t) => `'${t}'`).join(',') || 'NULL'})`);
    const sql = `SELECT * FROM ${tabela}${where.length ? ' WHERE ' + where.join(' AND ') : ''} ORDER BY ${cfg.ordem}`;
    return db.prepare(sql).all(...args);
  }

  // Registro existente, restrito ao que a empresa enxerga.
  function registro(tabela, id, empresaId) {
    const cfg = CADASTROS[tabela];
    const dono = cfg.global ? '' : cfg.compartilhavel ? ' AND (empresa_id = ? OR empresa_id IS NULL)' : ' AND empresa_id = ?';
    const r = db.prepare(`SELECT * FROM ${tabela} WHERE id=?${dono}`).get(id, ...(cfg.global ? [] : [empresaId]));
    if (!r) throw new HttpError(404, 'Registro não encontrado.');
    return r;
  }

  const contaVisivel = (contaId, emp) => !contaId || db.prepare('SELECT 1 FROM contas WHERE id=? AND (empresa_id=? OR empresa_id IS NULL)').get(Number(contaId), emp);
  const centroVisivel = (centroId, emp) => !centroId || db.prepare('SELECT 1 FROM centros WHERE id=? AND empresa_id=?').get(Number(centroId), emp);

  function salvar(tabela, empresaId, body, id, u) {
    const cfg = CADASTROS[tabela];
    const atual = id ? registro(tabela, id, empresaId) : null;
    exigir(u, cfg.modulo(atual?.tipo ?? body.tipo), COMPLETO);
    if (atual && 'tipo' in body && body.tipo !== atual.tipo) exigir(u, cfg.modulo(body.tipo), COMPLETO);
    // Um registro so pode ser da empresa atual ou compartilhado.
    if (cfg.compartilhavel && 'empresa_id' in body && body.empresa_id !== '' && body.empresa_id != null) body.empresa_id = empresaId;
    validar(tabela, body, empresaId);
    const campos = cfg.campos.filter((c) => c in body);
    const vals = campos.map((c) => (body[c] === '' ? null : typeof body[c] === 'boolean' ? Number(body[c]) : body[c]));
    if (id) {
      if (!campos.length) return id;
      db.prepare(`UPDATE ${tabela} SET ${campos.map((c) => `${c}=?`).join(', ')} WHERE id=?`).run(...vals, id);
      return id;
    }
    if (!cfg.global && !cfg.compartilhavel) { campos.push('empresa_id'); vals.push(empresaId); }
    if (cfg.compartilhavel && !('empresa_id' in body)) { campos.push('empresa_id'); vals.push(empresaId); }
    const r = db.prepare(`INSERT INTO ${tabela} (${campos.join(', ')}) VALUES (${campos.map(() => '?').join(', ')})`).run(...vals);
    const novo = Number(r.lastInsertRowid);
    // Quem cria uma conta controle com acesso restrito passa a ter acesso a ela.
    if (tabela === 'empresas' && !auth.podeEmpresa(db, u, novo))
      db.prepare('INSERT OR IGNORE INTO usuario_empresas (usuario_id, empresa_id) VALUES (?,?)').run(u.id, novo);
    return novo;
  }

  function validar(tabela, b, emp) {
    const obrig = { empresas: 'nome', contas: 'descricao', centros: 'nome', pessoas: 'nome', itens: 'descricao' }[tabela];
    if (obrig && obrig in b && !String(b[obrig] || '').trim()) throw new HttpError(400, 'Preencha o campo obrigatório: ' + obrig);
    if (tabela === 'movbancarias') {
      if (!(Number(b.valor) > 0)) throw new HttpError(400, 'Informe um valor maior que zero.');
      if (b.tipo === 'T' && (!b.destino_id || Number(b.destino_id) === Number(b.origem_id)))
        throw new HttpError(400, 'Selecione uma conta de destino diferente da origem.');
      if (!contaVisivel(b.origem_id, emp) || !contaVisivel(b.destino_id, emp)) throw new HttpError(400, 'Conta inválida.');
    }
  }

  function remover(tabela, empresaId, id, u) {
    const cfg = CADASTROS[tabela];
    const atual = registro(tabela, id, empresaId);
    exigir(u, cfg.modulo(atual.tipo), COMPLETO);
    if (tabela === 'empresas' && db.prepare('SELECT 1 FROM lancamentos WHERE empresa_id=? LIMIT 1').get(id))
      throw new HttpError(409, 'Esta conta controle possui lançamentos e não pode ser excluída.');
    if (tabela === 'contas' && db.prepare('SELECT 1 FROM lancamentos WHERE conta_id=? AND excluido_em IS NULL LIMIT 1').get(id))
      throw new HttpError(409, 'Esta conta possui lançamentos. Desative-a em vez de excluir.');
    if (tabela === 'centros') db.prepare('UPDATE lancamentos SET centro_id=NULL WHERE centro_id=?').run(id);
    if (cfg.softDelete) db.prepare(`UPDATE ${tabela} SET excluido_em=datetime('now','localtime') WHERE id=?`).run(id);
    else db.prepare(`DELETE FROM ${tabela} WHERE id=?`).run(id);
  }

  function lancamento(id, emp) {
    const l = db.prepare('SELECT * FROM lancamentos WHERE id=? AND empresa_id=?').get(id, emp);
    if (!l) throw new HttpError(404, 'Lançamento não encontrado.');
    return l;
  }

  function validaLanc(b, emp) {
    if (!contaVisivel(b.conta_id, emp)) throw new HttpError(400, 'Conta inválida.');
    if (!centroVisivel(b.centro_id, emp)) throw new HttpError(400, 'Centro de custo inválido.');
  }

  // ---------- Usuarios (FUseCad) ----------
  function salvarUsuarioApi(u, body, id) {
    exigir(u, 'config', COMPLETO);
    const alvo = id ? db.prepare('SELECT * FROM usuarios WHERE id=?').get(id) : null;
    if (id && !alvo) throw new HttpError(404, 'Usuário não encontrado.');
    if (!u.admin) {
      // Quem nao e administrador nao cria/edita administradores nem amplia acessos alem dos seus.
      if (alvo?.admin || Number(body.admin)) throw new HttpError(403, 'Somente um administrador pode gerenciar administradores.');
      const minhas = auth.empresasPermitidas(db, u);
      if (minhas) {
        if (Number(body.todas_empresas)) throw new HttpError(403, 'Você só pode liberar as contas controle a que tem acesso.');
        if ((body.empresas || []).some((e) => !minhas.includes(Number(e)))) throw new HttpError(403, 'Você só pode liberar as contas controle a que tem acesso.');
      }
    }
    return auth.salvarUsuario(db, body, id, u);
  }

  async function api(req, url, body, res) {
    const parts = url.pathname.split('/').filter(Boolean).slice(1); // remove "api"
    const [rec, idStr, acao] = parts;
    const id = idStr && /^\d+$/.test(idStr) ? Number(idStr) : null;
    const q = url.searchParams;
    const qo = Object.fromEntries(q);
    const m = req.method;
    const token = cookies(req)[COOKIE];

    // ---- Rotas publicas de autenticacao ----
    if (rec === 'auth') {
      const abre = ({ token: t, usuario }) => {
        res.setHeader('set-cookie', `${COOKIE}=${t}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200`);
        return usuario;
      };
      if (idStr === 'estado' && m === 'GET') {
        const u = auth.sessao(db, token);
        return { configurado: auth.existeUsuario(db), usuario: u ? auth.publico(db, u) : null };
      }
      if (idStr === 'setup' && m === 'POST') {
        auth.criarAdministrador(db, body);
        return abre(auth.login(db, body.email, body.senha));
      }
      if (idStr === 'login' && m === 'POST') return abre(auth.login(db, body.email, body.senha));
      if (idStr === 'logout' && m === 'POST') {
        if (token) auth.logout(db, token);
        res.setHeader('set-cookie', `${COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0`);
        return { ok: true };
      }
    }

    const u = auth.sessao(db, token);
    if (!u) throw new HttpError(401, 'Sessão expirada. Entre novamente.');

    if (rec === 'auth' && idStr === 'senha' && m === 'POST') { auth.alterarSenha(db, u, body.atual, body.nova); return { ok: true }; }

    if (rec === 'usuarios') {
      exigir(u, 'config', COMPLETO);
      if (m === 'GET' && !id) return auth.listarUsuarios(db);
      if (m === 'POST' && !id) return { id: salvarUsuarioApi(u, body) };
      if (m === 'PUT' && id) return { id: salvarUsuarioApi(u, body, id) };
      if (m === 'DELETE' && id) {
        const alvo = db.prepare('SELECT admin FROM usuarios WHERE id=?').get(id);
        if (alvo?.admin && !u.admin) throw new HttpError(403, 'Somente um administrador pode gerenciar administradores.');
        auth.excluirUsuario(db, id, u); return { ok: true };
      }
    }

    if (rec === 'empresas' && !id) {
      if (m === 'GET') return listar('empresas', null, q, u);
      if (m === 'POST') return { id: salvar('empresas', null, body, null, u) };
    }

    if (CADASTROS[rec]) {
      const emp = rec === 'empresas' ? null : empresaDe(req, url, u);
      if (rec === 'empresas' && id && !auth.podeEmpresa(db, u, id)) throw new HttpError(403, 'Seu usuário não tem acesso a esta conta controle.');
      if (rec === 'movbancarias' && m !== 'GET') {
        exigir(u, 'bancos', COMPLETO);
        const atual = id ? registro(rec, id, emp) : null;
        exigeDesbloqueio(req, u, emp, (lim) => (atual && atual.data <= lim) || (m !== 'DELETE' && String(body.data || fin.hoje()) <= lim));
      }
      if (rec === 'contas' && m === 'PUT' && id && 'saldo_inicial' in body) {
        exigir(u, 'bancos', COMPLETO);
        const atual = registro(rec, id, emp);
        exigeDesbloqueio(req, u, emp, () => Number(body.saldo_inicial || 0) !== Number(atual.saldo_inicial));
      }
      if (m === 'GET' && !id) return listar(rec, emp, q, u);
      if (m === 'POST' && !id) return { id: salvar(rec, emp, body, null, u) };
      if (m === 'PUT' && id) return { id: salvar(rec, emp, body, id, u) };
      if (m === 'DELETE' && id) { remover(rec, emp, id, u); return { ok: true }; }
    }

    const emp = empresaDe(req, url, u);
    const podeTipo = (t, min) => exigir(u, moduloDoTipo(t), min);
    const bloqueio = (afetado) => exigeDesbloqueio(req, u, emp, afetado);
    switch (rec) {
      case 'protecao':
        if (m === 'GET') return { bloqueio_ate: limiteBloqueio(emp) };
        if (m === 'PUT') {
          exigir(u, 'config', COMPLETO);
          const data = Number(body.ativo) ? String(body.data || '') : null;
          if (data !== null && !/^\d{4}-\d{2}-\d{2}$/.test(data)) throw new HttpError(400, 'Informe a data de bloqueio.');
          db.prepare('UPDATE empresas SET bloqueio_ate=? WHERE id=?').run(data, emp);
          return { bloqueio_ate: data };
        }
        break;
      case 'lancamentos': {
        if (m === 'GET' && !id) {
          if (qo.tipo) { podeTipo(qo.tipo, CONSULTA); return fin.listarLancamentos(db, emp, qo); }
          const vis = tiposVisiveis(u);
          return fin.listarLancamentos(db, emp, qo).filter((l) => vis.includes(l.tipo));
        }
        if (!id) {
          if (m === 'POST') {
            podeTipo(body.tipo, COMPLETO); validaLanc(body, emp);
            bloqueio((lim) => lancNoPeriodo(body, lim));
            return { id: fin.salvarLancamento(db, emp, body) };
          }
          break;
        }
        const l = lancamento(id, emp);
        if (m === 'GET') { podeTipo(l.tipo, CONSULTA); return l; }
        podeTipo(l.tipo, COMPLETO);
        if (m === 'PUT') {
          podeTipo(body.tipo, COMPLETO); validaLanc(body, emp);
          bloqueio((lim) => lancNoPeriodo(l, lim) || lancNoPeriodo(body, lim));
          return { id: fin.salvarLancamento(db, emp, body, id) };
        }
        if (m === 'DELETE') {
          const modo = q.get('modo') || 'esta';
          const afetados = !l.grupo || modo === 'esta' ? [l]
            : modo === 'seguintes' ? db.prepare('SELECT * FROM lancamentos WHERE grupo=? AND parcela>=? AND excluido_em IS NULL').all(l.grupo, l.parcela)
              : db.prepare("SELECT * FROM lancamentos WHERE grupo=? AND situacao='P' AND excluido_em IS NULL").all(l.grupo);
          bloqueio((lim) => afetados.some((x) => lancNoPeriodo(x, lim)));
          return { excluidos: fin.excluir(db, emp, id, modo) };
        }
        if (m === 'POST' && acao === 'baixar') {
          validaLanc(body, emp);
          bloqueio((lim) => lancNoPeriodo(l, lim) || (body.data_pagamento || fin.hoje()) <= lim);
          return { baixados: fin.baixar(db, emp, [id], body) };
        }
        if (m === 'POST' && acao === 'estornar') { bloqueio((lim) => lancNoPeriodo(l, lim)); return { estornados: fin.estornar(db, emp, id) }; }
        if (m === 'POST' && acao === 'restaurar') { bloqueio((lim) => lancNoPeriodo(l, lim)); return { restaurados: fin.restaurar(db, emp, id) }; }
        break;
      }
      case 'parcelar':
        if (m === 'POST') {
          podeTipo(body.tipo, COMPLETO); validaLanc(body, emp);
          // parcelas nascem em aberto: so a data de movimento conta (a 1a parcela tem a menor)
          const mov = body.mov_igual_vencimento ? body.vencimento || body.data_mov : body.data_mov;
          bloqueio((lim) => String(mov || fin.hoje()) <= lim);
          return { ids: fin.parcelar(db, emp, body) };
        }
        break;
      case 'baixa-multipla':
        if (m === 'POST') {
          const ids = (body.ids || []).map(Number);
          const ls = ids.map((i) => lancamento(i, emp));
          for (const l of ls) podeTipo(l.tipo, COMPLETO);
          validaLanc(body, emp);
          bloqueio((lim) => (body.data_pagamento || fin.hoje()) <= lim || ls.some((l) => lancNoPeriodo(l, lim)));
          return { baixados: fin.baixar(db, emp, ids, body) };
        }
        break;
      case 'transferir-empresa':
        if (m === 'POST') {
          const destino = Number(body.empresa_destino);
          if (!db.prepare('SELECT 1 FROM empresas WHERE id=?').get(destino)) throw new HttpError(400, 'Conta controle de destino inválida.');
          if (!auth.podeEmpresa(db, u, destino)) throw new HttpError(403, 'Seu usuário não tem acesso à conta controle de destino.');
          const ids = (body.ids || []).map(Number);
          const ls = ids.map((i) => lancamento(i, emp));
          for (const l of ls) podeTipo(l.tipo, COMPLETO);
          bloqueio((lim) => ls.some((l) => lancNoPeriodo(l, lim)));
          exigeDesbloqueio(req, u, destino, (lim) => ls.some((l) => lancNoPeriodo(l, lim)));
          const up = db.prepare('UPDATE lancamentos SET empresa_id=?, centro_id=NULL WHERE id=? AND empresa_id=?');
          return { transferidos: ids.reduce((n, i) => n + up.run(destino, i, emp).changes, 0) };
        }
        break;
      case 'excluidos': {
        const vis = tiposVisiveis(u);
        return db.prepare(`SELECT * FROM lancamentos WHERE empresa_id=? AND excluido_em IS NOT NULL ORDER BY excluido_em DESC LIMIT 500`).all(emp).filter((l) => vis.includes(l.tipo));
      }
      case 'saldos':
        if (nivel(u, 'bancos') < CONSULTA && nivel(u, 'fluxo') < CONSULTA) exigir(u, 'bancos', CONSULTA);
        return fin.saldos(db, emp, q.get('data') || undefined);
      case 'dashboard': exigir(u, 'fluxo', CONSULTA); return fin.dashboard(db, emp, qo);
      case 'linear': exigir(u, 'fluxo', CONSULTA); return fin.linear(db, emp, qo);
      case 'lembretes': {
        const vis = tiposVisiveis(u);
        return fin.lembretes(db, emp, q.get('dias') || 7).filter((l) => vis.includes(l.tipo));
      }
      case 'relatorios': {
        if (!idStr) return fin.RELATORIOS;
        const mod = MODULO_RELATORIO[idStr];
        if (idStr === 'analitico') {
          // "Todos" exige consulta a despesas e a receitas
          for (const t of qo.tipo === 'D' || qo.tipo === 'R' ? [qo.tipo] : ['D', 'R']) podeTipo(t, CONSULTA);
          if (!centroVisivel(qo.centro_id, emp) || !contaVisivel(qo.conta_id, emp)) throw new HttpError(400, 'Filtro inválido.');
        } else if (mod === 'tipo') podeTipo(qo.tipo === 'R' ? 'R' : 'D', CONSULTA);
        else if (mod) exigir(u, mod, CONSULTA);
        if (idStr === 'extrato' && !contaVisivel(qo.conta_id, emp)) throw new HttpError(400, 'Conta inválida.');
        return fin.relatorio(db, emp, idStr, qo);
      }
      case 'graficos': {
        if (idStr === 'desp_rec') { podeTipo('D', CONSULTA); podeTipo('R', CONSULTA); }
        else {
          podeTipo(qo.tipo === 'R' ? 'R' : 'D', CONSULTA);
          if (idStr === 'composicao' && qo.agrupar === 'centro') exigir(u, 'centros', CONSULTA);
        }
        return fin.grafico(db, emp, idStr, qo);
      }
      case 'ofx': {
        if (!contaVisivel(body.conta_id, emp)) throw new HttpError(400, 'Conta inválida.');
        if (m === 'POST' && idStr === 'analisar') { exigir(u, 'bancos', CONSULTA); return fin.analisarOfx(db, emp, Number(body.conta_id), body.texto || ''); }
        if (m === 'POST' && idStr === 'aplicar') {
          exigir(u, 'bancos', COMPLETO);
          const linhas = body.linhas || [];
          for (const l of linhas) if (l.acao !== 'ignorar') podeTipo(l.tipo, COMPLETO);
          for (const l of linhas) if (l.acao === 'baixar' && l.lancamento) lancamento(Number(l.lancamento.id), emp);
          bloqueio((lim) => linhas.some((l) => ['incluir', 'baixar'].includes(l.acao) && String(l.data) <= lim));
          return fin.aplicarOfx(db, emp, Number(body.conta_id), linhas);
        }
        break;
      }
    }
    throw new HttpError(404, 'Rota não encontrada.');
  }

  return async function handler(req, res) {
    const url = new URL(req.url, 'http://localhost');
    try {
      if (url.pathname.startsWith('/api/')) {
        let body = {};
        if (['POST', 'PUT', 'DELETE'].includes(req.method)) {
          // Exigir JSON impede que um formulario de outro site dispare acoes (CSRF).
          if (req.method !== 'DELETE' && !String(req.headers['content-type'] || '').startsWith('application/json'))
            throw new HttpError(415, 'Envie os dados em JSON.');
          const chunks = [];
          let size = 0;
          for await (const c of req) { size += c.length; if (size > 20e6) throw new HttpError(413, 'Requisição muito grande.'); chunks.push(c); }
          const raw = Buffer.concat(chunks).toString('utf8');
          try { body = raw ? JSON.parse(raw) : {}; } catch { throw new HttpError(400, 'JSON inválido.'); }
        }
        const out = await api(req, url, body, res);
        res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
        return res.end(JSON.stringify(out ?? null));
      }
      const rel = normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, '') || 'index.html';
      if (rel.startsWith('..')) throw new HttpError(403, 'Proibido.');
      const file = join(PUBLIC, rel);
      const data = await readFile(file).catch(() => readFile(join(PUBLIC, 'index.html')));
      res.writeHead(200, { 'content-type': MIME[extname(file)] || 'text/html; charset=utf-8', 'cache-control': 'no-cache' });
      res.end(data);
    } catch (e) {
      const status = e.status || (e.message?.includes('constraint') ? 409 : 400);
      res.writeHead(status, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ erro: e.message, ...(e.extra || {}) }));
    }
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dbFile = process.env.MCC_DB || fileURLToPath(new URL('../dados/mcc.db', import.meta.url));
  const port = Number(process.env.PORT) || 5180;
  const db = openDb(dbFile);
  createServer(criarApp(db)).listen(port, '127.0.0.1', () => {
    console.log(`MCC clone rodando em http://localhost:${port}  (banco: ${dbFile})`);
  });
}
