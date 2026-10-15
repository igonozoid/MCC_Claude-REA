"""Teste de fumaca da interface: abre todas as telas e gera todos os relatorios/graficos (offscreen)."""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from mcc.app import criar_app, Contexto  # noqa: E402
from mcc.core import auth, db as dbm  # noqa: E402
from mcc.core.servico import Sessao  # noqa: E402


class Interface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = criar_app([])
        cls.tmp = tempfile.TemporaryDirectory()
        caminho = os.path.join(cls.tmp.name, 't.db')
        db = dbm.abrir(caminho)
        auth.criar_administrador(db, {'nome': 'Admin', 'email': 'a@t.com', 'senha': 'segredo1'})
        u = auth.login(db, 'a@t.com', 'segredo1')
        s = Sessao(db, u)
        emp = s.salvar('empresas', {'nome': 'Empresa', 'telefone': '1', 'cidade': 'Vitória'})
        s.usar_empresa(emp)
        banco = s.salvar('contas', {'descricao': 'BANCO', 'saldo_inicial': 100})
        s.salvar('contas', {'descricao': 'CAIXA INTERNO', 'tipo': 'C'})
        cen = s.salvar('centros', {'nome': 'Adm', 'aplica_despesa': 1, 'aplica_receita': 1, 'orcamento': 500, 'projecao': 900})
        for m in range(1, 7):
            s.salvar_lancamento({'tipo': 'D', 'descricao': 'Luz', 'pessoa': 'EDP', 'valor': 100 + m, 'data_mov': f'2026-{m:02d}-05',
                                 'vencimento': f'2026-{m:02d}-10', 'situacao': 'V', 'data_pagamento': f'2026-{m:02d}-11', 'conta_id': banco, 'centro_id': cen})
            s.salvar_lancamento({'tipo': 'R', 'descricao': 'Venda', 'pessoa': 'Cliente', 'valor': 300, 'data_mov': f'2026-{m:02d}-06',
                                 'vencimento': f'2026-{m:02d}-15', 'conta_id': banco, 'centro_id': cen})
        s.parcelar({'tipo': 'D', 'descricao': 'Carro', 'valor': 50, 'parcelas': 3, 'vencimento': '2026-08-01', 'conta_id': banco})
        s.salvar('movbancarias', {'tipo': 'T', 'data': '2026-02-01', 'origem_id': banco, 'destino_id': banco + 1, 'valor': 10})
        cls.s, cls.banco = s, banco
        from mcc.ui.principal import JanelaPrincipal
        cls.j = JanelaPrincipal(Contexto(caminho, db), s)
        cls.j.usar_empresa(emp)
        cls.patch = mock.patch.multiple(QMessageBox, information=mock.DEFAULT, warning=mock.DEFAULT, critical=mock.DEFAULT)
        cls.mocks = cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.j.close()
        cls.tmp.cleanup()

    def setUp(self):
        for m in self.mocks.values():
            m.reset_mock()

    def sem_avisos(self):
        for nome, m in self.mocks.items():
            self.assertFalse(m.called, f'{nome}: {m.call_args}')

    def abrir(self, w):
        w.show()
        self.app.processEvents()
        w.close()

    def test_janela_principal_e_abas(self):
        for i in range(3):
            self.j.abas.setCurrentIndex(i)
            self.app.processEvents()
        for k in range(3):
            self.j.dash.mostrar(k)
        self.j.abas.setCurrentIndex(0)
        self.assertEqual(self.j.aba_d.grade.modelo.rowCount() >= 0, True)
        acoes = [a.text() for a in self.j._acoes]
        self.assertIn('IMPORTAR EXTRATO BANCÁRIO (OFX)', acoes)
        self.sem_avisos()

    def test_telas(self):
        from mcc.ui import acesso as A, cadastros as C, ferramentas as F, lancamentos as L, relatorios as R
        s, j = self.s, self.j
        l = s.listar_lancamentos(tipo='D')[0]
        parc = next(x for x in s.listar_lancamentos(tipo='D') if x.get('grupo'))
        for w in (L.FormLancamento(j.lanc, 'D', s.lancamento(l['id'])), L.FormLancamento(j.lanc, 'R'), L.FormParcelamento(j.lanc, 'D'),
                  L.FormBaixa(j.lanc, s.lancamento(parc['id'])), L.FormBaixaMultipla(j.lanc, 'R'), L.FormExcluirParcelas(j.lanc, s.lancamento(parc['id'])),
                  L.FormLocalizar(j.lanc, 'D'), C.NavContas(j, s), C.NavCentros(j, s), C.NavItens(j, s, 'D'), C.NavPessoas(j, s, 'F'),
                  C.NavEmpresas(j, s), C.NavMovBancarias(j, s), C.FormPessoa(j, s, 'C'), C.FormEmpresa(j, s, s.empresa()),
                  C.FormMovBancaria(j, s), A.NavUsuarios(j, s), A.FormUsuario(j, s), A.FormAlterarSenha(j, s), F.FormLembretes(j.ferr),
                  F.FormExcluidos(j.ferr), F.FormProtecao(j.ferr), F.FormConfigConta(j, s), F.FormBancoDados(j.ferr), F.FormConciliacao(j.ferr),
                  F.Calculadora(j, 10), R.FormAnalitico(j.relatorios), R.FormPeriodo(j, 'P', campo_data=True), R.FormRecibo(j.relatorios, s.lancamento(l['id']))):
            self.abrir(w)
        self.sem_avisos()

    def test_incluir_lancamento_pela_tela(self):
        from mcc.ui import lancamentos as L
        f = L.FormLancamento(self.j.lanc, 'D')
        f.ed_des.definir('Internet')
        f.ed_pes.definir('Vivo')
        f.ed_val.setText('99,90')
        f.cb_conta.definir(self.banco)
        f.confirmar()
        self.sem_avisos()
        self.assertTrue(any(x['descricao'] == 'Internet' and x['valor'] == 99.9 for x in self.s.listar_lancamentos(tipo='D')))

    def test_todos_relatorios_em_pdf(self):
        from PySide6.QtPrintSupport import QPrinter
        from mcc.ui.relatorios import PintorRelatorio, html_relatorio
        s = self.s
        casos = [('lancamentos', {'tipo': 'D'}), ('totais_item', {'tipo': 'R'}), ('por_pessoa', {'tipo': 'D'}), ('pontualidade', {'tipo': 'D'}),
                 ('fluxo_dia', {}), ('fluxo', {'previsao': '1'}), ('fechamento', {}), ('extrato', {'conta_id': self.banco}), ('saldos', {}),
                 ('comparativo_saldos', {'data1': '2026-01-01', 'data2': '2026-12-31'}), ('pessoas', {'pessoa_tipo': 'C'}),
                 ('demonstrativo', {'tipo': 'D', 'agrupar': 'centro', 'ano': 2026}), ('centros', {'tipo': 'D'}), ('centro_itens', {'tipo': 'D'}),
                 ('centro_itens', {'tipo': 'R', 'totais': '1'}), ('fluxo_centros', {}), ('dre', {}),
                 ('analitico', {'agrupar1': 'centro', 'agrupar2': 'mes'}), ('analitico', {'modo': 'totalizado', 'agrupar1': 'item', 'tipo': 'D'})]
        for nome, q in casos:
            rel = s.relatorio(nome, de='2026-01-01', ate='2026-12-31', **q)
            pr = QPrinter(QPrinter.HighResolution)
            p = PintorRelatorio(rel, s.empresa(), None, '#d4d0c8')
            p.configurar(pr)
            pr.setOutputFormat(QPrinter.PdfFormat)
            arq = os.path.join(self.tmp.name, f'{nome}.pdf')
            pr.setOutputFileName(arq)
            p.pintar(pr)
            self.assertGreater(os.path.getsize(arq), 1000, nome)
            self.assertIn('<table>', html_relatorio(rel, s.empresa(), '#fff'))

    def test_cabe_em_1280x720(self):
        """Notebook 1280x720: area util ~1280x650 (painel do sistema + barra de titulo)."""
        from mcc.ui import acesso as A, cadastros as C, ferramentas as F, lancamentos as L, relatorios as R
        m = self.j.minimumSizeHint()
        self.assertLessEqual(m.width(), 1270, 'janela principal mais larga que 1280')
        self.assertLessEqual(m.height(), 640, 'janela principal mais alta que 720')
        self.j.resize(1280, 650)
        self.app.processEvents()
        s, j = self.s, self.j
        l = s.listar_lancamentos(tipo='D')[0]
        for w in (L.FormLancamento(j.lanc, 'D', s.lancamento(l['id'])), L.FormParcelamento(j.lanc, 'D'), L.FormBaixaMultipla(j.lanc, 'R'),
                  C.FormPessoa(j, s, 'C'), C.FormEmpresa(j, s, s.empresa()), A.FormUsuario(j, s), F.FormConfigConta(j, s),
                  F.FormConciliacao(j.ferr), R.FormAnalitico(j.relatorios), R.FormPeriodo(j, 'P'), R.FormRecibo(j.relatorios, s.lancamento(l['id']))):
            tam = w.size() if w.minimumSize() == w.maximumSize() else w.minimumSizeHint()
            self.assertLessEqual(tam.width(), 1270, type(w).__name__)
            self.assertLessEqual(tam.height(), 640, type(w).__name__)
            w.close()

    def test_graficos(self):
        from mcc.ui.relatorios import JanelaGrafico
        for nome, q in (('desp_rec', {}), ('composicao', {'tipo': 'D', 'agrupar': 'centro'}), ('evolucao', {'tipo': 'D', 'agrupar': 'pessoa', 'valor': 'EDP'})):
            g = self.s.grafico(nome, de='2026-01-01', ate='2026-12-31', **q)
            self.abrir(JanelaGrafico(self.j.relatorios, g, q.get('tipo')))


if __name__ == '__main__':
    unittest.main()
