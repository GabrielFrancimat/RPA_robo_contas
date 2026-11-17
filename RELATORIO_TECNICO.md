# Relatório técnico — RPA de Contas a Pagar

## Resultado da execução

Os cinco desafios foram implementados em Python e executados no notebook, em kernel limpo. A versão `.py` também foi executada separadamente, em diretório de validação isolado, concluindo os mesmos testes sem erros. O código original do professor foi preservado separadamente. As funções dos desafios foram posicionadas antes de seu primeiro uso para permitir execução sequencial.

| Verificação | Resultado medido |
|---|---|
| PDFs do lote principal | 12 |
| Lançadas | 8 |
| Exceções de negócio | 3 |
| Aprovação humana | 1 |
| Exceções de sistema no lote controlado | 0 |
| Taxa de processamento automático (STP) | 66.67% |
| Soma dos tempos dos itens | 6.535 s |
| Tempo médio por nota lançada | 0.816 s |
| Registros antes/depois da repetição | 8 / 8 |
| Novas gravações na repetição | 0 |
| Classificação: casos sintéticos aderentes à expectativa | 13/13 |
| Casos sintéticos encaminhados ao humano | 4 |

A soma dos tempos dos itens exclui inicialização do navegador, login, consulta inicial e geração de relatório. O lote principal desativa falhas aleatórias; a resiliência é verificada separadamente com falhas controladas. No notebook original, a probabilidade de falha era 20% por tentativa.

## Bibliotecas e justificativa

Nenhuma biblioteca do exercício foi substituída. Não foi feito benchmark contra bibliotecas concorrentes, portanto não se afirma que esta combinação seja a mais rápida ou a melhor em todos os cenários. Ela atende aos requisitos demonstrados e evita custo de migração sem benefício comprovado.

| Biblioteca | Papel | Evidência e decisão |
|---|---|---|
| Playwright | Navegação, preenchimento e leitura da UI | 12 lançamentos de benchmark em dois layouts; consulta de idempotência e recuperação de HTTP 503. Mantido. |
| pypdf | Extrair texto dos PDFs | 60 leituras: 55 extrações e 5 rejeições esperadas do mesmo documento sem valor. Mantido para PDFs digitais de layout fixo. |
| fpdf2 | Gerar massa fictícia | 12 PDFs principais e PDFs adicionais de CNPJ alfanumérico/centro ausente, usados nos testes reais. Mantido. |
| pandas | Consolidação e métricas | Contagens, reconciliação, CSV e três abas do relatório. Mantido. |
| openpyxl | Escrita e formatação de Excel | Excel produzido e anexado com integridade binária conferida. Mantido. |
| Biblioteca padrão Python | E-mail, texto, temporização, testes | `email`, `unicodedata`, `time`, `statistics`, `json` e `unittest.mock`; sem serviço externo. |

`nbformat`, `nbclient` e `ipykernel` são dependências de execução/documentação do notebook, não substitutos das bibliotecas de RPA.

O pypdf extrai texto e não realiza OCR. Um PDF composto somente de imagens exigiria um componente de OCR e outra massa de avaliação. A documentação oficial descreve essa limitação: [extração no pypdf](https://pypdf.readthedocs.io/en/stable/user/extract-text.html).

Para controles de formulário, Playwright oferece localização por rótulo e por papel acessível, além de mecanismos de espera. Usamos essas capacidades no desafio de mudança de layout: [locators do Playwright](https://playwright.dev/python/docs/locators).

## Benchmark: IDs versus rótulos

| Layout | Estratégia | n | Média (s) | Mediana (s) | Desvio padrão (s) |
|---|---|---:|---:|---:|---:|
| v1 | ids | 3 | 0.840 | 0.815 | 0.050 |
| v1 | rotulos | 3 | 0.547 | 0.482 | 0.128 |
| v2 | ids | 3 | 0.911 | 0.882 | 0.120 |
| v2 | rotulos | 3 | 0.680 | 0.723 | 0.111 |

Método: três lançamentos por combinação; IDs e rótulos intercalados; uma sessão autenticada; notas distintas; mesmo ERP local. O tempo inclui navegação, preenchimento, espera de resposta e a latência artificial do ERP. Cada lançamento exige protocolo retornado. O mapa antigo de IDs falha no v2, como esperado; o mapa v2 corrigido funciona; os mesmos rótulos funcionam nos dois layouts.

Esta amostra pequena não sustenta uma conclusão de superioridade de velocidade. A vantagem defendida dos rótulos é funcional: uma implementação sobreviveu aos dois conjuntos de IDs. Textos traduzidos, rótulos duplicados ou remoção de associações `label/for` ainda podem quebrá-la.

## Benchmark: extração

Foram realizadas cinco passagens pelos mesmos 12 PDFs: 60 observações, com mediana de **1.529 ms por tentativa de extração**. Houve 55 extrações e cinco rejeições esperadas do PDF sem campo de valor. A extração não valida DV, duplicidade nem limite financeiro; essas são etapas posteriores. Leituras repetidas podem se beneficiar do cache do sistema operacional. Não representam 60 documentos independentes nem comprovam generalização para outros layouts.

## Testes de confiabilidade

1. **CNPJ:** testes fornecidos pelo professor, entradas inválidas e fluxo alfanumérico completo de PDF para formulário e consulta. A normalização antiga é substituída em todos os pontos de uso. O algoritmo segue o [manual oficial da Receita Federal](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj/manual-dv-cnpj.pdf).
2. **E-mail:** assunto, corpo, pendências e anexo; arquivo lido novamente com parser MIME, comparando os bytes do anexo. Não há envio externo.
3. **Idempotência:** duas execuções consecutivas com o mesmo ERP preservado; oito registros antes e depois, nenhum novo protocolo. A consulta operacional lê `/notas`; o banco aparece apenas como oráculo de teste do laboratório.
4. **Falhas:** um HTTP 503 injetado no navegador é recuperado na segunda tentativa; erro de negócio recebe uma tentativa; falha técnica persistente esgota três tentativas.
5. **Resposta perdida:** o teste grava uma nota e simula erro antes de entregar a confirmação ao orquestrador. Na retentativa, a consulta da UI recupera o protocolo: uma gravação, duas tentativas, nenhuma duplicação.
6. **Centro ausente:** três PDFs de integração; um com decisão segura é lançado; os dois incertos ficam pendentes. Treze descrições sintéticas verificam classificação, ausência de termos, empate e confiança abaixo de 70%.

## ROI: premissas e limites

Usando as premissas do professor — 800 notas/mês, quatro minutos manuais por nota, R$ 45/h e R$ 1.500/mês de custo do robô — o STP observado projeta **35.56 horas liberadas/mês** e **R$ 100.00/mês** de economia líquida. O ponto de equilíbrio é **62.5% de STP**.

Fórmula: `800 × STP × 4/60 × 45 − 1500`. Esses valores são projeções didáticas, não economia realizada. Não incluem custo inicial, revisão das exceções, manutenção variável, supervisão e tempo de classificação humana. O custo de implantação não foi informado, portanto não se calcula prazo de retorno do investimento.

## Melhorias integradas e limites remanescentes

- Preservação de letras do CNPJ na extração, validação, preenchimento e chave de idempotência.
- Consulta da UI antes de retentar gravação com resultado incerto.
- Registro de tentativas, duração, motivo, centro atribuído, confiança e versão do classificador.
- Campo centro de custo opcional na extração; baixa confiança encaminhada ao humano.
- Preservação do DataFrame do primeiro lote para impedir que a repetição distorça relatório e ROI.
- Captura de evidência protegida para não encerrar o lote se o screenshot falhar.

O classificador usa uma proporção de palavras-chave, não uma probabilidade calibrada; 13/13 é aderência a casos sintéticos escritos para o exercício. O sistema assume um robô por vez e não resolve concorrência entre trabalhadores. O ERP armazena dados em memória: reiniciar o servidor apaga os registros. Os testes de layout acrescentam notas depois da reconciliação; o Excel se refere exclusivamente ao primeiro lote de 12 PDFs, não ao estado final do ERP após os testes.

## Como defender uma eventual substituição

Antes de trocar qualquer biblioteca, medir a solução atual e a candidata com a mesma massa representativa, versões fixadas e ao menos 30 execuções por cenário. Definir previamente critérios de qualidade: campos extraídos corretamente, falsos aceites/rejeições, duplicações e recuperação de falhas. Comparar também mediana/p95 de latência, pico de memória, custo por mil documentos e esforço de manutenção. A troca só se justifica com ganho relevante sem regressão de qualidade. Esse experimento comparativo não foi realizado nesta entrega; nenhuma superioridade de alternativa é alegada.

## Ambiente e reprodução

Python 3.14.4; Linux-7.0.0-42-generic-x86_64-with-glibc2.43.

Versões: playwright 1.65.2, pypdf 7.1.0, fpdf2 2.9.0, pandas 3.1.1, openpyxl 3.1.5.

Consulte `README.md` para execução, `requirements-lock.txt` para o ambiente exato e `lab_rpa/saida/metricas.json`/CSVs para os dados brutos. A massa é sintética; a geração usa semente 2026. Tempos variam com a máquina, carga e latência simulada.

Outras referências oficiais: [fpdf2](https://py-pdf.github.io/fpdf2/), [pandas to_excel](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_excel.html), [estilos openpyxl](https://openpyxl.readthedocs.io/en/stable/styles.html).
