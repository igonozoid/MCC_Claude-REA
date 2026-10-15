# MCC — reimplementação

Reimplementação do **MCC** (controle financeiro, Delphi/Windows, usado via Wine) a partir da análise
do executável com o [REA](https://github.com/morluto/rea). Nenhum código do original foi copiado:
as telas e regras foram reconstruídas a partir da estrutura observada.

| Pasta | Conteúdo |
|---|---|
| [`mcc-desktop/`](mcc-desktop/) | Versão desktop em Python + PySide6 (Font Awesome), com telas e menus próximos do original. **Versão principal.** |
| [`mcc-clone/`](mcc-clone/) | Versão web (Node.js + SQLite, sem dependências). Usa o mesmo banco do desktop. |
| [`analise/`](analise/) | Resultado da análise: funcionalidades, modelo de dados, textos e esboço das telas. |
| [`tools/`](tools/) | Scripts usados na análise (extração e esboço dos formulários). |

## Rodar

Desktop:

```bash
cd mcc-desktop
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

Web (Node.js 22.13+):

```bash
cd mcc-clone && npm start   # http://localhost:5180
```

## Testes

```bash
cd mcc-desktop && QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -t .
cd mcc-clone && npm test
```

## Análise com REA

O REA não é versionado aqui. Para refazer a análise:

```bash
git clone https://github.com/morluto/rea.git && cd rea && npm ci && npm run build
```

As extrações brutas do executável (`analise/forms/`, `analise/pe-resources.json`) não são versionadas:
contêm dados do fornecedor. Elas podem ser regeneradas com `tools/dfm_extract.py`.
