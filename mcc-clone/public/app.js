// Interface do clone do MCC (equivalente a FPrin e formularios de cadastro).
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const moeda = (v) => (v == null || v === '' ? '' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }));
const dataBR = (d) => (d ? String(d).slice(0, 10).split('-').reverse().join('/') : '');
const hoje = () => new Date().toLocaleDateString('sv-SE');

const st = {
  empresa: null, empresas: [], aba: 'D', sel: new Set(), linhas: [],
  contas: [], centros: [], pessoas: [], itens: [], relatorios: {},
};

// ---------- API ----------
async function api(path, opts = {}) {
  const r = await fetch('/api/' + path, {
    method: opts.method || 'GET',
    headers: { 'content-type': 'application/json', ...(st.empresa ? { 'x-empresa': st.empresa.id } : {}),
      ...(opts.desbloqueio !== undefined ? { 'x-desbloqueio': encodeURIComponent(opts.desbloqueio) } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  // Protecao de dados: pede a senha do administrador e repete a mesma operacao.
  if (r.status === 423 && j.bloqueio_ate) {
    const senha = await pedirDesbloqueio(j.bloqueio_ate, j.senha_incorreta);
    if (senha == null) throw new Error(`Operação cancelada: movimentações bloqueadas até ${dataBR(j.bloqueio_ate)}.`);
    return api(path, { ...opts, desbloqueio: senha });
  }
  if (r.status === 401 && !path.startsWith('auth/')) { sessaoExpirada(); throw new Error(j.erro || 'Sessão expirada.'); }
  if (!r.ok) throw new Error(j.erro || 'Erro ' + r.status);
  return j;
}

// ---------- Protecao de dados (FLok / FLokSen) ----------
// Dialogo proprio (#dlgSenha) para nao descartar o formulario que estiver aberto em #dlg.
function pedirDesbloqueio(limite, incorreta) {
  const dlg = $('#dlgSenha'), form = $('#dlgSenhaForm');
  $('#dlgSenhaMsg').innerHTML = (incorreta ? '<b class="neg">Senha incorreta.</b> ' : '') +
    `Movimentações bloqueadas até <b>${dataBR(limite)}</b>. Deseja inserir a senha de desbloqueio?`;
  form.reset();
  return new Promise((resolve) => {
    form.onsubmit = (ev) => { if (ev.submitter?.value === 'ok') resolve(form.senha.value); };
    dlg.onclose = () => resolve(null); // resolve so vale na primeira chamada
    dlg.showModal();
    form.senha.focus();
  });
}

function mostrarProtecao() {
  const lim = st.empresa?.bloqueio_ate;
  const selo = $('#protecaoInfo');
  selo.hidden = !lim;
  selo.textContent = lim ? '🔒 até ' + dataBR(lim) : '';
}

async function telaProtecao() {
  const atual = (await api('protecao')).bloqueio_ate;
  await dialogo({
    titulo: 'Proteção de dados', largura: '520px',
    corpo: `<div class="aviso-box">Esta opção permite bloquear lançamentos até uma determinada data. Os lançamentos até a data
        ficam protegidos contra alterações e exclusões, e não são permitidas inserções nem movimentações no caixa até a data
        informada, garantindo os saldos de períodos anteriores. Para alterar algo no período bloqueado é preciso a senha de um administrador.</div>` +
      campos([['ativo', 'Definir proteção', 'radio', { padrao: atual ? 1 : 0, opcoes: [[1, 'Ativado'], [0, 'Desativado']] }],
        ['data', 'Bloqueado até', 'date', { padrao: atual || hoje() }]]),
    botoes: [{ rot: 'Cancela', valor: 'cancel' }, { rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
      const r = await api('protecao', { method: 'PUT', body: d });
      st.empresa.bloqueio_ate = r.bloqueio_ate;
      mostrarProtecao();
      toast(r.bloqueio_ate ? `Lançamentos bloqueados até ${dataBR(r.bloqueio_ate)}.` : 'Proteção de dados desativada.');
    } }],
    aoAbrir: (f) => { const s = () => (f.data.disabled = f.ativo.value !== '1'); $$('input[name=ativo]', f).forEach((r) => (r.onchange = s)); s(); },
  });
}

// ---------- Usuario logado / permissoes ----------
// Niveis por modulo (UsuPo1..6 do original): 2 completo, 1 somente consulta, 0 sem acesso.
const perm = (mod) => st.usuario?.perms?.[mod] ?? 0;
const permTipo = (tipo) => perm(tipo === 'R' ? 'receitas' : 'despesas');

let expirando = false;
async function sessaoExpirada() {
  if (expirando) return;
  expirando = true;
  st.usuario = null;
  document.body.classList.add('deslogado');
  toast('Sua sessão expirou. Entre novamente.', true);
  await telaLogin();
  expirando = false;
  await escolherEmpresa();
}

async function telaLogin() {
  $('#conteudo').innerHTML = '';
  await dialogo({
    titulo: 'Login de acesso', largura: '420px',
    corpo: campos([['email', 'E-mail do usuário', 'email', { req: true, inteiro: true, attrs: 'autocomplete="username" autofocus' }],
      ['senha', 'Senha de acesso', 'password', { req: true, inteiro: true, attrs: 'autocomplete="current-password"' }]]),
    botoes: [{ rot: 'Acessar', valor: 'ok', pri: true, acao: async (d) => { st.usuario = await api('auth/login', { method: 'POST', body: d }); } }],
    aoAbrir: () => ($('#dlg').oncancel = (ev) => ev.preventDefault()),
  });
  if (!st.usuario) return telaLogin(); // o login nao pode ser dispensado
  aplicarUsuario();
}

async function telaPrimeiroAcesso() {
  await dialogo({
    titulo: 'Bem-vindo ao MCC — usuário administrador', largura: '520px',
    corpo: '<p>Crie o usuário administrador. Ele tem acesso completo e cadastra os demais usuários e suas permissões.</p>' +
      campos([['nome', 'Nome do usuário administrador', 'text', { req: true, inteiro: true }],
        ['email', 'E-mail (login)', 'email', { req: true, inteiro: true, attrs: 'autocomplete="username"' }],
        ['senha', 'Senha de acesso (mín. 6)', 'password', { req: true, attrs: 'minlength="6" autocomplete="new-password"' }],
        ['confirma', 'Confirme a senha', 'password', { req: true, attrs: 'autocomplete="new-password"' }]]),
    botoes: [{ rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
      if (d.senha !== d.confirma) throw new Error('A confirmação não confere com a senha.');
      st.usuario = await api('auth/setup', { method: 'POST', body: d });
    } }],
    aoAbrir: () => ($('#dlg').oncancel = (ev) => ev.preventDefault()),
  });
  if (!st.usuario) return telaPrimeiroAcesso();
  aplicarUsuario();
}

// Mostra/oculta abas e menus conforme as permissoes do usuario.
function aplicarUsuario() {
  const u = st.usuario;
  document.body.classList.remove('deslogado');
  $('#nomeUsuario').textContent = u.nome;
  const visivel = { D: perm('despesas') > 0, R: perm('receitas') > 0, dash: perm('fluxo') > 0, saldos: perm('bancos') > 0 || perm('fluxo') > 0 };
  $$('#abas button').forEach((b) => (b.hidden = !visivel[b.dataset.aba]));
  if (!visivel[st.aba]) st.aba = Object.keys(visivel).find((k) => visivel[k]) || 'nenhuma';
  for (const el of $$('[data-perm]')) {
    // data-perm="modulo:nivel" (ou varios separados por "|", basta um)
    el.hidden = !el.dataset.perm.split('|').some((p) => { const [m, n = '1'] = p.split(':'); return perm(m) >= Number(n); });
  }
  for (const g of $$('.sub')) {
    const temItem = $$('a', g).some((a) => !a.hidden);
    g.closest('.menu').hidden = !temItem;
  }
  montarMenuRel();
}

async function sair() {
  await api('auth/logout', { method: 'POST' }).catch(() => {});
  location.reload();
}

async function alterarSenha() {
  await dialogo({
    titulo: 'Alterar senha de acesso', largura: '440px',
    corpo: campos([['atual', 'Senha atual', 'password', { req: true, inteiro: true, attrs: 'autocomplete="current-password"' }],
      ['nova', 'Digite a nova senha', 'password', { req: true, inteiro: true, attrs: 'minlength="6" autocomplete="new-password"' }],
      ['confirma', 'Confirme a senha', 'password', { req: true, inteiro: true, attrs: 'autocomplete="new-password"' }]]),
    botoes: [{ rot: 'Cancela', valor: 'cancel' }, { rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
      if (d.nova !== d.confirma) throw new Error('A confirmação não confere com a nova senha.');
      await api('auth/senha', { method: 'POST', body: d });
      toast('Senha alterada.');
    } }],
  });
}
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null)).toString();

function toast(msg, erro = false) {
  const t = $('#toast');
  t.textContent = msg; t.className = 'on' + (erro ? ' erro' : '');
  clearTimeout(t._h); t._h = setTimeout(() => (t.className = ''), 3200);
}
async function tenta(fn) {
  try { return await fn(); } catch (e) { toast(e.message, true); throw e; }
}

// ---------- Dialogos ----------
function dialogo({ titulo, corpo, botoes = [{ rot: 'Fechar', valor: 'cancel' }], largura, aoAbrir }) {
  const dlg = $('#dlg'), form = $('#dlgForm');
  // Um dialogo substitui o outro no mesmo <dialog>; o anterior e resolvido como cancelado.
  dlg.oncancel = null;
  const anterior = dlg._resolve;
  dlg._resolve = null;
  anterior?.(null);
  dlg.style.maxWidth = largura || '';
  form.innerHTML = `<header><span>${esc(titulo)}</span></header><div class="corpo">${corpo}</div>
    <footer>${botoes.map((b) => `<button class="btn ${b.pri ? 'pri' : ''}" value="${b.valor}" ${b.valor === 'cancel' ? 'formnovalidate' : ''}>${esc(b.rot)}</button>`).join('')}</footer>`;
  return new Promise((resolve) => {
    const fim = (v) => { if (dlg._resolve === fim) dlg._resolve = null; resolve(v); };
    dlg._resolve = fim;
    form.onsubmit = async (ev) => {
      const valor = ev.submitter?.value || 'ok';
      if (valor === 'cancel') return;
      const b = botoes.find((x) => x.valor === valor);
      if (b?.acao) {
        ev.preventDefault();
        try { const r = await b.acao(dados(form)); if (r !== false) { dlg.close(); fim(r ?? valor); } }
        catch (e) { toast(e.message, true); }
      } else fim(valor);
    };
    dlg.onclose = () => { if (!dlg.open) dlg._resolve?.(null); }; // ignora close atrasado de um dialogo anterior
    if (!dlg.open) dlg.showModal();
    aoAbrir?.(form);
  });
}
function fechar() { $('#dlg').close(); }

// Desabilita os campos de um formulario aberto em modo "somente consulta".
function somenteLeitura(form) {
  for (const el of $$('.corpo input, .corpo select, .corpo textarea', form)) {
    if (el.type === 'radio' || el.type === 'checkbox') el.onclick = (ev) => ev.preventDefault(); // trava sem esconder a marcacao
    else if (el.tagName === 'SELECT') el.disabled = true;
    else el.readOnly = true;
  }
}

function dados(form) {
  const o = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === 'checkbox') o[el.name] = el.checked ? 1 : 0;
    else if (el.type === 'radio') { if (el.checked) o[el.name] = el.value; }
    else o[el.name] = el.value;
  }
  return o;
}

// Monta campos a partir de uma especificacao [nome, rotulo, tipo, opcoes].
function campos(spec, v = {}) {
  return `<div class="campos">${spec.map(([n, rot, tipo = 'text', op = {}]) => {
    const val = v[n] ?? op.padrao ?? '';
    const cls = op.inteiro ? ' class="inteiro"' : '';
    const req = op.req ? ' required' : '';
    if (tipo === 'select')
      return `<label${cls}>${esc(rot)}<select name="${n}"${req}>${op.opcoes.map(([k, t]) => `<option value="${esc(k)}" ${String(k) === String(val) ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
    if (tipo === 'radio')
      return `<label${cls}>${esc(rot)}<span class="radio">${op.opcoes.map(([k, t]) => `<label class="check"><input type="radio" name="${n}" value="${esc(k)}" ${String(k) === String(val) ? 'checked' : ''}>${esc(t)}</label>`).join('')}</span></label>`;
    if (tipo === 'check')
      return `<label class="check${op.inteiro ? ' inteiro' : ''}"><input type="checkbox" name="${n}" ${Number(val) ? 'checked' : ''}>${esc(rot)}</label>`;
    if (tipo === 'textarea') return `<label class="inteiro">${esc(rot)}<textarea name="${n}">${esc(val)}</textarea></label>`;
    const list = op.lista ? ` list="${op.lista}"` : '';
    const step = tipo === 'number' ? ' step="0.01"' : '';
    return `<label${cls}>${esc(rot)}<input type="${tipo}" name="${n}" value="${esc(val)}"${req}${list}${step} ${op.attrs || ''}></label>`;
  }).join('')}</div>`;
}
const datalist = (id, itens) => `<datalist id="${id}">${itens.map((i) => `<option value="${esc(i)}">`).join('')}</datalist>`;

// ---------- Inicializacao / conta controle ----------
async function carregarAux() {
  [st.contas, st.centros, st.pessoas, st.itens] = await Promise.all([api('contas'), api('centros'), api('pessoas'), api('itens')]);
  const sel = $('#fConta'), atual = sel.value;
  sel.innerHTML = '<option value="">Todas as contas</option>' + st.contas.filter((c) => c.ativa).map((c) => `<option value="${c.id}">${esc(c.descricao)}</option>`).join('');
  sel.value = atual;
}

async function escolherEmpresa(forcar = false) {
  st.empresas = await api('empresas');
  const podeCriar = perm('config') >= 2;
  if (!st.empresas.length) {
    if (podeCriar) return cadastroEmpresa(null, true);
    $('#conteudo').innerHTML = '<div class="vazio">Seu usuário não tem acesso a nenhuma conta controle. Procure o administrador.</div>';
    return;
  }
  const salva = Number(localStorageGet('mcc.empresa'));
  let emp = !forcar && st.empresas.find((e) => e.id === salva);
  if (!emp && st.empresas.length === 1 && !forcar) emp = st.empresas[0];
  if (!emp) {
    const r = await dialogo({
      titulo: 'Conta controle', largura: '480px',
      corpo: `<p>Selecione a conta controle (empresa ou pessoa física) que deseja acessar:</p>
        ${campos([['empresa', 'Conta controle', 'select', { opcoes: st.empresas.map((e) => [e.id, e.nome]) }]])}`,
      botoes: [...(podeCriar ? [{ rot: 'Nova conta controle', valor: 'nova' }] : []), { rot: 'Entrar', valor: 'ok', pri: true, acao: (d) => d.empresa }],
    });
    if (r === 'nova') return cadastroEmpresa(null, true);
    emp = st.empresas.find((e) => e.id === Number(r)) || st.empresas[0];
  }
  await usarEmpresa(emp);
}

function localStorageGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function localStorageSet(k, v) { try { localStorage.setItem(k, v); } catch { /* sem armazenamento */ } }

async function usarEmpresa(emp) {
  st.empresa = emp;
  localStorageSet('mcc.empresa', emp.id);
  $('#nomeEmpresa').textContent = emp.nome;
  document.title = 'MCC — ' + emp.nome;
  mostrarProtecao();
  await carregarAux();
  await render();
  const lemb = await api('lembretes?dias=3');
  if (lemb.length) toast(`${lemb.length} conta(s) vencida(s) ou vencendo nos próximos 3 dias — veja em Cadastros › Lembretes.`);
}

const UFS = 'AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO'.split(' ');
const ENDERECO = [['endereco', 'Endereço', 'text', { inteiro: true }], ['bairro', 'Bairro'], ['cidade', 'Cidade'],
  ['uf', 'UF', 'select', { opcoes: [['', ''], ...UFS.map((u) => [u, u])] }], ['cep', 'CEP']];

async function cadastroEmpresa(v, primeira = false) {
  const spec = [['pessoa', 'Pessoa', 'radio', { opcoes: [['F', 'Física'], ['J', 'Jurídica']], padrao: 'J' }],
    ['nome', 'Nome ou razão social', 'text', { req: true, inteiro: true }], ['documento', 'CPF / CNPJ'], ['documento2', 'RG / Inscrição estadual'],
    ...ENDERECO, ['telefone', 'Telefone(s)'], ['email', 'E-mail', 'email'], ['site', 'Web site'],
    ['usa_centro_custo', 'Controlar lançamentos por centros de custo/lucro', 'check', { padrao: 1, inteiro: true }]];
  await dialogo({
    titulo: primeira ? 'Cadastro da conta — bem-vindo ao MCC' : v ? 'Alterar conta controle' : 'Nova conta controle',
    corpo: (primeira ? '<p>Cadastre a primeira conta controle (sua empresa ou você como pessoa física).</p>' : '') + campos(spec, v || {}),
    botoes: [...(primeira ? [] : [{ rot: 'Cancela', valor: 'cancel' }]), {
      rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
        if (v) await api('empresas/' + v.id, { method: 'PUT', body: d });
        else {
          const { id } = await api('empresas', { method: 'POST', body: d });
          if (primeira) {
            await usarEmpresa({ id, ...d });
            if (perm('bancos') >= 2) await api('contas', { method: 'POST', body: { descricao: 'CAIXA INTERNO', tipo: 'C', saldo_inicial: 0 } });
            await carregarAux();
          }
        }
        toast('Conta controle gravada.');
      },
    }],
  });
  if (v && st.empresa?.id === v.id) { st.empresa = (await api('empresas')).find((e) => e.id === v.id); $('#nomeEmpresa').textContent = st.empresa.nome; }
}

// ---------- Filtros ----------
function montarFiltros() {
  const ano = new Date().getFullYear();
  $('#fAno').innerHTML = Array.from({ length: 40 }, (_, i) => 2001 + i).map((a) => `<option ${a === ano ? 'selected' : ''}>${a}</option>`).join('');
  const meses = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
  $('#fMes').innerHTML = meses.map((m, i) => `<option value="${i + 1}">${m}</option>`).join('') +
    '<option value="T1">1º Tri</option><option value="T2">2º Tri</option><option value="T3">3º Tri</option><option value="T4">4º Tri</option>' +
    '<option value="S1">1º Sem</option><option value="S2">2º Sem</option><option value="ANO">Ano todo</option><option value="TODOS" selected>Todo período</option>';
  $('#fMes').value = String(new Date().getMonth() + 1);
  for (const el of $$('.filtros select')) el.addEventListener('change', () => render());
  let h; $('#fBusca').addEventListener('input', () => { clearTimeout(h); h = setTimeout(render, 250); });
}
const filtros = () => ({
  situacao: $('#fSit').value, conta_id: $('#fConta').value, campo_data: $('#fCampo').value,
  ano: $('#fAno').value, mes: $('#fMes').value, ordem: $('#fOrdem').value, busca: $('#fBusca').value.trim(),
});

// ---------- Render principal ----------
async function render() {
  dica(null);
  if (!st.empresa) return;
  $$('#abas button').forEach((b) => b.classList.toggle('ativa', b.dataset.aba === st.aba));
  $('.filtros').style.display = ['D', 'R'].includes(st.aba) ? '' : 'none';
  if (st.aba === 'D' || st.aba === 'R') return renderLancamentos();
  if (st.aba === 'dash') return renderDashboard();
  if (st.aba === 'saldos') return renderSaldos();
  $('#conteudo').innerHTML = '<div class="vazio">Seu usuário não tem acesso a nenhum módulo de lançamentos. Use os menus disponíveis ou procure o administrador.</div>';
}

async function renderLancamentos() {
  const tipo = st.aba;
  const seq = (st.seq = (st.seq || 0) + 1);
  const linhas = await api('lancamentos?' + qs({ tipo, ...filtros() }));
  if (seq !== st.seq || st.aba !== tipo) return; // resposta de um filtro/aba anterior
  st.linhas = linhas;
  st.sel = new Set([...st.sel].filter((id) => st.linhas.some((l) => l.id === id)));
  const nome = tipo === 'D' ? 'despesa' : 'receita';
  const tot = st.linhas.reduce((a, l) => { a.t += l.valor; a[l.situacao] += l.valor; return a; }, { t: 0, V: 0, P: 0 });
  const usaCentro = Number(st.empresa.usa_centro_custo);
  const edita = permTipo(tipo) >= 2;
  $('#conteudo').innerHTML = `
    <div class="acoes">
      <button class="btn pri" data-a="incluir" ${edita ? '' : 'hidden'}>Incluir nova ${nome}</button>
      <button class="btn" data-a="alterar">${edita ? 'Alterar' : 'Consultar'}</button>
      <button class="btn perigo" data-a="excluir" ${edita ? '' : 'hidden'}>Excluir</button>
      <button class="btn" data-a="baixar" ${edita ? '' : 'hidden'}>Baixar</button>
      <button class="btn" data-a="estornar" ${edita ? '' : 'hidden'}>Estornar baixa</button>
      <button class="btn" data-a="recibo">Recibo</button>
      <button class="btn" data-a="parcelar" ${edita ? '' : 'hidden'}>Parcelamento</button>
      ${edita ? '' : '<span class="leitura">Somente consulta</span>'}
      <div class="totais">
        <span>${st.linhas.length} lançamento(s)</span>
        <span>${tipo === 'D' ? 'Pago' : 'Recebido'}: <b class="pos">${moeda(tot.V)}</b></span>
        <span>Em aberto: <b class="neg">${moeda(tot.P)}</b></span>
        <span>Total: <b>${moeda(tot.t)}</b></span>
      </div>
    </div>
    <div class="grade"><table>
      <thead><tr><th><input type="checkbox" id="selTodos" aria-label="Selecionar todos"></th><th>Data</th><th>Documento</th><th>Descrição</th>
        <th>${tipo === 'D' ? 'Fornecedor' : 'Cliente'}</th><th class="num">Valor</th><th>Vcto/Pgto</th><th>Situação</th><th>Conta</th>
        ${usaCentro ? '<th>Centro</th>' : ''}<th>Observação</th></tr></thead>
      <tbody>${st.linhas.map((l) => `<tr data-id="${l.id}" class="${st.sel.has(l.id) ? 'sel' : ''}">
        <td><input type="checkbox" ${st.sel.has(l.id) ? 'checked' : ''} aria-label="Selecionar"></td>
        <td>${dataBR(l.data_mov)}</td><td>${esc(l.documento)}</td><td>${esc(l.descricao)}</td><td>${esc(l.pessoa)}</td>
        <td class="num">${moeda(l.valor)}</td><td>${dataBR(l.ven_pgto)}</td>
        <td><span class="tag ${l.situacao_desc.replace(' ', '-')}">${l.situacao_desc}</span></td>
        <td>${esc(l.conta)}</td>${usaCentro ? `<td>${esc(l.centro)}</td>` : ''}<td>${esc(l.observacao)}</td></tr>`).join('')}</tbody>
    </table>${st.linhas.length ? '' : '<div class="vazio">Nenhum lançamento no período/filtro selecionado.</div>'}</div>`;

  const tb = $('#conteudo tbody');
  tb.onclick = (ev) => {
    const tr = ev.target.closest('tr'); if (!tr) return;
    const id = Number(tr.dataset.id);
    if (ev.target.type === 'checkbox' || ev.ctrlKey || ev.metaKey) { st.sel.has(id) ? st.sel.delete(id) : st.sel.add(id); }
    else st.sel = new Set([id]);
    $$('tr', tb).forEach((r) => { const s = st.sel.has(Number(r.dataset.id)); r.classList.toggle('sel', s); $('input', r).checked = s; });
  };
  tb.ondblclick = (ev) => { const tr = ev.target.closest('tr'); if (tr) formLancamento(tipo, Number(tr.dataset.id)); };
  $('#selTodos').onchange = (ev) => { st.sel = ev.target.checked ? new Set(st.linhas.map((l) => l.id)) : new Set(); renderLancamentos(); };
  $('#conteudo .acoes').onclick = (ev) => {
    const a = ev.target.dataset.a; if (!a) return;
    const ids = [...st.sel];
    const um = () => { if (ids.length !== 1) { toast('Selecione um lançamento.', true); return null; } return ids[0]; };
    if (a === 'incluir') formLancamento(tipo);
    if (a === 'alterar' && um()) formLancamento(tipo, ids[0]);
    if (a === 'excluir' && um()) excluirLanc(ids[0]);
    if (a === 'baixar') ids.length > 1 ? baixaMultipla(ids) : um() && formBaixa(ids[0]);
    if (a === 'estornar' && um()) tenta(async () => { await api(`lancamentos/${ids[0]}/estornar`, { method: 'POST' }); toast('Baixa estornada.'); render(); });
    if (a === 'recibo' && um()) recibo(ids[0]);
    if (a === 'parcelar') formParcelamento(tipo);
  };
}

// ---------- Lancamentos ----------
function specLanc(tipo, v) {
  const itens = st.itens.filter((i) => i.tipo === tipo).map((i) => i.descricao);
  const pessoas = st.pessoas.filter((p) => p.tipo === (tipo === 'D' ? 'F' : 'C')).map((p) => p.nome);
  const centros = st.centros.filter((c) => (tipo === 'D' ? c.aplica_despesa : c.aplica_receita));
  const spec = [
    ['data_mov', 'Data movimento', 'date', { req: true, padrao: hoje() }],
    ['documento', 'Documento (NF, pedido, OS…)'],
    ['descricao', 'Descrição', 'text', { req: true, lista: 'dlItens' }],
    ['pessoa', tipo === 'D' ? 'Fornecedor' : 'Cliente', 'text', { lista: 'dlPessoas' }],
    ['valor', 'Valor', 'number', { req: true, attrs: 'min="0.01"' }],
    ['vencimento', 'Vencimento', 'date', { req: true, padrao: hoje() }],
    ['conta_id', 'Conta', 'select', { opcoes: [['', '(sem conta)'], ...st.contas.filter((c) => c.ativa || c.id === v?.conta_id).map((c) => [c.id, c.descricao])] }],
  ];
  if (Number(st.empresa.usa_centro_custo))
    spec.push(['centro_id', tipo === 'D' ? 'Centro de custo' : 'Centro de lucro', 'select', { opcoes: [['', '(nenhum)'], ...centros.map((c) => [c.id, c.nome])] }]);
  spec.push(['observacao', 'Observações (cheque, banco etc.)', 'text', { inteiro: true }]);
  return { spec, listas: datalist('dlItens', itens) + datalist('dlPessoas', pessoas) };
}

async function formLancamento(tipo, id) {
  const v = id ? await api('lancamentos/' + id) : { situacao: 'P' };
  const { spec, listas } = specLanc(tipo, v);
  spec.splice(6, 0, ['situacao', 'Situação', 'radio', { opcoes: [['V', tipo === 'D' ? 'Pago' : 'Recebido'], ['P', tipo === 'D' ? 'À pagar' : 'À receber']] }],
    ['data_pagamento', tipo === 'D' ? 'Data do pagamento' : 'Data do recebimento', 'date']);
  const nome = tipo === 'D' ? 'despesa' : 'receita';
  const leitura = permTipo(tipo) < 2;
  const extra = v.grupo ? `<p class="legenda">Parcela ${v.parcela} de ${v.total_parcelas}</p>` : '';
  await dialogo({
    titulo: (leitura ? 'Consultar ' : id ? 'Alterar ' : 'Incluir ') + nome, corpo: extra + campos(spec, v) + listas,
    botoes: leitura ? [{ rot: 'Fechar', valor: 'cancel' }] : [{ rot: 'Cancela', valor: 'cancel' }, {
      rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
        d.tipo = tipo;
        await api('lancamentos' + (id ? '/' + id : ''), { method: id ? 'PUT' : 'POST', body: d });
        toast(id ? 'Lançamento alterado.' : 'Lançamento incluído.');
      },
    }],
    aoAbrir: (f) => {
      const sync = () => { const pago = f.situacao.value === 'V'; f.data_pagamento.disabled = !pago; if (pago && !f.data_pagamento.value) f.data_pagamento.value = hoje(); };
      $$('input[name=situacao]', f).forEach((r) => (r.onchange = sync)); sync();
      f.data_mov.onchange = () => { if (!id && !f.vencimento.dataset.mexeu) f.vencimento.value = f.data_mov.value; };
      f.vencimento.oninput = () => (f.vencimento.dataset.mexeu = 1);
      if (leitura) somenteLeitura(f);
    },
  });
  await carregarAux(); render();
}

async function formParcelamento(tipo) {
  const { spec, listas } = specLanc(tipo, {});
  spec[4][1] = 'Valor da parcela'; spec[5][1] = '1º vencimento';
  spec.splice(6, 0, ['parcelas', 'Nº de parcelas', 'number', { req: true, padrao: 2, attrs: 'min="1" max="360" step="1"' }],
    ['periodicidade', 'Periodicidade', 'select', { padrao: 'mensal', opcoes: [['diaria', 'Diária'], ['semanal', 'Semanal'], ['quinzenal', 'Quinzenal'], ['mensal', 'Mensal'], ['bimestral', 'Bimestral'], ['trimestral', 'Trimestral'], ['semestral', 'Semestral'], ['anual', 'Anual']] }],
    ['mov_igual_vencimento', 'Data de movimento igual à data de vencimento', 'check', { inteiro: true }]);
  await dialogo({
    titulo: `Inserir múltiplas ${tipo === 'D' ? 'despesas' : 'receitas'} (parcelamento)`, corpo: campos(spec) + listas,
    botoes: [{ rot: 'Cancela', valor: 'cancel' }, {
      rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
        d.tipo = tipo; d.mov_igual_vencimento = !!d.mov_igual_vencimento;
        const { ids } = await api('parcelar', { method: 'POST', body: d });
        toast(`${ids.length} parcela(s) incluída(s).`);
      },
    }],
  });
  await carregarAux(); render();
}

async function formBaixa(id) {
  const l = await api('lancamentos/' + id);
  if (l.situacao === 'V') return toast('Este lançamento já está baixado.', true);
  await dialogo({
    titulo: `Baixar ${l.tipo === 'D' ? 'pagamento' : 'recebimento'}`, largura: '620px',
    corpo: `<p><b>${esc(l.descricao)}</b> ${l.pessoa ? '— ' + esc(l.pessoa) : ''}<br>Vencimento: ${dataBR(l.vencimento)}</p>` + campos([
      ['data_pagamento', l.tipo === 'D' ? 'Pagamento' : 'Recebimento', 'date', { req: true, padrao: hoje() }],
      ['valor', 'Valor', 'number', { req: true, padrao: l.valor }],
      ['conta_id', 'Conta', 'select', { padrao: l.conta_id, opcoes: [['', '(sem conta)'], ...st.contas.filter((c) => c.ativa).map((c) => [c.id, c.descricao])] }],
      ['observacao', 'Observações (cheque, banco etc.)', 'text', { padrao: l.observacao, inteiro: true }]]),
    botoes: [{ rot: 'Cancela', valor: 'cancel' }, {
      rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => { await api(`lancamentos/${id}/baixar`, { method: 'POST', body: d }); toast('Baixa efetuada.'); },
    }],
  });
  render();
}

async function baixaMultipla(ids) {
  if (!ids?.length) {
    if (!['D', 'R'].includes(st.aba)) { st.aba = 'D'; await render(); }
    ids = st.linhas.filter((l) => l.situacao === 'P').map((l) => l.id);
  }
  const ls = st.linhas.filter((l) => ids.includes(l.id) && l.situacao === 'P');
  if (!ls.length) return toast('Nenhum lançamento em aberto selecionado.', true);
  const total = ls.reduce((a, l) => a + l.valor, 0);
  await dialogo({
    titulo: 'Baixa múltipla',
    corpo: `<div class="grade" style="max-height:40vh"><table><thead><tr><th>Vencimento</th><th>Descrição</th><th>Nome</th><th>Documento</th><th class="num">Valor</th></tr></thead>
      <tbody>${ls.map((l) => `<tr><td>${dataBR(l.vencimento)}</td><td>${esc(l.descricao)}</td><td>${esc(l.pessoa)}</td><td>${esc(l.documento)}</td><td class="num">${moeda(l.valor)}</td></tr>`).join('')}</tbody>
      <tfoot><tr><td colspan="4">Total a ser baixado</td><td class="num">${moeda(total)}</td></tr></tfoot></table></div><br>` +
      campos([['data_pagamento', 'Data da baixa', 'date', { req: true, padrao: hoje() }],
        ['conta_id', 'Conta a ser movimentada', 'select', { opcoes: [['', '(manter a conta de cada lançamento)'], ...st.contas.filter((c) => c.ativa).map((c) => [c.id, c.descricao])] }]]),
    botoes: [{ rot: 'Cancela', valor: 'cancel' }, {
      rot: `Baixar todas (${ls.length})`, valor: 'ok', pri: true, acao: async (d) => {
        const r = await api('baixa-multipla', { method: 'POST', body: { ...d, ids: ls.map((l) => l.id) } });
        toast(`${r.baixados} lançamento(s) baixado(s).`);
      },
    }],
  });
  st.sel.clear(); render();
}

async function excluirLanc(id) {
  const l = await api('lancamentos/' + id);
  let modo = 'esta';
  if (l.grupo) {
    const r = await dialogo({
      titulo: 'Excluir lançamento parcelado', largura: '520px',
      corpo: `<p>${esc(l.descricao)} — parcela ${l.parcela} de ${l.total_parcelas}</p>` + campos([['modo', 'Escolha uma opção abaixo:', 'radio', {
        padrao: 'esta', inteiro: true, opcoes: [['esta', 'Somente esta parcela'], ['seguintes', 'Esta e as seguintes'], ['abertas', 'Todas as parcelas em aberto']] }]]),
      botoes: [{ rot: 'Cancela', valor: 'cancel' }, { rot: 'Excluir', valor: 'ok', pri: true, acao: (d) => d.modo }],
    });
    if (!r) return; modo = r;
  } else if (!confirm(`Excluir "${l.descricao}" de ${moeda(l.valor)}?`)) return;
  await tenta(async () => { const r = await api(`lancamentos/${id}?modo=${modo}`, { method: 'DELETE' }); toast(`${r.excluidos} lançamento(s) excluído(s). Podem ser restaurados em Registros excluídos.`); });
  st.sel.delete(id); render();
}

function extenso(valor) {
  const u = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove'];
  const d = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa'];
  const c = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos'];
  const ate999 = (n) => {
    if (n === 100) return 'cem';
    const p = [];
    if (n >= 100) { p.push(c[Math.floor(n / 100)]); n %= 100; }
    if (n >= 20) { p.push(d[Math.floor(n / 10)]); n %= 10; }
    if (n > 0) p.push(u[n]);
    return p.join(' e ');
  };
  const inteiro = Math.floor(valor), cent = Math.round((valor - inteiro) * 100);
  const partes = [];
  const mi = Math.floor(inteiro / 1e6), mil = Math.floor((inteiro % 1e6) / 1000), resto = inteiro % 1000;
  if (mi) partes.push(ate999(mi) + (mi === 1 ? ' milhão' : ' milhões'));
  if (mil) partes.push(mil === 1 ? 'mil' : ate999(mil) + ' mil');
  if (resto) partes.push(ate999(resto));
  let txt = partes.join(resto && resto < 100 || resto % 100 === 0 && resto ? ' e ' : ', ');
  if (inteiro) txt += (inteiro === 1 ? ' real' : (inteiro % 1e6 === 0 ? ' de reais' : ' reais'));
  if (cent) txt += (inteiro ? ' e ' : '') + ate999(cent) + (cent === 1 ? ' centavo' : ' centavos');
  return txt || 'zero real';
}

async function recibo(id) {
  const l = await api('lancamentos/' + id);
  const emp = st.empresa;
  const despesa = l.tipo === 'D';
  const pagador = despesa ? emp.nome : l.pessoa || '';
  const recebedor = despesa ? l.pessoa || '' : emp.nome;
  const w = window.open('', '_blank');
  if (!w) return toast('Permita pop-ups para emitir o recibo.', true);
  w.document.write(`<!doctype html><meta charset="utf-8"><title>Recibo</title>
    <style>body{font:15px system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 16px}h1{text-align:center;letter-spacing:.2em}
    .val{float:right;border:2px solid #000;padding:6px 14px;font-weight:700;font-size:18px}p{line-height:1.9}.ass{margin-top:70px;text-align:center}
    .ass span{display:inline-block;border-top:1px solid #000;padding-top:4px;min-width:340px}</style>
    <h1>RECIBO</h1><div class="val">${moeda(l.valor)}</div><br style="clear:both">
    <p>Recebi(emos) de <b>${esc(pagador)}</b> a importância de <b>${esc(extenso(l.valor))}</b>
    referente a <b>${esc(l.descricao)}</b>${l.documento ? ` (documento ${esc(l.documento)})` : ''}${l.observacao ? ` — ${esc(l.observacao)}` : ''}.</p>
    <p>Para maior clareza firmo(amos) o presente.</p>
    <p style="text-align:right">${esc(emp.cidade || '')}${emp.cidade ? ', ' : ''}${new Date((l.data_pagamento || hoje()) + 'T12:00').toLocaleDateString('pt-BR', { day: 'numeric', month: 'long', year: 'numeric' })}</p>
    <div class="ass"><span>${esc(recebedor)}</span></div><script>print()<\/script>`);
  w.document.close();
}

// ---------- Dashboard ----------
async function renderDashboard() {
  const per = localStorageGet('mcc.dashPer') || 'mes';
  $('#conteudo').innerHTML = `
    <div class="acoes">
      <label>Analisar: <select id="dPer">
        <option value="hoje">Hoje</option><option value="semana">Esta semana</option><option value="mes">Este mês</option><option value="periodo">Período específico</option></select></label>
      <span id="dPerCustom" hidden><input type="date" id="dDe"> a <input type="date" id="dAte"></span>
      <label class="check"><input type="checkbox" id="dVenc"> Considerar os vencidos</label>
      <button class="btn pri" id="dAtu">Atualizar</button>
    </div>
    <div id="dCards"></div>
    <div class="secao"><h3>Análise linear</h3>
      <div class="acoes"><span class="radio">
        <label class="check"><input type="radio" name="lin" value="dia">Diária</label>
        <label class="check"><input type="radio" name="lin" value="semana">Semanal</label>
        <label class="check"><input type="radio" name="lin" value="mes" checked>Mensal</label></span>
        <label class="check"><input type="checkbox" id="lD" checked>Pagamentos</label>
        <label class="check"><input type="checkbox" id="lR" checked>Recebimentos</label>
        <label class="check"><input type="checkbox" id="lM" checked>Margem</label>
      </div>
      <div class="grafico" id="dLin"></div>
    </div>`;
  $('#dPer').value = per;
  const atualiza = async () => {
    const p = $('#dPer').value; localStorageSet('mcc.dashPer', p);
    $('#dPerCustom').hidden = p !== 'periodo';
    const d = await api('dashboard?' + qs({ periodo: p, de: $('#dDe').value, ate: $('#dAte').value, vencidos: $('#dVenc').checked ? 1 : '' }));
    const card = (rot, v, cls = '') => `<div class="card"><div class="rot">${rot}</div><div class="val ${cls}">${moeda(v)}</div></div>`;
    $('#dCards').innerHTML = `
      <div class="secao"><h3>Análise em regime de caixa <small class="legenda">${dataBR(d.de)} a ${dataBR(d.ate)}</small></h3><div class="cards">
        ${card('À receber', d.caixa.a_receber, 'pos')}${card('À pagar', d.caixa.a_pagar, 'neg')}
        ${card('Recebido', d.caixa.recebido, 'pos')}${card('Pago', d.caixa.pago, 'neg')}</div></div>
      <div class="secao"><h3>Análise em regime de competência</h3><div class="cards">
        ${card('Receitas', d.competencia.receitas, 'pos')}${card('Despesas', d.competencia.despesas, 'neg')}
        ${card('Margem bruta', d.competencia.margem, d.competencia.margem >= 0 ? 'pos' : 'neg')}</div></div>`;
  };
  const linear = async () => {
    const ag = $('input[name=lin]:checked').value;
    const dados = await api('linear?' + qs({ agrupamento: ag, ano: $('#fAno').value }));
    const series = [['R', 'Recebimentos', 'recebimentos'], ['D', 'Pagamentos', 'pagamentos']].filter(([t]) => $('#l' + t).checked);
    desenharColunas($('#dLin'), {
      titulo: 'Pagamentos e recebimentos por período',
      series: series.map(([t, nome]) => ({ nome, slot: SLOT[t] })),
      pontos: dados.map((d) => ({ rotulo: /^\d{4}-\d{2}$/.test(d.periodo) ? 'JanFevMarAbrMaiJunJulAgoSetOutNovDez'.substr((d.periodo.slice(5) - 1) * 3, 3) : d.periodo.slice(5),
        valores: series.map(([, , k]) => d[k]), linha: d.margem })),
      linha: $('#lM').checked ? { nome: 'Margem', slot: SLOT.M } : null,
    });
  };
  $('#dAtu').onclick = atualiza; $('#dPer').onchange = atualiza; $('#dVenc').onchange = atualiza;
  $$('#conteudo input[name=lin], #lD, #lR, #lM').forEach((el) => (el.onchange = linear));
  await Promise.all([atualiza(), linear()]);
}

// ---------- Graficos (SVG/HTML, sem bibliotecas) ----------
// Cor segue a entidade, nunca a posicao: receitas = serie 1, despesas = serie 2, margem = serie 3.
const SLOT = { R: 1, D: 2, M: 3 };
const corSerie = (n) => `var(--serie-${n})`;

function dica(ev, html) {
  let el = $('.dica');
  if (!el) { el = document.createElement('div'); el.className = 'dica'; document.body.append(el); }
  if (!html) { el.hidden = true; return; }
  el.innerHTML = html; el.hidden = false;
  const r = el.getBoundingClientRect();
  const x = ev.clientX + 14 + r.width > innerWidth ? ev.clientX - r.width - 14 : ev.clientX + 14;
  el.style.left = Math.max(4, x) + 'px';
  el.style.top = Math.max(4, Math.min(innerHeight - r.height - 4, ev.clientY - r.height / 2)) + 'px';
}

// Escala "bonita": passos 1-2-5 x 10^n.
function escala(min, max) {
  if (max === min) max = min + 1;
  const bruto = (max - min) / 4, mag = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 5, 10].map((f) => f * mag).find((p) => p >= bruto);
  const lo = Math.floor(min / passo) * passo, hi = Math.ceil(max / passo) * passo;
  const ticks = [];
  for (let v = lo; v <= hi + passo / 2; v += passo) ticks.push(Math.round(v * 100) / 100);
  return { lo, hi, ticks };
}
const compacto = (v) => Math.abs(v) >= 1e6 ? (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi'
  : Math.abs(v) >= 1e3 ? (v / 1e3).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mil' : v.toLocaleString('pt-BR');

// Barra com topo arredondado (4px) apoiada na linha de base.
function barraPath(x, y0, w, h) {
  if (h <= 0) return '';
  const r = Math.min(4, w / 2, h);
  const y = y0 - h;
  return `M${x},${y0}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y0}Z`;
}

// Colunas agrupadas por periodo, com linha opcional (mesma unidade, mesmo eixo) e media opcional.
// cfg: { series: [{nome, slot}], pontos: [{rotulo, valores: [], linha?}], linha?: {nome, slot}, media?: number }
function desenharColunas(el, cfg) {
  const { series, pontos, linha, media } = cfg;
  if (!pontos.length || !pontos.some((p) => p.valores.some((v) => v) || (linha && p.linha))) {
    el.innerHTML = '<div class="vazio">Sem valores no período.</div>'; return;
  }
  // desenha na largura real do conteiner para o texto manter 11px
  const W = Math.max(320, Math.round(el.clientWidth || 900)), H = W < 560 ? 240 : 300, P = { l: 56, r: 12, t: 14, b: 40 };
  const todos = pontos.flatMap((p) => [...p.valores, ...(linha ? [p.linha] : [])]).concat(media ? [media] : [], [0]);
  const { lo, hi, ticks } = escala(Math.min(...todos), Math.max(...todos));
  const y = (v) => P.t + (H - P.t - P.b) * (1 - (v - lo) / (hi - lo));
  const bw = (W - P.l - P.r) / pontos.length, k = series.length;
  const grupo = Math.min(bw * 0.72, k * 26 + (k - 1) * 2);
  const w = (grupo - 2 * (k - 1)) / k;
  const passoRot = Math.max(1, Math.ceil(pontos.length / Math.max(1, Math.floor((W - P.l - P.r) / 64))));
  let svg = ticks.map((t) => `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="currentColor" stroke-opacity="${t === 0 ? .45 : .12}"/>
    <text x="${P.l - 8}" y="${y(t) + 4}" text-anchor="end">${compacto(t)}</text>`).join('');
  pontos.forEach((p, i) => {
    const x0 = P.l + i * bw;
    svg += `<rect class="faixa" data-i="${i}" x="${x0}" y="${P.t}" width="${bw}" height="${H - P.t - P.b}"/>`;
    p.valores.forEach((v, j) => {
      const x = x0 + (bw - grupo) / 2 + j * (w + 2); // 2px de folga entre barras vizinhas
      svg += `<path d="${barraPath(x, y(0), w, y(0) - y(Math.max(0, v)))}" fill="${corSerie(series[j].slot)}" pointer-events="none"/>`;
    });
    if (i % passoRot === 0) svg += `<text x="${x0 + bw / 2}" y="${H - P.b + 18}" text-anchor="middle">${esc(p.rotulo)}</text>`;
  });
  if (media) {
    svg += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(media)}" y2="${y(media)}" stroke="currentColor" stroke-width="1.5" stroke-dasharray="6 4" pointer-events="none"/>
      <text x="${W - P.r}" y="${y(media) - 6}" text-anchor="end">média ${esc(moeda(media))}</text>`;
  }
  if (linha) {
    const pts = pontos.map((p, i) => `${P.l + i * bw + bw / 2},${y(p.linha)}`);
    svg += `<polyline points="${pts.join(' ')}" fill="none" stroke="${corSerie(linha.slot)}" stroke-width="2" stroke-linejoin="round" pointer-events="none"/>` +
      pts.map((xy) => { const [cx, cy] = xy.split(','); return `<circle cx="${cx}" cy="${cy}" r="4" fill="${corSerie(linha.slot)}" stroke="var(--painel)" stroke-width="2" pointer-events="none"/>`; }).join('');
  }
  const itens = [...series.map((s) => `<span><i style="background:${corSerie(s.slot)}"></i>${esc(s.nome)}</span>`),
    ...(linha ? [`<span><i class="linha" style="background:${corSerie(linha.slot)}"></i>${esc(linha.nome)}</span>`] : []),
    ...(media ? ['<span><i class="tracejada"></i>Média do período</span>'] : [])];
  if (!el._observado) { // redesenha quando a largura muda
    el._observado = true;
    let larg = el.clientWidth;
    new ResizeObserver(() => { if (Math.abs(el.clientWidth - larg) > 24 && el._cfg) { larg = el.clientWidth; desenharColunas(el, el._cfg); } }).observe(el);
  }
  el._cfg = cfg;
  el.innerHTML = (itens.length >= 2 ? `<div class="legenda-g">${itens.join('')}</div>` : '') +
    `<svg class="grafico-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(cfg.titulo || 'Gráfico')}">${svg}</svg>`;
  const faixas = $$('.faixa', el);
  faixas.forEach((f) => {
    f.onmousemove = (ev) => {
      const p = pontos[f.dataset.i];
      faixas.forEach((o) => o.classList.toggle('on', o === f));
      dica(ev, `<b>${esc(p.rotulo)}</b>` + series.map((s, j) => `<div><span><i style="background:${corSerie(s.slot)}"></i>${esc(s.nome)}</span>${moeda(p.valores[j])}</div>`).join('') +
        (linha ? `<div><span><i style="background:${corSerie(linha.slot)}"></i>${esc(linha.nome)}</span>${moeda(p.linha)}</div>` : ''));
    };
    f.onmouseleave = () => { f.classList.remove('on'); dica(null); };
  });
}

// Ranking horizontal (parte do todo): uma cor, rotulos diretos com valor e percentual.
function desenharRanking(el, { pontos, slot }) {
  if (!pontos.length) { el.innerHTML = '<div class="vazio">Sem valores no período.</div>'; return; }
  const max = Math.max(...pontos.map((p) => p.valor));
  el.innerHTML = `<div class="ranking">${pontos.map((p, i) => `<div class="rot" title="${esc(p.rotulo)}">${esc(p.rotulo)}</div>
    <div class="trilho" data-i="${i}"><div class="barra" style="width:${(p.valor / max) * 100}%;background:${corSerie(slot)}"></div></div>
    <div class="val">${moeda(p.valor)}<small>${p.perc.toLocaleString('pt-BR')}%</small></div>`).join('')}</div>`;
  $$('.trilho', el).forEach((t) => {
    t.onmousemove = (ev) => { const p = pontos[t.dataset.i]; dica(ev, `<b>${esc(p.rotulo)}</b><div><span>Valor</span>${moeda(p.valor)}</div><div><span>Participação</span>${p.perc.toLocaleString('pt-BR')}%</div>`); };
    t.onmouseleave = () => dica(null);
  });
}

// ---------- Saldos ----------
async function renderSaldos() {
  const data = $('#sData')?.value || hoje();
  const s = await api('saldos?data=' + data);
  const ativas = s.filter((c) => c.ativa);
  const tot = ativas.reduce((a, c) => ({ s: a.s + c.saldo, p: a.p + c.previsto }), { s: 0, p: 0 });
  $('#conteudo').innerHTML = `<div class="acoes"><label>Posição em <input type="date" id="sData" value="${data}"></label>
      <button class="btn" id="sCad" ${perm('bancos') ? '' : 'hidden'}>Cadastro de contas bancárias</button></div>
    <div class="grade"><table><thead><tr><th>Conta</th><th>Tipo</th><th>Uso</th><th class="num">Saldo realizado</th><th class="num">Saldo previsto</th><th class="num">Limite</th></tr></thead>
    <tbody>${ativas.map((c) => `<tr><td>${esc(c.descricao)}</td><td>${c.tipo === 'C' ? 'Caixa interno' : 'Banco'}</td><td>${c.empresa_id ? 'Esta conta controle' : 'Compartilhada'}</td>
      <td class="num ${c.saldo < 0 ? 'neg' : ''}">${moeda(c.saldo)}</td><td class="num ${c.previsto < 0 ? 'neg' : ''}">${moeda(c.previsto)}</td><td class="num">${moeda(c.limite)}</td></tr>`).join('')}</tbody>
    <tfoot><tr><td colspan="3">Total</td><td class="num">${moeda(tot.s)}</td><td class="num">${moeda(tot.p)}</td><td></td></tr></tfoot></table></div>
    <p class="legenda">Saldo previsto inclui os lançamentos em aberto com vencimento até a data e as movimentações bancárias previstas.</p>`;
  $('#sData').onchange = renderSaldos;
  $('#sCad').onclick = () => cadastro('contas');
}

// ---------- Cadastros genericos ----------
const CAD = {
  empresas: { titulo: 'Cadastro de contas controle', rota: 'empresas', cols: [['nome', 'Conta controle'], ['documento', 'CPF/CNPJ'], ['cidade', 'Cidade'], ['telefone', 'Telefone']], form: (v) => cadastroEmpresa(v) },
  contas: {
    titulo: 'Contas bancárias', rota: 'contas', cols: [['descricao', 'Banco e conta'], ['tipo', 'Tipo', (v) => (v === 'C' ? 'Caixa interno' : 'Banco')], ['saldo_inicial', 'Saldo inicial', moeda], ['ativa', 'Ativa', (v) => (v ? 'Sim' : 'Não')], ['empresa_id', 'Utilização', (v) => (v ? 'Somente esta conta controle' : 'Compartilhada')]],
    spec: (v) => [['descricao', 'Banco e conta', 'text', { req: true, lista: 'dlBancos' }], ['tipo', 'Tipo', 'radio', { padrao: 'B', opcoes: [['B', 'Conta bancária'], ['C', 'Caixa interno']] }],
      ['saldo_inicial', 'Saldo inicial', 'number', { padrao: 0 }], ['limite', 'Limite', 'number', { padrao: 0 }],
      ['empresa_id', 'Utilização', 'select', { padrao: v.id ? v.empresa_id ?? '' : st.empresa.id, opcoes: [[st.empresa.id, 'Somente para a conta controle atual'], ['', 'Compartilhada em todas as contas controle']] }],
      ['ativa', 'Conta ativa', 'check', { padrao: 1 }]],
    extra: datalist('dlBancos', ['BANCO DO BRASIL', 'BRADESCO', 'CAIXA ECONOMICA FEDERAL', 'BANCO ITAÚ', 'BANCO SANTANDER', 'NUBANK', 'BANCO INTER', 'SICOOB', 'SICREDI', 'C6 BANK', 'BTG PACTUAL', 'MERCADOPAGO', 'PAGSEGURO', 'PICPAY', 'CAIXA INTERNO']),
  },
  centros: {
    titulo: 'Cadastro de centros de custo', rota: 'centros', cols: [['nome', 'Centro de custo'], ['orcamento', 'Orçamento (mensal)', moeda], ['projecao', 'Projeção (mensal)', moeda], ['aplica_despesa', 'Despesas', (v) => (v ? 'Sim' : 'Não')], ['aplica_receita', 'Receitas', (v) => (v ? 'Sim' : 'Não')]],
    spec: () => [['nome', 'Descrição do centro de custo', 'text', { req: true, inteiro: true }], ['aplica_despesa', 'Aplicar a despesas', 'check', { padrao: 1 }], ['orcamento', 'Orçamento (mensal)', 'number', { padrao: 0 }],
      ['aplica_receita', 'Aplicar a receitas', 'check', { padrao: 0 }], ['projecao', 'Projeção (mensal)', 'number', { padrao: 0 }]],
  },
  clientes: { titulo: 'Cadastro de clientes', rota: 'pessoas', tipo: 'C' },
  fornecedores: { titulo: 'Cadastro de fornecedores', rota: 'pessoas', tipo: 'F' },
  itensD: { titulo: 'Ítens de despesas', rota: 'itens', tipo: 'D', cols: [['descricao', 'Descrição']], spec: () => [['descricao', 'Descrição', 'text', { req: true, inteiro: true }]] },
  itensR: { titulo: 'Ítens de receitas', rota: 'itens', tipo: 'R', cols: [['descricao', 'Descrição']], spec: () => [['descricao', 'Descrição', 'text', { req: true, inteiro: true }]] },
};
for (const k of ['clientes', 'fornecedores']) {
  Object.assign(CAD[k], {
    cols: [['nome', 'Nome'], ['documento', 'CPF/CNPJ'], ['cidade', 'Cidade'], ['telefone', 'Telefone'], ['email', 'E-mail']],
    spec: (v) => [['pessoa', 'Pessoa', 'radio', { padrao: 'J', opcoes: [['F', 'Física'], ['J', 'Jurídica']] }],
      ['nome', 'Nome / razão social', 'text', { req: true, inteiro: true }], ['documento', 'CPF / CNPJ'], ['documento2', 'RG / Inscrição estadual'],
      ...ENDERECO, ['telefone', 'Telefone(s)'], ['email', 'E-mail', 'email'], ['contato', 'Contato'], ['limite', 'Limite de crédito', 'number', { padrao: 0 }],
      ['banco', 'Banco'], ['agencia', 'Agência'], ['conta_bancaria', 'Conta'],
      ['empresa_id', 'Compartilhamento', 'select', { padrao: v.id ? v.empresa_id ?? '' : st.empresa.id, opcoes: [[st.empresa.id, 'Somente para esta conta controle'], ['', 'Compartilhado com as outras contas']] }],
      ['observacao', 'Observações', 'textarea']],
  });
}

// Modulo que controla cada cadastro (mesma regra do servidor).
const MOD_CAD = { empresas: 'config', contas: 'bancos', centros: 'centros', clientes: 'receitas', fornecedores: 'despesas', itensD: 'despesas', itensR: 'receitas' };

async function cadastro(chave) {
  const c = CAD[chave];
  const edita = perm(MOD_CAD[chave]) >= 2;
  const carregar = async () => (await api(c.rota + (c.tipo ? '?tipo=' + c.tipo : ''))).filter((r) => !c.tipo || r.tipo === c.tipo);
  let lista = await carregar(), sel = null;
  const tabela = () => `<div class="acoes"><button class="btn pri" type="button" data-a="inc" ${edita ? '' : 'hidden'}>Incluir</button>
      <button class="btn" type="button" data-a="alt">${edita ? 'Alterar' : 'Consultar'}</button><button class="btn perigo" type="button" data-a="exc" ${edita ? '' : 'hidden'}>Excluir</button>
      ${edita ? '' : '<span class="leitura">Somente consulta</span>'}
      <input type="search" id="cadBusca" placeholder="Localizar…" style="margin-left:auto"></div>
    <div class="grade" style="max-height:50vh"><table><thead><tr>${c.cols.map(([, r]) => `<th>${r}</th>`).join('')}</tr></thead>
    <tbody>${lista.map((r) => `<tr data-id="${r.id}">${c.cols.map(([k, , f]) => `<td>${esc(f ? f(r[k]) : r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table>
    ${lista.length ? '' : '<div class="vazio">Nenhum registro.</div>'}</div>`;
  const editar = async (v = {}) => {
    if (c.form && edita) { await c.form(v.id ? v : null); return; }
    if (!edita) {
      await dialogo({ titulo: 'Consultar — ' + c.titulo, corpo: campos(c.spec ? c.spec(v) : [], v), aoAbrir: somenteLeitura });
      return;
    }
    await dialogo({
      titulo: (v.id ? 'Alterar — ' : 'Incluir — ') + c.titulo, corpo: campos(c.spec(v), v) + (c.extra || ''),
      botoes: [{ rot: 'Cancela', valor: 'cancel' }, {
        rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
          if (c.tipo) d.tipo = c.tipo;
          await api(c.rota + (v.id ? '/' + v.id : ''), { method: v.id ? 'PUT' : 'POST', body: d });
          toast('Registro gravado.');
        },
      }],
    });
  };
  const abrir = () => dialogo({
    titulo: c.titulo, corpo: tabela(),
    aoAbrir: (f) => {
      const tb = $('tbody', f);
      tb.onclick = (ev) => { const tr = ev.target.closest('tr'); if (!tr) return; sel = Number(tr.dataset.id); $$('tr', tb).forEach((r) => r.classList.toggle('sel', r === tr)); };
      tb.ondblclick = async (ev) => { const tr = ev.target.closest('tr'); if (tr) { await editar(lista.find((r) => r.id === Number(tr.dataset.id))); reabrir(); } };
      $('#cadBusca', f).oninput = (ev) => { const t = ev.target.value.toLowerCase(); $$('tr', tb).forEach((r) => (r.hidden = !r.textContent.toLowerCase().includes(t))); };
      $('.acoes', f).onclick = async (ev) => {
        const a = ev.target.dataset.a; if (!a) return;
        const v = lista.find((r) => r.id === sel);
        if (a !== 'inc' && !v) return toast('Selecione um registro.', true);
        if (a === 'inc') await editar();
        if (a === 'alt') await editar(v);
        if (a === 'exc') {
          if (!confirm('Excluir o registro selecionado?')) return abrir();
          await api(`${c.rota}/${v.id}`, { method: 'DELETE' }).then(() => toast('Registro excluído.')).catch((e) => toast(e.message, true));
        }
        reabrir();
      };
    },
  });
  const reabrir = async () => { lista = await carregar(); sel = null; await carregarAux(); abrir(); render(); };
  await abrir();
}

// ---------- Usuarios e permissoes (FUseBrs / FUseCad) ----------
const MODULOS = [
  ['config', 'Configurações', [[2, 'Acesso completo'], [0, 'Sem acesso']]],
  ['despesas', 'Controle de despesas'], ['receitas', 'Controle de receitas'],
  ['bancos', 'Controle de contas bancárias e movimentações'], ['centros', 'Controle de centros de custo'], ['fluxo', 'Fluxo de caixa'],
];
const NIVEIS = [[2, 'Acesso completo'], [1, 'Somente consulta'], [0, 'Sem acesso']];

async function telaUsuarios() {
  const [lista, empresas] = await Promise.all([api('usuarios'), api('empresas')]);
  let sel = null;
  await dialogo({
    titulo: 'Usuários',
    corpo: `<div class="acoes"><button class="btn pri" type="button" data-a="inc">Incluir</button>
        <button class="btn" type="button" data-a="alt">Alterar</button><button class="btn perigo" type="button" data-a="exc">Excluir</button></div>
      <div class="grade" style="max-height:50vh"><table><thead><tr><th>Usuário</th><th>E-mail</th><th>Categoria</th><th>Status</th><th>Contas controle</th><th>Último acesso</th></tr></thead>
      <tbody>${lista.map((u) => `<tr data-id="${u.id}"><td>${esc(u.nome)}</td><td>${esc(u.email)}</td><td>${u.admin ? 'Administrador' : 'Usuário'}</td>
        <td>${u.ativo ? 'Ativo' : 'Inativo'}</td><td>${u.todas_empresas ? 'Todas' : esc(u.empresas.map((e) => empresas.find((x) => x.id === e)?.nome || '?').join(', ') || 'Nenhuma')}</td>
        <td>${esc(u.ultimo_acesso || '—')}</td></tr>`).join('')}</tbody></table></div>`,
    aoAbrir: (f) => {
      const tb = $('tbody', f);
      tb.onclick = (ev) => { const tr = ev.target.closest('tr'); if (!tr) return; sel = Number(tr.dataset.id); $$('tr', tb).forEach((r) => r.classList.toggle('sel', r === tr)); };
      tb.ondblclick = (ev) => { const tr = ev.target.closest('tr'); if (tr) formUsuario(lista.find((u) => u.id === Number(tr.dataset.id)), empresas); };
      $('.acoes', f).onclick = async (ev) => {
        const a = ev.target.dataset.a; if (!a) return;
        const u = lista.find((x) => x.id === sel);
        if (a !== 'inc' && !u) return toast('Selecione um usuário.', true);
        if (a === 'inc') return formUsuario(null, empresas);
        if (a === 'alt') return formUsuario(u, empresas);
        if (a === 'exc') {
          if (!confirm(`Excluir o usuário ${u.nome}?`)) return;
          await tenta(async () => { await api('usuarios/' + u.id, { method: 'DELETE' }); toast('Usuário excluído.'); telaUsuarios(); });
        }
      };
    },
  });
}

async function formUsuario(u, empresas) {
  const novo = !u;
  u ||= { ativo: true, admin: false, todas_empresas: true, empresas: [], perms: { config: 0, despesas: 2, receitas: 2, bancos: 2, centros: 2, fluxo: 2 } };
  const souAdmin = st.usuario.admin;
  const radios = (nome, opcoes, val) => opcoes.map(([v, t]) => `<label><input type="radio" name="${nome}" value="${v}" ${Number(val) === v ? 'checked' : ''}> ${t}</label>`).join('');
  const corpo = campos([
    ['nome', 'Usuário (nome)', 'text', { req: true }], ['email', 'E-mail (login)', 'email', { req: true, attrs: 'autocomplete="off"' }],
    ['senha', novo ? 'Senha de acesso (mín. 6)' : 'Nova senha (deixe em branco para manter)', 'password', { req: novo, attrs: 'minlength="6" autocomplete="new-password"' }],
    ['confirma', 'Confirmação', 'password', { req: novo, attrs: 'autocomplete="new-password"' }],
    ...(souAdmin ? [['admin', 'Categoria', 'radio', { padrao: u.admin ? 1 : 0, opcoes: [[0, 'Usuário'], [1, 'Administrador']] }]] : []),
    ['ativo', 'Status', 'radio', { padrao: u.ativo ? 1 : 0, opcoes: [[1, 'Ativo'], [0, 'Inativo']] }],
  ], { nome: u.nome, email: u.email }) +
    `<h4>Acesso aos módulos</h4><p class="legenda" id="avisoAdmin" hidden>Administradores têm acesso completo a todos os módulos e contas controle.</p>
     <div class="perm-grade" id="perms">${MODULOS.map(([m, rot, op]) => `<fieldset><legend>${rot}</legend>${radios('perm_' + m, op || NIVEIS, u.perms[m])}</fieldset>`).join('')}</div>
     <h4>Acesso a contas controle</h4>
     <div id="contasAcesso"><span class="radio">${radios('todas_empresas', [[1, 'Todas as contas'], [0, 'Contas controle específicas:']], u.todas_empresas ? 1 : 0)}</span>
     <div class="empresas-lista">${empresas.map((e) => `<label><input type="checkbox" name="emp_${e.id}" ${u.empresas.includes(e.id) ? 'checked' : ''}> ${esc(e.nome)}</label>`).join('')}</div></div>`;
  await dialogo({
    titulo: novo ? 'Novo usuário' : 'Alterar usuário — ' + u.nome, corpo,
    botoes: [{ rot: 'Cancela', valor: 'cancel' }, { rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
      if (d.senha !== d.confirma) throw new Error('A confirmação não confere com a senha.');
      const body = { nome: d.nome, email: d.email, ativo: Number(d.ativo), todas_empresas: Number(d.todas_empresas) };
      if (souAdmin) body.admin = Number(d.admin);
      if (d.senha) body.senha = d.senha;
      for (const [m] of MODULOS) body['perm_' + m] = Number(d['perm_' + m]);
      body.empresas = empresas.filter((e) => d['emp_' + e.id]).map((e) => e.id);
      if (!body.todas_empresas && !body.empresas.length && !body.admin) throw new Error('Marque ao menos uma conta controle ou escolha "Todas as contas".');
      await api('usuarios' + (novo ? '' : '/' + u.id), { method: novo ? 'POST' : 'PUT', body });
      toast('Usuário gravado.');
    } }],
    aoAbrir: (f) => {
      const sync = () => {
        const adm = souAdmin && f.admin.value === '1';
        $('#avisoAdmin', f).hidden = !adm;
        $$('#perms input, #contasAcesso input', f).forEach((el) => (el.disabled = adm));
        if (!adm) $$('.empresas-lista input', f).forEach((el) => (el.disabled = f.todas_empresas.value === '1'));
      };
      $$('input[name=admin], input[name=todas_empresas]', f).forEach((r) => (r.onchange = sync));
      sync();
    },
  });
  telaUsuarios();
  // Se o usuario alterou a si mesmo, recarrega nome e permissoes.
  if (u.id === st.usuario.id) { st.usuario = (await api('auth/estado')).usuario; aplicarUsuario(); render(); }
}

// ---------- Movimentacoes bancarias ----------
async function movBancarias() {
  st.aba = 'mov';
  $$('#abas button').forEach((b) => b.classList.remove('ativa'));
  $('.filtros').style.display = 'none';
  const lista = await api('movbancarias');
  const nomeConta = (id) => st.contas.find((c) => c.id === id)?.descricao || '';
  const tipos = { D: 'Depósito', R: 'Retirada', T: 'Transferência' };
  $('#conteudo').innerHTML = `<h2 style="margin-top:0">Controle de movimentações bancárias</h2>
    <div class="acoes">${perm('bancos') >= 2 ? '<button class="btn pri" data-a="inc">Incluir</button><button class="btn" data-a="alt">Alterar</button><button class="btn perigo" data-a="exc">Excluir</button>' : '<span class="leitura">Somente consulta</span>'}</div>
    <div class="grade"><table><thead><tr><th>Data</th><th>Movimento</th><th>Conta</th><th>Conta destino</th><th class="num">Valor</th><th>Situação</th><th>Observação</th></tr></thead>
    <tbody>${lista.map((m) => `<tr data-id="${m.id}"><td>${dataBR(m.data)}</td><td>${tipos[m.tipo]}</td><td>${esc(nomeConta(m.origem_id))}</td>
      <td>${esc(nomeConta(m.destino_id))}</td><td class="num">${moeda(m.valor)}</td><td>${m.situacao === 'V' ? 'Realizado' : 'Previsto'}</td><td>${esc(m.observacao)}</td></tr>`).join('')}</tbody></table>
    ${lista.length ? '' : '<div class="vazio">Nenhuma movimentação. Use para depósitos, retiradas e transferências entre contas.</div>'}</div>`;
  let sel = null;
  const tb = $('#conteudo tbody');
  tb.onclick = (ev) => { const tr = ev.target.closest('tr'); if (!tr) return; sel = Number(tr.dataset.id); $$('tr', tb).forEach((r) => r.classList.toggle('sel', r === tr)); };
  const form = async (v = {}) => {
    const contas = st.contas.filter((c) => c.ativa).map((c) => [c.id, c.descricao]);
    await dialogo({
      titulo: v.id ? 'Alterar movimentação' : 'Nova movimentação bancária', largura: '640px',
      corpo: campos([['tipo', 'Movimento', 'radio', { padrao: 'T', inteiro: true, opcoes: [['D', 'Depósito'], ['R', 'Retirada'], ['T', 'Transferência']] }],
        ['data', 'Data', 'date', { req: true, padrao: hoje() }], ['valor', 'Valor', 'number', { req: true }],
        ['origem_id', 'Conta', 'select', { opcoes: contas }], ['destino_id', 'Conta destino', 'select', { opcoes: [['', ''], ...contas] }],
        ['situacao', 'Situação', 'radio', { padrao: 'V', opcoes: [['V', 'Realizado'], ['P', 'Previsto']] }],
        ['observacao', 'Observações (cheque)', 'text', { inteiro: true }]], v),
      botoes: [{ rot: 'Cancela', valor: 'cancel' }, { rot: 'Confirma', valor: 'ok', pri: true, acao: async (d) => {
        if (d.tipo !== 'T') d.destino_id = '';
        await api('movbancarias' + (v.id ? '/' + v.id : ''), { method: v.id ? 'PUT' : 'POST', body: d }); toast('Movimentação gravada.');
      } }],
      aoAbrir: (f) => { const s = () => (f.destino_id.disabled = f.tipo.value !== 'T'); $$('input[name=tipo]', f).forEach((r) => (r.onchange = s)); s(); },
    });
    movBancarias();
  };
  $('#conteudo .acoes').onclick = async (ev) => {
    const a = ev.target.dataset.a; const v = lista.find((m) => m.id === sel);
    if (a === 'inc') form();
    else if (!v) toast('Selecione uma movimentação.', true);
    else if (a === 'alt') form(v);
    else if (a === 'exc' && confirm('Excluir a movimentação selecionada?')) { await api('movbancarias/' + v.id, { method: 'DELETE' }); movBancarias(); }
  };
}

// ---------- Importacao OFX ----------
async function importarOfx() {
  st.aba = 'ofx';
  $$('#abas button').forEach((b) => b.classList.remove('ativa'));
  $('.filtros').style.display = 'none';
  $('#conteudo').innerHTML = `<h2 style="margin-top:0">Extrato bancário — importar OFX</h2>
    <div class="acoes"><label>1. Conta <select id="oConta">${st.contas.filter((c) => c.ativa).map((c) => `<option value="${c.id}">${esc(c.descricao)}</option>`).join('')}</select></label>
      <label>2. Arquivo OFX <input type="file" id="oArq" accept=".ofx,.OFX,text/plain"></label>
      <button class="btn pri" id="oAnalisar">3. Analisar</button></div><div id="oRes"></div>`;
  let linhas = [];
  $('#oAnalisar').onclick = () => tenta(async () => {
    const f = $('#oArq').files[0]; if (!f) throw new Error('Selecione o arquivo OFX.');
    const buf = await f.arrayBuffer();
    let texto = new TextDecoder('utf-8').decode(buf);
    if (texto.includes('�')) texto = new TextDecoder('windows-1252').decode(buf);
    linhas = await api('ofx/analisar', { method: 'POST', body: { conta_id: $('#oConta').value, texto } });
    const st2 = { novo: 'Novo', em_aberto: 'Em aberto no MCC', conciliado: 'Já lançado', importado: 'Já importado' };
    const opc = (l) => [['incluir', 'Incluir como novo'], ...(l.lancamento ? [[l.status === 'conciliado' ? 'conciliar' : 'baixar', l.status === 'conciliado' ? 'Conciliar' : `Baixar: ${l.lancamento.descricao}`]] : []), ['ignorar', 'Ignorar']];
    $('#oRes').innerHTML = linhas.length ? `<div class="grade"><table><thead><tr><th>Data</th><th>Histórico</th><th>Doc.</th><th class="num">Valor</th><th>Status</th><th>4. Ação</th></tr></thead>
      <tbody>${linhas.map((l, i) => `<tr><td>${dataBR(l.data)}</td><td>${esc(l.descricao)}</td><td>${esc(l.documento)}</td>
        <td class="num ${l.tipo === 'D' ? 'neg' : 'pos'}">${l.tipo === 'D' ? '-' : ''}${moeda(l.valor)}</td><td>${st2[l.status]}</td>
        <td><select data-i="${i}">${opc(l).map(([k, t]) => `<option value="${k}" ${k === l.acao ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table></div>
      <div class="acoes" style="margin-top:10px"><button class="btn pri" id="oAplicar">Aplicar</button></div>` : '<div class="vazio">Nenhuma transação encontrada no arquivo.</div>';
    $$('#oRes select').forEach((s) => (s.onchange = () => (linhas[s.dataset.i].acao = s.value)));
    $('#oAplicar')?.addEventListener('click', () => tenta(async () => {
      const r = await api('ofx/aplicar', { method: 'POST', body: { conta_id: $('#oConta').value, linhas } });
      toast(`${r.incluidos} incluído(s), ${r.baixados} baixado(s), ${r.conciliados} conciliado(s).`);
      $('#oRes').innerHTML = '';
      await carregarAux();
    }));
  });
}

// ---------- Relatorios ----------
const MENU_REL = [
  ['Despesas', [['lancamentos', 'Relatório de despesas', { tipo: 'D' }], ['totais_item', 'Relatório de despesas totais', { tipo: 'D' }]]],
  ['Receitas', [['lancamentos', 'Relatório de receitas', { tipo: 'R' }], ['totais_item', 'Relatório de receitas totais', { tipo: 'R' }]]],
  ['Contas a pagar', [['lancamentos', 'Contas em aberto', { tipo: 'D', situacao: 'P', campo_data: 'vencimento' }], ['lancamentos', 'Contas pagas', { tipo: 'D', situacao: 'V', campo_data: 'vencimento' }],
    ['por_pessoa', 'Contas a pagar por fornecedor', { tipo: 'D', situacao: 'P' }], ['pontualidade', 'Análise de pontualidade de pagamentos', { tipo: 'D' }]]],
  ['Contas a receber', [['lancamentos', 'Contas em aberto', { tipo: 'R', situacao: 'P', campo_data: 'vencimento' }], ['lancamentos', 'Contas recebidas', { tipo: 'R', situacao: 'V', campo_data: 'vencimento' }],
    ['por_pessoa', 'Contas a receber por cliente', { tipo: 'R', situacao: 'P' }], ['pontualidade', 'Análise de pontualidade de recebimentos', { tipo: 'R' }]]],
  ['Centros de custo', [['centros', 'Orçamento por centro de custo', { tipo: 'D' }], ['centros', 'Projeção por centro de lucro', { tipo: 'R' }],
    ['g:composicao', 'Gráfico de despesas totais por centro', { tipo: 'D', agrupar: 'centro' }], ['g:composicao', 'Gráfico de receitas totais por centro', { tipo: 'R', agrupar: 'centro' }]]],
  ['Gráficos gerenciais', [['g:desp_rec', 'Gráfico despesas x receitas', {}],
    ['g:composicao', 'Gráfico de despesas', { tipo: 'D', agrupar: 'item' }], ['g:composicao', 'Gráfico de receitas', { tipo: 'R', agrupar: 'item' }],
    ['g:evolucao', 'Evolução de despesas por ítem', { tipo: 'D', agrupar: 'item' }], ['g:evolucao', 'Evolução de despesas por fornecedor', { tipo: 'D', agrupar: 'pessoa' }],
    ['g:evolucao', 'Evolução de receitas por ítem', { tipo: 'R', agrupar: 'item' }], ['g:evolucao', 'Evolução de receitas por cliente', { tipo: 'R', agrupar: 'pessoa' }]]],
  ['Analítico', [['analitico', 'Relatório analítico', {}]]],
  ['Fluxo de caixa', [['fluxo_dia', 'Fluxo de caixa por dia (realizado)', {}], ['fluxo_dia', 'Previsão de caixa por dia', { previsao: '1' }]]],
  ['Bancos', [['extrato', 'Extrato de conta bancária', {}], ['saldos', 'Relatório de saldo de contas', {}]]],
  ['Demonstrativos', [['dre', 'Demonstrativo de resultados', {}],
    ['demonstrativo', 'Anual de despesas por ítem', { tipo: 'D', agrupar: 'item' }], ['demonstrativo', 'Anual de despesas por fornecedor', { tipo: 'D', agrupar: 'pessoa' }],
    ['demonstrativo', 'Anual de despesas por centro de custo', { tipo: 'D', agrupar: 'centro' }], ['demonstrativo', 'Anual de despesas por conta', { tipo: 'D', agrupar: 'conta' }],
    ['demonstrativo', 'Anual de receitas por ítem', { tipo: 'R', agrupar: 'item' }], ['demonstrativo', 'Anual de receitas por cliente', { tipo: 'R', agrupar: 'pessoa' }],
    ['demonstrativo', 'Anual de receitas por centro de lucro', { tipo: 'R', agrupar: 'centro' }], ['demonstrativo', 'Anual de receitas por conta', { tipo: 'R', agrupar: 'conta' }]]],
];

// Mesmo criterio do servidor (MODULO_RELATORIO): modulo exigido para ver cada relatorio.
function podeRelatorio(nome, fixos) {
  if (nome === 'analitico') return perm('despesas') > 0 || perm('receitas') > 0;
  if (nome === 'g:desp_rec') return perm('despesas') > 0 && perm('receitas') > 0;
  if (nome === 'g:composicao' && fixos.agrupar === 'centro') return perm('centros') > 0 && permTipo(fixos.tipo) > 0;
  if (['fluxo_dia', 'dre'].includes(nome)) return perm('fluxo') > 0;
  if (['extrato', 'saldos'].includes(nome)) return perm('bancos') > 0;
  if (nome === 'centros') return perm('centros') > 0 && permTipo(fixos.tipo) > 0;
  return permTipo(fixos.tipo) > 0;
}

function montarMenuRel() {
  $('#menuRel').innerHTML = MENU_REL.map(([g, itens], gi) => {
    const vis = itens.map((it, ii) => [it, ii]).filter(([[nome, , fixos]]) => podeRelatorio(nome, fixos));
    return vis.length ? `<div class="grupo">${g}</div>` + vis.map(([[, rot], ii]) => `<a data-acao="rel:${gi}:${ii}">${rot}</a>`).join('') : '';
  }).join('');
  $('#menuRel').closest('.menu').hidden = !$('#menuRel a');
}

async function abrirRelatorio(gi, ii) {
  const [nome, rotulo, fixos] = MENU_REL[gi][1][ii];
  if (nome.startsWith('g:')) return abrirGrafico(nome.slice(2), rotulo, fixos);
  if (nome === 'analitico') return telaAnalitico();
  const params = st.relatorios[nome]?.params || [];
  const spec = [];
  if (params.includes('periodo')) spec.push(['de', 'De', 'date', { padrao: `${$('#fAno').value}-01-01` }], ['ate', 'Até', 'date', { padrao: hoje() }]);
  if (params.includes('ano')) spec.push(['ano', 'Ano', 'number', { padrao: $('#fAno').value, attrs: 'step="1"' }]);
  if (params.includes('data')) spec.push(['data', 'Posição em', 'date', { padrao: hoje() }]);
  if (params.includes('conta')) spec.push(['conta_id', 'Conta', 'select', { opcoes: [...(nome === 'extrato' ? [] : [['', 'Todas']]), ...st.contas.map((c) => [c.id, c.descricao])] }]);
  if (params.includes('situacao') && !fixos.situacao) spec.push(['situacao', 'Situação', 'select', { opcoes: [['', 'Pagas ou em aberto'], ['V', 'Pagas'], ['P', 'Em aberto']] }]);
  let q = { ...fixos };
  if (spec.length) {
    const r = await dialogo({ titulo: rotulo, largura: '560px', corpo: campos(spec), botoes: [{ rot: 'Cancela', valor: 'cancel' }, { rot: 'Gerar', valor: 'ok', pri: true, acao: (d) => d }] });
    if (!r) return; q = { ...r, ...fixos };
  }
  const rel = await tenta(() => api(`relatorios/${nome}?` + qs(q)));
  rel.titulo = rotulo.startsWith('Contas') && fixos.tipo ? `${fixos.tipo === 'D' ? 'Contas a pagar' : 'Contas a receber'} — ${rotulo.toLowerCase()}` : rel.titulo;
  mostrarRelatorio(rel);
}

function fmtCel(v, fmt) {
  if (v == null || v === '') return '';
  if (fmt === 'moeda') return moeda(v);
  if (fmt === 'data') return dataBR(v);
  if (fmt === 'num') return Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 });
  return esc(v);
}

function mostrarRelatorio(rel) {
  dica(null);
  st.aba = 'rel';
  $$('#abas button').forEach((b) => b.classList.remove('ativa'));
  $('.filtros').style.display = 'none';
  const num = (c) => ['moeda', 'int', 'num'].includes(c.fmt);
  $('#conteudo').innerHTML = `<div class="rel-cab"><div><h2>${esc(rel.titulo)}</h2><p>${esc(st.empresa.nome)} — ${esc(rel.subtitulo)}</p></div>
      <div class="acoes noprint"><button class="btn" id="rCsv">Exportar CSV</button><button class="btn pri" onclick="print()">Imprimir / PDF</button></div></div>
    <div class="grade"><table><thead><tr>${rel.colunas.map((c) => `<th class="${num(c) ? 'num' : ''}">${esc(c.rotulo)}</th>`).join('')}</tr></thead>
    <tbody>${rel.linhas.map((l) => l._tipo === 'grupo'
      ? `<tr class="linha-grupo nivel-${l._nivel}"><td colspan="${rel.colunas.length}">${esc(l.data_mov)}</td></tr>`
      : `<tr class="${l._tipo === 'subtotal' ? 'linha-subtotal' : ''}">${rel.colunas.map((c) => `<td class="${num(c) ? 'num' : ''} ${c.fmt === 'moeda' && l[c.campo] < 0 ? 'neg' : ''}">${fmtCel(l[c.campo], c.fmt)}</td>`).join('')}</tr>`).join('')}</tbody>
    ${Object.keys(rel.totais).length ? `<tfoot><tr>${rel.colunas.map((c, i) => `<td class="${num(c) ? 'num' : ''}">${c.campo in rel.totais ? fmtCel(rel.totais[c.campo], c.fmt === 'int' ? 'num' : c.fmt) : i === 0 ? 'Total' : ''}</td>`).join('')}</tr></tfoot>` : ''}
    </table>${rel.linhas.length ? '' : '<div class="vazio">Nenhum registro para os parâmetros informados.</div>'}</div>`;
  $('#rCsv').onclick = () => baixarCsv(rel.titulo, rel.colunas.map((c) => c.rotulo),
    rel.linhas.map((l) => (l._tipo === 'grupo' ? [l.data_mov] : rel.colunas.map((c) => l[c.campo]))));
  if (rel.voltar) $('#conteudo .rel-cab .acoes').insertAdjacentHTML('afterbegin', '<button class="btn" id="rVoltar">Alterar parâmetros</button>'), ($('#rVoltar').onclick = rel.voltar);
}

// ---------- Graficos gerenciais (FChart) ----------
async function abrirGrafico(nome, rotulo, fixos) {
  const ano = $('#fAno').value;
  const spec = [['de', 'De', 'date', { padrao: `${ano}-01-01`, req: true }], ['ate', 'Até', 'date', { padrao: `${ano}-12-31`, req: true }],
    ['campo_data', 'Considerar a data de', 'select', { opcoes: [['data_mov', 'Movimento (competência)'], ['vencimento', 'Vencimento/pagamento (caixa)']] }],
    ['situacao', 'Situação', 'select', { opcoes: [['', 'Pagas e em aberto'], ['V', 'Somente pagas'], ['P', 'Somente em aberto']] }]];
  let extra = '';
  if (nome === 'evolucao') {
    const opcoes = await api('graficos/opcoes?' + qs({ tipo: fixos.tipo, agrupar: fixos.agrupar }));
    if (!opcoes.length) return toast('Ainda não há lançamentos para comparar.', true);
    const rot = fixos.agrupar === 'pessoa' ? (fixos.tipo === 'D' ? 'Fornecedor' : 'Cliente') : 'Ítem';
    spec.unshift(['valor', rot, 'text', { req: true, inteiro: true, lista: 'dlGraf', attrs: 'autocomplete="off"' }]);
    extra = datalist('dlGraf', opcoes);
  }
  const q = await dialogo({ titulo: rotulo, largura: '560px', corpo: campos(spec) + extra,
    botoes: [{ rot: 'Cancela', valor: 'cancel' }, { rot: 'Gerar', valor: 'ok', pri: true, acao: (d) => d }] });
  if (!q) return;
  const g = await tenta(() => api(`graficos/${nome}?` + qs({ ...q, ...fixos })));
  mostrarGrafico(g, fixos, () => abrirGrafico(nome, rotulo, fixos));
}

function mostrarGrafico(g, fixos, voltar) {
  dica(null);
  st.aba = 'rel';
  $$('#abas button').forEach((b) => b.classList.remove('ativa'));
  $('.filtros').style.display = 'none';
  const slot = SLOT[fixos.tipo] || SLOT.D;
  // tabela de dados sempre disponivel (acessibilidade e exportacao)
  let cab, linhas;
  if (g.forma === 'ranking') {
    cab = ['Descrição', 'Valor', '%'];
    linhas = g.pontos.map((p) => [p.rotulo, p.valor, p.perc]);
  } else {
    cab = ['Período', ...g.series, ...(g.linha ? [g.linha] : [])];
    linhas = g.pontos.map((p) => [p.rotulo, ...p.valores, ...(g.linha ? [p.margem] : [])]);
  }
  const fmt = (v, i) => (i === 0 ? esc(v) : cab[i] === '%' ? `${Number(v).toLocaleString('pt-BR')}%` : moeda(v));
  const totalTxt = g.forma === 'ranking' ? `Total: ${moeda(g.total)}` : g.media != null ? `Média mensal: ${moeda(g.media)}` : '';
  $('#conteudo').innerHTML = `<div class="rel-cab"><div><h2>${esc(g.titulo)}</h2><p>${esc(st.empresa.nome)} — ${esc(g.subtitulo)}${totalTxt ? ' · ' + totalTxt : ''}</p></div>
      <div class="acoes noprint"><button class="btn" id="gVoltar">Alterar parâmetros</button><button class="btn" id="gCsv">Exportar CSV</button>
        <button class="btn pri" onclick="print()">Imprimir / PDF</button></div></div>
    <div id="gArea"></div>
    <details class="tabela-dados" open><summary>Tabela de dados</summary><div class="grade"><table>
      <thead><tr>${cab.map((c, i) => `<th class="${i ? 'num' : ''}">${esc(c)}</th>`).join('')}</tr></thead>
      <tbody>${linhas.map((l) => `<tr>${l.map((v, i) => `<td class="${i ? 'num' : ''}">${fmt(v, i)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
  if (g.forma === 'ranking') desenharRanking($('#gArea'), { pontos: g.pontos, slot });
  else {
    const series = g.linha ? [{ nome: 'Receitas', slot: SLOT.R }, { nome: 'Despesas', slot: SLOT.D }] : [{ nome: g.series[0], slot }];
    desenharColunas($('#gArea'), { titulo: g.titulo, series, media: g.media,
      pontos: g.pontos.map((p) => ({ ...p, linha: p.margem })), linha: g.linha ? { nome: g.linha, slot: SLOT.M } : null });
  }
  $('#gVoltar').onclick = voltar;
  $('#gCsv').onclick = () => baixarCsv(g.titulo, cab, linhas);
}

// ---------- Relatorio analitico (FAnalise) ----------
const OPC_AGRUPAR = [['', '(nenhum)'], ['item', 'Descrição'], ['pessoa', 'Cliente/fornecedor'], ['conta', 'Conta'], ['centro', 'Centro de custo'],
  ['mes', 'Mês'], ['situacao', 'Situação'], ['tipo', 'Tipo (despesa/receita)']];

async function telaAnalitico() {
  const ano = $('#fAno').value;
  const tipos = [['D', 'Despesas'], ['R', 'Receitas'], ['T', 'Todos']].filter(([t]) => (t === 'T' ? perm('despesas') && perm('receitas') : permTipo(t)));
  const ult = st.ultAnalitico || { tipo: tipos[0][0], situacao: '', campo_data: 'data_mov', de: `${ano}-01-01`, ate: `${ano}-12-31`,
    modo: 'descritivo', ordem: 'data', titulo: 'Relatório de Movimentos' };
  const vis = (t) => tipos.some(([x]) => x === t || x === 'T');
  const itens = st.itens.filter((i) => vis(i.tipo)).map((i) => i.descricao);
  const pessoas = st.pessoas.map((p) => p.nome);
  const corpo = campos([
    ['tipo', 'Analisar', 'radio', { opcoes: tipos }],
    ['situacao', 'Com situação igual a', 'radio', { opcoes: [['V', 'Pago'], ['P', 'Em aberto'], ['', 'Todos']] }],
    ['campo_data', 'Analisar período por', 'select', { opcoes: [['data_mov', 'Data de movimento'], ['vencimento', 'Data de vencimento/pagamento']] }],
    ['de', 'Entre', 'date'], ['ate', 'e', 'date'],
    ['descricao', 'Descrição da despesa ou receita (contém)', 'text', { lista: 'dlAnaItens', attrs: 'placeholder="INDIFERENTE"' }],
    ['pessoa', 'Nome do cliente ou fornecedor (contém)', 'text', { lista: 'dlAnaPes', attrs: 'placeholder="INDIFERENTE"' }],
    ['conta_id', 'Da conta', 'select', { opcoes: [['', 'INDIFERENTE'], ...st.contas.map((c) => [c.id, c.descricao])] }],
    ...(Number(st.empresa.usa_centro_custo) ? [['centro_id', 'Centro de custo', 'select', { opcoes: [['', 'TODOS'], ...st.centros.map((c) => [c.id, c.nome])] }]] : []),
    ['agrupar1', 'Agrupar por', 'select', { opcoes: OPC_AGRUPAR }], ['agrupar2', 'Depois por', 'select', { opcoes: OPC_AGRUPAR }],
    ['modo', 'Tipo de relatório', 'radio', { opcoes: [['descritivo', 'Descritivo'], ['totalizado', 'Totalizado']] }],
    ['ordem', 'Ordenar por', 'select', { opcoes: [['data', 'Data de movimento'], ['vencimento', 'Data de vencimento/pagamento'], ['pessoa', 'Nome do cliente ou fornecedor'],
      ['descricao', 'Descrição da despesa/receita'], ['observacao', 'Observação'], ['documento', 'Documento'], ['valor', 'Valor']] }],
    ['decrescente', 'Decrescente', 'check'],
    ['titulo', 'Título do relatório', 'text', { inteiro: true }],
  ], ult) + datalist('dlAnaItens', [...new Set(itens)]) + datalist('dlAnaPes', [...new Set(pessoas)]);
  const q = await dialogo({ titulo: 'Relatório analítico', corpo,
    botoes: [{ rot: 'Fechar', valor: 'cancel' }, { rot: 'Submeter', valor: 'ok', pri: true, acao: (d) => {
      if (d.modo === 'totalizado' && !d.agrupar1 && !d.agrupar2) throw new Error('Escolha ao menos um agrupamento para o relatório totalizado.');
      return d;
    } }],
    aoAbrir: (f) => {
      const s = () => { const tot = f.modo.value === 'totalizado'; f.ordem.disabled = tot; f.decrescente.disabled = tot; };
      $$('input[name=modo]', f).forEach((r) => (r.onchange = s)); s();
    },
  });
  if (!q) return;
  st.ultAnalitico = q;
  const rel = await tenta(() => api('relatorios/analitico?' + qs({ ...q, decrescente: q.decrescente ? '1' : '' })));
  rel.voltar = telaAnalitico;
  mostrarRelatorio(rel);
}

function baixarCsv(nome, cab, linhas) {
  const cel = (v) => { const s = typeof v === 'number' ? String(v).replace('.', ',') : String(v ?? ''); return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const csv = '﻿' + [cab, ...linhas].map((l) => l.map(cel).join(';')).join('\r\n');
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })), download: nome.replace(/[^\w\- ]+/g, '').trim() + '.csv' });
  a.click(); URL.revokeObjectURL(a.href);
}

// ---------- Outras ferramentas ----------
async function lembretes() {
  const ls = await api('lembretes?dias=7');
  await dialogo({
    titulo: 'Lembrete de contas (vencidas e próximos 7 dias)',
    corpo: ls.length ? `<div class="grade"><table><thead><tr><th>Tipo</th><th>Vencimento</th><th>Descrição</th><th>Pessoa</th><th class="num">Valor</th><th>Status</th></tr></thead>
      <tbody>${ls.map((l) => `<tr><td>${l.tipo === 'D' ? 'Pagar' : 'Receber'}</td><td>${dataBR(l.vencimento)}</td><td>${esc(l.descricao)}</td><td>${esc(l.pessoa)}</td>
      <td class="num">${moeda(l.valor)}</td><td><span class="tag ${l.status === 'Vencida' ? 'Vencido' : 'A-pagar'}">${l.status}</span></td></tr>`).join('')}</tbody></table></div>` : '<div class="vazio">Nenhuma conta vencida ou a vencer nos próximos 7 dias.</div>',
  });
}

async function excluidos() {
  const ls = await api('excluidos');
  await dialogo({
    titulo: 'Registros excluídos',
    corpo: ls.length ? `<div class="grade"><table><thead><tr><th>Excluído em</th><th>Tipo</th><th>Data</th><th>Descrição</th><th>Pessoa</th><th class="num">Valor</th><th></th></tr></thead>
      <tbody>${ls.map((l) => `<tr><td>${esc(l.excluido_em)}</td><td>${l.tipo === 'D' ? 'Despesa' : 'Receita'}</td><td>${dataBR(l.data_mov)}</td><td>${esc(l.descricao)}</td><td>${esc(l.pessoa)}</td>
      <td class="num">${moeda(l.valor)}</td><td><button type="button" class="btn" data-rest="${l.id}">Restaurar</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="vazio">Nenhum registro excluído.</div>',
    aoAbrir: (f) => $$('[data-rest]', f).forEach((b) => (b.onclick = async () => {
      await api(`lancamentos/${b.dataset.rest}/restaurar`, { method: 'POST' }); b.closest('tr').remove(); toast('Lançamento restaurado.'); render();
    })),
  });
}

async function transferirEmpresa() {
  const ids = [...st.sel];
  if (!ids.length || !['D', 'R'].includes(st.aba)) return toast('Selecione os lançamentos na aba Despesas ou Receitas.', true);
  const outras = (await api('empresas')).filter((e) => e.id !== st.empresa.id);
  if (!outras.length) return toast('Cadastre outra conta controle primeiro.', true);
  await dialogo({
    titulo: 'Transferir lançamento para outra conta', largura: '520px',
    corpo: `<p>${ids.length} lançamento(s) selecionado(s) serão movidos.</p>` + campos([['empresa_destino', 'Conta controle de destino', 'select', { opcoes: outras.map((e) => [e.id, e.nome]) }]]),
    botoes: [{ rot: 'Cancela', valor: 'cancel' }, { rot: 'Transferir', valor: 'ok', pri: true, acao: async (d) => {
      const r = await api('transferir-empresa', { method: 'POST', body: { ...d, ids } }); toast(`${r.transferidos} lançamento(s) transferido(s).`);
    } }],
  });
  st.sel.clear(); render();
}

function exportar() {
  if (!['D', 'R'].includes(st.aba)) return toast('Abra a aba Despesas ou Receitas para exportar.', true);
  baixarCsv(st.aba === 'D' ? 'Despesas' : 'Receitas', ['Data', 'Documento', 'Descrição', 'Pessoa', 'Valor', 'Vencimento', 'Pagamento', 'Situação', 'Conta', 'Centro', 'Observação'],
    st.linhas.map((l) => [dataBR(l.data_mov), l.documento, l.descricao, l.pessoa, l.valor, dataBR(l.vencimento), dataBR(l.data_pagamento), l.situacao_desc, l.conta, l.centro, l.observacao]));
}

// ---------- Eventos globais ----------
document.addEventListener('click', (ev) => {
  const a = ev.target.closest('[data-acao]')?.dataset.acao; if (!a) return;
  document.activeElement?.blur();
  if (a.startsWith('cad:')) return cadastro(a.slice(4));
  if (a.startsWith('rel:')) { const [, g, i] = a.split(':'); return abrirRelatorio(Number(g), Number(i)); }
  ({
    'trocar-empresa': () => escolherEmpresa(true), lembretes, excluidos, exportar, 'baixa-multipla': () => baixaMultipla(),
    parcelarD: () => formParcelamento('D'), parcelarR: () => formParcelamento('R'), 'transferir-empresa': transferirEmpresa,
    movbancarias: movBancarias, ofx: importarOfx, senha: alterarSenha, usuarios: telaUsuarios, protecao: telaProtecao, sair,
  })[a]?.();
});
$('#abas').onclick = (ev) => { const b = ev.target.closest('[data-aba]'); if (b) { st.aba = b.dataset.aba; st.sel.clear(); render(); } };
document.addEventListener('keydown', (ev) => {
  if ($('#dlg').open || !['D', 'R'].includes(st.aba) || ev.target.matches('input, select, textarea')) return;
  if (ev.key === 'Insert' && permTipo(st.aba) >= 2) formLancamento(st.aba);
  if (ev.key === 'F5') { ev.preventDefault(); render(); }
});

(async function init() {
  montarFiltros();
  const estado = await api('auth/estado');
  if (!estado.configurado) await telaPrimeiroAcesso();
  else if (!estado.usuario) await telaLogin();
  else { st.usuario = estado.usuario; aplicarUsuario(); }
  await escolherEmpresa();
  st.relatorios = await api('relatorios').catch(() => ({}));
})();
