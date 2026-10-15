"""Regras de negocio do MCC: filtros da tela principal, saldos, baixas, parcelamento,
dashboard, relatorios, graficos e importacao OFX.

Porte direto de mcc-clone/src/finance.js; os resultados sao os mesmos.
"""
import calendar
import re
import uuid
from datetime import date, datetime, timedelta

from .db import dicts, tx, um

MESES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
MESES_LONGOS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro',
                'Novembro', 'Dezembro']

# Data "Vcto/Pgto" do original: pagamento quando pago, vencimento quando em aberto.
VEN_PGTO = "(CASE WHEN l.situacao='V' THEN COALESCE(l.data_pagamento,l.vencimento) ELSE l.vencimento END)"


def hoje():
    return date.today().isoformat()


def r2(v):
    return round((v or 0) + 1e-9, 2) if (v or 0) >= 0 else round((v or 0) - 1e-9, 2)


def br(d):
    return '/'.join(reversed(d[:10].split('-'))) if d else ''


def rotulo_mes(am):
    return f'{MESES[int(am[5:7]) - 1]}/{am[:4]}' if am and re.fullmatch(r'\d{4}-\d{2}', am) else am


def _vazio(v):
    return v is None or v == ''


# ---------- Periodos ----------

def periodo(ano, mes):
    """Periodos do combo EdMes: '1'..'12', T1..T4, S1..S2, ANO, TODOS."""
    ano = int(ano or date.today().year)
    mes = str(mes or '')
    if not mes or mes == 'TODOS':
        return None
    m1, m2 = 1, 12
    if mes.isdigit():
        m1 = m2 = int(mes)
    elif re.fullmatch(r'T[1-4]', mes):
        m1 = (int(mes[1]) - 1) * 3 + 1
        m2 = m1 + 2
    elif re.fullmatch(r'S[12]', mes):
        m1 = 1 if mes == 'S1' else 7
        m2 = m1 + 5
    return f'{ano}-{m1:02d}-01', f'{ano}-{m2:02d}-{calendar.monthrange(ano, m2)[1]:02d}'


def periodo_dash(tipo, de=None, ate=None):
    """Periodos do dashboard: hoje, semana, mes ou intervalo."""
    d = date.today()
    if tipo == 'semana':
        ini = d - timedelta(days=(d.weekday() + 1) % 7)  # semana de domingo a sabado
        return ini.isoformat(), (ini + timedelta(days=6)).isoformat()
    if tipo == 'mes':
        return d.replace(day=1).isoformat(), d.replace(day=calendar.monthrange(d.year, d.month)[1]).isoformat()
    if tipo == 'periodo' and de and ate:
        return de, ate
    return d.isoformat(), d.isoformat()


# ---------- Lancamentos ----------

ORDENS = {
    'data': 'l.data_mov, l.id', 'vencimento': f'{VEN_PGTO}, l.id', 'documento': 'ordem_pt(l.documento), l.id',
    'descricao': 'ordem_pt(l.descricao), l.id', 'pessoa': 'ordem_pt(l.pessoa), l.id', 'valor': 'l.valor, l.id',
    'situacao': 'l.situacao, l.id', 'observacao': 'ordem_pt(l.observacao), l.id',
}


def listar_lancamentos(db, empresa_id, q=None):
    q = q or {}
    where, args = ['l.empresa_id = ?', 'l.excluido_em IS NULL'], [empresa_id]
    if q.get('tipo'):
        where.append('l.tipo = ?'); args.append(q['tipo'])
    if q.get('tipos'):
        where.append(f"l.tipo IN ({','.join('?' * len(q['tipos']))})"); args += list(q['tipos'])
    if q.get('situacao') in ('V', 'P'):
        where.append('l.situacao = ?'); args.append(q['situacao'])
    if q.get('conta_id'):
        where.append('l.conta_id = ?'); args.append(int(q['conta_id']))
    if q.get('pessoa'):
        where.append('l.pessoa = ?'); args.append(q['pessoa'])
    per = (q['de'], q['ate']) if q.get('de') and q.get('ate') else periodo(q.get('ano'), q.get('mes'))
    if per:
        if q.get('campo_data') == 'vencimento':
            where.append(f'{VEN_PGTO} BETWEEN ? AND ?'); args += per
        elif q.get('campo_data') == 'ambos':
            where.append(f'(l.data_mov BETWEEN ? AND ? OR {VEN_PGTO} BETWEEN ? AND ?)'); args += [*per, *per]
        else:
            where.append('l.data_mov BETWEEN ? AND ?'); args += per
    if q.get('busca'):
        where.append("(l.descricao LIKE ? OR l.pessoa LIKE ? OR l.documento LIKE ? OR l.observacao LIKE ? "
                     "OR printf('%.2f', l.valor) LIKE ?)")
        b = f"%{q['busca']}%"; args += [b] * 5
    if q.get('busca_campo') and q.get('busca_valor') not in (None, ''):  # Localizar (FPesq) por um campo
        campo = {'descricao': 'l.descricao', 'pessoa': 'l.pessoa', 'documento': 'l.documento', 'observacao': 'l.observacao'}.get(q['busca_campo'])
        if campo:
            where.append(f'{campo} LIKE ?'); args.append(f"%{q['busca_valor']}%")
        elif q['busca_campo'] == 'valor':
            where.append('ABS(l.valor - ?) < 0.005'); args.append(float(q['busca_valor']))
    ordem = ORDENS.get(q.get('ordem'), ORDENS['data'])
    if q.get('decrescente'):
        ordem = ordem.replace(', l.id', ' DESC, l.id DESC')
    return dicts(db.execute(f"""
        SELECT l.*, {VEN_PGTO} AS ven_pgto, c.descricao AS conta, ce.nome AS centro,
          CASE WHEN l.situacao='V' THEN (CASE l.tipo WHEN 'D' THEN 'Pago' ELSE 'Recebido' END)
               WHEN l.vencimento < date('now','localtime') THEN 'Vencido'
               ELSE (CASE l.tipo WHEN 'D' THEN 'A pagar' ELSE 'A receber' END) END AS situacao_desc
        FROM lancamentos l
        LEFT JOIN contas c ON c.id = l.conta_id
        LEFT JOIN centros ce ON ce.id = l.centro_id
        WHERE {' AND '.join(where)} ORDER BY {ordem}""", args))


def lancamento(db, empresa_id, id_):
    return um(db.execute('SELECT * FROM lancamentos WHERE id=? AND empresa_id=?', (id_, empresa_id)))


CAMPOS_LANC = ['tipo', 'data_mov', 'documento', 'descricao', 'pessoa', 'valor', 'situacao',
               'vencimento', 'data_pagamento', 'observacao', 'conta_id', 'centro_id']


def normaliza_lanc(b):
    o = {k: (None if _vazio(b.get(k)) else b.get(k)) for k in CAMPOS_LANC}
    if o['tipo'] not in ('D', 'R'):
        raise ValueError('Tipo deve ser D (despesa) ou R (receita).')
    if not o['descricao'] or not str(o['descricao']).strip():
        raise ValueError('Informe a descrição.')
    o['descricao'] = str(o['descricao']).strip()
    try:
        o['valor'] = float(o['valor'])
    except (TypeError, ValueError):
        o['valor'] = 0
    if not o['valor'] > 0:
        raise ValueError('Informe um valor maior que zero.')
    o['data_mov'] = o['data_mov'] or hoje()
    o['vencimento'] = o['vencimento'] or o['data_mov']
    o['situacao'] = 'V' if o['situacao'] == 'V' else 'P'
    o['data_pagamento'] = (o['data_pagamento'] or o['vencimento']) if o['situacao'] == 'V' else None
    return o


def registra_auxiliares(db, empresa_id, o):
    """Cadastra automaticamente descricoes e pessoas novas, como o MCC faz nos combos."""
    db.execute('INSERT OR IGNORE INTO itens (empresa_id, tipo, descricao) VALUES (?,?,?)', (empresa_id, o['tipo'], o['descricao']))
    if o.get('pessoa'):
        existe = db.execute('SELECT 1 FROM pessoas WHERE nome = ? AND (empresa_id = ? OR empresa_id IS NULL)',
                            (o['pessoa'], empresa_id)).fetchone()
        if not existe:
            db.execute('INSERT INTO pessoas (empresa_id, tipo, nome) VALUES (?,?,?)',
                       (empresa_id, 'F' if o['tipo'] == 'D' else 'C', o['pessoa']))


def salvar_lancamento(db, empresa_id, b, id_=None):
    o = normaliza_lanc(b)
    with tx(db):
        registra_auxiliares(db, empresa_id, o)
        vals = [o[k] for k in CAMPOS_LANC]
        if id_:
            sets = ', '.join(f'{k} = ?' for k in CAMPOS_LANC)
            r = db.execute(f"""UPDATE lancamentos SET {sets}, alterado_em = datetime('now','localtime')
                WHERE id = ? AND empresa_id = ? AND excluido_em IS NULL""", (*vals, id_, empresa_id))
            if not r.rowcount:
                raise ValueError('Lançamento não encontrado.')
            return id_
        r = db.execute(f"INSERT INTO lancamentos (empresa_id, {', '.join(CAMPOS_LANC)}) VALUES (?, {', '.join('?' * len(CAMPOS_LANC))})",
                       (empresa_id, *vals))
        return r.lastrowid


# Periodicidades do FMulCad: (meses, dias)
PERIODOS = {'diaria': (0, 1), 'semanal': (0, 7), 'quinzenal': (0, 15), 'mensal': (1, 0),
            'bimestral': (2, 0), 'trimestral': (3, 0), 'semestral': (6, 0), 'anual': (12, 0)}


def soma_periodo(data_iso, n, per):
    m, d = PERIODOS.get(per, PERIODOS['mensal'])
    base = date.fromisoformat(data_iso)
    if m:
        total = base.month - 1 + m * n
        y, mo = base.year + total // 12, total % 12 + 1
        return date(y, mo, min(base.day, calendar.monthrange(y, mo)[1])).isoformat()  # 31/01 + 1 mes = 28/02
    return (base + timedelta(days=d * n)).isoformat()


def parcelar(db, empresa_id, b):
    try:
        n = int(float(b.get('parcelas') or 0))
    except ValueError:
        n = 0
    if not 1 <= n <= 360:
        raise ValueError('Número de parcelas deve estar entre 1 e 360.')
    base = normaliza_lanc({**b, 'situacao': 'P'})
    grupo = str(uuid.uuid4())
    ids = []
    with tx(db):
        registra_auxiliares(db, empresa_id, base)
        for i in range(n):
            ven = soma_periodo(base['vencimento'], i, b.get('periodicidade'))
            mov = ven if b.get('mov_igual_vencimento') else base['data_mov']
            doc = f"{base['documento']} {i + 1}/{n}" if base['documento'] else f'{i + 1}/{n}'
            r = db.execute("""INSERT INTO lancamentos (empresa_id, tipo, data_mov, documento, descricao, pessoa, valor,
                situacao, vencimento, observacao, conta_id, centro_id, grupo, parcela, total_parcelas)
                VALUES (?,?,?,?,?,?,?,'P',?,?,?,?,?,?,?)""",
                           (empresa_id, base['tipo'], mov, doc, base['descricao'], base['pessoa'], base['valor'], ven,
                            base['observacao'], base['conta_id'], base['centro_id'], grupo, i + 1, n))
            ids.append(r.lastrowid)
    return ids


def baixar(db, empresa_id, ids, b=None):
    b = b or {}
    data = b.get('data_pagamento') or hoje()
    n = 0
    with tx(db):
        for id_ in ids:
            um_so = len(ids) == 1
            valor = float(b['valor']) if um_so and b.get('valor') else None
            obs = (b.get('observacao') or None) if um_so else None
            n += db.execute("""UPDATE lancamentos SET situacao='V', data_pagamento=?,
                conta_id=COALESCE(?, conta_id), valor=COALESCE(?, valor), observacao=COALESCE(?, observacao),
                alterado_em=datetime('now','localtime')
                WHERE id=? AND empresa_id=? AND situacao='P' AND excluido_em IS NULL""",
                            (data, b.get('conta_id') or None, valor, obs, id_, empresa_id)).rowcount
    return n


def estornar(db, empresa_id, id_):
    return db.execute("""UPDATE lancamentos SET situacao='P', data_pagamento=NULL, alterado_em=datetime('now','localtime')
        WHERE id=? AND empresa_id=?""", (id_, empresa_id)).rowcount


def afetados_exclusao(db, l, modo):
    """Lancamentos que uma exclusao atinge (FMultDelMov: esta, esta e as seguintes, todas em aberto)."""
    if not l.get('grupo') or modo == 'esta':
        return [l]
    if modo == 'seguintes':
        return dicts(db.execute('SELECT * FROM lancamentos WHERE grupo=? AND parcela>=? AND excluido_em IS NULL', (l['grupo'], l['parcela'])))
    if modo == 'todas':
        return dicts(db.execute('SELECT * FROM lancamentos WHERE grupo=? AND excluido_em IS NULL', (l['grupo'],)))
    return dicts(db.execute("SELECT * FROM lancamentos WHERE grupo=? AND situacao='P' AND excluido_em IS NULL", (l['grupo'],)))


def excluir(db, empresa_id, id_, modo='esta'):
    l = lancamento(db, empresa_id, id_)
    if not l:
        raise ValueError('Lançamento não encontrado.')
    agora = "datetime('now','localtime')"
    if not l['grupo'] or modo == 'esta':
        return db.execute(f'UPDATE lancamentos SET excluido_em={agora} WHERE id=?', (id_,)).rowcount
    if modo == 'seguintes':
        return db.execute(f'UPDATE lancamentos SET excluido_em={agora} WHERE grupo=? AND parcela>=? AND excluido_em IS NULL',
                          (l['grupo'], l['parcela'])).rowcount
    if modo == 'todas':  # FMultDelMov: "Excluir todos os registros em aberto ou pagos"
        return db.execute(f'UPDATE lancamentos SET excluido_em={agora} WHERE grupo=? AND excluido_em IS NULL', (l['grupo'],)).rowcount
    return db.execute(f"UPDATE lancamentos SET excluido_em={agora} WHERE grupo=? AND situacao='P' AND excluido_em IS NULL",
                      (l['grupo'],)).rowcount


def restaurar(db, empresa_id, id_):
    return db.execute('UPDATE lancamentos SET excluido_em=NULL WHERE id=? AND empresa_id=?', (id_, empresa_id)).rowcount


def excluidos(db, empresa_id):
    return dicts(db.execute('SELECT * FROM lancamentos WHERE empresa_id=? AND excluido_em IS NOT NULL ORDER BY excluido_em DESC LIMIT 500',
                            (empresa_id,)))


def transferir_empresa(db, empresa_id, destino, ids):
    n = 0
    with tx(db):
        for i in ids:
            n += db.execute('UPDATE lancamentos SET empresa_id=?, centro_id=NULL WHERE id=? AND empresa_id=?', (destino, i, empresa_id)).rowcount
    return n


# ---------- Saldos ----------

def saldos(db, empresa_id, ate=None):
    """Saldo de cada conta visivel. realizado: so o que foi pago ate a data;
    previsto: inclui o que esta em aberto (vencimento ate a data)."""
    ate = ate or hoje()
    contas = dicts(db.execute('SELECT * FROM contas WHERE (empresa_id = ? OR empresa_id IS NULL) ORDER BY ordem_pt(descricao)', (empresa_id,)))
    out = []
    for c in contas:
        l = db.execute("""SELECT
            COALESCE(SUM(CASE WHEN situacao='V' AND data_pagamento<=? THEN (CASE tipo WHEN 'R' THEN valor ELSE -valor END) END),0) AS real,
            COALESCE(SUM(CASE WHEN (situacao='V' AND data_pagamento<=?) OR (situacao='P' AND vencimento<=?)
                THEN (CASE tipo WHEN 'R' THEN valor ELSE -valor END) END),0) AS prev
            FROM lancamentos WHERE conta_id=? AND excluido_em IS NULL""", (ate, ate, ate, c['id'])).fetchone()
        m = db.execute("""SELECT COALESCE(SUM(CASE WHEN situacao='V' THEN v END),0) AS real, COALESCE(SUM(v),0) AS prev FROM (
              SELECT situacao, CASE tipo WHEN 'D' THEN valor ELSE -valor END AS v FROM movbancarias
                WHERE origem_id=? AND data<=? AND excluido_em IS NULL
              UNION ALL
              SELECT situacao, valor FROM movbancarias WHERE tipo='T' AND destino_id=? AND data<=? AND excluido_em IS NULL)""",
                       (c['id'], ate, c['id'], ate)).fetchone()
        out.append({**c, 'saldo': r2(c['saldo_inicial'] + l['real'] + m['real']),
                    'previsto': r2(c['saldo_inicial'] + l['prev'] + m['prev'])})
    return out


# ---------- Dashboard ----------

def dashboard(db, empresa_id, periodo_tipo='mes', de=None, ate=None, vencidos=False):
    de, ate = periodo_dash(periodo_tipo, de, ate)

    def soma(sql, *a):
        return r2(db.execute(f'SELECT COALESCE(SUM(valor),0) FROM lancamentos WHERE empresa_id=? AND excluido_em IS NULL AND {sql}',
                             (empresa_id, *a)).fetchone()[0])
    venc, vargs = ('vencimento <= ?', (ate,)) if vencidos else ('vencimento BETWEEN ? AND ?', (de, ate))
    rec = soma("tipo='R' AND data_mov BETWEEN ? AND ?", de, ate)
    des = soma("tipo='D' AND data_mov BETWEEN ? AND ?", de, ate)
    return {
        'de': de, 'ate': ate,
        'caixa': {
            'a_receber': soma(f"tipo='R' AND situacao='P' AND {venc}", *vargs),
            'a_pagar': soma(f"tipo='D' AND situacao='P' AND {venc}", *vargs),
            'recebido': soma("tipo='R' AND situacao='V' AND data_pagamento BETWEEN ? AND ?", de, ate),
            'pago': soma("tipo='D' AND situacao='V' AND data_pagamento BETWEEN ? AND ?", de, ate),
        },
        'competencia': {'receitas': rec, 'despesas': des, 'margem': r2(rec - des)},
    }


def dashboard_itens(db, empresa_id, de, ate, campo='data_mov', tipo='D', situacao=None):
    """Totais por item no periodo (graficos de barras/pizza do dashboard)."""
    col = 'data_pagamento' if campo == 'pagamento' else campo
    sit = f" AND situacao='{situacao}'" if situacao in ('V', 'P') else ''
    return dicts(db.execute(f"""SELECT descricao, SUM(valor) AS valor FROM lancamentos
        WHERE empresa_id=? AND excluido_em IS NULL AND tipo=? AND {col} BETWEEN ? AND ?{sit}
        GROUP BY descricao ORDER BY valor DESC""", (empresa_id, tipo, de, ate)))


def linear(db, empresa_id, agrupamento='mes', ano=None):
    """Analise linear: pagamentos x recebimentos realizados por dia/semana/mes."""
    ano = int(ano or date.today().year)
    d = date.today()
    if agrupamento == 'dia':
        de, ate, fmt = (d - timedelta(days=29)).isoformat(), d.isoformat(), '%Y-%m-%d'
    elif agrupamento == 'semana':
        de, ate, fmt = (d - timedelta(days=77)).isoformat(), d.isoformat(), '%Y-S%W'
    else:
        de, ate, fmt = f'{ano}-01-01', f'{ano}-12-31', '%Y-%m'
    rows = dicts(db.execute(f"""SELECT strftime('{fmt}', data_pagamento) AS periodo,
          SUM(CASE tipo WHEN 'D' THEN valor ELSE 0 END) AS pagamentos,
          SUM(CASE tipo WHEN 'R' THEN valor ELSE 0 END) AS recebimentos
        FROM lancamentos WHERE empresa_id=? AND excluido_em IS NULL AND situacao='V' AND data_pagamento BETWEEN ? AND ?
        GROUP BY 1 ORDER BY 1""", (empresa_id, de, ate)))
    if agrupamento == 'dia':
        todos = [(date.fromisoformat(de) + timedelta(days=i)).isoformat() for i in range(30)]
    elif agrupamento == 'semana':
        todos = [r['periodo'] for r in rows]
    else:
        todos = [f'{ano}-{i:02d}' for i in range(1, 13)]
    por = {r['periodo']: r for r in rows}
    out = []
    for p in todos:
        r = por.get(p, {'pagamentos': 0, 'recebimentos': 0})
        out.append({'periodo': p, 'pagamentos': r2(r['pagamentos']), 'recebimentos': r2(r['recebimentos']),
                    'margem': r2(r['recebimentos'] - r['pagamentos'])})
    return out


def lembretes(db, empresa_id, dias=7):
    """Lembrete de contas (FLemb): vencidas e a vencer nos proximos dias."""
    lim = (date.today() + timedelta(days=int(dias))).isoformat()
    return dicts(db.execute("""SELECT l.*, CASE WHEN vencimento < date('now','localtime') THEN 'Vencida' ELSE 'A vencer' END AS status
        FROM lancamentos l WHERE empresa_id=? AND excluido_em IS NULL AND situacao='P' AND vencimento <= ?
        ORDER BY vencimento""", (empresa_id, lim)))


# ---------- Relatorios ----------

def _tipo_nome(t):
    return 'despesas' if t == 'D' else 'receitas'


def _filtro_periodo(q, campo):
    per = (q['de'], q['ate']) if q.get('de') and q.get('ate') else periodo(q.get('ano'), q.get('mes'))
    if per:
        return f' AND {campo} BETWEEN ? AND ?', list(per), f'{br(per[0])} a {br(per[1])}'
    return '', [], 'Todo período'


def tabela(titulo, subtitulo, colunas, linhas, somar):
    """Resultado padrao de relatorio. Linhas de grupo/subtotal (_tipo) nao entram no total."""
    totais = {k: r2(sum(float(r.get(k) or 0) for r in linhas if not r.get('_tipo'))) for k in somar}
    return {'titulo': titulo, 'subtitulo': subtitulo,
            'colunas': [{'campo': c[0], 'rotulo': c[1], 'fmt': c[2] if len(c) > 2 else None} for c in colunas],
            'linhas': linhas, 'totais': totais}


def relatorio(db, empresa_id, nome, q):
    tipo = 'R' if q.get('tipo') == 'R' else 'D'
    sit = f" AND l.situacao='{q['situacao']}'" if q.get('situacao') in ('V', 'P') else ''
    base = 'FROM lancamentos l WHERE l.empresa_id=? AND l.excluido_em IS NULL'
    if nome == 'lancamentos':
        psql, pargs, ptxt = _filtro_periodo(q, VEN_PGTO if q.get('campo_data') == 'vencimento' else 'l.data_mov')
        conta = f" AND l.conta_id={int(q['conta_id'])}" if q.get('conta_id') else ''
        linhas = dicts(db.execute(f"""SELECT l.data_mov, l.documento, l.descricao, l.pessoa, {VEN_PGTO} AS ven_pgto,
              CASE l.situacao WHEN 'V' THEN 'Quitado' ELSE 'Em aberto' END AS sit, l.observacao, l.valor
            {base} AND l.tipo=?{sit}{conta}{psql} ORDER BY l.data_mov""", (empresa_id, tipo, *pargs)))
        return tabela(q.get('titulo') or f'Relatório de {_tipo_nome(tipo)}', ptxt,
                      [('data_mov', 'Data', 'data'), ('documento', 'Documento'), ('descricao', 'Descrição'), ('pessoa', 'Pessoa'),
                       ('ven_pgto', 'Vcto/Pgto', 'data'), ('sit', 'Situação'), ('observacao', 'Observação'), ('valor', 'Valor', 'moeda')],
                      linhas, ['valor'])
    if nome == 'totais_item':
        psql, pargs, ptxt = _filtro_periodo(q, 'l.data_mov')
        linhas = dicts(db.execute(f"""SELECT l.descricao, COUNT(*) AS qtd, SUM(l.valor) AS total {base} AND l.tipo=?{sit}{psql}
            GROUP BY l.descricao ORDER BY total DESC""", (empresa_id, tipo, *pargs)))
        return tabela(f'Relatório de {_tipo_nome(tipo)} totais', ptxt,
                      [('descricao', 'Ítem'), ('qtd', 'Lançamentos', 'int'), ('total', 'Total', 'moeda')], linhas, ['qtd', 'total'])
    if nome == 'por_pessoa':
        psql, pargs, ptxt = _filtro_periodo(q, VEN_PGTO)
        linhas = dicts(db.execute(f"""SELECT COALESCE(l.pessoa,'(sem pessoa)') AS pessoa, COUNT(*) AS qtd, SUM(l.valor) AS total
            {base} AND l.tipo=?{sit}{psql} GROUP BY 1 ORDER BY total DESC""", (empresa_id, tipo, *pargs)))
        return tabela('Contas a pagar por fornecedor' if tipo == 'D' else 'Contas a receber por cliente', ptxt,
                      [('pessoa', 'Fornecedor' if tipo == 'D' else 'Cliente'), ('qtd', 'Lançamentos', 'int'), ('total', 'Total', 'moeda')],
                      linhas, ['qtd', 'total'])
    if nome == 'pontualidade':
        psql, pargs, ptxt = _filtro_periodo(q, 'l.vencimento')
        linhas = dicts(db.execute(f"""SELECT COALESCE(l.pessoa,'(sem pessoa)') AS pessoa, COUNT(*) AS ocorrencias,
              MAX(julianday(l.data_pagamento)-julianday(l.vencimento)) AS maior_atraso,
              MIN(julianday(l.data_pagamento)-julianday(l.vencimento)) AS maior_antecipacao,
              AVG(julianday(l.data_pagamento)-julianday(l.vencimento)) AS media
            {base} AND l.tipo=? AND l.situacao='V'{psql} GROUP BY 1 ORDER BY media DESC""", (empresa_id, tipo, *pargs)))
        for r in linhas:
            r['maior_atraso'] = max(0, round(r['maior_atraso'] or 0))
            r['maior_antecipacao'] = max(0, round(-(r['maior_antecipacao'] or 0)))
            r['media'] = round(r['media'] or 0)
        return tabela(f"Análise de pontualidade de {'pagamentos' if tipo == 'D' else 'recebimentos'}", ptxt,
                      [('pessoa', 'Pessoa'), ('ocorrencias', 'Ocorrências', 'int'), ('maior_atraso', 'Maior atraso (dias)', 'int'),
                       ('maior_antecipacao', 'Maior antecipação (dias)', 'int'), ('media', 'Média (dias, + = atraso)', 'int')], linhas, [])
    if nome == 'fluxo_dia':
        prev = q.get('previsao') == '1'
        psql, pargs, ptxt = _filtro_periodo(q, VEN_PGTO)
        cond = '' if prev else " AND l.situacao='V'"
        linhas = dicts(db.execute(f"""SELECT {VEN_PGTO} AS dia,
              SUM(CASE l.tipo WHEN 'D' THEN l.valor ELSE 0 END) AS despesas,
              SUM(CASE l.tipo WHEN 'R' THEN l.valor ELSE 0 END) AS receitas
            {base}{cond}{psql} GROUP BY 1 ORDER BY 1""", (empresa_id, *pargs)))
        acc = 0
        for r in linhas:
            r['saldo_dia'] = r2(r['receitas'] - r['despesas']); acc = r2(acc + r['saldo_dia']); r['acumulado'] = acc
        return tabela('Previsão de caixa por dia' if prev else 'Fluxo de caixa por dia (realizado)', ptxt,
                      [('dia', 'Dia', 'data'), ('receitas', 'Receitas', 'moeda'), ('despesas', 'Despesas', 'moeda'),
                       ('saldo_dia', 'Saldo do dia', 'moeda'), ('acumulado', 'Acumulado', 'moeda')], linhas, ['receitas', 'despesas', 'saldo_dia'])
    if nome == 'fluxo':
        # Fluxo de caixa (realizado) / previsao de caixa por lancamento, com saldo acumulado
        prev = q.get('previsao') == '1'
        psql, pargs, ptxt = _filtro_periodo(q, VEN_PGTO)
        cond = '' if prev else " AND l.situacao='V'"
        linhas = dicts(db.execute(f"""SELECT {VEN_PGTO} AS data, CASE l.tipo WHEN 'D' THEN 'Despesa' ELSE 'Receita' END AS tipo_txt,
              l.documento, l.descricao, l.pessoa, CASE l.situacao WHEN 'V' THEN 'Quitado' ELSE 'Em aberto' END AS sit,
              CASE l.tipo WHEN 'R' THEN l.valor END AS receitas, CASE l.tipo WHEN 'D' THEN l.valor END AS despesas
            {base}{cond}{psql} ORDER BY 1, l.id""", (empresa_id, *pargs)))
        acc = 0
        for r in linhas:
            acc = r2(acc + (r['receitas'] or 0) - (r['despesas'] or 0)); r['saldo'] = acc
        return tabela('Previsão de caixa' if prev else 'Fluxo de caixa (realizado)', ptxt,
                      [('data', 'Data', 'data'), ('tipo_txt', 'Tipo'), ('documento', 'Doc.'), ('descricao', 'Descrição'), ('pessoa', 'Pessoa'),
                       ('sit', 'Situação'), ('receitas', 'Receitas', 'moeda'), ('despesas', 'Despesas', 'moeda'), ('saldo', 'Saldo', 'moeda')],
                      linhas, ['receitas', 'despesas'])
    if nome == 'extrato':
        conta_id = int(q.get('conta_id') or 0)
        if not conta_id:
            raise ValueError('Selecione a conta.')
        conta = um(db.execute('SELECT * FROM contas WHERE id=?', (conta_id,)))
        prev = q.get('previsao') == '1'
        per = (q['de'], q['ate']) if q.get('de') and q.get('ate') else (periodo(q.get('ano'), q.get('mes')) or ('0000-01-01', '9999-12-31'))
        try:
            vespera = (date.fromisoformat(per[0]) - timedelta(days=1)).isoformat()
        except ValueError:
            vespera = per[0]
        sal = next((c for c in saldos(db, empresa_id, vespera) if c['id'] == conta_id), None)
        inicial = (sal['previsto'] if prev else sal['saldo']) if sal else conta['saldo_inicial']
        sit_l = "situacao IN ('V','P')" if prev else "situacao='V'"
        data_l = "CASE situacao WHEN 'V' THEN data_pagamento ELSE vencimento END" if prev else 'data_pagamento'
        sit_m = "situacao IN ('V','P')" if prev else "situacao='V'"
        linhas = dicts(db.execute(f"""
            SELECT {data_l} AS data, descricao || COALESCE(' - ' || pessoa, '') AS historico, documento,
              CASE tipo WHEN 'R' THEN valor END AS credito, CASE tipo WHEN 'D' THEN valor END AS debito,
              CASE situacao WHEN 'V' THEN '' ELSE 'previsto' END AS obs
              FROM lancamentos WHERE conta_id=? AND {sit_l} AND excluido_em IS NULL AND {data_l} BETWEEN ? AND ?
            UNION ALL
            SELECT data, CASE tipo WHEN 'D' THEN 'Depósito' WHEN 'R' THEN 'Retirada' ELSE 'Transferência enviada' END || COALESCE(' - ' || observacao,''), NULL,
              CASE tipo WHEN 'D' THEN valor END, CASE WHEN tipo IN ('R','T') THEN valor END, CASE situacao WHEN 'V' THEN '' ELSE 'previsto' END
              FROM movbancarias WHERE origem_id=? AND {sit_m} AND excluido_em IS NULL AND data BETWEEN ? AND ?
            UNION ALL
            SELECT data, 'Transferência recebida' || COALESCE(' - ' || observacao,''), NULL, valor, NULL, CASE situacao WHEN 'V' THEN '' ELSE 'previsto' END
              FROM movbancarias WHERE tipo='T' AND destino_id=? AND {sit_m} AND excluido_em IS NULL AND data BETWEEN ? AND ?
            ORDER BY 1""", (conta_id, *per, conta_id, *per, conta_id, *per)))
        s = inicial
        for r in linhas:
            s = r2(s + (r['credito'] or 0) - (r['debito'] or 0)); r['saldo'] = s
        linhas.insert(0, {'data': per[0], 'historico': 'Saldo anterior', 'saldo': inicial})
        titulo = ('Extrato de previsão bancária' if prev else ('Extrato do caixa interno' if conta['tipo'] == 'C' else 'Extrato de conta bancária'))
        return tabela(f"{titulo} — {conta['descricao']}", f'{br(per[0])} a {br(per[1])}',
                      [('data', 'Data', 'data'), ('historico', 'Histórico'), ('documento', 'Doc.'), ('obs', ''), ('credito', 'Crédito', 'moeda'),
                       ('debito', 'Débito', 'moeda'), ('saldo', 'Saldo', 'moeda')], linhas, ['credito', 'debito'])
    if nome == 'fechamento':
        # Extrato de fechamento de caixa: movimento realizado de todas as contas no periodo
        psql, pargs, ptxt = _filtro_periodo(q, 'l.data_pagamento')
        linhas = dicts(db.execute(f"""SELECT l.data_pagamento AS data, c.descricao AS conta, l.descricao || COALESCE(' - ' || l.pessoa,'') AS historico,
              l.documento, CASE l.tipo WHEN 'R' THEN l.valor END AS credito, CASE l.tipo WHEN 'D' THEN l.valor END AS debito
            {base.replace('FROM lancamentos l', 'FROM lancamentos l LEFT JOIN contas c ON c.id=l.conta_id')} AND l.situacao='V'{psql}
            ORDER BY l.data_pagamento, ordem_pt(c.descricao)""", (empresa_id, *pargs)))
        acc = 0
        for r in linhas:
            acc = r2(acc + (r['credito'] or 0) - (r['debito'] or 0)); r['saldo'] = acc
        return tabela('Extrato de fechamento de caixa', ptxt,
                      [('data', 'Data', 'data'), ('conta', 'Conta'), ('historico', 'Histórico'), ('documento', 'Doc.'),
                       ('credito', 'Crédito', 'moeda'), ('debito', 'Débito', 'moeda'), ('saldo', 'Movimento acumulado', 'moeda')],
                      linhas, ['credito', 'debito'])
    if nome == 'saldos':
        data = q.get('data') or hoje()
        linhas = [c for c in saldos(db, empresa_id, data) if c['ativa']]
        return tabela('Relatório de saldo de contas', f'Posição em {br(data)}',
                      [('descricao', 'Conta'), ('saldo', 'Saldo realizado', 'moeda'), ('previsto', 'Saldo previsto', 'moeda')], linhas, ['saldo', 'previsto'])
    if nome == 'comparativo_saldos':
        d1, d2 = q.get('data1') or hoje(), q.get('data2') or hoje()
        s1 = {c['id']: c for c in saldos(db, empresa_id, d1)}
        linhas = []
        for c in saldos(db, empresa_id, d2):
            if not c['ativa']:
                continue
            a = s1[c['id']]['saldo']
            linhas.append({'descricao': c['descricao'], 'saldo1': a, 'saldo2': c['saldo'], 'compara': r2(c['saldo'] - a)})
        return tabela('Relatório comparativo de saldos', f'{br(d1)} x {br(d2)}',
                      [('descricao', 'Conta'), ('saldo1', f'Saldo em {br(d1)}', 'moeda'), ('saldo2', f'Saldo em {br(d2)}', 'moeda'),
                       ('compara', 'Variação', 'moeda')], linhas, ['saldo1', 'saldo2', 'compara'])
    if nome == 'pessoas':
        tp = 'C' if q.get('pessoa_tipo') == 'C' else 'F'
        linhas = dicts(db.execute("""SELECT nome, CASE pessoa WHEN 'F' THEN 'Física' ELSE 'Jurídica' END AS pessoa_txt, documento,
              endereco, bairro, cidade, uf, cep, telefone, email, contato FROM pessoas
            WHERE tipo=? AND (empresa_id=? OR empresa_id IS NULL) ORDER BY ordem_pt(nome)""", (tp, empresa_id)))
        for r in linhas:
            r['local'] = ' - '.join(x for x in [r['cidade'], r['uf']] if x)
        return tabela('Relatório de clientes' if tp == 'C' else 'Relatório de fornecedores', f'{len(linhas)} cadastro(s)',
                      [('nome', 'Nome'), ('pessoa_txt', 'Pessoa'), ('documento', 'CPF/CNPJ'), ('endereco', 'Endereço'),
                       ('local', 'Cidade/UF'), ('telefone', 'Telefone'), ('email', 'E-mail')], linhas, [])
    if nome == 'demonstrativo':
        ano = int(q.get('ano') or date.today().year)
        grp = {'item': 'l.descricao', 'pessoa': "COALESCE(l.pessoa,'(sem pessoa)')", 'centro': "COALESCE(ce.nome,'(sem centro)')",
               'conta': "COALESCE(c.descricao,'(sem conta)')"}.get(q.get('agrupar'), 'l.descricao')
        meses = ',\n'.join(f"""SUM(CASE WHEN strftime('%m', l.data_mov)='{i + 1:02d}' THEN l.valor ELSE 0 END) AS "{m}\"""" for i, m in enumerate(MESES))
        linhas = dicts(db.execute(f"""SELECT {grp} AS descricao, {meses}, SUM(l.valor) AS total
            FROM lancamentos l LEFT JOIN centros ce ON ce.id=l.centro_id LEFT JOIN contas c ON c.id=l.conta_id
            WHERE l.empresa_id=? AND l.excluido_em IS NULL AND l.tipo=? AND strftime('%Y', l.data_mov)=?
            GROUP BY 1 ORDER BY total DESC""", (empresa_id, tipo, str(ano))))
        for r in linhas:
            r['media'] = r2(r['total'] / 12)
        return tabela(f'Demonstrativo anual de {_tipo_nome(tipo)}', str(ano),
                      [('descricao', 'Descrição'), *[(m, m, 'moeda') for m in MESES], ('media', 'Média', 'moeda'), ('total', 'Total', 'moeda')],
                      linhas, [*MESES, 'media', 'total'])
    if nome == 'centros':
        psql, pargs, ptxt = _filtro_periodo(q, 'l.data_mov')
        per = (q['de'], q['ate']) if q.get('de') and q.get('ate') else periodo(q.get('ano'), q.get('mes'))
        n_meses = max(1, round((date.fromisoformat(per[1]) - date.fromisoformat(per[0])).days / 30.44)) if per else 12
        meta = 'ce.orcamento' if tipo == 'D' else 'ce.projecao'
        aplica = 'ce.aplica_despesa' if tipo == 'D' else 'ce.aplica_receita'
        linhas = dicts(db.execute(f"""SELECT ce.nome, {meta} * ? AS meta,
              COALESCE((SELECT SUM(l.valor) FROM lancamentos l WHERE l.centro_id=ce.id AND l.empresa_id=? AND l.excluido_em IS NULL
                AND l.tipo=?{psql}),0) AS realizado
            FROM centros ce WHERE ce.empresa_id=? AND {aplica}=1 ORDER BY ordem_pt(ce.nome)""", (n_meses, empresa_id, tipo, *pargs, empresa_id)))
        for r in linhas:
            r['diferenca'] = r2(r['meta'] - r['realizado'])
            r['perc'] = r2(r['realizado'] / r['meta'] * 100) if r['meta'] else None
        return tabela('Orçamento por centro de custo' if tipo == 'D' else 'Projeção por centro de lucro', ptxt,
                      [('nome', 'Centro'), ('meta', 'Orçamento' if tipo == 'D' else 'Projeção', 'moeda'), ('realizado', 'Realizado', 'moeda'),
                       ('diferenca', 'Diferença', 'moeda'), ('perc', '% atingido', 'num')], linhas, ['meta', 'realizado', 'diferenca'])
    if nome == 'centro_itens':
        # Relatorio de despesas/receitas (detalhado ou totais) por centro de custo
        psql, pargs, ptxt = _filtro_periodo(q, 'l.data_mov')
        if q.get('totais') == '1':
            linhas = dicts(db.execute(f"""SELECT COALESCE(ce.nome,'(sem centro)') AS centro, COUNT(*) AS qtd, SUM(l.valor) AS total
                FROM lancamentos l LEFT JOIN centros ce ON ce.id=l.centro_id WHERE l.empresa_id=? AND l.excluido_em IS NULL AND l.tipo=?{psql}
                GROUP BY 1 ORDER BY total DESC""", (empresa_id, tipo, *pargs)))
            return tabela(f'Relatório de {_tipo_nome(tipo)} totais por centro', ptxt,
                          [('centro', 'Centro'), ('qtd', 'Lançamentos', 'int'), ('total', 'Total', 'moeda')], linhas, ['qtd', 'total'])
        return analitico(db, empresa_id, {**q, 'tipo': tipo, 'agrupar1': 'centro', 'agrupar2': 'item', 'modo': 'totalizado',
                                          'titulo': f'Relatório de {_tipo_nome(tipo)} por centro'})
    if nome == 'fluxo_centros':
        psql, pargs, ptxt = _filtro_periodo(q, VEN_PGTO)
        linhas = dicts(db.execute(f"""SELECT COALESCE(ce.nome,'(sem centro)') AS centro,
              SUM(CASE WHEN l.tipo='D' AND l.situacao='V' THEN l.valor ELSE 0 END) AS pago,
              SUM(CASE WHEN l.tipo='R' AND l.situacao='V' THEN l.valor ELSE 0 END) AS recebido,
              SUM(CASE WHEN l.tipo='D' AND l.situacao='P' THEN l.valor ELSE 0 END) AS a_pagar,
              SUM(CASE WHEN l.tipo='R' AND l.situacao='P' THEN l.valor ELSE 0 END) AS a_receber
            FROM lancamentos l LEFT JOIN centros ce ON ce.id=l.centro_id WHERE l.empresa_id=? AND l.excluido_em IS NULL{psql}
            GROUP BY 1 ORDER BY ordem_pt(centro)""", (empresa_id, *pargs)))
        for r in linhas:
            r['saldo_real'] = r2(r['recebido'] - r['pago'])
            r['saldo_prev'] = r2(r['recebido'] + r['a_receber'] - r['pago'] - r['a_pagar'])
        return tabela('Relatório de fluxo de caixa por centro', ptxt,
                      [('centro', 'Centro'), ('pago', 'Total pago', 'moeda'), ('recebido', 'Total recebido', 'moeda'),
                       ('a_pagar', 'Total a pagar', 'moeda'), ('a_receber', 'Total a receber', 'moeda'),
                       ('saldo_real', 'Saldo real', 'moeda'), ('saldo_prev', 'Saldo previsto', 'moeda')],
                      linhas, ['pago', 'recebido', 'a_pagar', 'a_receber', 'saldo_real', 'saldo_prev'])
    if nome == 'dre':
        psql, pargs, ptxt = _filtro_periodo(q, 'l.data_mov')
        linhas = dicts(db.execute(f"""SELECT CASE l.tipo WHEN 'R' THEN 'Receitas' ELSE 'Despesas' END AS grupo, l.descricao,
              SUM(CASE l.tipo WHEN 'R' THEN l.valor ELSE -l.valor END) AS valor
            {base}{psql} GROUP BY l.tipo, l.descricao ORDER BY l.tipo DESC, ABS(valor) DESC""", (empresa_id, *pargs)))
        return tabela('Demonstrativo de resultados', ptxt, [('grupo', 'Grupo'), ('descricao', 'Ítem'), ('valor', 'Valor', 'moeda')], linhas, ['valor'])
    if nome == 'analitico':
        return analitico(db, empresa_id, q)
    raise ValueError(f'Relatório desconhecido: {nome}')


# ---------- Relatorio analitico (FAnalise) com agrupamentos livres ----------

AGRUPAMENTOS = {  # lista fechada: nunca SQL vindo da interface
    'item': ('Descrição', lambda d: 'l.descricao'),
    'pessoa': ('Cliente/fornecedor', lambda d: "COALESCE(NULLIF(l.pessoa,''),'(sem pessoa)')"),
    'conta': ('Conta', lambda d: "COALESCE(c.descricao,'(sem conta)')"),
    'centro': ('Centro de custo', lambda d: "COALESCE(ce.nome,'(sem centro)')"),
    'mes': ('Mês', lambda d: f"strftime('%Y-%m', {d})"),
    'situacao': ('Situação', lambda d: "CASE l.situacao WHEN 'V' THEN 'Pago' ELSE 'Em aberto' END"),
    'tipo': ('Tipo', lambda d: "CASE l.tipo WHEN 'D' THEN 'Despesas' ELSE 'Receitas' END"),
}
ORDENS_ANALITICO = {'data': 'l.data_mov', 'vencimento': VEN_PGTO, 'pessoa': 'ordem_pt(l.pessoa)', 'descricao': 'ordem_pt(l.descricao)',
                    'observacao': 'ordem_pt(l.observacao)', 'documento': 'ordem_pt(l.documento)', 'valor': 'l.valor'}


def analitico(db, empresa_id, q):
    tipos = [q['tipo']] if q.get('tipo') in ('D', 'R') else ['D', 'R']
    campo_data = VEN_PGTO if q.get('campo_data') == 'vencimento' else 'l.data_mov'
    where = ['l.empresa_id = ?', 'l.excluido_em IS NULL', f"l.tipo IN ({','.join(repr(t) for t in tipos)})"]
    args = [empresa_id]
    if q.get('situacao') in ('V', 'P'):
        where.append('l.situacao = ?'); args.append(q['situacao'])
    if q.get('de'):
        where.append(f'{campo_data} >= ?'); args.append(q['de'])
    if q.get('ate'):
        where.append(f'{campo_data} <= ?'); args.append(q['ate'])
    if q.get('descricao'):
        where.append('l.descricao LIKE ?'); args.append(f"%{q['descricao']}%")
    if q.get('pessoa'):
        where.append('l.pessoa LIKE ?'); args.append(f"%{q['pessoa']}%")
    if q.get('conta_id'):
        where.append('l.conta_id = ?'); args.append(int(q['conta_id']))
    if q.get('centro_id'):
        where.append('l.centro_id = ?'); args.append(int(q['centro_id']))
    grupos = []
    for g in (q.get('agrupar1'), q.get('agrupar2')):
        if g and g in AGRUPAMENTOS and g not in grupos:
            grupos.append(g)
    gexpr = [AGRUPAMENTOS[g][1](campo_data) for g in grupos]
    dois = len(tipos) == 2
    frm = f"""FROM lancamentos l LEFT JOIN contas c ON c.id = l.conta_id LEFT JOIN centros ce ON ce.id = l.centro_id
        WHERE {' AND '.join(where)}"""
    sub = ' '.join(x for x in [q.get('de') and f"de {br(q['de'])}", q.get('ate') and f"até {br(q['ate'])}"] if x) or 'Todo período'
    titulo = (str(q.get('titulo') or '').strip()[:80]) or 'Relatório analítico'
    valor_cols = [('receitas', 'Receitas', 'moeda'), ('despesas', 'Despesas', 'moeda'), ('saldo', 'Saldo', 'moeda')] if dois else [('total', 'Total', 'moeda')]
    soma_valores = ("SUM(CASE l.tipo WHEN 'R' THEN l.valor ELSE 0 END) AS receitas, SUM(CASE l.tipo WHEN 'D' THEN l.valor ELSE 0 END) AS despesas"
                    if dois else 'SUM(l.valor) AS total')

    def fecha_valores(r):
        if dois:
            r['saldo'] = r2((r.get('receitas') or 0) - (r.get('despesas') or 0))
        return r

    def rotular(g, v):
        return rotulo_mes(v) if g == 'mes' else v

    if q.get('modo') == 'totalizado':
        if not grupos:
            raise ValueError('Escolha ao menos um agrupamento para o relatório totalizado.')
        sel = ', '.join(f'{e} AS g{i}' for i, e in enumerate(gexpr))
        gs = ', '.join(f'g{i}' for i in range(len(gexpr)))
        ords = ', '.join(f'ordem_pt(g{i})' for i in range(len(gexpr)))
        linhas = [fecha_valores({**r, 'g0': rotular(grupos[0], r['g0']), **({'g1': rotular(grupos[1], r['g1'])} if len(grupos) > 1 else {})})
                  for r in dicts(db.execute(f'SELECT {sel}, COUNT(*) AS qtd, {soma_valores} {frm} GROUP BY {gs} ORDER BY {ords}', args))]
        saida = []
        if len(grupos) == 2:  # subtotal ao fim de cada grupo do 1o nivel
            atual, acc = object(), None

            def fecha():
                if acc:
                    saida.append(fecha_valores({**acc, '_tipo': 'subtotal', 'g0': f'Subtotal {atual}', 'g1': ''}))
            for r in linhas:
                if r['g0'] != atual:
                    fecha(); atual = r['g0']; acc = {'qtd': 0, 'receitas': 0, 'despesas': 0, 'total': 0}
                for k in ('qtd', 'receitas', 'despesas', 'total'):
                    acc[k] = r2(acc[k] + (r.get(k) or 0))
                saida.append(r)
            fecha()
        else:
            saida = linhas
        return tabela(titulo, f"{sub} · totalizado por {' e '.join(AGRUPAMENTOS[g][0].lower() for g in grupos)}",
                      [*[(f'g{i}', AGRUPAMENTOS[g][0]) for i, g in enumerate(grupos)], ('qtd', 'Lançamentos', 'int'), *valor_cols],
                      saida, ['qtd', *[c[0] for c in valor_cols]])

    ordem = ORDENS_ANALITICO.get(q.get('ordem'), ORDENS_ANALITICO['data'])
    direcao = 'DESC' if q.get('decrescente') in ('1', True, 1) else 'ASC'
    gsel = ''.join(f'{e} AS g{i}, ' for i, e in enumerate(gexpr))
    gord = ''.join(f'ordem_pt(g{i}), ' for i in range(len(gexpr)))
    linhas = [fecha_valores(r) for r in dicts(db.execute(f"""SELECT {gsel}
          l.id, l.tipo, l.data_mov, {VEN_PGTO} AS ven_pgto, l.documento, l.descricao, l.pessoa, l.observacao,
          c.descricao AS conta, ce.nome AS centro, CASE l.situacao WHEN 'V' THEN 'Pago' ELSE 'Em aberto' END AS sit,
          CASE l.tipo WHEN 'R' THEN l.valor END AS receitas, CASE l.tipo WHEN 'D' THEN l.valor END AS despesas, l.valor AS total
        {frm} ORDER BY {gord}{ordem} {direcao}, l.id""", args))]
    saida = []
    acc = [None] * len(grupos)
    chave = [object()] * len(grupos)

    def fecha(nivel):
        for n in range(len(grupos) - 1, nivel - 1, -1):
            if acc[n]:
                saida.append(fecha_valores({'_tipo': 'subtotal', '_nivel': n,
                                            'descricao': f'Subtotal {rotular(grupos[n], chave[n])} ({acc[n]["qtd"]})',
                                            **{k: v for k, v in acc[n].items() if k != 'qtd'}}))
            acc[n] = None
    for r in linhas:
        mudou = next((n for n in range(len(grupos)) if r[f'g{n}'] != chave[n]), -1)
        if mudou >= 0:
            fecha(mudou)
            for n in range(mudou, len(grupos)):
                chave[n] = r[f'g{n}']
                acc[n] = {'receitas': 0, 'despesas': 0, 'total': 0, 'qtd': 0}
                saida.append({'_tipo': 'grupo', '_nivel': n, 'data_mov': f'{AGRUPAMENTOS[grupos[n]][0]}: {rotular(grupos[n], chave[n])}'})
        for a in acc:
            if a:
                a['qtd'] += 1
                for k in ('receitas', 'despesas', 'total'):
                    a[k] = r2(a[k] + (r.get(k) or 0))
        resto = {k: v for k, v in r.items() if not re.fullmatch(r'g\d', k)}
        saida.append({**resto, 'tipo': 'Despesa' if r['tipo'] == 'D' else 'Receita'})
    fecha(0)
    return tabela(titulo, f'{sub} · {len(linhas)} lançamento(s)',
                  [('data_mov', 'Data', 'data'), ('ven_pgto', 'Vcto/Pgto', 'data'), *([('tipo', 'Tipo')] if dois else []), ('documento', 'Doc.'),
                   ('descricao', 'Descrição'), ('pessoa', 'Pessoa'), ('conta', 'Conta'), ('centro', 'Centro'), ('sit', 'Situação'),
                   ('observacao', 'Observação'), *valor_cols],
                  saida, [c[0] for c in valor_cols])


# ---------- Graficos gerenciais (FChart) ----------

def meses_entre(de, ate):
    out = []
    y, m = int(de[:4]), int(de[5:7])
    y2, m2 = int(ate[:4]), int(ate[5:7])
    while (y < y2 or (y == y2 and m <= m2)) and len(out) < 120:
        out.append(f'{y}-{m:02d}')
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def grafico(db, empresa_id, nome, q):
    ano = date.today().year
    de, ate = q.get('de') or f'{ano}-01-01', q.get('ate') or f'{ano}-12-31'
    campo = VEN_PGTO if q.get('campo_data') == 'vencimento' else 'l.data_mov'
    sit = f" AND l.situacao='{q['situacao']}'" if q.get('situacao') in ('V', 'P') else ''
    base = f"""FROM lancamentos l LEFT JOIN centros ce ON ce.id = l.centro_id
        WHERE l.empresa_id=? AND l.excluido_em IS NULL AND {campo} BETWEEN ? AND ?{sit}"""
    sub = f'{br(de)} a {br(ate)}'
    tipo = 'R' if q.get('tipo') == 'R' else 'D'
    nome_tipo = _tipo_nome(tipo)
    if nome == 'desp_rec':
        rows = {r['mes']: r for r in dicts(db.execute(f"""SELECT strftime('%Y-%m', {campo}) AS mes,
              SUM(CASE l.tipo WHEN 'R' THEN l.valor ELSE 0 END) AS r, SUM(CASE l.tipo WHEN 'D' THEN l.valor ELSE 0 END) AS d
            {base} GROUP BY 1""", (empresa_id, de, ate)))}
        pontos = []
        for m in meses_entre(de, ate):
            r = rows.get(m, {'r': 0, 'd': 0})
            pontos.append({'rotulo': rotulo_mes(m), 'valores': [r2(r['r']), r2(r['d'])], 'margem': r2(r['r'] - r['d'])})
        return {'forma': 'colunas', 'titulo': 'Gráfico despesas x receitas', 'subtitulo': sub, 'series': ['Receitas', 'Despesas'],
                'linha': 'Margem', 'pontos': pontos}
    if nome == 'composicao':
        agr = {'item': 'l.descricao', 'pessoa': "COALESCE(NULLIF(l.pessoa,''),'(sem pessoa)')", 'centro': "COALESCE(ce.nome,'(sem centro)')"}.get(q.get('agrupar'), 'l.descricao')
        rows = dicts(db.execute(f'SELECT {agr} AS rotulo, SUM(l.valor) AS valor {base} AND l.tipo=? GROUP BY 1 ORDER BY valor DESC', (empresa_id, de, ate, tipo)))
        total = sum(r['valor'] for r in rows)
        top = rows[:12]
        resto = sum(r['valor'] for r in rows[12:])
        if resto > 0:
            top.append({'rotulo': f'Outros ({len(rows) - 12})', 'valor': resto})
        por = {'item': 'ítem', 'pessoa': 'fornecedor' if tipo == 'D' else 'cliente',
               'centro': 'centro de custo' if tipo == 'D' else 'centro de lucro'}.get(q.get('agrupar'), 'ítem')
        return {'forma': 'ranking', 'titulo': f'Gráfico de {nome_tipo} por {por}', 'subtitulo': sub, 'total': r2(total),
                'pontos': [{'rotulo': r['rotulo'], 'valor': r2(r['valor']), 'perc': r2(r['valor'] / total * 100) if total else 0} for r in top]}
    if nome == 'evolucao':
        agrupar = 'pessoa' if q.get('agrupar') == 'pessoa' else 'item'
        col = 'l.pessoa' if agrupar == 'pessoa' else 'l.descricao'
        alvo = str(q.get('valor') or '')
        if not alvo:
            raise ValueError('Selecione ' + (('o fornecedor' if tipo == 'D' else 'o cliente') if agrupar == 'pessoa' else 'o ítem') + '.')
        por = {r['mes']: r['v'] for r in dicts(db.execute(f"SELECT strftime('%Y-%m', {campo}) AS mes, SUM(l.valor) AS v {base} AND l.tipo=? AND {col}=? GROUP BY 1",
                                                          (empresa_id, de, ate, tipo, alvo)))}
        pontos = [{'rotulo': rotulo_mes(m), 'valores': [r2(por.get(m, 0))]} for m in meses_entre(de, ate)]
        media = r2(sum(p['valores'][0] for p in pontos) / len(pontos)) if pontos else 0
        return {'forma': 'colunas', 'titulo': f'Evolução de {nome_tipo} — {alvo}', 'subtitulo': sub, 'series': [alvo], 'media': media, 'pontos': pontos}
    if nome == 'opcoes':
        col = 'l.pessoa' if q.get('agrupar') == 'pessoa' else 'l.descricao'
        return [r[0] for r in db.execute(f"""SELECT DISTINCT {col} FROM lancamentos l WHERE l.empresa_id=? AND l.excluido_em IS NULL AND l.tipo=?
            AND {col} IS NOT NULL AND {col} <> '' ORDER BY ordem_pt({col})""", (empresa_id, tipo))]
    raise ValueError(f'Gráfico desconhecido: {nome}')


# ---------- Importacao de extrato OFX (FConcilia) ----------

def parse_ofx(texto):
    def tag(bloco, t):
        m = re.search(rf'<{t}>([^<\r\n]*)', bloco, re.I)
        return m.group(1).strip() if m else ''
    out = []
    for b in re.split(r'<STMTTRN>', texto, flags=re.I)[1:]:
        b = re.split(r'</STMTTRN>', b, flags=re.I)[0]
        dt = tag(b, 'DTPOSTED')
        try:
            valor = float(tag(b, 'TRNAMT').replace(',', '.'))
        except ValueError:
            continue
        linha = {'fitid': tag(b, 'FITID') or f"{dt}-{valor}-{tag(b, 'MEMO')}", 'data': f'{dt[:4]}-{dt[4:6]}-{dt[6:8]}',
                 'valor': abs(valor), 'tipo': 'D' if valor < 0 else 'R', 'descricao': tag(b, 'MEMO') or tag(b, 'NAME'),
                 'documento': tag(b, 'CHECKNUM') or tag(b, 'REFNUM')}
        if linha['valor'] > 0 and re.fullmatch(r'\d{4}-\d{2}-\d{2}', linha['data']):
            out.append(linha)
    return out


def analisar_ofx(db, empresa_id, conta_id, texto):
    """Classifica cada linha: ja importada, ja quitada (conciliado), em aberto que pode ser baixado, ou nova."""
    out = []
    for l in parse_ofx(texto):
        if db.execute('SELECT 1 FROM ofx_importados WHERE conta_id=? AND fitid=?', (conta_id, l['fitid'])).fetchone():
            out.append({**l, 'status': 'importado', 'acao': 'ignorar'}); continue
        m = um(db.execute("""SELECT id, descricao, pessoa, situacao, vencimento, data_pagamento FROM lancamentos
            WHERE empresa_id=? AND excluido_em IS NULL AND tipo=? AND ABS(valor-?)<0.005 AND (conta_id=? OR conta_id IS NULL)
              AND ABS(julianday(CASE situacao WHEN 'V' THEN data_pagamento ELSE vencimento END)-julianday(?)) <= ?
            ORDER BY situacao DESC, ABS(julianday(vencimento)-julianday(?)) LIMIT 1""",
                          (empresa_id, l['tipo'], l['valor'], conta_id, l['data'], 7, l['data'])))
        if m and m['situacao'] == 'V':
            out.append({**l, 'status': 'conciliado', 'lancamento': m, 'acao': 'conciliar'})
        elif m:
            out.append({**l, 'status': 'em_aberto', 'lancamento': m, 'acao': 'baixar'})
        else:
            out.append({**l, 'status': 'novo', 'acao': 'incluir'})
    return out


def aplicar_ofx(db, empresa_id, conta_id, linhas):
    res = {'incluidos': 0, 'baixados': 0, 'conciliados': 0}
    with tx(db):
        for l in linhas:
            if l['acao'] == 'ignorar':
                continue
            if l['acao'] == 'incluir':
                desc = l.get('descricao') or 'Extrato bancário'
                registra_auxiliares(db, empresa_id, {'tipo': l['tipo'], 'descricao': desc, 'pessoa': l.get('pessoa')})
                db.execute("""INSERT INTO lancamentos (empresa_id, tipo, data_mov, documento, descricao, pessoa, valor, situacao,
                    vencimento, data_pagamento, observacao, conta_id, centro_id) VALUES (?,?,?,?,?,?,?,'V',?,?,?,?,?)""",
                           (empresa_id, l['tipo'], l['data'], l.get('documento') or None, desc, l.get('pessoa') or None, l['valor'],
                            l['data'], l['data'], 'Importado do extrato OFX', conta_id, l.get('centro_id') or None))
                res['incluidos'] += 1
            elif l['acao'] == 'baixar' and l.get('lancamento'):
                db.execute("""UPDATE lancamentos SET situacao='V', data_pagamento=?, conta_id=?, alterado_em=datetime('now','localtime')
                    WHERE id=? AND empresa_id=?""", (l['data'], conta_id, l['lancamento']['id'], empresa_id))
                res['baixados'] += 1
            else:
                res['conciliados'] += 1
            db.execute('INSERT OR IGNORE INTO ofx_importados (conta_id, fitid) VALUES (?,?)', (conta_id, l['fitid']))
    return res


# ---------- Valor por extenso (recibo) ----------

_U = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze', 'quatorze',
      'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
_D = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
_C = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']


def _ate999(n):
    if n == 100:
        return 'cem'
    p = []
    if n >= 100:
        p.append(_C[n // 100]); n %= 100
    if n >= 20:
        p.append(_D[n // 10]); n %= 10
    if n > 0:
        p.append(_U[n])
    return ' e '.join(p)


def extenso(valor):
    valor = round(float(valor), 2)
    inteiro, cent = int(valor), int(round((valor - int(valor)) * 100))
    partes = []
    mi, mil, resto = inteiro // 1_000_000, (inteiro % 1_000_000) // 1000, inteiro % 1000
    if mi:
        partes.append(_ate999(mi) + (' milhão' if mi == 1 else ' milhões'))
    if mil:
        partes.append('mil' if mil == 1 else _ate999(mil) + ' mil')
    if resto:
        partes.append(_ate999(resto))
    # "mil e cem", "dois mil e trezentos", mas "mil trezentos e dez"
    if len(partes) > 1:
        ultimo = ' e ' if not resto or resto < 100 or resto % 100 == 0 else ' '
        txt = ' '.join(partes[:-1]) + ultimo + partes[-1]
    else:
        txt = partes[0] if partes else ''
    if inteiro:
        txt += ' real' if inteiro == 1 else (' de reais' if inteiro % 1_000_000 == 0 else ' reais')
    if cent:
        txt += (' e ' if inteiro else '') + _ate999(cent) + (' centavo' if cent == 1 else ' centavos')
    return txt or 'zero real'


def moeda(v, simbolo=True):
    if v is None or v == '':
        return ''
    s = f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'R$ {s}' if simbolo else s


def agora_txt():
    return datetime.now().strftime('%d/%m/%Y %H:%M')
