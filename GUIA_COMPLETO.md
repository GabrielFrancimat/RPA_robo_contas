# Guia completo — Robô de contas a pagar

Este projeto é um laboratório de RPA (automação de processos robóticos) para o cenário fictício da TransVia Logística. Ele simula o recebimento de notas fiscais em PDF, confere seus dados, registra as notas aceitas em um ERP web de demonstração e produz arquivos para acompanhamento. O notebook principal é `RPA_Contas_a_Pagar_Resolvido.ipynb`; o enunciado original está em `material_original/RPA_Lab_original.ipynb`.

## Fluxo geral

1. Configurar diretórios, credenciais de demonstração, limites e navegador.
2. Gerar 12 PDFs fictícios com casos normais e problemas propositais.
3. Iniciar um ERP local em memória, com login, formulário e listagem de notas.
4. Ler cada PDF e extrair número, data, fornecedor, CNPJ, descrição, centro de custo e valor.
5. Validar os dados e consultar a listagem do ERP para evitar repetição.
6. Encaminhar casos que precisam de aprovação e preencher o formulário dos demais com Playwright.
7. Registrar o resultado, gerar uma planilha Excel e criar um arquivo de e-mail com o relatório anexo.
8. Conciliar protocolos e valores da execução com a tela de consulta do ERP.
9. Executar os testes adicionais dos cinco desafios avaliativos.

O padrão didático se aproxima de uma fila de transações: cada PDF é processado separadamente, com resultados e tratamentos de erro. A aprovação é representada como pendência nos resultados; não há uma aplicação de aprovação ou envio automático ao aprovador.

## Cobertura dos enunciados

A tabela compara o código e os artefatos com o notebook original. A existência de código e testes não substitui a avaliação do professor nem comprova que atividades manuais foram realizadas.

| Parte | O que foi encontrado | Situação e evidência |
|---|---|---|
| 1 — PDFs | Geração de 12 notas, com CNPJ inválido, duplicidade, valor alto e ausência de valor. | Implementada; geração no notebook e PDFs em `lab_rpa/entrada/`. |
| 2 — ERP | Servidor local com login por cookie, formulário, listagem, layouts v1/v2, latência e falha 503 configurável. | Implementado. Lançamento manual e cronometragem pedidos para a aula dependem do aluno e não foram comprovados nesta revisão. |
| 3 — Extração | `pypdf` lê texto e expressões regulares identificam os campos; documento ilegível ou sem campo obrigatório gera erro de negócio. | Implementada para o layout sintético; não realiza OCR. |
| 4 — Regras | Número, data, fornecedor, descrição, CNPJ, valor, centro, duplicidade e limite são validados separadamente da interface. | Implementada; há testes de limites e formatos em `testes/bateria.py`. |
| 5 — Interface | Login, leitura e lançamento pelo Playwright; seletores centralizados e por rótulo; captura de tela disponível. | Implementada e exercitada nos dois layouts. |
| 6 — Orquestração | Lote, classificação por status, até três tentativas técnicas, espera exponencial, consulta da UI e aprovação humana. | Implementada com ressalva: erros de sistema tentam capturar screenshot; erros de negócio são registrados em log e resultado, mas não têm screenshot por exceção, embora o enunciado mencione captura e log para cada exceção. A inicialização/login ou consulta inicial podem interromper o lote antes do processamento individual. |
| 7 — Excel e ROI | Abas de resumo, lançadas e itens para análise; cálculo de STP e projeção financeira. | Implementada. A discussão e alteração das premissas são atividades para a turma; o ponto de equilíbrio calculado está no relatório técnico. |
| 8 — Auditoria | Consulta à tela, comparação de protocolos e valores com o primeiro lote. | Implementada para o cenário de teste; as asserções assumem oito lançamentos. |
| 9 — Avaliação | Os cinco desafios e reflexões estão no notebook. | Implementados e testados nos cenários descritos abaixo; **os nomes da dupla ainda precisam ser preenchidos** na célula `DUPLA`. |

### Desafios da parte 9

- **1 — CNPJ alfanumérico:** normalização, validação dos dígitos verificadores e extração aceitam letras nas 12 primeiras posições; os dois dígitos finais continuam numéricos. Há casos válidos e inválidos e teste passando pelo PDF e pela interface.
- **2 — E-mail:** `gerar_email` cria `.eml` com data, total, contagens, pendências e Excel anexado. O teste confere os bytes do anexo. O arquivo é preparado localmente, sem transmissão por SMTP.
- **3 — Idempotência:** o robô lê `/notas` pela interface, formando chaves de número e CNPJ. O teste executa o lote novamente com o ERP preservado e verifica que não surgem novas gravações. Em uma resposta perdida, consulta a tela antes de repetir o lançamento.
- **4 — Mudança de layout:** existem mapas de IDs para v1 e v2; testes demonstram a falha do mapa antigo no v2, o mapa atualizado e o preenchimento por rótulos nos dois layouts.
- **5 — Centro de custo:** palavras-chave sugerem centro e confiança. Empate, ausência de termos ou confiança inferior a 70% encaminham para aprovação. Chamada a LLM era opcional e não foi implementada.

As reflexões estão escritas, mas devem ser lidas e revisadas pela dupla. Preencha os nomes reais no notebook antes de entregar.

Na revisão deste projeto, a bateria `testes/bateria.py --fase depois` foi executada em uma cópia isolada: **60 verificações passaram, sem falhas**. Ela cobre validações, extração, interface, recuperação de falhas, idempotência e e-mail; não comprova a execução das atividades manuais nem testa todas as condições possíveis.

## Como as decisões funcionam

### Dados e regras

Os PDFs são digitais e de formato conhecido. `extrair_nota` usa os rótulos do documento como referência; PDFs de outras organizações, imagens digitalizadas ou layouts diferentes podem exigir adaptação e OCR. O campo de centro de custo pode estar ausente; os demais campos esperados precisam ser encontrados.

O validador exige data real em `dd/mm/aaaa`, CNPJ com dígitos verificadores corretos, número numérico, fornecedor e descrição preenchidos, valor positivo e finito e centro válido quando informado. A chave de duplicidade combina número da nota com CNPJ normalizado. A verificação do CNPJ não consulta cadastro nem confirma a existência do fornecedor.

O limite configurado é **R$ 50.000,00**: valor superior vai para aprovação; valor exatamente igual ao limite pode continuar. Ao faltar o centro, o classificador procura termos associados a Operações, TI, Engenharia e Administrativo. A confiança é a proporção de palavras correspondentes ao centro vencedor entre as palavras encontradas. Por exemplo, um único termo reconhecido pode resultar em 100%; esse número não é uma probabilidade estatística de acerto. Decisões incertas não são lançadas.

### Status e falhas

- `SUCESSO`: lançamento confirmado e protocolo retornado.
- `EXCECAO_NEGOCIO`: o documento ou seus dados não atendem às regras, incluindo duplicidade e PDF ilegível; não recebe retentativa automática.
- `EXCECAO_SISTEMA`: falha técnica que não foi resolvida, como problema de navegação; a captura de tela é tentada quando há navegador disponível.
- `PENDENTE_APROVACAO`: valor acima do limite ou classificação de centro insuficientemente segura.

Falhas técnicas tratadas pela rotina de retentativa recebem até três tentativas, com espera inicial de 0,5 segundo e progressão exponencial. O ERP de exemplo mantém registros apenas na memória: se o servidor reiniciar, os lançamentos desaparecem. A estratégia de consulta antes de repetir reduz duplicações para um robô, mas não garante exclusividade transacional com vários robôs simultâneos.

## Resultados e arquivos

No lote sintético documentado há 12 notas: **8 sucessos, 3 exceções de negócio e 1 pendência de aprovação**, correspondendo a 66,67% de processamento automático (STP). O teste de reexecução registrou 8 notas antes e depois, sem novos lançamentos. São resultados de laboratório, não garantias para dados reais.

- `lab_rpa/entrada/`: PDFs principais gerados.
- `lab_rpa/entrada_testes/`: PDFs adicionais de teste.
- `lab_rpa/saida/`: planilhas, CSVs, métricas e `resumo_lote.eml`.
- `lab_rpa/evidencias/`: exemplos de capturas de tela.
- `lab_rpa/robo.log`: registro da execução.
- `RELATORIO_TECNICO.md`: análise técnica e medições de uma execução.
- `postman/`: coleção para exercitar o ERP de teste; o robô operacional usa a interface.
- `testes/`: bateria adversarial e carregador isolado de definições do notebook.
- `solucao/`: trechos integrados ao notebook pelo script de montagem.
- `scripts/`: montagem, execução do notebook, relatório e utilitários de teste.
- `robo_contas_a_pagar.py`: versão em script da solução.

Os tempos registrados no relatório técnico e em `lab_rpa/saida/metricas.json` não coincidem; parecem refletir execuções diferentes. Portanto, consulte cada artefato como registro de sua própria execução e regenere relatório e métricas juntos para uma comparação atualizada.

## Indicadores e ROI

O STP é o número de notas lançadas automaticamente dividido pelo total processado. A projeção do exercício usa 800 notas/mês, quatro minutos manuais por nota, R$ 45 por hora e custo mensal do robô de R$ 1.500:

`economia líquida mensal = 800 × STP × (4 / 60) × 45 − 1.500`

Com STP de 8/12, a projeção é de aproximadamente 35,56 horas liberadas e R$ 100 líquidos por mês. Com essas premissas, o ponto de equilíbrio é 62,5% de STP. Não inclui implantação, trabalho de revisão das exceções e outros custos; não representa economia efetivamente medida nem prazo de retorno.

## Como executar e estudar

Siga as instruções do `README.md`: crie um ambiente virtual, instale `requirements.txt`, instale o Chromium do Playwright e execute `python scripts/executar_notebook.py` ou o notebook inteiro. A execução completa recria PDFs e evidências e inicializa o ERP; preserve previamente os arquivos gerados que quiser guardar. O navegador fica invisível com `HEADLESS = True`; mude para `False` em ambiente gráfico para observar a automação.

Para compreender o código, leia as partes do notebook em sequência e acompanhe, em especial, `extrair_nota`, `validar_nota`, `classificar_centro_custo`, `RoboERP`, `ler_notas_do_erp`, `executar_robo` e `gerar_email`. Para reproduzir a bateria adicional, use o Python do ambiente virtual em `python testes/bateria.py --fase depois`; ela escreve em `output/bateria/depois/` e inicia um ERP de teste local. O script pode sobrescrever arquivos de resultados nessa pasta.

A solução é didática: não recebe e-mails reais, não envia o `.eml`, não persiste o ERP, não executa OCR e não deve ser usada com dados reais sem adaptações e validação apropriadas.
