import { test } from 'node:test';
import assert from 'node:assert/strict';
import { openDb } from '../src/db.js';
import * as fin from '../src/finance.js';

function setup() {
  const db = openDb(':memory:');
  const emp = Number(db.prepare("INSERT INTO empresas (nome) VALUES ('Teste')").run().lastInsertRowid);
  const banco = Number(db.prepare("INSERT INTO contas (empresa_id, descricao, saldo_inicial) VALUES (?, 'BANCO', 1000)").run(emp).lastInsertRowid);
  const caixa = Number(db.prepare("INSERT INTO contas (empresa_id, descricao, tipo) VALUES (?, 'CAIXA', 'C')").run(emp).lastInsertRowid);
  return { db, emp, banco, caixa };
}

test('periodos do filtro principal', () => {
  assert.deepEqual(fin.periodo(2025, '2'), ['2025-02-01', '2025-02-28']);
  assert.deepEqual(fin.periodo(2024, '2'), ['2024-02-01', '2024-02-29']);
  assert.deepEqual(fin.periodo(2025, 'T3'), ['2025-07-01', '2025-09-30']);
  assert.deepEqual(fin.periodo(2025, 'S2'), ['2025-07-01', '2025-12-31']);
  assert.deepEqual(fin.periodo(2025, 'ANO'), ['2025-01-01', '2025-12-31']);
  assert.equal(fin.periodo(2025, 'TODOS'), null);
});

test('lancamento, baixa e saldo', () => {
  const { db, emp, banco } = setup();
  const d = fin.salvarLancamento(db, emp, { tipo: 'D', descricao: 'Aluguel', pessoa: 'Imob', valor: 300, vencimento: '2025-01-10', conta_id: banco });
  fin.salvarLancamento(db, emp, { tipo: 'R', descricao: 'Venda', valor: 500, situacao: 'V', vencimento: '2025-01-05', conta_id: banco });
  let s = fin.saldos(db, emp, '2025-01-31').find((c) => c.id === banco);
  assert.equal(s.saldo, 1500);
  assert.equal(s.previsto, 1200);
  assert.equal(fin.baixar(db, emp, [d], { data_pagamento: '2025-01-12' }), 1);
  s = fin.saldos(db, emp, '2025-01-31').find((c) => c.id === banco);
  assert.equal(s.saldo, 1200);
  // descricao e pessoa novas sao cadastradas automaticamente
  assert.ok(db.prepare("SELECT 1 FROM itens WHERE descricao='Aluguel' AND tipo='D'").get());
  assert.ok(db.prepare("SELECT 1 FROM pessoas WHERE nome='Imob' AND tipo='F'").get());
});

test('validacoes do lancamento', () => {
  const { db, emp } = setup();
  assert.throws(() => fin.salvarLancamento(db, emp, { tipo: 'D', descricao: 'X', valor: 0 }), /valor/);
  assert.throws(() => fin.salvarLancamento(db, emp, { tipo: 'D', valor: 10 }), /descrição/);
  assert.throws(() => fin.salvarLancamento(db, emp, { tipo: 'X', descricao: 'X', valor: 10 }), /Tipo/);
});

test('parcelamento mensal respeita fim de mes e exclusao por grupo', () => {
  const { db, emp } = setup();
  const ids = fin.parcelar(db, emp, { tipo: 'D', descricao: 'Carro', valor: 100, vencimento: '2025-01-31', parcelas: 4, periodicidade: 'mensal', documento: 'NF1' });
  const ls = db.prepare('SELECT vencimento, documento FROM lancamentos ORDER BY parcela').all();
  assert.deepEqual(ls.map((l) => l.vencimento), ['2025-01-31', '2025-02-28', '2025-03-31', '2025-04-30']);
  assert.equal(ls[1].documento, 'NF1 2/4');
  fin.baixar(db, emp, [ids[0]]);
  assert.equal(fin.excluir(db, emp, ids[2], 'seguintes'), 2);
  assert.equal(fin.excluir(db, emp, ids[1], 'abertas'), 1);
  assert.equal(db.prepare('SELECT COUNT(*) n FROM lancamentos WHERE excluido_em IS NULL').get().n, 1);
});

test('transferencia entre contas afeta os dois saldos', () => {
  const { db, emp, banco, caixa } = setup();
  db.prepare("INSERT INTO movbancarias (empresa_id, tipo, data, origem_id, destino_id, valor) VALUES (?, 'T', '2025-01-02', ?, ?, 200)").run(emp, banco, caixa);
  db.prepare("INSERT INTO movbancarias (empresa_id, tipo, situacao, data, origem_id, valor) VALUES (?, 'D', 'P', '2025-01-03', ?, 50)").run(emp, caixa);
  const s = fin.saldos(db, emp, '2025-01-31');
  assert.equal(s.find((c) => c.id === banco).saldo, 800);
  assert.equal(s.find((c) => c.id === caixa).saldo, 200);
  assert.equal(s.find((c) => c.id === caixa).previsto, 250);
});

test('filtros e relatorios', () => {
  const { db, emp, banco } = setup();
  fin.salvarLancamento(db, emp, { tipo: 'D', descricao: 'Luz', valor: 80, data_mov: '2025-03-01', vencimento: '2025-03-10', situacao: 'V', data_pagamento: '2025-03-12', conta_id: banco });
  fin.salvarLancamento(db, emp, { tipo: 'D', descricao: 'Luz', valor: 90, data_mov: '2025-04-01', vencimento: '2025-04-10' });
  assert.equal(fin.listarLancamentos(db, emp, { tipo: 'D', ano: 2025, mes: '3' }).length, 1);
  assert.equal(fin.listarLancamentos(db, emp, { tipo: 'D', situacao: 'P' }).length, 1);
  assert.equal(fin.listarLancamentos(db, emp, { tipo: 'D', busca: 'luz' }).length, 2);
  const tot = fin.relatorio(db, emp, 'totais_item', { tipo: 'D' });
  assert.equal(tot.linhas[0].total, 170);
  const dem = fin.relatorio(db, emp, 'demonstrativo', { tipo: 'D', ano: 2025 });
  assert.equal(dem.linhas[0].Mar, 80);
  assert.equal(dem.linhas[0].Abr, 90);
  const pont = fin.relatorio(db, emp, 'pontualidade', { tipo: 'D' });
  assert.equal(pont.linhas[0].maior_atraso, 2);
  const ext = fin.relatorio(db, emp, 'extrato', { conta_id: banco, de: '2025-03-01', ate: '2025-03-31' });
  assert.equal(ext.linhas.at(-1).saldo, 920);
});

test('importacao OFX: novo, baixa de aberto e duplicidade', () => {
  const { db, emp, banco } = setup();
  fin.salvarLancamento(db, emp, { tipo: 'D', descricao: 'Internet', valor: 99.9, vencimento: '2025-05-10', conta_id: banco });
  const ofx = `OFXHEADER:100\n<OFX><BANKTRANLIST>
    <STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20250511120000<TRNAMT>-99.90<FITID>A1<MEMO>PAG INTERNET</STMTTRN>
    <STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20250512<TRNAMT>250.00<FITID>A2<MEMO>PIX RECEBIDO</STMTTRN>
  </BANKTRANLIST></OFX>`;
  const a = fin.analisarOfx(db, emp, banco, ofx);
  assert.deepEqual(a.map((l) => l.status), ['em_aberto', 'novo']);
  assert.deepEqual(fin.aplicarOfx(db, emp, banco, a), { incluidos: 1, baixados: 1, conciliados: 0 });
  assert.equal(fin.saldos(db, emp, '2025-05-31')[0].saldo, 1000 - 99.9 + 250);
  assert.deepEqual(fin.analisarOfx(db, emp, banco, ofx).map((l) => l.status), ['importado', 'importado']);
});

test('relatorio analitico: descritivo com grupos, totalizado e filtros', () => {
  const { db, emp, banco, caixa } = setup();
  const L = (b) => fin.salvarLancamento(db, emp, { tipo: 'D', valor: 10, conta_id: banco, ...b });
  L({ descricao: 'Luz', pessoa: 'EDP', valor: 100, data_mov: '2025-01-05' });
  L({ descricao: 'Luz', pessoa: 'EDP', valor: 120, data_mov: '2025-02-05', situacao: 'V' });
  L({ descricao: 'Água', pessoa: 'Cesan', valor: 50, data_mov: '2025-01-07', conta_id: caixa });
  L({ tipo: 'R', descricao: 'Venda', pessoa: 'Cliente A', valor: 1000, data_mov: '2025-01-10' });

  // descritivo agrupado por tipo e item: cabecalhos, subtotais e total geral sem dupla contagem
  const d = fin.analitico(db, emp, { agrupar1: 'tipo', agrupar2: 'item' });
  const grupos = d.linhas.filter((l) => l._tipo === 'grupo').map((l) => l.data_mov);
  // ordem alfabetica em portugues: "Água" antes de "Luz"
  assert.deepEqual(grupos, ['Tipo: Despesas', 'Descrição: Água', 'Descrição: Luz', 'Tipo: Receitas', 'Descrição: Venda']);
  assert.deepEqual(d.totais, { receitas: 1000, despesas: 270, saldo: 730 });
  const subLuz = d.linhas.find((l) => l._tipo === 'subtotal' && l.descricao.startsWith('Subtotal Luz'));
  assert.equal(subLuz.despesas, 220);

  // totalizado por mes, so despesas pagas/abertas
  const t = fin.analitico(db, emp, { modo: 'totalizado', tipo: 'D', agrupar1: 'mes' });
  assert.deepEqual(t.linhas.map((l) => [l.g0, l.total]), [['Jan/2025', 150], ['Fev/2025', 120]]);
  assert.equal(t.totais.total, 270);

  // dois niveis no totalizado gera subtotal; filtros de pessoa e conta
  const t2 = fin.analitico(db, emp, { modo: 'totalizado', tipo: 'D', agrupar1: 'conta', agrupar2: 'item' });
  assert.equal(t2.linhas.filter((l) => l._tipo === 'subtotal').length, 2);
  assert.equal(t2.totais.total, 270);
  assert.equal(fin.analitico(db, emp, { tipo: 'D', pessoa: 'edp' }).totais.total, 220);
  assert.equal(fin.analitico(db, emp, { tipo: 'D', conta_id: caixa }).totais.total, 50);
  assert.equal(fin.analitico(db, emp, { tipo: 'D', situacao: 'V' }).totais.total, 120);
  // agrupamento desconhecido e ignorado (nunca vira SQL)
  assert.doesNotThrow(() => fin.analitico(db, emp, { agrupar1: "x'); DROP TABLE lancamentos;--" }));
  assert.throws(() => fin.analitico(db, emp, { modo: 'totalizado' }), /agrupamento/);
});

test('graficos gerenciais: despesas x receitas, composicao e evolucao', () => {
  const { db, emp } = setup();
  const L = (b) => fin.salvarLancamento(db, emp, { tipo: 'D', valor: 10, ...b });
  L({ descricao: 'Luz', pessoa: 'EDP', valor: 100, data_mov: '2025-01-05' });
  L({ descricao: 'Luz', pessoa: 'EDP', valor: 140, data_mov: '2025-03-05' });
  L({ descricao: 'Água', valor: 60, data_mov: '2025-01-07' });
  L({ tipo: 'R', descricao: 'Venda', valor: 500, data_mov: '2025-01-10' });
  const q = { de: '2025-01-01', ate: '2025-03-31' };
  const dr = fin.grafico(db, emp, 'desp_rec', q);
  assert.deepEqual(dr.pontos.map((p) => p.rotulo), ['Jan/2025', 'Fev/2025', 'Mar/2025']);
  assert.deepEqual(dr.pontos[0].valores, [500, 160]);
  assert.equal(dr.pontos[0].margem, 340);
  const comp = fin.grafico(db, emp, 'composicao', { ...q, tipo: 'D', agrupar: 'item' });
  assert.deepEqual(comp.pontos.map((p) => [p.rotulo, p.valor, p.perc]), [['Luz', 240, 80], ['Água', 60, 20]]);
  const ev = fin.grafico(db, emp, 'evolucao', { ...q, tipo: 'D', agrupar: 'pessoa', valor: 'EDP' });
  assert.deepEqual(ev.pontos.map((p) => p.valores[0]), [100, 0, 140]);
  assert.equal(ev.media, 80);
  assert.deepEqual(fin.grafico(db, emp, 'opcoes', { tipo: 'D', agrupar: 'item' }), ['Água', 'Luz']);
  assert.throws(() => fin.grafico(db, emp, 'evolucao', { tipo: 'D' }), /Selecione/);
});
