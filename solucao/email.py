from email.message import EmailMessage
from email import policy
from email.parser import BytesParser


def gerar_email(df, arquivo_excel) -> Path:
    msg = EmailMessage()
    msg['From'] = 'robo.ap@transvia.com.br'
    msg['To'] = 'gerencia.ap@transvia.com.br'
    msg['Subject'] = f'Contas a pagar | {dt.date.today():%d/%m/%Y} | {len(df)} notas'
    resumo_status = df.status.value_counts().to_dict()
    linhas = ['Resumo do processamento de contas a pagar:', '']
    for status in [STATUS_SUCESSO, STATUS_NEGOCIO, STATUS_SISTEMA, STATUS_APROVACAO]:
        linhas.append(f'{status}: {resumo_status.get(status, 0)}')
    linhas.extend(['', 'Notas para análise humana:'])
    pendentes = df[df.status != STATUS_SUCESSO]
    if pendentes.empty:
        linhas.append('Nenhuma pendência.')
    for r in pendentes.itertuples():
        linhas.append(f'- {r.arquivo} | NF {r.numero or "não extraída"} | {r.status} | {r.mensagem}')
    msg.set_content('\n'.join(linhas))
    arquivo_excel = Path(arquivo_excel)
    msg.add_attachment(arquivo_excel.read_bytes(), maintype='application',
        subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=arquivo_excel.name)
    caminho = PASTA_SAIDA / 'resumo_lote.eml'
    caminho.write_bytes(msg.as_bytes(policy=policy.SMTP))
    return caminho


arquivo_email = gerar_email(df_primeiro_lote, arquivo_rel)
email_lido = BytesParser(policy=policy.default).parsebytes(arquivo_email.read_bytes())
anexos = list(email_lido.iter_attachments())
assert len(anexos) == 1 and anexos[0].get_payload(decode=True) == arquivo_rel.read_bytes()
assert str(len(df_primeiro_lote)) in str(email_lido['Subject'])
print('E-mail validado (incluindo integridade do anexo):', arquivo_email)
