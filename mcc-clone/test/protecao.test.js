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

function cliente() {
  let cookie = '';
  return async (path, { method = 'GET', body, empresa = emp, senha } = {}) => {
    const r = await fetch(base + path, {
      method,
      headers: { 'content-type': 'application/json', ...(cookie ? { cookie } : {}), ...(empresa ? { 'x-empresa': String(empresa) } : {}),
        ...(senha !== undefined ? { 'x-desbloqueio': encodeURIComponent(senha) } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const sc = r.headers.get('set-cookie');
    if (sc) cookie = sc.split(';')[0];
    return { status: r.status, json: await r.json() };
  };
}

const adm = cliente(), op = cliente();
let emp, banco, antigo, pagoAntigo, abertoAntigo, recente;

test('preparacao: dados antes e depois da data de bloqueio', async () => {
  await adm('auth/setup', { method: 'POST', empresa: null, body: { nome: 'Admin', email: 'adm@t.com', senha: 'Senha-Ádmin1' } });
  emp = (await adm('empresas', { method: 'POST', empresa: null, body: { nome: 'E1' } })).json.id;
  banco = (await adm('contas', { method: 'POST', body: { descricao: 'BANCO', saldo_inicial: 100 } })).json.id;
  const L = (b) => adm('lancamentos', { method: 'POST', body: { tipo: 'D', descricao: 'X', valor: 10, conta_id: banco, ...b } }).then((r) => r.json.id);
  antigo = await L({ data_mov: '2025-01-10', vencimento: '2025-01-20' });                                   // movimento no periodo
  pagoAntigo = await L({ data_mov: '2025-02-10', vencimento: '2025-02-10', situacao: 'V', data_pagamento: '2025-02-10' });
  abertoAntigo = await L({ data_mov: '2025-04-01', vencimento: '2025-02-15' });                             // vencido mas movimento depois
  recente = await L({ data_mov: '2025-04-05', vencimento: '2025-04-30' });
  await adm('usuarios', { method: 'POST', empresa: null, body: { nome: 'Op', email: 'op@t.com', senha: 'senha123' } });
  await op('auth/login', { method: 'POST', empresa: null, body: { email: 'op@t.com', senha: 'senha123' } });
});

test('somente configuracoes define a protecao', async () => {
  assert.equal((await op('protecao', { method: 'PUT', body: { ativo: 1, data: '2025-03-31' } })).status, 403);
  assert.equal((await adm('protecao', { method: 'PUT', body: { ativo: 1, data: 'ontem' } })).status, 400);
  assert.deepEqual((await adm('protecao', { method: 'PUT', body: { ativo: 1, data: '2025-03-31' } })).json, { bloqueio_ate: '2025-03-31' });
  assert.equal((await op('protecao')).json.bloqueio_ate, '2025-03-31');
  assert.equal((await op('empresas', { empresa: null })).json[0].bloqueio_ate, '2025-03-31');
});

test('lancamentos do periodo protegido sao recusados com 423 e a data', async () => {
  const r = await op(`lancamentos/${antigo}`, { method: 'PUT', body: { tipo: 'D', descricao: 'Y', valor: 11, data_mov: '2025-01-10', vencimento: '2025-01-20' } });
  assert.equal(r.status, 423);
  assert.equal(r.json.bloqueio_ate, '2025-03-31');
  assert.match(r.json.erro, /bloqueadas até 31\/03\/2025/);
  assert.equal((await op(`lancamentos/${antigo}`, { method: 'DELETE' })).status, 423);
  assert.equal((await op(`lancamentos/${pagoAntigo}/estornar`, { method: 'POST', body: {} })).status, 423);
  assert.equal((await op('lancamentos', { method: 'POST', body: { tipo: 'R', descricao: 'Retroativo', valor: 5, data_mov: '2025-03-31' } })).status, 423);
  // mover um lancamento recente para dentro do periodo tambem e bloqueado
  assert.equal((await op(`lancamentos/${recente}`, { method: 'PUT', body: { tipo: 'D', descricao: 'X', valor: 10, data_mov: '2025-03-01', vencimento: '2025-04-30' } })).status, 423);
  // baixar com data de pagamento dentro do periodo
  assert.equal((await op(`lancamentos/${abertoAntigo}/baixar`, { method: 'POST', body: { data_pagamento: '2025-03-15' } })).status, 423);
  assert.equal((await op('parcelar', { method: 'POST', body: { tipo: 'D', descricao: 'P', valor: 1, parcelas: 2, data_mov: '2025-03-01', vencimento: '2025-05-01' } })).status, 423);
  assert.equal((await op('baixa-multipla', { method: 'POST', body: { ids: [abertoAntigo, recente], data_pagamento: '2025-03-30' } })).status, 423);
});

test('fora do periodo continua livre', async () => {
  assert.equal((await op(`lancamentos/${abertoAntigo}/baixar`, { method: 'POST', body: { data_pagamento: '2025-04-02' } })).status, 200);
  assert.equal((await op(`lancamentos/${recente}`, { method: 'PUT', body: { tipo: 'D', descricao: 'Z', valor: 12, data_mov: '2025-04-05', vencimento: '2025-04-30' } })).status, 200);
  assert.equal((await op('lancamentos', { method: 'POST', body: { tipo: 'R', descricao: 'Nova', valor: 5, data_mov: '2025-04-01' } })).status, 200);
});

test('caixa: movimentacoes e saldo inicial protegidos', async () => {
  const caixa = (await adm('contas', { method: 'POST', body: { descricao: 'CAIXA', tipo: 'C' } })).json.id;
  assert.equal((await op('movbancarias', { method: 'POST', body: { tipo: 'T', data: '2025-03-10', origem_id: banco, destino_id: caixa, valor: 5 } })).status, 423);
  assert.equal((await op('movbancarias', { method: 'POST', body: { tipo: 'T', data: '2025-04-10', origem_id: banco, destino_id: caixa, valor: 5 } })).status, 200);
  assert.equal((await op(`contas/${banco}`, { method: 'PUT', body: { descricao: 'BANCO', saldo_inicial: 999 } })).status, 423);
  assert.equal((await op(`contas/${banco}`, { method: 'PUT', body: { descricao: 'BANCO NOVO NOME', saldo_inicial: 100 } })).status, 200);
});

test('senha de desbloqueio: errada recusa, do administrador libera so aquela operacao', async () => {
  const errada = await op(`lancamentos/${antigo}`, { method: 'DELETE', senha: 'senha123' }); // senha do proprio operador nao vale
  assert.equal(errada.status, 423);
  assert.equal(errada.json.senha_incorreta, true);
  assert.equal((await op(`lancamentos/${antigo}`, { method: 'DELETE', senha: 'Senha-Ádmin1' })).status, 200);
  assert.equal((await op(`lancamentos/${pagoAntigo}/estornar`, { method: 'POST', body: {} })).status, 423);
});

test('desativar a protecao libera tudo', async () => {
  await adm('protecao', { method: 'PUT', body: { ativo: 0 } });
  assert.equal((await op(`lancamentos/${pagoAntigo}/estornar`, { method: 'POST', body: {} })).status, 200);
});
