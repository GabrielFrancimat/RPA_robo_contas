# Casos sintéticos: medem aderência às regras, não acurácia de produção.
CASOS_CLASSIFICACAO = [
    ('Manutenção preventiva de frota', 'OPERACOES'),
    ('Frete Fortaleza-Recife', 'OPERACOES'),
    ('Lavagem de caminhões', 'OPERACOES'),
    ('Licença de software de GPS', 'TI'),
    ('Suporte ao sistema', 'TI'),
    ('Laudo estrutural', 'ENGENHARIA'),
    ('Sinalização e recapeamento', 'ENGENHARIA'),
    ('Serviço de limpeza e conservação', 'ADMINISTRATIVO'),
    ('Manutenção de ar-condicionado', 'ADMINISTRATIVO'),
    ('Consultoria diversa', None),
    ('Software para frota', None),
    ('GPS e software para frota', None),
    ('', None),
]
classificacoes = []
for descricao, esperado in CASOS_CLASSIFICACAO:
    centro, confianca = classificar_centro_custo(descricao)
    decisao = centro if confianca >= LIMIAR_CONFIANCA else None
    assert decisao == esperado, (descricao, centro, confianca)
    classificacoes.append(dict(descricao=descricao, esperado=esperado, centro=centro,
        confianca=confianca, decisao=decisao))
pd.DataFrame(classificacoes).to_csv(PASTA_SAIDA / 'classificacao.csv', index=False)

# Verifica integração com PDFs sem centro e perda de confirmação após gravar.
async def validar_extra_e_resposta_incerta():
    global PASTA_ENTRADA
    entrada_original = PASTA_ENTRADA
    entrada_teste = BASE / 'entrada_testes'
    entrada_teste.mkdir(exist_ok=True)
    for antigo in entrada_teste.glob('*.pdf'):
        antigo.unlink()
    for numero, descricao in [('830001', 'Manutenção de frota'), ('830002', 'Consultoria diversa'),
                               ('830003', 'Software para frota')]:
        gerar_pdf_nf(dict(notas_geradas[0], numero=numero, centro_custo=None,
                         descricao=descricao), entrada_teste / f'{numero}.pdf')
    try:
        PASTA_ENTRADA = entrada_teste
        # Simula ERP gravando com sucesso, mas a confirmação se perdendo para o robô.
        original = RoboERP.lancar
        chamadas = []
        async def resposta_perdida(self, nota):
            protocolo = await original(self, nota)
            chamadas.append(protocolo)
            raise ErroSistema('Confirmação perdida após gravar (injeção de teste)')
        with patch.object(RoboERP, 'lancar', resposta_perdida):
            resultados_extra = await executar_robo()
        assert [r.status for r in resultados_extra] == [STATUS_SUCESSO, STATUS_APROVACAO, STATUS_APROVACAO]
        assert resultados_extra[0].tentativas == 2
        assert len(chamadas) == 1, 'A retentativa não deve repetir a gravação'
        async with RoboERP() as robo:
            registros = await ler_registros_do_erp(robo)
            assert sum(n['numero'] == '830001' for n in registros) == 1
            assert not any(n['numero'] in {'830002', '830003'} for n in registros)
        return resultados_extra
    finally:
        PASTA_ENTRADA = entrada_original

resultados_extra = rodar(validar_extra_e_resposta_incerta())
pd.DataFrame([asdict(r) for r in resultados_extra]).to_csv(PASTA_SAIDA / 'teste_extra.csv', index=False)

# Benchmark do extrator mantido: mesma massa de 12 documentos, 5 repetições.
medidas_pdf = []
for repeticao in range(5):
    for pdf in sorted(PASTA_ENTRADA.glob('*.pdf')):
        inicio = time.perf_counter()
        try:
            extrair_nota(pdf)
            status = 'EXTRAIDO'
        except ErroNegocio:
            status = 'REJEITADO'
        medidas_pdf.append(dict(repeticao=repeticao + 1, arquivo=pdf.name,
            segundos=time.perf_counter() - inicio, status=status))
assert sum(m['status'] == 'EXTRAIDO' for m in medidas_pdf) == 55
pd.DataFrame(medidas_pdf).to_csv(PASTA_SAIDA / 'benchmark_pdf.csv', index=False)

# Artefatos legíveis por máquina para reproduzir a defesa das escolhas.
import platform
from importlib.metadata import version
metricas = {
    'ambiente': {'python': platform.python_version(), 'sistema': platform.platform(),
        'bibliotecas': {p: version(p) for p in ['playwright', 'pypdf', 'fpdf2', 'pandas', 'openpyxl']}},
    'lote': {'total': len(df_primeiro_lote), 'status': df_primeiro_lote.status.value_counts().to_dict(),
        'tempo_itens_s': float(df_primeiro_lote.duracao_s.sum()),
        'media_sucesso_s': float(df_primeiro_lote.loc[df_primeiro_lote.status == STATUS_SUCESSO, 'duracao_s'].mean()),
        'stp': float((df_primeiro_lote.status == STATUS_SUCESSO).mean())},
    'idempotencia': {'antes': len(antes), 'depois': len(depois), 'novos_lancamentos': 0},
    'interface': benchmark_interface.groupby(['layout', 'estrategia']).segundos.agg(['count', 'mean', 'median', 'std']).reset_index().to_dict('records'),
    'extracao': {'amostras': len(medidas_pdf), 'extraidos': 55, 'rejeitados': 5,
        'mediana_ms': statistics.median(m['segundos'] for m in medidas_pdf) * 1000},
    'classificacao': {'casos_sinteticos': len(classificacoes), 'aderencia_esperada': 1.0,
        'encaminhados_humano': sum(c['decisao'] is None for c in classificacoes)},
    'resiliencia': {'tentativas_503': 2, 'tentativas_negocio': 1, 'tentativas_falha_persistente': MAX_TENTATIVAS,
        'gravacoes_com_confirmacao_perdida': 1},
    'roi_hipotetico': {'horas_liberadas_mes': float(horas_economizadas),
        'economia_liquida_mes': float(economia_mes),
        'stp_equilibrio': CUSTO_MENSAL_ROBO / (NOTAS_POR_MES * MIN_HUMANO_POR_NOTA / 60 * CUSTO_HORA_ANALISTA)},
}
(PASTA_SAIDA / 'metricas.json').write_text(json.dumps(metricas, ensure_ascii=False, indent=2), encoding='utf-8')
df_primeiro_lote.to_csv(PASTA_SAIDA / 'primeiro_lote.csv', index=False)
print('Desafio 5: 13 casos sintéticos aprovados; integração mantém notas incertas fora do ERP.')
print(json.dumps(metricas, ensure_ascii=False, indent=2))
