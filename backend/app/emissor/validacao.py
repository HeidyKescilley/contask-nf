"""Validação da nota antes da transmissão: tudo o que dá para conferir sem enviar à Sefin.

Roda as mesmas etapas da emissão até o ponto do envio (empresa e certificado, regras da NFS-e, montagem,
assinatura e esquema oficial) e acrescenta consultas só de leitura que antecipam recusas comuns:
- o município emissor aderiu ao emissor nacional (convênio);
- o código de serviço tem alíquota publicada no município (sem ela, a Sefin pode recusar com E0312);
- o CNPJ do prestador está estabelecido no município emissor (E0084).
Nada é gravado, nenhum número é reservado e nada vai para a Sefin.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.emissor import parametros
from app.emissor.dps import DpsInvalida, id_dps
from app.models import Empresa, NotaEmitida

OK, ALERTA, ERRO, PULADO = "ok", "alerta", "erro", "pulado"


@dataclass
class Item:
    id: str
    titulo: str
    situacao: str
    detalhe: str


def _municipio(cod: str | None) -> str:
    from app.fiscal.danfse import municipio_uf
    return municipio_uf(cod) or (cod or "-")


def validar(db: Session, esc: int, ent) -> dict:
    from app.api.emissor import certificado_emissor, emite_por_procuracao
    from app.core.certificados import carregar_pfx
    from app.core.config import config
    from app.core.escritorios import em_teste, emissoes_do_escritorio
    from app.emissor import motor

    itens: list[Item] = []

    def fim(ambiente: int | None = None, canal: str | None = None) -> dict:
        db.rollback()
        erros = [i for i in itens if i.situacao == ERRO]
        alertas = [i for i in itens if i.situacao == ALERTA]
        return {"pronta": not erros, "erros": len(erros), "alertas": len(alertas), "ambiente": ambiente, "canal": canal,
                "itens": [asdict(i) for i in itens]}

    corrige = bool(ent.substituicao and ent.substituicao.get("nota_id"))
    if not corrige and em_teste(db, esc) and emissoes_do_escritorio(db, esc) >= config().teste_max_emissoes:
        itens.append(Item("teste", "Teste grátis", ERRO, f"A emissão do teste grátis ({config().teste_max_emissoes} nota) já foi usada."))

    # 1. Empresa, certificado e canal
    try:
        e, cfg = motor._empresa_pronta(db, esc, ent.empresa_id)
    except motor.ErroEmissao as ex:
        itens.append(Item("empresa", "Empresa e certificado", ERRO, str(ex)))
        return fim()
    cert = certificado_emissor(db, e)
    amb, canal = motor.ambiente(cfg), motor.canal(cfg)
    via = "Assina por procuração, com o certificado da contabilidade" if emite_por_procuracao(db, e)         else "Assina com o certificado da própria empresa"
    itens.append(Item("empresa", "Empresa e certificado", OK,
                      f"{via}: {cert.titular_nome}, válido até {cert.validade:%d/%m/%Y}. "
                      f"{'Produção (nota com valor fiscal)' if amb == 1 else 'Homologação (sem valor fiscal)'}, "
                      f"{'ISSNet do DF' if canal == motor.ISSNET_DF else 'Sefin Nacional'}."))

    # 2. Prestador estabelecido no município emissor (E0084)
    cod_receita = str((e.dados_brasilapi or {}).get("codigo_municipio_ibge") or "")
    if cod_receita and cod_receita != cfg.cod_municipio:
        itens.append(Item("municipio", "Município do prestador", ALERTA,
                          f"Na Receita o CNPJ está em {_municipio(cod_receita)}, mas a nota sai por {_municipio(cfg.cod_municipio)}. "
                          "A Sefin recusa quando o prestador não tem estabelecimento no município emissor (E0084)."))
    else:
        itens.append(Item("municipio", "Município do prestador", OK, f"Emissão por {_municipio(cfg.cod_municipio)}."))

    # 3. Regras da NFS-e, montagem, assinatura e esquema oficial (o mesmo caminho da emissão, sem enviar)
    nota = NotaEmitida(escritorio_id=esc, empresa_id=e.id, ambiente=amb, serie=cfg.serie,
                       numero=cfg.proximo_numero if canal == motor.NACIONAL else 1, situacao="validacao", canal=canal)
    try:
        motor._preencher(db, nota, e, cfg, ent)
        if ent.substituicao:
            nota.subst_chave, _ = motor._substituida(db, esc, e, amb, ent.substituicao)
            nota.subst_motivo = ent.substituicao.get("motivo")
            nota.subst_justificativa = " ".join((ent.substituicao.get("justificativa") or "").split())
        nota.id_dps = id_dps(cfg.cod_municipio, e.cnpj, nota.serie, nota.numero)
        motor._xml_assinado(db, e, cfg, nota)
        itens.append(Item("xml", "Regras da NFS-e e esquema oficial", OK,
                          "Dados conferidos com as regras da NFS-e; o XML foi montado, assinado e passou no esquema oficial (XSD)."))
    except (motor.ErroEmissao, DpsInvalida) as ex:
        itens.append(Item("xml", "Regras da NFS-e e esquema oficial", ERRO, str(ex)))
    except Exception as ex:  # noqa: BLE001 - certificado ilegível, etc.
        itens.append(Item("xml", "Regras da NFS-e e esquema oficial", ERRO, f"Não foi possível montar e assinar o XML: {type(ex).__name__}."))
    finally:
        if nota in db:
            db.expunge(nota)

    # 4. Parametrização do município (Sefin Nacional; o ISSNet do DF tem regras próprias)
    if canal != motor.NACIONAL:
        itens.append(Item("convenio", "Parâmetros do município", PULADO,
                          "No ISSNet do DF a alíquota vem do cadastro da empresa no próprio ISSNet."))
        return fim(amb, canal)
    if not nota.ctribnac:
        return fim(amb, canal)
    try:
        pfx, senha = carregar_pfx(cert)
        with parametros.fabrica(pfx, senha) as cli:
            del senha
            conv = cli.convenio(cfg.cod_municipio)
            if conv.aderente_emissor_nacional:
                itens.append(Item("convenio", "Convênio do município", OK, f"{_municipio(cfg.cod_municipio)} usa o emissor nacional."))
            else:
                itens.append(Item("convenio", "Convênio do município", ERRO,
                                  f"{_municipio(cfg.cod_municipio)} não aderiu ao emissor nacional: a Sefin recusa a DPS."))
            codigo = parametros.codigo_servico(nota.ctribnac, nota.ctribmun)
            cmun = nota.cod_municipio_prestacao or cfg.cod_municipio
            a = cli.aliquota(cmun, codigo, nota.competencia)
            if a.encontrada:
                aliq = f"{a.aliquota:.2f}".replace(".", ",") + "%" if a.aliquota is not None else "publicada"
                itens.append(Item("aliquota", "Código de serviço no município", OK,
                                  f"{codigo} tem alíquota de ISS {aliq} em {_municipio(cmun)} na competência."))
            else:
                itens.append(Item("aliquota", "Código de serviço no município", ALERTA,
                                  f"{_municipio(cmun)} não publica alíquota para {codigo} na competência. Muitas notas assim são "
                                  "autorizadas, mas a Sefin pode recusar o código (E0312): confira o código de tributação "
                                  "e, se o município usar, o código municipal de 3 dígitos."))
    except parametros.ErroParametros as ex:
        itens.append(Item("convenio", "Parâmetros do município", ALERTA, f"Não foi possível consultar agora: {ex}."))
    except Exception as ex:  # noqa: BLE001
        itens.append(Item("convenio", "Parâmetros do município", ALERTA, f"Não foi possível consultar agora ({type(ex).__name__})."))
    return fim(amb, canal)
