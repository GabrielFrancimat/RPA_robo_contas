@dataclass
class Resultado:
    arquivo: str
    status: str
    numero: str = ''
    fornecedor: str = ''
    cnpj: str = ''
    valor: float | None = None
    protocolo: str = ''
    tentativas: int = 0
    mensagem: str = ''
    evidencia: str = ''
    duracao_s: float = 0.0
    centro_custo: str = ''
    confianca: float | None = None
    classificador: str = ''
    descricao: str = ''


async def com_retentativas(funcao, *args, tentativas=MAX_TENTATIVAS, espera_base=0.5):
    for n in range(1, tentativas + 1):
        try:
            return await funcao(*args), n
        except (ErroSistema, PWTimeout) as e:
            if n == tentativas:
                erro = ErroSistema(f'Falhou após {n} tentativas: {e}')
                erro.tentativas = n
                raise erro from e
            log.warning('Retentativa %d/%d: %s', n, tentativas, e)
            await asyncio.sleep(espera_base * 2 ** (n - 1))


async def executar_robo() -> list[Resultado]:
    inicio = time.perf_counter()
    resultados = []
    chaves_vistas = set()
    async with RoboERP() as robo:
        ja_no_erp, _ = await com_retentativas(ler_notas_do_erp, robo)
        for item in sorted(PASTA_ENTRADA.glob('*.pdf')):
            t0 = time.perf_counter()
            r = Resultado(arquivo=item.name, status='')
            try:
                nota = extrair_nota(item)
                r.numero, r.fornecedor, r.cnpj, r.valor = nota.numero, nota.prestador, nota.cnpj, nota.valor
                r.descricao = nota.descricao
                chave = (nota.numero, limpar_cnpj(nota.cnpj))
                if chave in ja_no_erp:
                    raise ErroNegocio('Já existe no ERP — ignorado por idempotência')
                decisao = validar_nota(nota, chaves_vistas)
                motivos = []
                if decisao == STATUS_APROVACAO:
                    motivos.append(f'Valor acima do limite de R$ {brl(LIMITE_APROVACAO)}')
                if not nota.centro_custo:
                    centro, r.confianca = classificar_centro_custo(nota.descricao)
                    r.classificador = VERSAO_CLASSIFICADOR
                    if centro is None or r.confianca < LIMIAR_CONFIANCA:
                        motivos.append(f'Centro de custo incerto: confiança {r.confianca:.0%}')
                    else:
                        nota.centro_custo = centro
                elif nota.centro_custo not in CENTROS:
                    raise ErroNegocio(f'Centro de custo inválido: {nota.centro_custo}')
                r.centro_custo = nota.centro_custo
                if motivos:
                    r.status, r.mensagem = STATUS_APROVACAO, '; '.join(motivos)
                else:
                    # Antes de repetir um POST com resposta incerta, consulta o ERP.
                    # Evita duplicação se a gravação ocorreu e apenas a resposta se perdeu.
                    async def transacao():
                        r.tentativas += 1
                        if r.tentativas > 1:
                            for registro in await ler_registros_do_erp(robo):
                                if (registro['numero'], registro['cnpj']) == chave:
                                    return registro['protocolo']
                        return await robo.lancar(nota)
                    r.protocolo, _ = await com_retentativas(transacao)
                    r.status = STATUS_SUCESSO
                    ja_no_erp.add(chave)
            except ErroNegocio as e:
                r.status, r.mensagem = STATUS_NEGOCIO, str(e)
            except Exception as e:
                r.status, r.mensagem = STATUS_SISTEMA, str(e)
                # A falha da captura não pode encerrar o lote.
                try:
                    r.evidencia = await robo.evidencia(item.stem)
                except Exception as captura:
                    log.warning('Não foi possível capturar evidência: %s', captura)
            r.duracao_s = round(time.perf_counter() - t0, 4)
            log.info('%s | %s | %s', item.name, r.status, r.protocolo or r.mensagem)
            resultados.append(r)
    log.info('Lote concluído em %.2fs', time.perf_counter() - inicio)
    return resultados


resultados = rodar(executar_robo())
df = pd.DataFrame([asdict(r) for r in resultados])
df_primeiro_lote = df.copy(deep=True)
display(df[['arquivo', 'status', 'numero', 'valor', 'protocolo', 'tentativas', 'mensagem']])
