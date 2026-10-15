"""Camada de servico: tudo o que as telas fazem passa por aqui, com as mesmas
checagens do servidor web (mcc-clone/src/server.js): permissao por modulo, acesso a
conta controle e protecao de dados (FLok).

Operacoes que podem cair no periodo protegido aceitam `senha=` (senha de um
administrador). Sem ela, levantam Bloqueado; a tela pede a senha e repete.
"""
from datetime import date, timedelta

from . import auth, finance as fin
from .auth import COMPLETO, CONSULTA, AcessoNegado, exigir, modulo_do_tipo, nivel
from .db import dicts, tx, um


class Bloqueado(Exception):
    def __init__(self, limite, incorreta=False):
        super().__init__(f'Movimentações bloqueadas até {fin.br(limite)}.')
        self.limite = limite
        self.incorreta = incorreta


# tabela -> campos editaveis, escopo e modulo que controla a escrita (pode depender do tipo)
CADASTROS = {
    'empresas': {'campos': ['nome', 'pessoa', 'documento', 'documento2', 'endereco', 'bairro', 'cidade', 'uf', 'cep', 'telefone',
                            'email', 'site', 'usa_centro_custo'], 'global': True, 'ordem': 'ordem_pt(nome)', 'modulo': lambda t: 'config'},
    'contas': {'campos': ['empresa_id', 'descricao', 'tipo', 'saldo_inicial', 'limite', 'ativa'], 'compartilhavel': True,
               'ordem': 'ordem_pt(descricao)', 'modulo': lambda t: 'bancos'},
    'centros': {'campos': ['nome', 'aplica_despesa', 'aplica_receita', 'orcamento', 'projecao'], 'ordem': 'ordem_pt(nome)',
                'modulo': lambda t: 'centros'},
    'pessoas': {'campos': ['empresa_id', 'tipo', 'pessoa', 'nome', 'documento', 'documento2', 'endereco', 'bairro', 'cidade', 'uf', 'cep',
                           'telefone', 'email', 'contato', 'banco', 'agencia', 'conta_bancaria', 'limite', 'observacao'],
                'compartilhavel': True, 'ordem': 'ordem_pt(nome)', 'modulo': lambda t: 'receitas' if t == 'C' else 'despesas'},
    'itens': {'campos': ['tipo', 'descricao'], 'ordem': 'ordem_pt(descricao)', 'modulo': modulo_do_tipo},
    'movbancarias': {'campos': ['tipo', 'situacao', 'data', 'origem_id', 'destino_id', 'valor', 'observacao'],
                     'ordem': 'data DESC, id DESC', 'soft': True, 'modulo': lambda t: 'bancos', 'leitura': 'bancos'},
}
OBRIGATORIO = {'empresas': 'nome', 'contas': 'descricao', 'centros': 'nome', 'pessoas': 'nome', 'itens': 'descricao'}


class Sessao:
    def __init__(self, db, usuario, empresa_id=None):
        self.db = db
        self.u = usuario
        self.empresa_id = empresa_id

    # ---------- usuario / empresa ----------
    def nivel(self, modulo):
        return nivel(self.u, modulo)

    def nivel_tipo(self, tipo):
        return nivel(self.u, modulo_do_tipo(tipo))

    def tipos_visiveis(self):
        return [t for t in ('D', 'R') if self.nivel_tipo(t) >= CONSULTA]

    def recarregar_usuario(self):
        self.u = auth.recarregar(self.db, self.u)

    def empresas(self):
        perm = auth.empresas_permitidas(self.db, self.u)
        rows = dicts(self.db.execute('SELECT * FROM empresas ORDER BY ordem_pt(nome)'))
        return rows if perm is None else [e for e in rows if e['id'] in perm]

    def empresa(self):
        return um(self.db.execute('SELECT * FROM empresas WHERE id=?', (self.empresa_id,)))

    def usar_empresa(self, empresa_id):
        if not auth.pode_empresa(self.db, self.u, empresa_id):
            raise AcessoNegado('Seu usuário não tem acesso a esta conta controle.')
        self.empresa_id = empresa_id

    # ---------- protecao de dados ----------
    def limite_bloqueio(self, empresa_id=None):
        r = self.db.execute('SELECT bloqueio_ate FROM empresas WHERE id=?', (empresa_id or self.empresa_id,)).fetchone()
        return r[0] if r else None

    @staticmethod
    def lanc_no_periodo(l, lim):
        """Pertence ao periodo protegido pela data de movimento ou, se pago, pela data do pagamento."""
        mov = l.get('data_mov') or fin.hoje()
        if mov <= lim:
            return True
        return l.get('situacao') == 'V' and (l.get('data_pagamento') or l.get('vencimento') or mov) <= lim

    def _desbloqueio(self, afetado, senha, empresa_id=None):
        lim = self.limite_bloqueio(empresa_id)
        if not lim or not afetado(lim):
            return
        if senha is not None:
            if auth.senha_administrador(self.db, senha, self.u['id']):
                return
            raise Bloqueado(lim, incorreta=True)
        raise Bloqueado(lim)

    def definir_protecao(self, ativo, data=None):
        exigir(self.u, 'config', COMPLETO)
        valor = (data or None) if ativo else None
        if ativo and not valor:
            raise ValueError('Informe a data de bloqueio.')
        self.db.execute('UPDATE empresas SET bloqueio_ate=? WHERE id=?', (valor, self.empresa_id))
        return valor

    # ---------- cadastros genericos ----------
    def _registro(self, tabela, id_):
        cfg = CADASTROS[tabela]
        if cfg.get('global'):
            r = um(self.db.execute(f'SELECT * FROM {tabela} WHERE id=?', (id_,)))
        elif cfg.get('compartilhavel'):
            r = um(self.db.execute(f'SELECT * FROM {tabela} WHERE id=? AND (empresa_id=? OR empresa_id IS NULL)', (id_, self.empresa_id)))
        else:
            r = um(self.db.execute(f'SELECT * FROM {tabela} WHERE id=? AND empresa_id=?', (id_, self.empresa_id)))
        if not r:
            raise ValueError('Registro não encontrado.')
        return r

    def listar(self, tabela, tipo=None):
        cfg = CADASTROS[tabela]
        if cfg.get('leitura'):
            exigir(self.u, cfg['leitura'], CONSULTA)
        if tabela == 'empresas':
            return self.empresas()
        where, args = [], []
        where.append('(empresa_id = ? OR empresa_id IS NULL)' if cfg.get('compartilhavel') else 'empresa_id = ?')
        args.append(self.empresa_id)
        if cfg.get('soft'):
            where.append('excluido_em IS NULL')
        if tipo:
            where.append('tipo = ?'); args.append(tipo)
        if tabela == 'itens':
            vis = self.tipos_visiveis() or ['-']
            where.append(f"tipo IN ({','.join('?' * len(vis))})"); args += vis
        return dicts(self.db.execute(f"SELECT * FROM {tabela} WHERE {' AND '.join(where)} ORDER BY {cfg['ordem']}", args))

    def obter(self, tabela, id_):
        return self._registro(tabela, id_)

    def salvar(self, tabela, dados, id_=None, senha=None):
        cfg = CADASTROS[tabela]
        b = dict(dados)
        atual = self._registro(tabela, id_) if id_ else None
        exigir(self.u, cfg['modulo']((atual or {}).get('tipo', b.get('tipo'))), COMPLETO)
        if atual and 'tipo' in b and b['tipo'] != atual.get('tipo'):
            exigir(self.u, cfg['modulo'](b['tipo']), COMPLETO)
        if cfg.get('compartilhavel') and b.get('empresa_id') not in (None, ''):
            b['empresa_id'] = self.empresa_id  # so a empresa atual ou compartilhado
        campo_obrig = OBRIGATORIO.get(tabela)
        if campo_obrig and campo_obrig in b and not str(b[campo_obrig] or '').strip():
            raise ValueError('Preencha o campo obrigatório.')
        if tabela == 'movbancarias':
            self._valida_mov(b)
            self._desbloqueio(lambda lim: (atual and atual['data'] <= lim) or str(b.get('data') or fin.hoje()) <= lim, senha)
        if tabela == 'contas' and atual and 'saldo_inicial' in b:
            self._desbloqueio(lambda lim: float(b.get('saldo_inicial') or 0) != float(atual['saldo_inicial']), senha)
        campos = [c for c in cfg['campos'] if c in b]
        vals = [None if b[c] == '' else b[c] for c in campos]
        if id_:
            if campos:
                self.db.execute(f"UPDATE {tabela} SET {', '.join(f'{c}=?' for c in campos)} WHERE id=?", (*vals, id_))
            return id_
        if not cfg.get('global') and (not cfg.get('compartilhavel') or 'empresa_id' not in b):
            campos.append('empresa_id'); vals.append(self.empresa_id)
        novo = self.db.execute(f"INSERT INTO {tabela} ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})", vals).lastrowid
        if tabela == 'empresas' and not auth.pode_empresa(self.db, self.u, novo):
            self.db.execute('INSERT OR IGNORE INTO usuario_empresas (usuario_id, empresa_id) VALUES (?,?)', (self.u['id'], novo))
        return novo

    def _valida_mov(self, b):
        try:
            valor = float(b.get('valor') or 0)
        except ValueError:
            valor = 0
        if valor <= 0:
            raise ValueError('Informe um valor maior que zero.')
        if b.get('tipo') == 'T' and (not b.get('destino_id') or int(b['destino_id']) == int(b.get('origem_id') or 0)):
            raise ValueError('Selecione uma conta de destino diferente da origem.')
        if not self._conta_visivel(b.get('origem_id')) or not self._conta_visivel(b.get('destino_id')):
            raise ValueError('Conta inválida.')

    def remover(self, tabela, id_, senha=None):
        cfg = CADASTROS[tabela]
        atual = self._registro(tabela, id_)
        exigir(self.u, cfg['modulo'](atual.get('tipo')), COMPLETO)
        if tabela == 'empresas' and self.db.execute('SELECT 1 FROM lancamentos WHERE empresa_id=? LIMIT 1', (id_,)).fetchone():
            raise ValueError('Esta conta controle possui lançamentos e não pode ser excluída.')
        if tabela == 'contas' and self.db.execute('SELECT 1 FROM lancamentos WHERE conta_id=? AND excluido_em IS NULL LIMIT 1', (id_,)).fetchone():
            raise ValueError('Esta conta possui lançamentos. Desative-a em vez de excluir.')
        if tabela == 'movbancarias':
            self._desbloqueio(lambda lim: atual['data'] <= lim, senha)
        if tabela == 'centros':
            self.db.execute('UPDATE lancamentos SET centro_id=NULL WHERE centro_id=?', (id_,))
        if cfg.get('soft'):
            self.db.execute(f"UPDATE {tabela} SET excluido_em=datetime('now','localtime') WHERE id=?", (id_,))
        else:
            self.db.execute(f'DELETE FROM {tabela} WHERE id=?', (id_,))

    # ---------- lancamentos ----------
    def _conta_visivel(self, conta_id):
        return not conta_id or self.db.execute('SELECT 1 FROM contas WHERE id=? AND (empresa_id=? OR empresa_id IS NULL)',
                                               (int(conta_id), self.empresa_id)).fetchone() is not None

    def _centro_visivel(self, centro_id):
        return not centro_id or self.db.execute('SELECT 1 FROM centros WHERE id=? AND empresa_id=?', (int(centro_id), self.empresa_id)).fetchone() is not None

    def _valida_lanc(self, b):
        if not self._conta_visivel(b.get('conta_id')):
            raise ValueError('Conta inválida.')
        if not self._centro_visivel(b.get('centro_id')):
            raise ValueError('Centro de custo inválido.')

    def _lanc(self, id_):
        l = fin.lancamento(self.db, self.empresa_id, id_)
        if not l:
            raise ValueError('Lançamento não encontrado.')
        return l

    def listar_lancamentos(self, **q):
        if q.get('tipo'):
            exigir(self.u, modulo_do_tipo(q['tipo']), CONSULTA)
        else:
            q['tipos'] = self.tipos_visiveis() or ['-']
        return fin.listar_lancamentos(self.db, self.empresa_id, q)

    def lancamento(self, id_):
        l = self._lanc(id_)
        exigir(self.u, modulo_do_tipo(l['tipo']), CONSULTA)
        return l

    def salvar_lancamento(self, dados, id_=None, senha=None):
        exigir(self.u, modulo_do_tipo(dados.get('tipo')), COMPLETO)
        self._valida_lanc(dados)
        if id_:
            l = self._lanc(id_)
            exigir(self.u, modulo_do_tipo(l['tipo']), COMPLETO)
            self._desbloqueio(lambda lim: self.lanc_no_periodo(l, lim) or self.lanc_no_periodo(dados, lim), senha)
        else:
            self._desbloqueio(lambda lim: self.lanc_no_periodo(dados, lim), senha)
        return fin.salvar_lancamento(self.db, self.empresa_id, dados, id_)

    def parcelar(self, dados, senha=None):
        exigir(self.u, modulo_do_tipo(dados.get('tipo')), COMPLETO)
        self._valida_lanc(dados)
        mov = (dados.get('vencimento') or dados.get('data_mov')) if dados.get('mov_igual_vencimento') else dados.get('data_mov')
        self._desbloqueio(lambda lim: str(mov or fin.hoje()) <= lim, senha)
        return fin.parcelar(self.db, self.empresa_id, dados)

    def baixar(self, ids, dados=None, senha=None):
        dados = dados or {}
        ls = [self._lanc(i) for i in ids]
        for l in ls:
            exigir(self.u, modulo_do_tipo(l['tipo']), COMPLETO)
        self._valida_lanc(dados)
        self._desbloqueio(lambda lim: (dados.get('data_pagamento') or fin.hoje()) <= lim or any(self.lanc_no_periodo(l, lim) for l in ls), senha)
        return fin.baixar(self.db, self.empresa_id, ids, dados)

    def estornar(self, id_, senha=None):
        l = self._lanc(id_)
        exigir(self.u, modulo_do_tipo(l['tipo']), COMPLETO)
        self._desbloqueio(lambda lim: self.lanc_no_periodo(l, lim), senha)
        return fin.estornar(self.db, self.empresa_id, id_)

    def excluir(self, id_, modo='esta', senha=None):
        l = self._lanc(id_)
        exigir(self.u, modulo_do_tipo(l['tipo']), COMPLETO)
        afetados = fin.afetados_exclusao(self.db, l, modo)
        self._desbloqueio(lambda lim: any(self.lanc_no_periodo(x, lim) for x in afetados), senha)
        return fin.excluir(self.db, self.empresa_id, id_, modo)

    def restaurar(self, id_, senha=None):
        l = self._lanc(id_)
        exigir(self.u, modulo_do_tipo(l['tipo']), COMPLETO)
        self._desbloqueio(lambda lim: self.lanc_no_periodo(l, lim), senha)
        return fin.restaurar(self.db, self.empresa_id, id_)

    def excluidos(self):
        vis = self.tipos_visiveis()
        return [l for l in fin.excluidos(self.db, self.empresa_id) if l['tipo'] in vis]

    def transferir_empresa(self, ids, destino, senha=None):
        if not auth.pode_empresa(self.db, self.u, destino):
            raise AcessoNegado('Seu usuário não tem acesso à conta controle de destino.')
        ls = [self._lanc(i) for i in ids]
        for l in ls:
            exigir(self.u, modulo_do_tipo(l['tipo']), COMPLETO)
        self._desbloqueio(lambda lim: any(self.lanc_no_periodo(l, lim) for l in ls), senha)
        self._desbloqueio(lambda lim: any(self.lanc_no_periodo(l, lim) for l in ls), senha, empresa_id=destino)
        return fin.transferir_empresa(self.db, self.empresa_id, destino, ids)

    def lembretes(self, dias=7):
        vis = self.tipos_visiveis()
        return [l for l in fin.lembretes(self.db, self.empresa_id, dias) if l['tipo'] in vis]

    # ---------- saldos / dashboard ----------
    def saldos(self, ate=None):
        if self.nivel('bancos') < CONSULTA and self.nivel('fluxo') < CONSULTA:
            exigir(self.u, 'bancos', CONSULTA)
        return fin.saldos(self.db, self.empresa_id, ate)

    def dashboard(self, **q):
        exigir(self.u, 'fluxo', CONSULTA)
        return fin.dashboard(self.db, self.empresa_id, **q)

    def dashboard_itens(self, **q):
        exigir(self.u, 'fluxo', CONSULTA)
        return fin.dashboard_itens(self.db, self.empresa_id, **q)

    def linear(self, **q):
        exigir(self.u, 'fluxo', CONSULTA)
        return fin.linear(self.db, self.empresa_id, **q)

    # ---------- relatorios / graficos ----------
    MODULO_RELATORIO = {'lancamentos': 'tipo', 'totais_item': 'tipo', 'por_pessoa': 'tipo', 'pontualidade': 'tipo', 'demonstrativo': 'tipo',
                        'fluxo_dia': 'fluxo', 'fluxo': 'fluxo', 'dre': 'fluxo', 'fechamento': 'fluxo', 'extrato': 'bancos', 'saldos': 'bancos',
                        'comparativo_saldos': 'bancos', 'centros': 'centros', 'centro_itens': 'centros', 'fluxo_centros': 'centros'}

    def relatorio(self, nome, **q):
        if nome == 'analitico':
            for t in ([q['tipo']] if q.get('tipo') in ('D', 'R') else ['D', 'R']):
                exigir(self.u, modulo_do_tipo(t), CONSULTA)
        elif nome == 'pessoas':
            exigir(self.u, 'receitas' if q.get('pessoa_tipo') == 'C' else 'despesas', CONSULTA)
        else:
            mod = self.MODULO_RELATORIO.get(nome)
            if mod == 'tipo':
                exigir(self.u, modulo_do_tipo('R' if q.get('tipo') == 'R' else 'D'), CONSULTA)
            elif mod:
                exigir(self.u, mod, CONSULTA)
            if nome in ('centro_itens',):
                exigir(self.u, modulo_do_tipo('R' if q.get('tipo') == 'R' else 'D'), CONSULTA)
        if q.get('conta_id') and not self._conta_visivel(q['conta_id']):
            raise ValueError('Conta inválida.')
        return fin.relatorio(self.db, self.empresa_id, nome, q)

    def grafico(self, nome, **q):
        if nome == 'desp_rec':
            exigir(self.u, 'despesas', CONSULTA); exigir(self.u, 'receitas', CONSULTA)
        else:
            exigir(self.u, modulo_do_tipo('R' if q.get('tipo') == 'R' else 'D'), CONSULTA)
            if nome == 'composicao' and q.get('agrupar') == 'centro':
                exigir(self.u, 'centros', CONSULTA)
        return fin.grafico(self.db, self.empresa_id, nome, q)

    # ---------- OFX ----------
    def analisar_ofx(self, conta_id, texto):
        exigir(self.u, 'bancos', CONSULTA)
        if not self._conta_visivel(conta_id):
            raise ValueError('Conta inválida.')
        return fin.analisar_ofx(self.db, self.empresa_id, int(conta_id), texto)

    def aplicar_ofx(self, conta_id, linhas, senha=None):
        exigir(self.u, 'bancos', COMPLETO)
        if not self._conta_visivel(conta_id):
            raise ValueError('Conta inválida.')
        for l in linhas:
            if l['acao'] != 'ignorar':
                exigir(self.u, modulo_do_tipo(l['tipo']), COMPLETO)
            if l['acao'] == 'baixar' and l.get('lancamento'):
                self._lanc(int(l['lancamento']['id']))
        self._desbloqueio(lambda lim: any(l['acao'] in ('incluir', 'baixar') and str(l['data']) <= lim for l in linhas), senha)
        return fin.aplicar_ofx(self.db, self.empresa_id, int(conta_id), linhas)

    # ---------- usuarios ----------
    def listar_usuarios(self):
        exigir(self.u, 'config', COMPLETO)
        out = []
        for u in auth.listar_usuarios(self.db):
            u['empresas'] = auth.empresas_do_usuario(self.db, u['id'])
            out.append(u)
        return out

    def salvar_usuario(self, dados, id_=None):
        exigir(self.u, 'config', COMPLETO)
        alvo = um(self.db.execute('SELECT * FROM usuarios WHERE id=?', (id_,))) if id_ else None
        if id_ and not alvo:
            raise ValueError('Usuário não encontrado.')
        if not self.u['admin']:
            if (alvo and alvo['admin']) or int(dados.get('admin') or 0):
                raise AcessoNegado('Somente um administrador pode gerenciar administradores.')
            minhas = auth.empresas_permitidas(self.db, self.u)
            if minhas is not None:
                if int(dados.get('todas_empresas') or 0) or any(int(e) not in minhas for e in dados.get('empresas') or []):
                    raise AcessoNegado('Você só pode liberar as contas controle a que tem acesso.')
        r = auth.salvar_usuario(self.db, dados, id_, self.u)
        if id_ == self.u['id']:
            self.recarregar_usuario()
        return r

    def excluir_usuario(self, id_):
        exigir(self.u, 'config', COMPLETO)
        alvo = um(self.db.execute('SELECT admin FROM usuarios WHERE id=?', (id_,)))
        if alvo and alvo['admin'] and not self.u['admin']:
            raise AcessoNegado('Somente um administrador pode gerenciar administradores.')
        auth.excluir_usuario(self.db, id_, self.u)

    def alterar_senha(self, atual, nova):
        auth.alterar_senha(self.db, self.u, atual, nova)
        self.recarregar_usuario()

    # ---------- extras so do desktop ----------
    def pessoa_extra(self, pessoa_id):
        import json
        r = self.db.execute('SELECT dados, criado_em FROM pessoas_extra WHERE pessoa_id=?', (pessoa_id,)).fetchone()
        return ({**json.loads(r[0]), '_criado_em': r[1]} if r else {})

    def salvar_pessoa_extra(self, pessoa_id, dados):
        import json
        p = self._registro('pessoas', pessoa_id)
        exigir(self.u, CADASTROS['pessoas']['modulo'](p['tipo']), COMPLETO)
        limpo = {k: v for k, v in dados.items() if not k.startswith('_')}
        self.db.execute("""INSERT INTO pessoas_extra (pessoa_id, dados) VALUES (?,?)
            ON CONFLICT(pessoa_id) DO UPDATE SET dados=excluded.dados""", (pessoa_id, json.dumps(limpo, ensure_ascii=False)))

    CONFIG_PADRAO = {'exibir_saldos': '1', 'itens_proprios': '1', 'campo_inicial': 'descricao', 'conta_padrao': ''}

    def config(self, chave=None):
        rows = {r[0]: r[1] for r in self.db.execute('SELECT chave, valor FROM empresa_config WHERE empresa_id=?', (self.empresa_id,))}
        cfg = {**self.CONFIG_PADRAO, **rows}
        return cfg if chave is None else cfg.get(chave)

    def salvar_config(self, valores):
        exigir(self.u, 'config', COMPLETO)
        for k, v in valores.items():
            self.db.execute("""INSERT INTO empresa_config (empresa_id, chave, valor) VALUES (?,?,?)
                ON CONFLICT(empresa_id, chave) DO UPDATE SET valor=excluded.valor""", (self.empresa_id, k, '' if v is None else str(v)))

    def itens_descricoes(self, tipo):
        """Descricoes para o combo do lancamento: so desta conta controle ou de todas (FConfigConta)."""
        if self.config('itens_proprios') == '1':
            return [i['descricao'] for i in self.listar('itens', tipo=tipo)]
        exigir(self.u, modulo_do_tipo(tipo), CONSULTA)
        perm = auth.empresas_permitidas(self.db, self.u)
        rows = self.db.execute('SELECT DISTINCT descricao, empresa_id FROM itens WHERE tipo=? ORDER BY ordem_pt(descricao)', (tipo,))
        vistos, out = set(), []
        for desc, emp in rows:
            if (perm is None or emp in perm) and desc not in vistos:
                vistos.add(desc)
                out.append(desc)
        return out

    # ---------- logomarca (so desktop) ----------
    def logo(self, empresa_id=None):
        r = self.db.execute('SELECT imagem FROM empresa_logos WHERE empresa_id=?', (empresa_id or self.empresa_id,)).fetchone()
        return bytes(r[0]) if r else None

    def definir_logo(self, dados_png):
        exigir(self.u, 'config', COMPLETO)
        if dados_png:
            self.db.execute('INSERT OR REPLACE INTO empresa_logos (empresa_id, imagem) VALUES (?,?)', (self.empresa_id, dados_png))
        else:
            self.db.execute('DELETE FROM empresa_logos WHERE empresa_id=?', (self.empresa_id,))
