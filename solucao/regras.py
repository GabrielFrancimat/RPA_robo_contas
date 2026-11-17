# Validações de negócio: validar antes de reservar uma chave no lote.
import math

STATUS_SUCESSO = 'SUCESSO'
STATUS_NEGOCIO = 'EXCECAO_NEGOCIO'
STATUS_SISTEMA = 'EXCECAO_SISTEMA'
STATUS_APROVACAO = 'PENDENTE_APROVACAO'


def validar_nota(nota: NotaFiscal, chaves_ja_vistas: set) -> str | None:
    if not isinstance(nota.numero, str) or not re.fullmatch(r'[0-9]+', nota.numero):
        raise ErroNegocio('Número de nota ausente ou inválido')
    for nome in ['prestador', 'descricao']:
        valor = getattr(nota, nome)
        if not isinstance(valor, str) or not valor.strip():
            raise ErroNegocio(f'Campo obrigatório vazio: {nome}')
    try:
        if not re.fullmatch(r'[0-9]{2}/[0-9]{2}/[0-9]{4}', nota.data_emissao):
            raise ValueError('Formato de data inválido')
        dt.datetime.strptime(nota.data_emissao, '%d/%m/%Y')
    except (TypeError, ValueError):
        raise ErroNegocio('Data de emissão inválida: informe uma data real em dd/mm/aaaa')
    if not cnpj_valido(nota.cnpj):
        raise ErroNegocio(f'CNPJ inválido: {nota.cnpj}')
    if isinstance(nota.valor, bool) or not isinstance(nota.valor, (int, float)) or not math.isfinite(nota.valor) or nota.valor <= 0:
        raise ErroNegocio('Valor deve ser um número finito e positivo')
    if nota.centro_custo and nota.centro_custo not in CENTROS:
        raise ErroNegocio(f'Centro de custo inválido: {nota.centro_custo}')
    chave = (nota.numero, limpar_cnpj(nota.cnpj))
    if chave in chaves_ja_vistas:
        raise ErroNegocio(f'NF {nota.numero} duplicada para o CNPJ {nota.cnpj}')
    chaves_ja_vistas.add(chave)
    return STATUS_APROVACAO if nota.valor > LIMITE_APROVACAO else None
