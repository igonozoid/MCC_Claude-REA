# MCC — clone web

Reimplementação do **MCC** (controle financeiro, Delphi/Windows) que roda nativamente no
Linux, sem Wine. Foi construído a partir da análise do `mcc.exe` com o REA
(ver `../analise/MCC-funcionalidades.md`), sem copiar código do original.

## Rodar

```bash
cd mcc-clone
npm start
```

Abra http://localhost:5180. Os dados ficam em `mcc-clone/dados/mcc.db` (SQLite); para usar
outro arquivo, defina `MCC_DB=/caminho/arquivo.db`, e para outra porta, `PORT=...`.
Requer Node.js 22.13+ (instalado via nvm em `~/.nvm`). Não há dependências npm.

```bash
npm test
```

## O que já existe

| Original (tela) | Clone |
|---|---|
| FPrin: abas Despesas/Receitas, filtros (situação, conta, campo de data, ano, mês/tri/sem/ano/todo), ordem, busca | ✔ |
| FMovCad: incluir/alterar lançamento, cadastro automático de ítens e pessoas | ✔ |
| FBaixa / FBaixaMult: baixa simples e múltipla, estorno | ✔ |
| FMulCad: parcelamento (diária … anual), FMultDelMov: excluir esta/seguintes/abertas | ✔ |
| Dashboard: regime de caixa, competência e análise linear | ✔ |
| Saldos realizados e previstos por conta | ✔ |
| Cadastros: contas controle, contas bancárias, centros de custo, clientes, fornecedores, ítens | ✔ |
| FTraCad: depósitos, retiradas, transferências (realizado/previsto) | ✔ |
| FConcilia: importação OFX com conciliação (novo / baixar em aberto / já lançado / já importado) | ✔ |
| Relatórios: despesas/receitas, totais por ítem, contas a pagar/receber, por pessoa, pontualidade, fluxo e previsão de caixa por dia, extrato, saldos, demonstrativo anual (ítem/pessoa/centro/conta), orçamento/projeção por centro, DRE — com impressão/PDF e CSV | ✔ |
| FRecibo: recibo com valor por extenso | ✔ |
| Lembrete de contas, registros excluídos (com restauração), transferir para outra conta controle | ✔ |
| FLog / FUseCad: login, usuários, permissões por módulo e acesso por conta controle | ✔ |
| FLok / FLokSen: proteção de dados (bloqueio até uma data, senha de desbloqueio do administrador) | ✔ |
| FChart: gráficos despesas × receitas, composição por ítem/pessoa/centro, evolução mensal por ítem e por pessoa | ✔ |
| FAnalise: relatório analítico descritivo ou totalizado, com filtros e até dois agrupamentos livres | ✔ |

## Gráficos e relatório analítico

Em *Relatórios › Gráficos gerenciais* (e *Centros de custo*): despesas × receitas por mês com a margem,
composição de despesas/receitas (ranking com valor e %, até 12 categorias e "Outros"), e evolução
mensal de um ítem, fornecedor ou cliente com a média do período. Todos têm dica ao passar o mouse,
tabela de dados, CSV e impressão. Cores fixas por entidade (receitas azul, despesas laranja,
margem verde-água), validadas para daltonismo nos temas claro e escuro.

*Relatórios › Analítico › Relatório analítico* reproduz o FAnalise: analisar despesas, receitas ou
todos; situação; período por movimento ou vencimento/pagamento; filtros de descrição, pessoa, conta
e centro; ordenação; título; modo **Descritivo** (cada lançamento, com cabeçalho e subtotal por
grupo) ou **Totalizado** (um total por grupo). Os agrupamentos são livres, em até dois níveis:
descrição, cliente/fornecedor, conta, centro, mês, situação ou tipo.

## Usuários e permissões

No primeiro acesso o sistema pede o **usuário administrador** (acesso completo a tudo).
Em *menu do usuário › Usuários e permissões* cada usuário recebe, como no original:

| Módulo (campo original) | Níveis |
|---|---|
| Configurações (`UsuPo1`): contas controle e usuários | Acesso completo / Sem acesso |
| Controle de despesas (`UsuPo2`): despesas, fornecedores, ítens de despesa | Completo / Somente consulta / Sem acesso |
| Controle de receitas (`UsuPo3`): receitas, clientes, ítens de receita | Completo / Somente consulta / Sem acesso |
| Controle de centros de custo (`UsuPo4`) | Completo / Somente consulta / Sem acesso |
| Contas bancárias e movimentações (`UsuPo5`): contas, transferências, OFX, extrato | Completo / Somente consulta / Sem acesso |
| Fluxo de caixa (`UsuPo6`): dashboard, fluxo/previsão de caixa, DRE | Completo / Somente consulta / Sem acesso |

Além disso: acesso a **todas as contas controle** ou a **contas específicas**, e status ativo/inativo.
As regras valem no servidor (a API recusa com 403), não só na interface. Senhas ficam com
hash scrypt; a sessão é um cookie HttpOnly que expira após 12 h sem uso; 5 senhas erradas
seguidas bloqueiam o e-mail por 1 minuto. Desativar um usuário encerra as sessões dele.

## Proteção de dados

Em *menu do usuário › Proteção de dados* (exige Configurações) define-se, por conta controle,
uma data de bloqueio. Até essa data, como no original:

- lançamentos com **data de movimento** até a data, ou **pagos** com pagamento até a data, não podem
  ser incluídos, alterados, baixados, estornados, excluídos, restaurados nem transferidos;
- também ficam bloqueadas baixas com data de pagamento no período, parcelamentos que começam nele,
  movimentações bancárias datadas nele, importação OFX de linhas do período e mudança de saldo inicial de contas.

Ao tentar, aparece *"Movimentações bloqueadas até dd/mm/aaaa. Deseja inserir a senha de desbloqueio?"*.
A senha de **qualquer administrador ativo** libera somente aquela operação (o servidor responde 423 até
receber a senha; erros contam para o bloqueio por tentativas). O cabeçalho mostra 🔒 com a data.

## Ainda não implementado

- Recuperação de senha por e-mail ("esqueci a senha" do FLog).
- Logomarca nos relatórios, cor dos relatórios, suporte online e licença (específicos do fornecedor original).
- Importação dos dados existentes do MCC: ficam no servidor remoto do fornecedor, não no PC.
