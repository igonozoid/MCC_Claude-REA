# MCC desktop (Python + PySide6)

Reimplementação desktop do **MCC** com telas, menus e aparência o mais próximos possível do original
(Delphi/VCL). A disposição de cada tela segue a geometria, as cores e as fontes extraídas dos
formulários do `mcc.exe` (ver `../analise/`), redesenhada à mão em Qt. Nenhum arquivo do fornecedor
é embutido. Os ícones são Font Awesome 6 (QtAwesome).

## Rodar

```bash
cd mcc-desktop
./run.sh
```

No primeiro uso o MCC pede o **usuário administrador** e a **primeira conta controle**.
Dependências: `.venv` com `PySide6` e `QtAwesome` (`pip install -r requirements.txt`).

Testes (regras, permissões, proteção de dados e todas as telas/relatórios offscreen):

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -t .
```

## Banco de dados

SQLite, por padrão em `~/.local/share/MCC/mcc.db`. Em *Ferramentas › Configurações › Banco de
dados* é possível apontar outro arquivo (rede/pasta compartilhada) e fazer cópia de segurança.
A variável `MCC_DB` também escolhe o arquivo. **É o mesmo formato do clone web** (`../mcc-clone`):
usuários, senhas e lançamentos funcionam nos dois. O desktop usa três tabelas só dele
(`pessoas_extra`, `empresa_config`, `empresa_logos`), que o clone web ignora.

## O que existe (equivalência com o original)

| Original | Desktop |
|---|---|
| FPrin: faixa de botões (Cadastros, Ferramentas, Bancos, Relatórios, Suporte, Acesso fácil) com os mesmos menus, linha do usuário, faixa da conta controle, filtros, quadro **Saldos**, abas Despesas/Receitas/Dashboard, busca rápida | ✔ |
| Botão Incluir com seta (múltiplos lançamentos), Baixar com menu (selecionado / múltipla), navegador, menu de contexto com **transferir para outra conta** e **repetir no mês seguinte** | ✔ |
| Dashboard: Caixa / Competência / Linear com os cartões coloridos e gráficos | ✔ |
| FMovCad, FMulCad, FBaixa, FBaixaMult, FMultDelMov (inclui "excluir todos os registros em aberto ou pagos"), FPesM (localizar) | ✔ |
| Cadastros FBan/FCen/FCon/FPes (4 abas: dados, perfil do cliente, dados bancários, observações)/FIte/FTra | ✔ |
| FConcilia: importação OFX em 4 passos com validação por linha (FConciliaCad) | ✔ |
| FLog, FCad (primeiro acesso), FLogin (conta controle), FUseBrs/FUseCad (permissões por módulo e por conta controle), FAlterSenha | ✔ |
| FLok/FLokSen: proteção de dados com senha do administrador | ✔ |
| FConfigConta: saldo do caixa interno, centros de custo, exibir saldos, ítens próprios ou de todas as contas, campo inicial do lançamento, conta padrão | ✔ |
| FLemb (com "ativar lembrete novamente"), FDeleteDes (restaurar), FPeriodo (atalhos de período) | ✔ |
| Relatórios do menu (todos), no estilo QuickReport: faixas na **cor dos relatórios**, **logomarca**, paginação; geração na tela (FPrint), PDF, preview do sistema ou HTML; exportação CSV | ✔ |
| FAnalise com agrupamentos livres; FChart (despesas x receitas, composição, evolução) | ✔ |
| FRecibo: recibo (1 ou 2 vias, valor por extenso) e **duplicata** (mercantil/serviço), margens configuráveis | ✔ |

Não reproduzidos (dependem do servidor do fornecedor): suporte online, licença, atualização automática.
