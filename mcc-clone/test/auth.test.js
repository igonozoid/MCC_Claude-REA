import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { openDb } from '../src/db.js';
import { criarApp } from '../src/server.js';

let srv, base;
before(async () => {
  srv = createServer(criarApp(openDb(':memory:')));
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  base = `http://127.0.0.1:${srv.address().port}/api/`;
});
after(() => srv.close());

// Cliente com cookie de sessao proprio.
function cliente() {
  let cookie = '';
  return async (path, { method = 'GET', body, empresa } = {}) => {
    const r = await fetch(base + path, {
      method,
      headers: { 'content-type': 'application/json', ...(cookie ? { cookie } : {}), ...(empresa ? { 'x-empresa': String(empresa) } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const sc = r.headers.get('set-cookie');
    if (sc) cookie = sc.split(';')[0];
    return { status: r.status, json: await r.json() };
  };
}

const admin = cliente();
let emp1, emp2, despesaId, receitaId;

test('primeiro acesso cria o administrador e exige login no resto', async () => {
  const anon = cliente();
  assert.equal((await anon('auth/estado')).json.configurado, false);
  assert.equal((await anon('empresas')).status, 401);
  const r = await admin('auth/setup', { method: 'POST', body: { nome: 'Admin', email: 'Admin@Teste.com', senha: 'segredo1' } });
  assert.equal(r.status, 200);
  assert.equal(r.json.admin, true);
  assert.equal((await anon('auth/setup', { method: 'POST', body: { nome: 'X', email: 'x@x.com', senha: 'segredo1' } })).status, 409);
  emp1 = (await admin('empresas', { method: 'POST', body: { nome: 'Empresa 1' } })).json.id;
  emp2 = (await admin('empresas', { method: 'POST', body: { nome: 'Empresa 2' } })).json.id;
  despesaId = (await admin('lancamentos', { method: 'POST', empresa: emp1, body: { tipo: 'D', descricao: 'Luz', valor: 50 } })).json.id;
  receitaId = (await admin('lancamentos', { method: 'POST', empresa: emp1, body: { tipo: 'R', descricao: 'Venda', valor: 90 } })).json.id;
});

test('login: senha errada, e-mail sem diferenciar maiusculas, bloqueio por tentativas', async () => {
  const c = cliente();
  assert.equal((await c('auth/login', { method: 'POST', body: { email: 'admin@teste.com', senha: 'errada' } })).status, 401);
  assert.equal((await c('auth/login', { method: 'POST', body: { email: 'ADMIN@teste.com', senha: 'segredo1' } })).status, 200);
  const b = cliente();
  for (let i = 0; i < 5; i++) await b('auth/login', { method: 'POST', body: { email: 'ninguem@x.com', senha: 'x' } });
  assert.equal((await b('auth/login', { method: 'POST', body: { email: 'ninguem@x.com', senha: 'x' } })).status, 429);
});

test('somente consulta em despesas, sem acesso a receitas, restrito a uma empresa', async () => {
  const r = await admin('usuarios', { method: 'POST', body: {
    nome: 'Joana', email: 'joana@teste.com', senha: 'senha123', perm_despesas: 1, perm_receitas: 0,
    perm_bancos: 0, perm_centros: 2, perm_fluxo: 0, perm_config: 0, todas_empresas: 0, empresas: [emp1] } });
  assert.equal(r.status, 200);
  const j = cliente();
  const login = await j('auth/login', { method: 'POST', body: { email: 'joana@teste.com', senha: 'senha123' } });
  assert.deepEqual(login.json.perms, { config: 0, despesas: 1, receitas: 0, centros: 2, bancos: 0, fluxo: 0 });

  // empresas: so enxerga a liberada
  assert.deepEqual((await j('empresas')).json.map((e) => e.id), [emp1]);
  assert.equal((await j('lancamentos?tipo=D', { empresa: emp2 })).status, 403);

  // despesas: le, mas nao grava
  assert.equal((await j('lancamentos?tipo=D', { empresa: emp1 })).json.length, 1);
  assert.equal((await j(`lancamentos/${despesaId}`, { empresa: emp1 })).status, 200);
  assert.equal((await j('lancamentos', { method: 'POST', empresa: emp1, body: { tipo: 'D', descricao: 'X', valor: 1 } })).status, 403);
  assert.equal((await j(`lancamentos/${despesaId}/baixar`, { method: 'POST', empresa: emp1, body: {} })).status, 403);
  assert.equal((await j(`lancamentos/${despesaId}`, { method: 'DELETE', empresa: emp1 })).status, 403);

  // receitas: nada; lista sem tipo filtra; itens/relatorios/lembretes idem
  assert.equal((await j('lancamentos?tipo=R', { empresa: emp1 })).status, 403);
  assert.equal((await j(`lancamentos/${receitaId}`, { empresa: emp1 })).status, 403);
  assert.deepEqual((await j('lancamentos', { empresa: emp1 })).json.map((l) => l.tipo), ['D']);
  assert.ok((await j('itens', { empresa: emp1 })).json.every((i) => i.tipo === 'D'));
  assert.equal((await j('relatorios/totais_item?tipo=R', { empresa: emp1 })).status, 403);
  assert.equal((await j('relatorios/totais_item?tipo=D', { empresa: emp1 })).status, 200);

  // outros modulos
  assert.equal((await j('dashboard', { empresa: emp1 })).status, 403);
  assert.equal((await j('saldos', { empresa: emp1 })).status, 403);
  assert.equal((await j('movbancarias', { empresa: emp1 })).status, 403);
  assert.equal((await j('contas', { method: 'POST', empresa: emp1, body: { descricao: 'X' } })).status, 403);
  assert.equal((await j('centros', { method: 'POST', empresa: emp1, body: { nome: 'Obra' } })).status, 200);
  assert.equal((await j('usuarios')).status, 403);
  assert.equal((await j('empresas', { method: 'POST', body: { nome: 'Nova' } })).status, 403);
  // cliente pertence a receitas, fornecedor a despesas (consulta)
  assert.equal((await j('pessoas', { method: 'POST', empresa: emp1, body: { tipo: 'C', nome: 'Cli' } })).status, 403);
  assert.equal((await j('pessoas', { method: 'POST', empresa: emp1, body: { tipo: 'F', nome: 'For' } })).status, 403);
});

test('desativar usuario derruba a sessao; protecao do ultimo administrador', async () => {
  const lista = (await admin('usuarios')).json;
  const joana = lista.find((u) => u.email === 'joana@teste.com');
  const adm = lista.find((u) => u.admin);
  const j = cliente();
  await j('auth/login', { method: 'POST', body: { email: 'joana@teste.com', senha: 'senha123' } });
  assert.equal((await admin('usuarios/' + joana.id, { method: 'PUT', body: { ativo: 0 } })).status, 200);
  assert.equal((await j('empresas')).status, 401);
  assert.equal((await j('auth/login', { method: 'POST', body: { email: 'joana@teste.com', senha: 'senha123' } })).status, 403);
  assert.equal((await admin('usuarios/' + adm.id, { method: 'PUT', body: { admin: 0 } })).status, 400);
  assert.equal((await admin('usuarios/' + adm.id, { method: 'DELETE' })).status, 400);
  assert.equal((await admin('usuarios', { method: 'POST', body: { nome: 'Dup', email: 'JOANA@teste.com', senha: 'senha123' } })).status, 409);
});

test('usuario de configuracoes (nao admin) nao cria administrador nem amplia acesso', async () => {
  await admin('usuarios', { method: 'POST', body: { nome: 'Gerente', email: 'ger@teste.com', senha: 'senha123', perm_config: 2, todas_empresas: 0, empresas: [emp1] } });
  const g = cliente();
  await g('auth/login', { method: 'POST', body: { email: 'ger@teste.com', senha: 'senha123' } });
  assert.equal((await g('usuarios', { method: 'POST', body: { nome: 'A', email: 'a@t.com', senha: 'senha123', admin: 1 } })).status, 403);
  assert.equal((await g('usuarios', { method: 'POST', body: { nome: 'A', email: 'a@t.com', senha: 'senha123', todas_empresas: 1 } })).status, 403);
  assert.equal((await g('usuarios', { method: 'POST', body: { nome: 'A', email: 'a@t.com', senha: 'senha123', todas_empresas: 0, empresas: [emp2] } })).status, 403);
  assert.equal((await g('usuarios', { method: 'POST', body: { nome: 'A', email: 'a@t.com', senha: 'senha123', todas_empresas: 0, empresas: [emp1] } })).status, 200);
  // cria uma empresa e passa a ter acesso a ela
  const nova = (await g('empresas', { method: 'POST', body: { nome: 'Filial' } })).json.id;
  assert.ok((await g('empresas')).json.some((e) => e.id === nova));
});

test('troca de senha e logout', async () => {
  const c = cliente();
  await c('auth/login', { method: 'POST', body: { email: 'ger@teste.com', senha: 'senha123' } });
  assert.equal((await c('auth/senha', { method: 'POST', body: { atual: 'errada', nova: 'nova1234' } })).status, 400);
  assert.equal((await c('auth/senha', { method: 'POST', body: { atual: 'senha123', nova: 'curta' } })).status, 400);
  assert.equal((await c('auth/senha', { method: 'POST', body: { atual: 'senha123', nova: 'nova1234' } })).status, 200);
  await c('auth/logout', { method: 'POST' });
  assert.equal((await c('empresas')).status, 401);
  assert.equal((await c('auth/login', { method: 'POST', body: { email: 'ger@teste.com', senha: 'nova1234' } })).status, 200);
});

test('requisicoes de escrita sem JSON sao recusadas (CSRF)', async () => {
  const r = await fetch(base + 'auth/login', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: 'email=a&senha=b' });
  assert.equal(r.status, 415);
});
