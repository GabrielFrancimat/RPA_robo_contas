# MBA — Robô de Contas a Pagar

Solução dos cinco desafios do laboratório do Prof. MSc. Kaio Mesquita, em Python, mantendo Playwright, pypdf, fpdf2, pandas e openpyxl. O material original está preservado em `material_original/`.

## Entrega

- `RPA_Contas_a_Pagar_Resolvido.ipynb`: notebook autossuficiente, com enunciados, implementação integrada, reflexões e saídas da execução.
- `robo_contas_a_pagar.py`: mesma solução em script Python.
- `RELATORIO_TECNICO.md`: resultados medidos, justificativas e limites da avaliação.
- `lab_rpa/saida/`: Excel, e-mail `.eml`, métricas e CSVs dos testes.
- `lab_rpa/evidencias/`: capturas dos testes de interface.

Preencha os dois nomes na célula `DUPLA`. As reflexões estão redigidas como base para leitura, revisão e defesa pela dupla.

## Executar localmente

Use Python 3.10 ou superior. O ambiente validado e as versões exatas estão em `requirements-lock.txt` e `lab_rpa/saida/metricas.json`. O lock reproduz o ambiente Python 3.14 usado nesta entrega; para outra versão de Python, use `requirements.txt`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
python scripts/executar_notebook.py
```

Ou abra o notebook no VS Code/Jupyter e execute todas as células, com o interpretador do ambiente virtual. Para rodar como script:

```bash
python robo_contas_a_pagar.py
```

No Windows, ative com `.venv\Scripts\activate`. Se faltar `venv`/`ensurepip` no Linux, instale o pacote de ambiente virtual da distribuição. Se o Chromium indicar bibliotecas de sistema ausentes, use `python -m playwright install --with-deps chromium` em ambiente com permissão para instalar esses pacotes.

## Organização e reexecução

`scripts/montar_entrega.py` combina o original com os trechos em `solucao/`. Esses trechos compartilham o namespace do notebook e não são módulos independentes. Para alterar a implementação de modo reproduzível, edite os trechos e execute:

```bash
python scripts/montar_entrega.py
python scripts/executar_notebook.py
python scripts/gerar_relatorio.py
```

A montagem limpa as saídas anteriores do notebook. A execução gera novas evidências e relatórios. Os PDFs de entrada são recriados e o ERP de laboratório começa vazio a cada execução completa. O teste de idempotência, dentro da execução, repete apenas o robô sem reiniciar o ERP.

O lote principal usa `FALHA_ALEATORIA_ERP = 0.0`; os testes injetam falhas controladas. Para experimentar o comportamento aleatório original, altere para `0.20`, sabendo que as asserções de contagem do cenário controlado podem falhar. Não use dados reais neste ERP didático.

No Colab remoto, mantenha `HEADLESS = True`: `127.0.0.1` representa a máquina remota, não seu computador. O notebook usa Playwright no mesmo ambiente do ERP e não exige acesso manual àquela URL. Os artefatos precisam ser baixados antes de encerrar a sessão.

## Escopo dos testes

- CNPJ numérico, alfanumérico, DV inválido e símbolos inválidos; fluxo PDF → tela → consulta.
- 12 PDFs: 8 sucessos, 3 exceções de negócio, 1 aprovação.
- Conferência de protocolos e valores pela tela do ERP.
- Reexecução com zero novas gravações.
- Layout v1/v2, IDs e rótulos; falha esperada do mapa antigo no v2.
- HTTP 503 transitório, esgotamento de retentativas e negócio sem retentativa.
- Perda de confirmação depois da gravação, com recuperação sem duplicação.
- Centro ausente: classificação segura ou aprovação humana; casos ambíguos e vazios.
- E-mail local com anexo Excel idêntico ao arquivo original.

O e-mail não é enviado. O ERP e a classificação são didáticos. Tempos são medições locais; ROI usa premissas hipotéticas fornecidas pelo professor.
