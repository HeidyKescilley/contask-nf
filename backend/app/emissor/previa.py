"""Prévia da nota antes da transmissão: o PDF no leiaute do DANFSe, sem valor fiscal.

A DPS é montada com as mesmas regras da emissão (motor._preencher + dps.montar), mas não é assinada,
não gasta número e não vai para a Sefin. Ela é embrulhada numa NFS-e fictícia, só com o que o
DANFSe lê do grupo infNFSe (emitente, municípios e valores estimados), e desenhada pelo gerador
próprio (danfse.gerar_danfse com previa=True). Nada é gravado no banco.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from lxml import etree
from sqlalchemy.orm import Session

from app.emissor import tabelas
from app.emissor.dps import NS, BRASILIA, DpsInvalida, id_dps, montar, montar_issnet
from app.fiscal.danfse import gerar_danfse, municipio_uf
from app.models import Empresa, NotaEmitida

MARCA = "PRÉVIA"


def _e(pai, tag: str, valor=None):
    el = etree.SubElement(pai, f"{{{NS}}}{tag}")
    if valor is not None and valor != "":
        el.text = str(valor)
    return el


def _dig(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _municipio(cod: str | None) -> str | None:
    m = municipio_uf(cod)
    return m.split(" / ")[0] if m else None


def _emitente(inf, e: Empresa, cfg) -> None:
    """Grupo emit da NFS-e: na nota real vem do cadastro da Receita; aqui, dos dados da BrasilAPI."""
    b = e.dados_brasilapi or {}
    em = _e(inf, "emit")
    _e(em, "CNPJ", e.cnpj)
    if cfg.inscricao_municipal:
        _e(em, "IM", cfg.inscricao_municipal.strip())
    _e(em, "xNome", e.razao_social)
    end = _e(em, "enderNac")
    for tag, valor in (("xLgr", " ".join(x for x in (b.get("descricao_tipo_de_logradouro"), b.get("logradouro")) if x)),
                       ("nro", b.get("numero")), ("xCpl", b.get("complemento")), ("xBairro", b.get("bairro")),
                       ("cMun", cfg.cod_municipio), ("UF", e.uf or b.get("uf")), ("CEP", _dig(b.get("cep")))):
        if valor:
            _e(end, tag, str(valor).strip())
    if _dig(b.get("ddd_telefone_1")):
        _e(em, "fone", _dig(b.get("ddd_telefone_1")))
    if b.get("email"):
        _e(em, "email", str(b["email"]).lower())


def _valores(inf, nota: NotaEmitida) -> None:
    """Estimativa dos valores que a Sefin calcula na autorização. Sem alíquota informada (fora do Simples
    a alíquota é a do município), o ISS fica em branco e o líquido não desconta ISS retido."""
    base = nota.valor_servico - nota.desconto
    iss = (base * nota.aliquota_iss / 100).quantize(Decimal("0.01")) if nota.aliquota_iss else None
    federais = nota.ret_pis + nota.ret_cofins + nota.ret_csll + nota.ret_irrf + nota.ret_cp
    retido = federais + (iss if nota.iss_retido and iss else Decimal("0"))
    v = _e(inf, "valores")
    _e(v, "vBC", f"{base:.2f}")
    if nota.aliquota_iss:
        _e(v, "pAliqAplic", f"{nota.aliquota_iss:.2f}")
        _e(v, "vISSQN", f"{iss:.2f}")
    if retido > 0:
        _e(v, "vTotalRet", f"{retido:.2f}")
    _e(v, "vLiq", f"{max(base - retido, Decimal('0')):.2f}")


def nfse_previa(dps_raiz, e: Empresa, cfg, nota: NotaEmitida) -> bytes:
    raiz = etree.Element(f"{{{NS}}}NFSe", nsmap={None: NS}, versao="1.01")
    inf = etree.SubElement(raiz, f"{{{NS}}}infNFSe", Id="NFS")
    _e(inf, "xLocEmi", _municipio(cfg.cod_municipio))
    _e(inf, "xLocPrestacao", _municipio(nota.cod_municipio_prestacao))
    serv = tabelas.servico(nota.ctribnac)
    if serv:
        _e(inf, "xTribNac", serv["descricao"])
    _e(inf, "ambGer", 2)
    _emitente(inf, e, cfg)
    _valores(inf, nota)
    inf.append(dps_raiz)
    return etree.tostring(raiz, encoding="utf-8")


def gerar(db: Session, esc: int, ent) -> tuple[bytes, NotaEmitida]:
    """PDF da prévia. Valida como na emissão (mensagens de erro iguais), mas não exige certificado:
    a prévia serve para conferir os dados antes de a empresa estar pronta para transmitir."""
    from app.api.emissor import config_prestador
    from app.emissor import motor
    from app.emissor.municipio import garantir_municipio

    e = db.get(Empresa, ent.empresa_id)
    if e is None or e.escritorio_id != esc:
        raise motor.ErroEmissao("Empresa não encontrada.", 404)
    cfg = config_prestador(db, e)
    if not garantir_municipio(db, e, cfg):
        raise motor.ErroEmissao("Não foi possível descobrir o código IBGE do município da empresa. Confira o município "
                                "e a UF no cadastro da empresa ou informe o código nos dados do prestador.")
    canal = motor.canal(cfg)
    nota = NotaEmitida(escritorio_id=esc, empresa_id=e.id, ambiente=motor.ambiente(cfg), serie=cfg.serie,
                       numero=cfg.proximo_numero if canal == motor.NACIONAL else 1, situacao="previa", canal=canal)
    try:
        motor._preencher(db, nota, e, cfg, ent)
        nota.id_dps = id_dps(cfg.cod_municipio, e.cnpj, nota.serie, nota.numero)
        dados = motor._dados(e, cfg, nota)
        dados.emitido_em = datetime.now(BRASILIA)
        dps = montar_issnet(dados) if canal == motor.ISSNET_DF else montar(dados)
    except DpsInvalida as ex:
        raise motor.ErroEmissao(str(ex)) from None
    finally:
        if nota in db:  # a prévia nunca vira registro
            db.expunge(nota)
    return gerar_danfse(nfse_previa(dps, e, cfg, nota), marca_dagua=MARCA, previa=True), nota
