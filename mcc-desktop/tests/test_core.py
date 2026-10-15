"""Testes do nucleo (mesmos cenarios dos testes do clone web)."""
import unittest

from mcc.core import auth, db as dbm, finance as fin
from mcc.core.auth import AcessoNegado
from mcc.core.servico import Bloqueado, Sessao


def base():
    db = dbm.abrir(':memory:')
    emp = db.execute("INSERT INTO empresas (nome) VALUES ('Teste')").lastrowid
    banco = db.execute("INSERT INTO contas (empresa_id, descricao, saldo_inicial) VALUES (?, 'BANCO', 1000)", (emp,)).lastrowid
    caixa = db.execute("INSERT INTO contas (empresa_id, descricao, tipo) VALUES (?, 'CAIXA', 'C')", (emp,)).lastrowid
    return db, emp, banco, caixa


class Regras(unittest.TestCase):
    def test_periodos(self):
        self.assertEqual(fin.periodo(2025, '2'), ('2025-02-01', '2025-02-28'))
        self.assertEqual(fin.periodo(2024, '2'), ('2024-02-01', '2024-02-29'))
        self.assertEqual(fin.periodo(2025, 'T3'), ('2025-07-01', '2025-09-30'))
        self.assertEqual(fin.periodo(2025, 'S2'), ('2025-07-01', '2025-12-31'))
        self.assertEqual(fin.periodo(2025, 'ANO'), ('2025-01-01', '2025-12-31'))
        self.assertIsNone(fin.periodo(2025, 'TODOS'))

    def test_lancamento_baixa_saldo(self):
        db, emp, banco, _ = base()
        d = fin.salvar_lancamento(db, emp, {'tipo': 'D', 'descricao': 'Aluguel', 'pessoa': 'Imob', 'valor': 300, 'vencimento': '2025-01-10', 'conta_id': banco})
        fin.salvar_lancamento(db, emp, {'tipo': 'R', 'descricao': 'Venda', 'valor': 500, 'situacao': 'V', 'vencimento': '2025-01-05', 'conta_id': banco})
        s = next(c for c in fin.saldos(db, emp, '2025-01-31') if c['id'] == banco)
        self.assertEqual((s['saldo'], s['previsto']), (1500, 1200))
        self.assertEqual(fin.baixar(db, emp, [d], {'data_pagamento': '2025-01-12'}), 1)
        self.assertEqual(next(c for c in fin.saldos(db, emp, '2025-01-31') if c['id'] == banco)['saldo'], 1200)
        self.assertTrue(db.execute("SELECT 1 FROM itens WHERE descricao='Aluguel' AND tipo='D'").fetchone())
        self.assertTrue(db.execute("SELECT 1 FROM pessoas WHERE nome='Imob' AND tipo='F'").fetchone())

    def test_validacoes(self):
        db, emp, _, _ = base()
        with self.assertRaisesRegex(ValueError, 'valor'):
            fin.salvar_lancamento(db, emp, {'tipo': 'D', 'descricao': 'X', 'valor': 0})
        with self.assertRaisesRegex(ValueError, 'descrição'):
            fin.salvar_lancamento(db, emp, {'tipo': 'D', 'valor': 10})
        with self.assertRaisesRegex(ValueError, 'Tipo'):
            fin.salvar_lancamento(db, emp, {'tipo': 'X', 'descricao': 'X', 'valor': 10})

    def test_parcelamento(self):
        db, emp, _, _ = base()
        ids = fin.parcelar(db, emp, {'tipo': 'D', 'descricao': 'Carro', 'valor': 100, 'vencimento': '2025-01-31', 'parcelas': 4,
                                     'periodicidade': 'mensal', 'documento': 'NF1'})
        ls = db.execute('SELECT vencimento, documento FROM lancamentos ORDER BY parcela').fetchall()
        self.assertEqual([l[0] for l in ls], ['2025-01-31', '2025-02-28', '2025-03-31', '2025-04-30'])
        self.assertEqual(ls[1][1], 'NF1 2/4')
        fin.baixar(db, emp, [ids[0]])
        self.assertEqual(fin.excluir(db, emp, ids[2], 'seguintes'), 2)
        self.assertEqual(fin.excluir(db, emp, ids[1], 'abertas'), 1)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM lancamentos WHERE excluido_em IS NULL').fetchone()[0], 1)

    def test_transferencia(self):
        db, emp, banco, caixa = base()
        db.execute("INSERT INTO movbancarias (empresa_id, tipo, data, origem_id, destino_id, valor) VALUES (?, 'T', '2025-01-02', ?, ?, 200)", (emp, banco, caixa))
        db.execute("INSERT INTO movbancarias (empresa_id, tipo, situacao, data, origem_id, valor) VALUES (?, 'D', 'P', '2025-01-03', ?, 50)", (emp, caixa))
        s = {c['id']: c for c in fin.saldos(db, emp, '2025-01-31')}
        self.assertEqual(s[banco]['saldo'], 800)
        self.assertEqual((s[caixa]['saldo'], s[caixa]['previsto']), (200, 250))

    def test_filtros_relatorios(self):
        db, emp, banco, _ = base()
        fin.salvar_lancamento(db, emp, {'tipo': 'D', 'descricao': 'Luz', 'valor': 80, 'data_mov': '2025-03-01', 'vencimento': '2025-03-10',
                                        'situacao': 'V', 'data_pagamento': '2025-03-12', 'conta_id': banco})
        fin.salvar_lancamento(db, emp, {'tipo': 'D', 'descricao': 'Luz', 'valor': 90, 'data_mov': '2025-04-01', 'vencimento': '2025-04-10'})
        self.assertEqual(len(fin.listar_lancamentos(db, emp, {'tipo': 'D', 'ano': 2025, 'mes': '3'})), 1)
        self.assertEqual(len(fin.listar_lancamentos(db, emp, {'tipo': 'D', 'situacao': 'P'})), 1)
        self.assertEqual(len(fin.listar_lancamentos(db, emp, {'tipo': 'D', 'busca': 'luz'})), 2)
        self.assertEqual(fin.relatorio(db, emp, 'totais_item', {'tipo': 'D'})['linhas'][0]['total'], 170)
        dem = fin.relatorio(db, emp, 'demonstrativo', {'tipo': 'D', 'ano': 2025})
        self.assertEqual((dem['linhas'][0]['Mar'], dem['linhas'][0]['Abr']), (80, 90))
        self.assertEqual(fin.relatorio(db, emp, 'pontualidade', {'tipo': 'D'})['linhas'][0]['maior_atraso'], 2)
        ext = fin.relatorio(db, emp, 'extrato', {'conta_id': banco, 'de': '2025-03-01', 'ate': '2025-03-31'})
        self.assertEqual(ext['linhas'][-1]['saldo'], 920)
        for nome in ('fluxo', 'fechamento', 'comparativo_saldos', 'fluxo_centros', 'centro_itens', 'dre', 'saldos', 'centros'):
            self.assertIn('linhas', fin.relatorio(db, emp, nome, {'tipo': 'D', 'ano': 2025, 'mes': 'ANO'}))
        self.assertEqual(fin.relatorio(db, emp, 'pessoas', {'pessoa_tipo': 'F'})['linhas'], [])

    def test_ofx(self):
        db, emp, banco, _ = base()
        fin.salvar_lancamento(db, emp, {'tipo': 'D', 'descricao': 'Internet', 'valor': 99.9, 'vencimento': '2025-05-10', 'conta_id': banco})
        ofx = """OFXHEADER:100\n<OFX><BANKTRANLIST>
          <STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20250511120000<TRNAMT>-99.90<FITID>A1<MEMO>PAG INTERNET</STMTTRN>
          <STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20250512<TRNAMT>250.00<FITID>A2<MEMO>PIX RECEBIDO</STMTTRN>
        </BANKTRANLIST></OFX>"""
        a = fin.analisar_ofx(db, emp, banco, ofx)
        self.assertEqual([l['status'] for l in a], ['em_aberto', 'novo'])
        self.assertEqual(fin.aplicar_ofx(db, emp, banco, a), {'incluidos': 1, 'baixados': 1, 'conciliados': 0})
        self.assertAlmostEqual(fin.saldos(db, emp, '2025-05-31')[0]['saldo'], 1000 - 99.9 + 250)
        self.assertEqual([l['status'] for l in fin.analisar_ofx(db, emp, banco, ofx)], ['importado', 'importado'])

    def test_analitico_e_graficos(self):
        db, emp, banco, caixa = base()
        L = lambda **b: fin.salvar_lancamento(db, emp, {'tipo': 'D', 'valor': 10, 'conta_id': banco, **b})
        L(descricao='Luz', pessoa='EDP', valor=100, data_mov='2025-01-05')
        L(descricao='Luz', pessoa='EDP', valor=120, data_mov='2025-02-05', situacao='V')
        L(descricao='Água', pessoa='Cesan', valor=50, data_mov='2025-01-07', conta_id=caixa)
        L(tipo='R', descricao='Venda', pessoa='Cliente A', valor=1000, data_mov='2025-01-10')
        d = fin.analitico(db, emp, {'agrupar1': 'tipo', 'agrupar2': 'item'})
        grupos = [l['data_mov'] for l in d['linhas'] if l.get('_tipo') == 'grupo']
        self.assertEqual(grupos, ['Tipo: Despesas', 'Descrição: Água', 'Descrição: Luz', 'Tipo: Receitas', 'Descrição: Venda'])
        self.assertEqual(d['totais'], {'receitas': 1000, 'despesas': 270, 'saldo': 730})
        t = fin.analitico(db, emp, {'modo': 'totalizado', 'tipo': 'D', 'agrupar1': 'mes'})
        self.assertEqual([(l['g0'], l['total']) for l in t['linhas']], [('Jan/2025', 150), ('Fev/2025', 120)])
        t2 = fin.analitico(db, emp, {'modo': 'totalizado', 'tipo': 'D', 'agrupar1': 'conta', 'agrupar2': 'item'})
        self.assertEqual(len([l for l in t2['linhas'] if l.get('_tipo') == 'subtotal']), 2)
        self.assertEqual(fin.analitico(db, emp, {'tipo': 'D', 'pessoa': 'edp'})['totais']['total'], 220)
        with self.assertRaisesRegex(ValueError, 'agrupamento'):
            fin.analitico(db, emp, {'modo': 'totalizado'})
        q = {'de': '2025-01-01', 'ate': '2025-03-31'}
        dr = fin.grafico(db, emp, 'desp_rec', q)
        self.assertEqual(dr['pontos'][0]['valores'], [1000, 150])
        comp = fin.grafico(db, emp, 'composicao', {**q, 'tipo': 'D', 'agrupar': 'item'})
        self.assertEqual([(p['rotulo'], p['valor']) for p in comp['pontos']], [('Luz', 220), ('Água', 50)])
        ev = fin.grafico(db, emp, 'evolucao', {**q, 'tipo': 'D', 'agrupar': 'pessoa', 'valor': 'EDP'})
        self.assertEqual([p['valores'][0] for p in ev['pontos']], [100, 120, 0])
        self.assertEqual(fin.grafico(db, emp, 'opcoes', {'tipo': 'D', 'agrupar': 'item'}), ['Água', 'Luz'])

    def test_extenso(self):
        self.assertEqual(fin.extenso(1), 'um real')
        self.assertEqual(fin.extenso(1310), 'mil trezentos e dez reais')
        self.assertEqual(fin.extenso(2300), 'dois mil e trezentos reais')
        self.assertEqual(fin.extenso(100.5), 'cem reais e cinquenta centavos')
        self.assertEqual(fin.extenso(1000000), 'um milhão de reais')
        self.assertEqual(fin.moeda(1234.5), 'R$ 1.234,50')


class Permissoes(unittest.TestCase):
    def setUp(self):
        self.db, self.emp, self.banco, _ = base()
        self.emp2 = self.db.execute("INSERT INTO empresas (nome) VALUES ('Outra')").lastrowid
        auth.criar_administrador(self.db, {'nome': 'Admin', 'email': 'adm@t.com', 'senha': 'Senha-Ádmin1'})
        self.adm = Sessao(self.db, auth.login(self.db, 'adm@t.com', 'Senha-Ádmin1'), self.emp)

    def test_hash_compativel_com_clone_web(self):
        # hash gerado pelo node (scryptSync, N=16384 r=8 p=1, 64 bytes) para a senha "segredo1"
        h = auth.hash_senha('segredo1')
        self.assertTrue(auth.confere('segredo1', h))
        self.assertFalse(auth.confere('outra', h))

    def test_consulta_e_empresa(self):
        auth.salvar_usuario(self.db, {'nome': 'Joana', 'email': 'joana@t.com', 'senha': 'senha123', 'perm_despesas': 1, 'perm_receitas': 0,
                                      'perm_bancos': 0, 'perm_fluxo': 0, 'todas_empresas': 0, 'empresas': [self.emp]})
        j = Sessao(self.db, auth.login(self.db, 'joana@t.com', 'senha123'), self.emp)
        self.assertEqual([e['id'] for e in j.empresas()], [self.emp])
        with self.assertRaises(AcessoNegado):
            j.usar_empresa(self.emp2)
        did = self.adm.salvar_lancamento({'tipo': 'D', 'descricao': 'Luz', 'valor': 50})
        self.adm.salvar_lancamento({'tipo': 'R', 'descricao': 'Venda', 'valor': 90})
        self.assertEqual(len(j.listar_lancamentos(tipo='D')), 1)
        self.assertEqual([l['tipo'] for l in j.listar_lancamentos()], ['D'])
        for f in (lambda: j.salvar_lancamento({'tipo': 'D', 'descricao': 'X', 'valor': 1}), lambda: j.baixar([did]),
                  lambda: j.excluir(did), lambda: j.listar_lancamentos(tipo='R'), lambda: j.dashboard(), lambda: j.saldos(),
                  lambda: j.listar('movbancarias'), lambda: j.salvar('contas', {'descricao': 'X'}), lambda: j.listar_usuarios(),
                  lambda: j.salvar('empresas', {'nome': 'Nova'}), lambda: j.relatorio('totais_item', tipo='R'),
                  lambda: j.salvar('pessoas', {'tipo': 'C', 'nome': 'Cli'})):
            with self.assertRaises(AcessoNegado):
                f()
        self.assertTrue(all(i['tipo'] == 'D' for i in j.listar('itens')))
        j.salvar('centros', {'nome': 'Obra'})  # centros: acesso completo

    def test_ultimo_admin_e_nao_admin(self):
        adm_id = self.adm.u['id']
        with self.assertRaisesRegex(ValueError, 'administrador'):
            self.adm.salvar_usuario({'admin': 0}, adm_id)
        with self.assertRaises(ValueError):
            self.adm.excluir_usuario(adm_id)
        auth.salvar_usuario(self.db, {'nome': 'Ger', 'email': 'ger@t.com', 'senha': 'senha123', 'perm_config': 2, 'todas_empresas': 0, 'empresas': [self.emp]})
        g = Sessao(self.db, auth.login(self.db, 'ger@t.com', 'senha123'), self.emp)
        with self.assertRaises(AcessoNegado):
            g.salvar_usuario({'nome': 'A', 'email': 'a@t.com', 'senha': 'senha123', 'admin': 1})
        with self.assertRaises(AcessoNegado):
            g.salvar_usuario({'nome': 'A', 'email': 'a@t.com', 'senha': 'senha123', 'todas_empresas': 0, 'empresas': [self.emp2]})
        g.salvar_usuario({'nome': 'A', 'email': 'a@t.com', 'senha': 'senha123', 'todas_empresas': 0, 'empresas': [self.emp]})
        nova = g.salvar('empresas', {'nome': 'Filial'})
        self.assertIn(nova, [e['id'] for e in g.empresas()])
        with self.assertRaisesRegex(ValueError, 'e-mail'):
            self.adm.salvar_usuario({'nome': 'Dup', 'email': 'A@T.COM', 'senha': 'senha123'})

    def test_login_bloqueio(self):
        with self.assertRaises(AcessoNegado):
            auth.login(self.db, 'adm@t.com', 'errada')
        self.assertTrue(auth.login(self.db, 'ADM@t.com', 'Senha-Ádmin1'))
        for _ in range(5):
            with self.assertRaises(AcessoNegado):
                auth.login(self.db, 'x@x.com', 'x')
        with self.assertRaisesRegex(AcessoNegado, 'tentativas'):
            auth.login(self.db, 'x@x.com', 'x')


class Protecao(unittest.TestCase):
    def setUp(self):
        self.db, self.emp, self.banco, self.caixa = base()
        auth.criar_administrador(self.db, {'nome': 'Admin', 'email': 'adm@t.com', 'senha': 'Senha-Ádmin1'})
        self.adm = Sessao(self.db, auth.login(self.db, 'adm@t.com', 'Senha-Ádmin1'), self.emp)
        auth.salvar_usuario(self.db, {'nome': 'Op', 'email': 'op@t.com', 'senha': 'senha123'})
        self.op = Sessao(self.db, auth.login(self.db, 'op@t.com', 'senha123'), self.emp)
        L = lambda **b: self.adm.salvar_lancamento({'tipo': 'D', 'descricao': 'X', 'valor': 10, 'conta_id': self.banco, **b})
        self.antigo = L(data_mov='2025-01-10', vencimento='2025-01-20')
        self.pago = L(data_mov='2025-02-10', vencimento='2025-02-10', situacao='V', data_pagamento='2025-02-10')
        self.aberto = L(data_mov='2025-04-01', vencimento='2025-02-15')
        with self.assertRaises(AcessoNegado):
            self.op.definir_protecao(True, '2025-03-31')
        self.adm.definir_protecao(True, '2025-03-31')

    def test_bloqueia_e_libera(self):
        with self.assertRaises(Bloqueado) as c:
            self.op.salvar_lancamento({'tipo': 'D', 'descricao': 'Y', 'valor': 11, 'data_mov': '2025-01-10'}, self.antigo)
        self.assertEqual(c.exception.limite, '2025-03-31')
        for f in (lambda: self.op.excluir(self.antigo), lambda: self.op.estornar(self.pago),
                  lambda: self.op.baixar([self.aberto], {'data_pagamento': '2025-03-15'}),
                  lambda: self.op.parcelar({'tipo': 'D', 'descricao': 'P', 'valor': 1, 'parcelas': 2, 'data_mov': '2025-03-01'}),
                  lambda: self.op.salvar('movbancarias', {'tipo': 'T', 'data': '2025-03-10', 'origem_id': self.banco, 'destino_id': self.caixa, 'valor': 5}),
                  lambda: self.op.salvar('contas', {'descricao': 'BANCO', 'saldo_inicial': 999}, self.banco)):
            with self.assertRaises(Bloqueado):
                f()
        self.op.baixar([self.aberto], {'data_pagamento': '2025-04-02'})
        self.op.salvar('contas', {'descricao': 'BANCO NOVO', 'saldo_inicial': 1000}, self.banco)
        with self.assertRaises(Bloqueado) as c:
            self.op.excluir(self.antigo, senha='senha123')  # senha do operador nao vale
        self.assertTrue(c.exception.incorreta)
        self.op.excluir(self.antigo, senha='Senha-Ádmin1')
        with self.assertRaises(Bloqueado):
            self.op.estornar(self.pago)
        self.adm.definir_protecao(False)
        self.op.estornar(self.pago)


if __name__ == '__main__':
    unittest.main()
