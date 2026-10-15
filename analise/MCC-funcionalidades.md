# MCC — análise por engenharia reversa (REA)

Alvo: `C:\MCC\mcc.exe` (Wine), SHA-256 `3d784b3b6dfbab086bd201de3050c7bbd4787a25642757f9bce13bbaf9c6a6b7`.

## Como foi analisado

1. `rea inspect-artifact` e `rea inspect-pe-resources` → PE32 i386, 407 recursos,
   151 RCDATA (`analise/pe-resources.json`).
2. Os RCDATA começando com `TPF0` são formulários Delphi (VCL + FireDAC).
   `tools/dfm_extract.py` converte os 80 DFMs para texto (`analise/forms/`).
3. `tools/dfm_summary.py` gera `schema.json` (61 tabelas em memória e seus campos)
   e `screens.txt` (textos, menus e colunas de cada tela).

Nenhum código foi copiado: o clone reimplementa o comportamento observado nas telas
e no modelo de dados.

## Arquitetura original

- Cliente desktop Delphi. Os dados ficam num **servidor remoto DataSnap REST**
  (`TDSRestConnection`, porta 5081) e o cliente trabalha com `TFDMemTable`.
- O executável contém **uma credencial embutida** do servidor (em `TCM_MCC`).
  Ela não foi usada nem copiada para o clone. É um problema de segurança do original.
- O clone guarda tudo localmente em SQLite.

## Modelo de dados (nomes originais → clone)

| Original | Significado | Campos principais |
|---|---|---|
| `Con*` | Conta controle (empresa / pessoa física) | Nom, Pes (F/J), Do1/Do2 (CPF/CNPJ), endereço, Tel, Eml, Web |
| `Ban*` | Conta bancária / caixa interno | Des (banco e conta), Sal (saldo inicial), Lim, Act (ativa), compartilhada ou só desta empresa |
| `Cen*` | Centro de custo / lucro | Nom, Des/Rec (aplica a despesas/receitas), Orc (orçamento mensal), Pro (projeção mensal) |
| `Pes*` | Cliente / fornecedor | Tip (C/F), Pes (F/J), documentos, endereço, contato, dados bancários, Obs |
| `Ite*` | Itens (descrições) de despesa e de receita | Des, Tip |
| `Mov*` | Lançamento (despesa `D` / receita `R`) | Dat (movimento), Doc, Des (item), Pes (pessoa), Val, Sit (`V` pago / `P` a pagar), Ven (venc./pgto), Dt1 (vencimento original), Obs, Ban (conta), centro de custo |
| `Tra*` | Movimentação bancária | Tip (`D` depósito, `R` retirada, `T` transferência), Sit (`V` realizado / `P` previsto), Dat, Ori, Des, Val, Obs |
| `Usu*` | Usuários | Nom, Eml, senha, permissões por módulo (0 sem acesso, 1 consulta, 2 completo), contas permitidas |
| `Ext*` | Linha de extrato importado (OFX) para conciliação | Dat, Ope, Val, Des, Doc, Sta |

## Telas e funções observadas

- **Principal (`TFPRIN`)**: abas Despesas / Receitas / Dashboard / Saldos.
  Filtros: situação (pagas / em aberto / todas), conta, campo de data (movimento,
  vencimento ou ambos), ano e mês/trimestre/semestre/ano/todo período, busca rápida.
  Ordenação por data, vencimento, documento, descrição, pessoa, valor, situação
  ou observação. Ações: incluir, alterar, excluir, localizar, baixar e recibo.
- **Lançamento (`TFMOVCAD`)**, **parcelamento (`TFMULCAD`**, com periodicidade
  diária a anual), **baixa (`TFBAIXA`)**, **baixa múltipla (`TFBAIXAMULT`)**,
  **exclusão de parcelas (`TFMULTDELMOV`)**, **transferir para outra conta**.
- **Dashboard**: regime de caixa (a receber, a pagar, pago, recebido; hoje,
  semana, mês ou período; considerar vencidos), regime de competência
  (receitas, despesas, margem bruta) e análise linear (diária, semanal ou mensal).
- **Cadastros**: contas controle, contas bancárias, centros de custo, clientes,
  fornecedores, itens de despesa e de receita, usuários e permissões.
- **Bancos**: movimentações bancárias, importação de extrato OFX com
  conciliação em 4 passos, extratos, saldos e comparativo de saldos.
- **Relatórios** (cerca de 50): despesas e receitas (detalhado e totais), contas a
  pagar e a receber (em aberto, pagas, todas, por pessoa), pontualidade, fluxo
  de caixa (realizado, por dia, previsão), extratos, demonstrativo anual
  (por item, pessoa, centro e conta), análise por centro de custo (orçamento,
  projeção, fluxo), gráficos gerenciais, relatório analítico e recibo/duplicata.
- **Outros**: lembrete de contas, registros excluídos, proteção de dados (senha
  de bloqueio), login, suporte online, licença e termos de uso.
