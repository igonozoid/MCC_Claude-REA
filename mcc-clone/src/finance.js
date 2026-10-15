// Regras de negocio do MCC: filtros da tela principal, saldos, baixas,
// parcelamento, dashboard e relatorios.
import { randomUUID } from 'node:crypto';
import { tx } from './db.js';

const pad = (n) => String(n).padStart(2, '0');
export const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const hoje = () => iso(new Date());
const r2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;

// Data "Vcto/Pgto" do original: pagamento quando pago, vencimento quando em aberto.
const VEN_PGTO = "(CASE WHEN l.situacao='V' THEN COALESCE(l.data_pagamento,l.vencimento) ELSE l.vencimento END)";

// Periodos do combo EdMes: 1..12, T1..T4, S1..S2, ANO, TODOS.
export function periodo(ano, mes) {
  ano = Number(ano) || new Date().getFullYear();
  if (!mes || mes === 'TODOS') return null;
  let m1 = 1, m2 = 12;
  if (/^\d+$/.test(mes)) m1 = m2 = Number(mes);
  else if (/^T[1-4]$/.test(mes)) { m1 = (Number(mes[1]) - 1) * 3 + 1; m2 = m1 + 2; }
  else if (/^S[12]$/.test(mes)) { m1 = mes === 'S1' ? 1 : 7; m2 = m1 + 5; }
  const fim = new Date(ano, m2, 0);
  return [`${ano}-${pad(m1)}-01`, iso(fim)];
}

// Periodos do dashboard: Hoje, Esta Semana, Este Mes, ou intervalo.
export function periodoDash(tipo, de, ate) {
  const d = new Date();
  if (tipo === 'semana') {
    const ini = new Date(d); ini.setDate(d.getDate() - d.getDay());
    const fim = new Date(ini); fim.setDate(ini.getDate() + 6);
    return [iso(ini), iso(fim)];
  }
  if (tipo === 'mes') return [iso(new Date(d.getFullYear(), d.getMonth(), 1)), iso(new Date(d.getFullYear(), d.getMonth() + 1, 0))];
  if (tipo === 'periodo' && de && ate) return [de, ate];
  return [iso(d), iso(d)];
}

const ORDENS = {
  data: 'l.data_mov, l.id', vencimento: `${VEN_PGTO}, l.id`, documento: 'l.documento, l.id',
  descricao: 'l.descricao, l.id', pessoa: 'l.pessoa, l.id', valor: 'l.valor, l.id',
  situacao: 'l.situacao, l.id', observacao: 'l.observacao, l.id',
};

export function listarLancamentos(db, empresaId, q = {}) {
  const where = ['l.empresa_id = ?', 'l.excluido_em IS NULL'];
  const args = [empresaId];
  if (q.tipo) { where.push('l.tipo = ?'); args.push(q.tipo); }
  if (q.situacao === 'V' || q.situacao === 'P') { where.push('l.situacao = ?'); args.push(q.situacao); }
  if (q.conta_id) { where.push('l.conta_id = ?'); args.push(Number(q.conta_id)); }
  if (q.pessoa) { where.push('l.pessoa = ?'); args.push(q.pessoa); }
  const per = q.de && q.ate ? [q.de, q.ate] : periodo(q.ano, q.mes);
  if (per) {
    if (q.campo_data === 'vencimento') { where.push(`${VEN_PGTO} BETWEEN ? AND ?`); args.push(...per); }
    else if (q.campo_data === 'ambos') {
      where.push(`(l.data_mov BETWEEN ? AND ? OR ${VEN_PGTO} BETWEEN ? AND ?)`); args.push(...per, ...per);
    } else { where.push('l.data_mov BETWEEN ? AND ?'); args.push(...per); }
  }
  if (q.busca) {
    where.push("(l.descricao LIKE ? OR l.pessoa LIKE ? OR l.documento LIKE ? OR l.observacao LIKE ? OR printf('%.2f', l.valor) LIKE ?)");
    const b = `%${q.busca}%`; args.push(b, b, b, b, b);
  }
  const ordem = ORDENS[q.ordem] || ORDENS.data;
  return db.prepare(`
    SELECT l.*, ${VEN_PGTO} AS ven_pgto, c.descricao AS conta, ce.nome AS centro,
      CASE WHEN l.situacao='V' THEN (CASE l.tipo WHEN 'D' THEN 'Pago' ELSE 'Recebido' END)
           WHEN l.vencimento < date('now','localtime') THEN 'Vencido'
           ELSE (CASE l.tipo WHEN 'D' THEN 'A pagar' ELSE 'A receber' END) END AS situacao_desc
    FROM lancamentos l
    LEFT JOIN contas c ON c.id = l.conta_id
    LEFT JOIN centros ce ON ce.id = l.centro_id
    WHERE ${where.join(' AND ')} ORDER BY ${ordem}`).all(...args);
}

const CAMPOS_LANC = ['tipo', 'data_mov', 'documento', 'descricao', 'pessoa', 'valor', 'situacao',
  'vencimento', 'data_pagamento', 'observacao', 'conta_id', 'centro_id'];

function normalizaLanc(b) {
  const o = {};
  for (const k of CAMPOS_LANC) o[k] = b[k] === '' || b[k] === undefined ? null : b[k];
  if (!['D', 'R'].includes(o.tipo)) throw new Error('Tipo deve ser D (despesa) ou R (receita).');
  if (!o.descricao) throw new Error('Informe a descrição.');
  o.valor = Number(o.valor);
  if (!(o.valor > 0)) throw new Error('Informe um valor maior que zero.');
  o.data_mov ||= hoje();
  o.vencimento ||= o.data_mov;
  o.situacao = o.situacao === 'V' ? 'V' : 'P';
  if (o.situacao === 'V') o.data_pagamento ||= o.vencimento;
  else o.data_pagamento = null;
  return o;
}

// Cadastra automaticamente descricoes e pessoas novas, como o MCC faz nos combos.
function registraAuxiliares(db, empresaId, o) {
  db.prepare('INSERT OR IGNORE INTO itens (empresa_id, tipo, descricao) VALUES (?,?,?)').run(empresaId, o.tipo, o.descricao);
  if (o.pessoa) {
    const tipoPes = o.tipo === 'D' ? 'F' : 'C';
    const existe = db.prepare('SELECT 1 FROM pessoas WHERE nome = ? AND (empresa_id = ? OR empresa_id IS NULL)').get(o.pessoa, empresaId);
    if (!existe) db.prepare('INSERT INTO pessoas (empresa_id, tipo, nome) VALUES (?,?,?)').run(empresaId, tipoPes, o.pessoa);
  }
}

export function salvarLancamento(db, empresaId, b, id) {
  const o = normalizaLanc(b);
  return tx(db, () => {
    registraAuxiliares(db, empresaId, o);
    if (id) {
      const sets = CAMPOS_LANC.map((k) => `${k} = ?`).join(', ');
      const r = db.prepare(`UPDATE lancamentos SET ${sets}, alterado_em = datetime('now','localtime')
        WHERE id = ? AND empresa_id = ? AND excluido_em IS NULL`).run(...CAMPOS_LANC.map((k) => o[k]), id, empresaId);
      if (!r.changes) throw new Error('Lançamento não encontrado.');
      return id;
    }
    const r = db.prepare(`INSERT INTO lancamentos (empresa_id, ${CAMPOS_LANC.join(', ')})
      VALUES (?, ${CAMPOS_LANC.map(() => '?').join(', ')})`).run(empresaId, ...CAMPOS_LANC.map((k) => o[k]));
    return Number(r.lastInsertRowid);
  });
}

// Periodicidades do FMulCad.
const PERIODOS = { diaria: [0, 1], semanal: [0, 7], quinzenal: [0, 15], mensal: [1, 0],
  bimestral: [2, 0], trimestral: [3, 0], semestral: [6, 0], anual: [12, 0] };

function somaPeriodo(dataIso, n, per) {
  const [m, d] = PERIODOS[per] || PERIODOS.mensal;
  const [y, mo, dd] = dataIso.split('-').map(Number);
  if (m) {
    const alvo = new Date(y, mo - 1 + m * n, 1);
    const ultimo = new Date(alvo.getFullYear(), alvo.getMonth() + 1, 0).getDate();
    alvo.setDate(Math.min(dd, ultimo)); // 31/01 + 1 mes = 28/02
    return iso(alvo);
  }
  return iso(new Date(y, mo - 1, dd + d * n));
}

export function parcelar(db, empresaId, b) {
  const n = Math.trunc(Number(b.parcelas));
  if (!(n >= 1 && n <= 360)) throw new Error('Número de parcelas deve estar entre 1 e 360.');
  const base = normalizaLanc({ ...b, situacao: 'P' });
  const grupo = randomUUID();
  return tx(db, () => {
    registraAuxiliares(db, empresaId, base);
    const ins = db.prepare(`INSERT INTO lancamentos (empresa_id, tipo, data_mov, documento, descricao, pessoa, valor,
      situacao, vencimento, observacao, conta_id, centro_id, grupo, parcela, total_parcelas)
      VALUES (?,?,?,?,?,?,?,'P',?,?,?,?,?,?,?)`);
    const ids = [];
    for (let i = 0; i < n; i++) {
      const ven = somaPeriodo(base.vencimento, i, b.periodicidade);
      const mov = b.mov_igual_vencimento ? ven : base.data_mov;
      const doc = base.documento ? `${base.documento} ${i + 1}/${n}` : `${i + 1}/${n}`;
      ids.push(Number(ins.run(empresaId, base.tipo, mov, doc, base.descricao, base.pessoa, base.valor, ven,
        base.observacao, base.conta_id, base.centro_id, grupo, i + 1, n).lastInsertRowid));
    }
    return ids;
  });
}

export function baixar(db, empresaId, ids, b = {}) {
  const data = b.data_pagamento || hoje();
  return tx(db, () => {
    const up = db.prepare(`UPDATE lancamentos SET situacao='V', data_pagamento=?,
        conta_id=COALESCE(?, conta_id), valor=COALESCE(?, valor), observacao=COALESCE(?, observacao),
        alterado_em=datetime('now','localtime')
      WHERE id=? AND empresa_id=? AND situacao='P' AND excluido_em IS NULL`);
    let n = 0;
    for (const id of ids) {
      const valor = ids.length === 1 && b.valor ? Number(b.valor) : null;
      n += up.run(data, b.conta_id || null, valor, ids.length === 1 ? b.observacao || null : null, id, empresaId).changes;
    }
    return n;
  });
}

export function estornar(db, empresaId, id) {
  return db.prepare(`UPDATE lancamentos SET situacao='P', data_pagamento=NULL, alterado_em=datetime('now','localtime')
    WHERE id=? AND empresa_id=?`).run(id, empresaId).changes;
}

// FMultDelMov: excluir somente esta parcela, esta e as seguintes, ou todas em aberto.
export function excluir(db, empresaId, id, modo = 'esta') {
  const l = db.prepare('SELECT * FROM lancamentos WHERE id=? AND empresa_id=?').get(id, empresaId);
  if (!l) throw new Error('Lançamento não encontrado.');
  const now = "datetime('now','localtime')";
  if (!l.grupo || modo === 'esta')
    return db.prepare(`UPDATE lancamentos SET excluido_em=${now} WHERE id=?`).run(id).changes;
  if (modo === 'seguintes')
    return db.prepare(`UPDATE lancamentos SET excluido_em=${now} WHERE grupo=? AND parcela>=? AND excluido_em IS NULL`).run(l.grupo, l.parcela).changes;
  return db.prepare(`UPDATE lancamentos SET excluido_em=${now} WHERE grupo=? AND situacao='P' AND excluido_em IS NULL`).run(l.grupo).changes;
}

export function restaurar(db, empresaId, id) {
  return db.prepare('UPDATE lancamentos SET excluido_em=NULL WHERE id=? AND empresa_id=?').run(id, empresaId).changes;
}

// ---------- Saldos ----------

// Saldo de cada conta visivel para a empresa. realizado: so o que foi pago/realizado
// ate a data; previsto: inclui o que esta em aberto (vencimento ate a data).
export function saldos(db, empresaId, ate = hoje()) {
  const contas = db.prepare(`SELECT * FROM contas WHERE (empresa_id = ? OR empresa_id IS NULL) ORDER BY descricao`).all(empresaId);
  const lanc = db.prepare(`SELECT
      COALESCE(SUM(CASE WHEN situacao='V' AND data_pagamento<=? THEN (CASE tipo WHEN 'R' THEN valor ELSE -valor END) END),0) AS real,
      COALESCE(SUM(CASE WHEN (situacao='V' AND data_pagamento<=?) OR (situacao='P' AND vencimento<=?) THEN (CASE tipo WHEN 'R' THEN valor ELSE -valor END) END),0) AS prev
    FROM lancamentos WHERE conta_id=? AND excluido_em IS NULL`);
  const mov = db.prepare(`SELECT
      COALESCE(SUM(CASE WHEN situacao='V' THEN v END),0) AS real, COALESCE(SUM(v),0) AS prev FROM (
        SELECT situacao, CASE tipo WHEN 'D' THEN valor ELSE -valor END AS v FROM movbancarias
          WHERE origem_id=? AND data<=? AND excluido_em IS NULL
        UNION ALL
        SELECT situacao, valor FROM movbancarias
          WHERE tipo='T' AND destino_id=? AND data<=? AND excluido_em IS NULL)`);
  return contas.map((c) => {
    const l = lanc.get(ate, ate, ate, c.id);
    const m = mov.get(c.id, ate, c.id, ate);
    return { ...c, saldo: r2(c.saldo_inicial + l.real + m.real), previsto: r2(c.saldo_inicial + l.prev + m.prev) };
  });
}

// ---------- Dashboard ----------

export function dashboard(db, empresaId, q) {
  const [de, ate] = periodoDash(q.periodo, q.de, q.ate);
  const soma = (sql, ...a) => r2(db.prepare(`SELECT COALESCE(SUM(valor),0) AS s FROM lancamentos
    WHERE empresa_id=? AND excluido_em IS NULL AND ${sql}`).get(empresaId, ...a).s);
  const venc = q.vencidos === '1' ? 'vencimento <= ?' : 'vencimento BETWEEN ? AND ?';
  const vArgs = q.vencidos === '1' ? [ate] : [de, ate];
  return {
    de, ate,
    caixa: {
      a_receber: soma(`tipo='R' AND situacao='P' AND ${venc}`, ...vArgs),
      a_pagar: soma(`tipo='D' AND situacao='P' AND ${venc}`, ...vArgs),
      recebido: soma("tipo='R' AND situacao='V' AND data_pagamento BETWEEN ? AND ?", de, ate),
      pago: soma("tipo='D' AND situacao='V' AND data_pagamento BETWEEN ? AND ?", de, ate),
    },
    competencia: (() => {
      const rec = soma("tipo='R' AND data_mov BETWEEN ? AND ?", de, ate);
      const des = soma("tipo='D' AND data_mov BETWEEN ? AND ?", de, ate);
      return { receitas: rec, despesas: des, margem: r2(rec - des) };
    })(),
  };
}

// Analise linear: pagamentos x recebimentos realizados por dia/semana/mes.
export function linear(db, empresaId, q) {
  const ano = Number(q.ano) || new Date().getFullYear();
  let fmt, de, ate;
  if (q.agrupamento === 'dia') {
    const d = new Date(); ate = iso(d); d.setDate(d.getDate() - 29); de = iso(d); fmt = '%Y-%m-%d';
  } else if (q.agrupamento === 'semana') {
    const d = new Date(); ate = iso(d); d.setDate(d.getDate() - 7 * 11); de = iso(d); fmt = '%Y-S%W';
  } else { de = `${ano}-01-01`; ate = `${ano}-12-31`; fmt = '%Y-%m'; }
  const rows = db.prepare(`SELECT strftime('${fmt}', data_pagamento) AS periodo,
      SUM(CASE tipo WHEN 'D' THEN valor ELSE 0 END) AS pagamentos,
      SUM(CASE tipo WHEN 'R' THEN valor ELSE 0 END) AS recebimentos
    FROM lancamentos WHERE empresa_id=? AND excluido_em IS NULL AND situacao='V' AND data_pagamento BETWEEN ? AND ?
    GROUP BY 1 ORDER BY 1`).all(empresaId, de, ate);
  // Preenche os periodos sem movimento para o eixo ficar continuo.
  let todos = rows.map((r) => r.periodo);
  if (q.agrupamento === 'dia') todos = Array.from({ length: 30 }, (_, i) => { const d = new Date(de + 'T12:00'); d.setDate(d.getDate() + i); return iso(d); });
  else if (q.agrupamento !== 'semana') todos = Array.from({ length: 12 }, (_, i) => `${ano}-${pad(i + 1)}`);
  const porPeriodo = new Map(rows.map((r) => [r.periodo, r]));
  return todos.map((p) => {
    const r = porPeriodo.get(p) || { pagamentos: 0, recebimentos: 0 };
    return { periodo: p, pagamentos: r2(r.pagamentos), recebimentos: r2(r.recebimentos), margem: r2(r.recebimentos - r.pagamentos) };
  });
}

// Lembrete de contas (FLemb): vencidas e a vencer nos proximos dias.
export function lembretes(db, empresaId, dias = 7) {
  const lim = new Date(); lim.setDate(lim.getDate() + Number(dias));
  return db.prepare(`SELECT l.*, CASE WHEN vencimento < date('now','localtime') THEN 'Vencida' ELSE 'A vencer' END AS status
    FROM lancamentos l WHERE empresa_id=? AND excluido_em IS NULL AND situacao='P' AND vencimento <= ?
    ORDER BY vencimento`).all(empresaId, iso(lim));
}

// ---------- Relatorios ----------

const MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
const tipoNome = (t) => (t === 'D' ? 'despesas' : 'receitas');

export const RELATORIOS = {
  lancamentos: { titulo: 'Relatório de despesas/receitas', params: ['tipo', 'periodo', 'situacao', 'conta'] },
  totais_item: { titulo: 'Totais por ítem', params: ['tipo', 'periodo', 'situacao'] },
  por_pessoa: { titulo: 'Contas por cliente/fornecedor', params: ['tipo', 'periodo', 'situacao'] },
  pontualidade: { titulo: 'Análise de pontualidade', params: ['tipo', 'periodo'] },
  fluxo_dia: { titulo: 'Fluxo de caixa por dia', params: ['periodo', 'previsao'] },
  extrato: { titulo: 'Extrato de conta bancária', params: ['periodo', 'conta'] },
  saldos: { titulo: 'Saldo de contas', params: ['data'] },
  demonstrativo: { titulo: 'Demonstrativo anual', params: ['tipo', 'ano', 'agrupar'] },
  centros: { titulo: 'Orçamento/projeção por centro de custo', params: ['tipo', 'periodo'] },
  dre: { titulo: 'Demonstrativo de resultados', params: ['periodo'] },
  analitico: { titulo: 'Relatório analítico', params: ['analitico'] },
};

function filtroPeriodo(q, campo) {
  const per = q.de && q.ate ? [q.de, q.ate] : periodo(q.ano, q.mes);
  return per ? { sql: ` AND ${campo} BETWEEN ? AND ?`, args: per, txt: `${br(per[0])} a ${br(per[1])}` } : { sql: '', args: [], txt: 'Todo período' };
}
const br = (d) => (d ? d.split('-').reverse().join('/') : '');

export function relatorio(db, empresaId, nome, q) {
  const tipo = q.tipo === 'R' ? 'R' : 'D';
  const sit = q.situacao === 'V' || q.situacao === 'P' ? ` AND l.situacao='${q.situacao}'` : '';
  const base = `FROM lancamentos l WHERE l.empresa_id=? AND l.excluido_em IS NULL`;
  switch (nome) {
    case 'lancamentos': {
      const p = filtroPeriodo(q, q.campo_data === 'vencimento' ? VEN_PGTO : 'l.data_mov');
      const conta = q.conta_id ? ' AND l.conta_id=' + Number(q.conta_id) : '';
      const linhas = db.prepare(`SELECT l.data_mov, l.documento, l.descricao, l.pessoa, ${VEN_PGTO} AS ven_pgto,
          CASE l.situacao WHEN 'V' THEN 'Quitado' ELSE 'Em aberto' END AS sit, l.observacao, l.valor
        ${base} AND l.tipo=?${sit}${conta}${p.sql} ORDER BY l.data_mov`).all(empresaId, tipo, ...p.args);
      return tabela(`Relatório de ${tipoNome(tipo)}`, p.txt,
        [['data_mov', 'Data', 'data'], ['documento', 'Documento'], ['descricao', 'Descrição'], ['pessoa', 'Pessoa'],
          ['ven_pgto', 'Vcto/Pgto', 'data'], ['sit', 'Situação'], ['observacao', 'Observação'], ['valor', 'Valor', 'moeda']], linhas, ['valor']);
    }
    case 'totais_item': {
      const p = filtroPeriodo(q, 'l.data_mov');
      const linhas = db.prepare(`SELECT l.descricao, COUNT(*) AS qtd, SUM(l.valor) AS total ${base} AND l.tipo=?${sit}${p.sql}
        GROUP BY l.descricao ORDER BY total DESC`).all(empresaId, tipo, ...p.args);
      return tabela(`Relatório de ${tipoNome(tipo)} totais`, p.txt,
        [['descricao', 'Ítem'], ['qtd', 'Lançamentos', 'int'], ['total', 'Total', 'moeda']], linhas, ['qtd', 'total']);
    }
    case 'por_pessoa': {
      const p = filtroPeriodo(q, VEN_PGTO);
      const linhas = db.prepare(`SELECT COALESCE(l.pessoa,'(sem pessoa)') AS pessoa, COUNT(*) AS qtd, SUM(l.valor) AS total
        ${base} AND l.tipo=?${sit}${p.sql} GROUP BY 1 ORDER BY total DESC`).all(empresaId, tipo, ...p.args);
      return tabela(tipo === 'D' ? 'Contas a pagar por fornecedor' : 'Contas a receber por cliente', p.txt,
        [['pessoa', tipo === 'D' ? 'Fornecedor' : 'Cliente'], ['qtd', 'Lançamentos', 'int'], ['total', 'Total', 'moeda']], linhas, ['qtd', 'total']);
    }
    case 'pontualidade': {
      const p = filtroPeriodo(q, 'l.vencimento');
      const linhas = db.prepare(`SELECT COALESCE(l.pessoa,'(sem pessoa)') AS pessoa, COUNT(*) AS ocorrencias,
          MAX(julianday(l.data_pagamento)-julianday(l.vencimento)) AS maior_atraso,
          MIN(julianday(l.data_pagamento)-julianday(l.vencimento)) AS maior_antecipacao,
          AVG(julianday(l.data_pagamento)-julianday(l.vencimento)) AS media
        ${base} AND l.tipo=? AND l.situacao='V'${p.sql} GROUP BY 1 ORDER BY media DESC`).all(empresaId, tipo, ...p.args)
        .map((r) => ({ ...r, maior_atraso: Math.max(0, r.maior_atraso), maior_antecipacao: Math.max(0, -r.maior_antecipacao), media: Math.round(r.media) }));
      return tabela(`Análise de pontualidade de ${tipo === 'D' ? 'pagamentos' : 'recebimentos'}`, p.txt,
        [['pessoa', 'Pessoa'], ['ocorrencias', 'Ocorrências', 'int'], ['maior_atraso', 'Maior atraso (dias)', 'int'],
          ['maior_antecipacao', 'Maior antecipação (dias)', 'int'], ['media', 'Média (dias, + = atraso)', 'int']], linhas, []);
    }
    case 'fluxo_dia': {
      const prev = q.previsao === '1';
      const p = filtroPeriodo(q, VEN_PGTO);
      const cond = prev ? '' : " AND l.situacao='V'";
      const linhas = db.prepare(`SELECT ${VEN_PGTO} AS dia,
          SUM(CASE l.tipo WHEN 'D' THEN l.valor ELSE 0 END) AS despesas,
          SUM(CASE l.tipo WHEN 'R' THEN l.valor ELSE 0 END) AS receitas
        ${base}${cond}${p.sql} GROUP BY 1 ORDER BY 1`).all(empresaId, ...p.args);
      let acc = 0;
      for (const r of linhas) { r.saldo_dia = r2(r.receitas - r.despesas); acc = r2(acc + r.saldo_dia); r.acumulado = acc; }
      return tabela(prev ? 'Previsão de caixa por dia' : 'Fluxo de caixa por dia (realizado)', p.txt,
        [['dia', 'Dia', 'data'], ['receitas', 'Receitas', 'moeda'], ['despesas', 'Despesas', 'moeda'],
          ['saldo_dia', 'Saldo do dia', 'moeda'], ['acumulado', 'Acumulado', 'moeda']], linhas, ['receitas', 'despesas', 'saldo_dia']);
    }
    case 'extrato': {
      const contaId = Number(q.conta_id);
      if (!contaId) throw new Error('Selecione a conta.');
      const conta = db.prepare('SELECT * FROM contas WHERE id=?').get(contaId);
      const per = (q.de && q.ate ? [q.de, q.ate] : periodo(q.ano, q.mes)) || ['0000-01-01', '9999-12-31'];
      const dia = new Date(per[0] + 'T12:00:00'); dia.setDate(dia.getDate() - 1);
      const inicial = saldos(db, empresaId, iso(dia)).find((c) => c.id === contaId)?.saldo ?? conta.saldo_inicial;
      const linhas = db.prepare(`
        SELECT data_pagamento AS data, descricao || COALESCE(' - ' || pessoa, '') AS historico, documento,
          CASE tipo WHEN 'R' THEN valor END AS credito, CASE tipo WHEN 'D' THEN valor END AS debito
          FROM lancamentos WHERE conta_id=? AND situacao='V' AND excluido_em IS NULL AND data_pagamento BETWEEN ? AND ?
        UNION ALL
        SELECT data, CASE tipo WHEN 'D' THEN 'Depósito' WHEN 'R' THEN 'Retirada' ELSE 'Transferência enviada' END || COALESCE(' - ' || observacao,''), NULL,
          CASE tipo WHEN 'D' THEN valor END, CASE WHEN tipo IN ('R','T') THEN valor END
          FROM movbancarias WHERE origem_id=? AND situacao='V' AND excluido_em IS NULL AND data BETWEEN ? AND ?
        UNION ALL
        SELECT data, 'Transferência recebida' || COALESCE(' - ' || observacao,''), NULL, valor, NULL
          FROM movbancarias WHERE tipo='T' AND destino_id=? AND situacao='V' AND excluido_em IS NULL AND data BETWEEN ? AND ?
        ORDER BY 1`).all(contaId, ...per, contaId, ...per, contaId, ...per);
      let s = inicial;
      for (const r of linhas) { s = r2(s + (r.credito || 0) - (r.debito || 0)); r.saldo = s; }
      linhas.unshift({ data: per[0], historico: 'Saldo anterior', saldo: inicial });
      return tabela(`Extrato — ${conta.descricao}`, `${br(per[0])} a ${br(per[1])}`,
        [['data', 'Data', 'data'], ['historico', 'Histórico'], ['documento', 'Doc.'], ['credito', 'Crédito', 'moeda'],
          ['debito', 'Débito', 'moeda'], ['saldo', 'Saldo', 'moeda']], linhas, ['credito', 'debito']);
    }
    case 'saldos': {
      const data = q.data || hoje();
      const linhas = saldos(db, empresaId, data).filter((c) => c.ativa);
      return tabela('Relatório de saldo de contas', `Posição em ${br(data)}`,
        [['descricao', 'Conta'], ['saldo', 'Saldo realizado', 'moeda'], ['previsto', 'Saldo previsto', 'moeda']], linhas, ['saldo', 'previsto']);
    }
    case 'demonstrativo': {
      const ano = Number(q.ano) || new Date().getFullYear();
      const grp = { item: 'l.descricao', pessoa: "COALESCE(l.pessoa,'(sem pessoa)')", centro: "COALESCE(ce.nome,'(sem centro)')", conta: "COALESCE(c.descricao,'(sem conta)')" }[q.agrupar] || 'l.descricao';
      const meses = MESES.map((m, i) => `SUM(CASE WHEN strftime('%m', l.data_mov)='${pad(i + 1)}' THEN l.valor ELSE 0 END) AS "${m}"`).join(',\n');
      const linhas = db.prepare(`SELECT ${grp} AS descricao, ${meses}, SUM(l.valor) AS total
        FROM lancamentos l LEFT JOIN centros ce ON ce.id=l.centro_id LEFT JOIN contas c ON c.id=l.conta_id
        WHERE l.empresa_id=? AND l.excluido_em IS NULL AND l.tipo=? AND strftime('%Y', l.data_mov)=?
        GROUP BY 1 ORDER BY total DESC`).all(empresaId, tipo, String(ano));
      for (const r of linhas) r.media = r2(r.total / 12);
      return tabela(`Demonstrativo anual de ${tipoNome(tipo)}`, String(ano),
        [['descricao', 'Descrição'], ...MESES.map((m) => [m, m, 'moeda']), ['media', 'Média', 'moeda'], ['total', 'Total', 'moeda']],
        linhas, [...MESES, 'media', 'total']);
    }
    case 'centros': {
      const p = filtroPeriodo(q, 'l.data_mov');
      const per = q.de && q.ate ? [q.de, q.ate] : periodo(q.ano, q.mes);
      const nMeses = per ? Math.max(1, Math.round((new Date(per[1]) - new Date(per[0])) / 2.63e9)) : 12;
      const linhas = db.prepare(`SELECT ce.nome, ${tipo === 'D' ? 'ce.orcamento' : 'ce.projecao'} * ? AS meta,
          COALESCE((SELECT SUM(l.valor) ${base.replace('WHERE', 'WHERE l.centro_id=ce.id AND')} AND l.tipo=?${p.sql}),0) AS realizado
        FROM centros ce WHERE ce.empresa_id=? AND ${tipo === 'D' ? 'ce.aplica_despesa' : 'ce.aplica_receita'}=1 ORDER BY ce.nome`)
        .all(nMeses, empresaId, tipo, ...p.args, empresaId)
        .map((r) => ({ ...r, diferenca: r2(r.meta - r.realizado), perc: r.meta ? r2((r.realizado / r.meta) * 100) : null }));
      return tabela(tipo === 'D' ? 'Orçamento por centro de custo' : 'Projeção por centro de lucro', p.txt,
        [['nome', 'Centro'], ['meta', tipo === 'D' ? 'Orçamento' : 'Projeção', 'moeda'], ['realizado', 'Realizado', 'moeda'],
          ['diferenca', 'Diferença', 'moeda'], ['perc', '% atingido', 'num']], linhas, ['meta', 'realizado', 'diferenca']);
    }
    case 'dre': {
      const p = filtroPeriodo(q, 'l.data_mov');
      const linhas = db.prepare(`SELECT CASE l.tipo WHEN 'R' THEN 'Receitas' ELSE 'Despesas' END AS grupo, l.descricao,
          SUM(CASE l.tipo WHEN 'R' THEN l.valor ELSE -l.valor END) AS valor
        ${base}${p.sql} GROUP BY l.tipo, l.descricao ORDER BY l.tipo DESC, ABS(valor) DESC`).all(empresaId, ...p.args);
      return tabela('Demonstrativo de resultados', p.txt,
        [['grupo', 'Grupo'], ['descricao', 'Ítem'], ['valor', 'Valor', 'moeda']], linhas, ['valor']);
    }
    case 'analitico':
      return analitico(db, empresaId, q);
    default:
      throw new Error('Relatório desconhecido: ' + nome);
  }
}

function tabela(titulo, subtitulo, colunas, linhas, somar) {
  const totais = {};
  // linhas de grupo/subtotal (_tipo) nao entram no total geral
  for (const k of somar) totais[k] = r2(linhas.filter((r) => !r._tipo).reduce((a, r) => a + (Number(r[k]) || 0), 0));
  return { titulo, subtitulo, colunas: colunas.map(([campo, rotulo, fmt]) => ({ campo, rotulo, fmt })), linhas, totais };
}

// ---------- Importacao de extrato OFX (FConcilia) ----------

export function parseOfx(texto) {
  const tag = (bloco, t) => (bloco.match(new RegExp(`<${t}>([^<\\r\\n]*)`, 'i')) || [])[1]?.trim() || '';
  const blocos = texto.split(/<STMTTRN>/i).slice(1).map((b) => b.split(/<\/STMTTRN>/i)[0]);
  return blocos.map((b) => {
    const dt = tag(b, 'DTPOSTED');
    const valor = Number(tag(b, 'TRNAMT').replace(',', '.'));
    return {
      fitid: tag(b, 'FITID') || `${dt}-${valor}-${tag(b, 'MEMO')}`,
      data: `${dt.slice(0, 4)}-${dt.slice(4, 6)}-${dt.slice(6, 8)}`,
      valor: Math.abs(valor), tipo: valor < 0 ? 'D' : 'R',
      descricao: tag(b, 'MEMO') || tag(b, 'NAME'), documento: tag(b, 'CHECKNUM') || tag(b, 'REFNUM'),
    };
  }).filter((l) => l.valor > 0 && /^\d{4}-\d{2}-\d{2}$/.test(l.data));
}

// Classifica cada linha: ja importada, ja quitada no MCC (conciliado), em aberto que pode ser
// baixado com esta linha, ou nova.
export function analisarOfx(db, empresaId, contaId, texto) {
  const linhas = parseOfx(texto);
  const jaImp = db.prepare('SELECT 1 FROM ofx_importados WHERE conta_id=? AND fitid=?');
  const busca = db.prepare(`SELECT id, descricao, pessoa, situacao, vencimento, data_pagamento FROM lancamentos
    WHERE empresa_id=? AND excluido_em IS NULL AND tipo=? AND ABS(valor-?)<0.005 AND (conta_id=? OR conta_id IS NULL)
      AND ABS(julianday(CASE situacao WHEN 'V' THEN data_pagamento ELSE vencimento END)-julianday(?)) <= ?
    ORDER BY situacao DESC, ABS(julianday(vencimento)-julianday(?)) LIMIT 1`);
  return linhas.map((l) => {
    if (jaImp.get(contaId, l.fitid)) return { ...l, status: 'importado', acao: 'ignorar' };
    const m = busca.get(empresaId, l.tipo, l.valor, contaId, l.data, 7, l.data);
    if (m?.situacao === 'V') return { ...l, status: 'conciliado', lancamento: m, acao: 'conciliar' };
    if (m) return { ...l, status: 'em_aberto', lancamento: m, acao: 'baixar' };
    return { ...l, status: 'novo', acao: 'incluir' };
  });
}

export function aplicarOfx(db, empresaId, contaId, linhas) {
  return tx(db, () => {
    const marca = db.prepare('INSERT OR IGNORE INTO ofx_importados (conta_id, fitid) VALUES (?,?)');
    const res = { incluidos: 0, baixados: 0, conciliados: 0 };
    for (const l of linhas) {
      if (l.acao === 'ignorar') continue;
      if (l.acao === 'incluir') {
        registraAuxiliares(db, empresaId, { tipo: l.tipo, descricao: l.descricao || 'Extrato bancário', pessoa: l.pessoa || null });
        db.prepare(`INSERT INTO lancamentos (empresa_id, tipo, data_mov, documento, descricao, pessoa, valor, situacao,
          vencimento, data_pagamento, observacao, conta_id, centro_id) VALUES (?,?,?,?,?,?,?,'V',?,?,?,?,?)`)
          .run(empresaId, l.tipo, l.data, l.documento || null, l.descricao || 'Extrato bancário', l.pessoa || null,
            l.valor, l.data, l.data, 'Importado do extrato OFX', contaId, l.centro_id || null);
        res.incluidos++;
      } else if (l.acao === 'baixar' && l.lancamento) {
        db.prepare(`UPDATE lancamentos SET situacao='V', data_pagamento=?, conta_id=?, alterado_em=datetime('now','localtime')
          WHERE id=? AND empresa_id=?`).run(l.data, contaId, l.lancamento.id, empresaId);
        res.baixados++;
      } else res.conciliados++;
      marca.run(contaId, l.fitid);
    }
    return res;
  });
}

// ---------- Relatorio analitico (FAnalise) com agrupamentos livres ----------

const NOMES_MES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
const rotuloMes = (am) => (/^\d{4}-\d{2}$/.test(am || '') ? `${NOMES_MES[Number(am.slice(5)) - 1]}/${am.slice(0, 4)}` : am);

// Dimensoes de agrupamento permitidas (lista fechada: nunca SQL vindo do cliente).
export const AGRUPAMENTOS = {
  item: ['Descrição', () => 'l.descricao'],
  pessoa: ['Cliente/fornecedor', () => "COALESCE(NULLIF(l.pessoa,''),'(sem pessoa)')"],
  conta: ['Conta', () => "COALESCE(c.descricao,'(sem conta)')"],
  centro: ['Centro de custo', () => "COALESCE(ce.nome,'(sem centro)')"],
  mes: ['Mês', (data) => `strftime('%Y-%m', ${data})`],
  situacao: ['Situação', () => "CASE l.situacao WHEN 'V' THEN 'Pago' ELSE 'Em aberto' END"],
  tipo: ['Tipo', () => "CASE l.tipo WHEN 'D' THEN 'Despesas' ELSE 'Receitas' END"],
};
const ORDENS_ANALITICO = { data: 'l.data_mov', vencimento: VEN_PGTO, pessoa: 'l.pessoa', descricao: 'l.descricao', observacao: 'l.observacao', documento: 'l.documento', valor: 'l.valor' };

export function analitico(db, empresaId, q) {
  const tipos = q.tipo === 'D' || q.tipo === 'R' ? [q.tipo] : ['D', 'R'];
  const campoData = q.campo_data === 'vencimento' ? VEN_PGTO : 'l.data_mov';
  const where = ['l.empresa_id = ?', 'l.excluido_em IS NULL', `l.tipo IN (${tipos.map((t) => `'${t}'`).join(',')})`];
  const args = [empresaId];
  if (q.situacao === 'V' || q.situacao === 'P') { where.push('l.situacao = ?'); args.push(q.situacao); }
  if (q.de) { where.push(`${campoData} >= ?`); args.push(q.de); }
  if (q.ate) { where.push(`${campoData} <= ?`); args.push(q.ate); }
  if (q.descricao) { where.push('l.descricao LIKE ?'); args.push(`%${q.descricao}%`); }
  if (q.pessoa) { where.push('l.pessoa LIKE ?'); args.push(`%${q.pessoa}%`); }
  if (q.conta_id) { where.push('l.conta_id = ?'); args.push(Number(q.conta_id)); }
  if (q.centro_id) { where.push('l.centro_id = ?'); args.push(Number(q.centro_id)); }

  const grupos = [q.agrupar1, q.agrupar2].filter((g, i, a) => g && AGRUPAMENTOS[g] && a.indexOf(g) === i);
  const gExpr = grupos.map((g) => AGRUPAMENTOS[g][1](campoData));
  const dois = tipos.length === 2; // "Todos": receitas e despesas em colunas separadas e saldo
  const from = `FROM lancamentos l LEFT JOIN contas c ON c.id = l.conta_id LEFT JOIN centros ce ON ce.id = l.centro_id
    WHERE ${where.join(' AND ')}`;
  const sub = [q.de && `de ${br(q.de)}`, q.ate && `até ${br(q.ate)}`].filter(Boolean).join(' ') || 'Todo período';
  const titulo = String(q.titulo || '').trim().slice(0, 80) || 'Relatório analítico';
  const valorCols = dois
    ? [['receitas', 'Receitas', 'moeda'], ['despesas', 'Despesas', 'moeda'], ['saldo', 'Saldo', 'moeda']]
    : [['total', 'Total', 'moeda']];
  const somaValores = dois
    ? "SUM(CASE l.tipo WHEN 'R' THEN l.valor ELSE 0 END) AS receitas, SUM(CASE l.tipo WHEN 'D' THEN l.valor ELSE 0 END) AS despesas"
    : 'SUM(l.valor) AS total';
  const fechaValores = (r) => { if (dois) r.saldo = r2((r.receitas || 0) - (r.despesas || 0)); return r; };
  const rotular = (g, v) => (g === 'mes' ? rotuloMes(v) : v);

  if (q.modo === 'totalizado') {
    if (!grupos.length) throw new Error('Escolha ao menos um agrupamento para o relatório totalizado.');
    const sel = gExpr.map((e, i) => `${e} AS g${i}`).join(', ');
    const linhas = db.prepare(`SELECT ${sel}, COUNT(*) AS qtd, ${somaValores} ${from}
      GROUP BY ${gExpr.map((_, i) => `g${i}`).join(', ')} ORDER BY ${gExpr.map((_, i) => `ordem_pt(g${i})`).join(', ')}`).all(...args)
      .map((r) => fechaValores({ ...r, g0: rotular(grupos[0], r.g0), g1: grupos[1] ? rotular(grupos[1], r.g1) : undefined }));
    // com dois niveis, insere subtotal ao fim de cada grupo do 1o nivel
    const saida = [];
    if (grupos.length === 2) {
      let atual = null, acc = null;
      const fecha = () => acc && saida.push(fechaValores({ ...acc, _tipo: 'subtotal', g0: `Subtotal ${atual}`, g1: '' }));
      for (const r of linhas) {
        if (r.g0 !== atual) { fecha(); atual = r.g0; acc = { qtd: 0, receitas: 0, despesas: 0, total: 0 }; }
        for (const k of ['qtd', 'receitas', 'despesas', 'total']) acc[k] = r2(acc[k] + (r[k] || 0));
        saida.push(r);
      }
      fecha();
    } else saida.push(...linhas);
    const t = tabela(titulo, `${sub} · totalizado por ${grupos.map((g) => AGRUPAMENTOS[g][0].toLowerCase()).join(' e ')}`,
      [...grupos.map((g, i) => [`g${i}`, AGRUPAMENTOS[g][0]]), ['qtd', 'Lançamentos', 'int'], ...valorCols],
      saida, ['qtd', ...valorCols.map((c) => c[0])]);
    return t;
  }

  // Descritivo: cada lancamento, com cabecalho e subtotal por grupo.
  const ordem = ORDENS_ANALITICO[q.ordem] || ORDENS_ANALITICO.data;
  const dir = q.decrescente === '1' ? 'DESC' : 'ASC';
  const linhas = db.prepare(`SELECT ${gExpr.map((e, i) => `${e} AS g${i}, `).join('')}
      l.id, l.tipo, l.data_mov, ${VEN_PGTO} AS ven_pgto, l.documento, l.descricao, l.pessoa, l.observacao,
      c.descricao AS conta, ce.nome AS centro, CASE l.situacao WHEN 'V' THEN 'Pago' ELSE 'Em aberto' END AS sit,
      CASE l.tipo WHEN 'R' THEN l.valor END AS receitas, CASE l.tipo WHEN 'D' THEN l.valor END AS despesas, l.valor AS total
    ${from} ORDER BY ${gExpr.map((_, i) => `ordem_pt(g${i}), `).join('')}${['l.pessoa', 'l.descricao', 'l.observacao', 'l.documento'].includes(ordem) ? `ordem_pt(${ordem})` : ordem} ${dir}, l.id`).all(...args).map(fechaValores);

  const saida = [];
  const acc = grupos.map(() => null), chave = grupos.map(() => undefined);
  const zera = () => ({ receitas: 0, despesas: 0, total: 0, qtd: 0 });
  const fecha = (nivel) => {
    for (let n = grupos.length - 1; n >= nivel; n--) {
      if (acc[n]) saida.push(fechaValores({ _tipo: 'subtotal', _nivel: n, descricao: `Subtotal ${rotular(grupos[n], chave[n])} (${acc[n].qtd})`, ...acc[n], qtd: undefined }));
      acc[n] = null;
    }
  };
  for (const r of linhas) {
    let mudou = grupos.findIndex((_, n) => r[`g${n}`] !== chave[n]);
    if (mudou >= 0) {
      fecha(mudou);
      for (let n = mudou; n < grupos.length; n++) {
        chave[n] = r[`g${n}`];
        acc[n] = zera();
        saida.push({ _tipo: 'grupo', _nivel: n, data_mov: `${AGRUPAMENTOS[grupos[n]][0]}: ${rotular(grupos[n], chave[n])}` });
      }
    }
    for (const a of acc) if (a) { a.qtd++; for (const k of ['receitas', 'despesas', 'total']) a[k] = r2(a[k] + (r[k] || 0)); }
    const { g0, g1, ...resto } = r;
    saida.push({ ...resto, tipo: r.tipo === 'D' ? 'Despesa' : 'Receita' });
  }
  fecha(0);
  return tabela(titulo, `${sub} · ${linhas.length} lançamento(s)`,
    [['data_mov', 'Data', 'data'], ['ven_pgto', 'Vcto/Pgto', 'data'], ...(dois ? [['tipo', 'Tipo']] : []), ['documento', 'Doc.'],
      ['descricao', 'Descrição'], ['pessoa', 'Pessoa'], ['conta', 'Conta'], ['centro', 'Centro'], ['sit', 'Situação'],
      ['observacao', 'Observação'], ...valorCols],
    saida, valorCols.map((c) => c[0]));
}

// ---------- Graficos gerenciais (FChart) ----------

// Meses de um intervalo, para o eixo ficar continuo mesmo sem movimento.
function mesesEntre(de, ate) {
  const out = [];
  let [y, m] = de.slice(0, 7).split('-').map(Number);
  const [y2, m2] = ate.slice(0, 7).split('-').map(Number);
  while ((y < y2 || (y === y2 && m <= m2)) && out.length < 120) { out.push(`${y}-${pad(m)}`); m++; if (m > 12) { m = 1; y++; } }
  return out;
}

export function grafico(db, empresaId, nome, q) {
  const ano = new Date().getFullYear();
  const de = q.de || `${ano}-01-01`, ate = q.ate || `${ano}-12-31`;
  const campo = q.campo_data === 'vencimento' ? VEN_PGTO : 'l.data_mov';
  const sit = q.situacao === 'V' || q.situacao === 'P' ? ` AND l.situacao='${q.situacao}'` : '';
  const base = `FROM lancamentos l LEFT JOIN centros ce ON ce.id = l.centro_id
    WHERE l.empresa_id=? AND l.excluido_em IS NULL AND ${campo} BETWEEN ? AND ?${sit}`;
  const sub = `${br(de)} a ${br(ate)}`;
  const tipo = q.tipo === 'R' ? 'R' : 'D';
  const nomeTipo = tipo === 'D' ? 'despesas' : 'receitas';

  if (nome === 'desp_rec') {
    const rows = db.prepare(`SELECT strftime('%Y-%m', ${campo}) AS mes,
        SUM(CASE l.tipo WHEN 'R' THEN l.valor ELSE 0 END) AS r, SUM(CASE l.tipo WHEN 'D' THEN l.valor ELSE 0 END) AS d
      ${base} GROUP BY 1`).all(empresaId, de, ate);
    const por = new Map(rows.map((r) => [r.mes, r]));
    const pontos = mesesEntre(de, ate).map((m) => {
      const r = por.get(m) || { r: 0, d: 0 };
      return { rotulo: rotuloMes(m), valores: [r2(r.r), r2(r.d)], margem: r2(r.r - r.d) };
    });
    return { forma: 'colunas', titulo: 'Gráfico despesas x receitas', subtitulo: sub, series: ['Receitas', 'Despesas'], linha: 'Margem', pontos };
  }

  if (nome === 'composicao') {
    const agr = { item: 'l.descricao', pessoa: "COALESCE(NULLIF(l.pessoa,''),'(sem pessoa)')", centro: "COALESCE(ce.nome,'(sem centro)')" }[q.agrupar] || 'l.descricao';
    const rows = db.prepare(`SELECT ${agr} AS rotulo, SUM(l.valor) AS valor ${base} AND l.tipo=? GROUP BY 1 ORDER BY valor DESC`).all(empresaId, de, ate, tipo);
    const total = rows.reduce((a, r) => a + r.valor, 0);
    // ate 12 categorias; o restante e somado em "Outros"
    const top = rows.slice(0, 12), resto = rows.slice(12).reduce((a, r) => a + r.valor, 0);
    if (resto > 0) top.push({ rotulo: `Outros (${rows.length - 12})`, valor: resto });
    const por = { item: 'ítem', pessoa: tipo === 'D' ? 'fornecedor' : 'cliente', centro: tipo === 'D' ? 'centro de custo' : 'centro de lucro' }[q.agrupar] || 'ítem';
    return { forma: 'ranking', titulo: `Gráfico de ${nomeTipo} por ${por}`, subtitulo: sub, total: r2(total),
      pontos: top.map((r) => ({ rotulo: r.rotulo, valor: r2(r.valor), perc: total ? r2((r.valor / total) * 100) : 0 })) };
  }

  if (nome === 'evolucao') {
    const agrupar = q.agrupar === 'pessoa' ? 'pessoa' : 'item';
    const col = agrupar === 'pessoa' ? 'l.pessoa' : 'l.descricao';
    const alvo = String(q.valor || '');
    if (!alvo) throw new Error(`Selecione ${agrupar === 'pessoa' ? (tipo === 'D' ? 'o fornecedor' : 'o cliente') : 'o ítem'}.`);
    const rows = db.prepare(`SELECT strftime('%Y-%m', ${campo}) AS mes, SUM(l.valor) AS v ${base} AND l.tipo=? AND ${col}=? GROUP BY 1`)
      .all(empresaId, de, ate, tipo, alvo);
    const por = new Map(rows.map((r) => [r.mes, r.v]));
    const pontos = mesesEntre(de, ate).map((m) => ({ rotulo: rotuloMes(m), valores: [r2(por.get(m) || 0)] }));
    const media = pontos.length ? r2(pontos.reduce((a, p) => a + p.valores[0], 0) / pontos.length) : 0;
    return { forma: 'colunas', titulo: `Evolução de ${nomeTipo} — ${alvo}`, subtitulo: sub, series: [alvo], media, pontos };
  }

  // Opcoes para o seletor da evolucao (itens ou pessoas com movimento do tipo).
  if (nome === 'opcoes') {
    const col = q.agrupar === 'pessoa' ? 'l.pessoa' : 'l.descricao';
    return db.prepare(`SELECT DISTINCT ${col} AS v FROM lancamentos l WHERE l.empresa_id=? AND l.excluido_em IS NULL AND l.tipo=?
      AND ${col} IS NOT NULL AND ${col} <> '' ORDER BY ordem_pt(${col})`).all(empresaId, tipo).map((r) => r.v);
  }
  throw new Error('Gráfico desconhecido: ' + nome);
}
