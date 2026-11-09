"""POC: monta, valida (XSD 1.01), assina e envia uma DPS para a PRODUÇÃO RESTRITA."""
import base64, gzip, hashlib, json, sys, warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cert import carregar, cliente, RESTRITA  # noqa: E402
from lxml import etree  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding  # noqa: E402
from cryptography.hazmat.primitives.serialization import pkcs12  # noqa: E402

NS = "http://www.sped.fazenda.gov.br/nfse"
DS = "http://www.w3.org/2000/09/xmldsig#"
XSD = Path(__file__).parent / "xsd_pr"  # XSD da produção restrita (20/10/2026); baixe e extraia aqui
SAIDA = Path(__file__).parent / "saida"  # fora do git: XML com dados de clientes
BRT = timezone(timedelta(hours=-3))

ALG = {
    "sha256": ("http://www.w3.org/2001/04/xmldsig-more#rsa-sha256", "http://www.w3.org/2001/04/xmlenc#sha256", hashes.SHA256(), hashlib.sha256),
    "sha1": ("http://www.w3.org/2000/09/xmldsig#rsa-sha1", "http://www.w3.org/2000/09/xmldsig#sha1", hashes.SHA1(), hashlib.sha1),
}
C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"  # a Sefin só aceita a canonicalização exclusiva (E0714 com a inclusiva)


def e(pai, tag, texto=None):
    el = etree.SubElement(pai, f"{{{NS}}}{tag}")
    if texto is not None:
        el.text = str(texto)
    return el


def montar(*, cnpj_prest, cmun, serie, ndps, tomador_cnpj, tomador_nome, valor, ctribnac, nbs, desc, simples):
    agora = datetime.now(BRT).replace(microsecond=0) - timedelta(minutes=2)
    id_dps = f"DPS{cmun}2{cnpj_prest}{int(serie):05d}{int(ndps):015d}"
    raiz = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS}, versao="1.01")
    inf = etree.SubElement(raiz, f"{{{NS}}}infDPS", Id=id_dps)
    e(inf, "tpAmb", 2)  # 2 = homologação (produção restrita)
    e(inf, "dhEmi", agora.isoformat())
    e(inf, "verAplic", "ContaskNF-0.1")
    e(inf, "serie", serie)
    e(inf, "nDPS", ndps)
    e(inf, "dCompet", agora.date().isoformat())
    e(inf, "tpEmit", 1)
    e(inf, "finNFSe", 0)  # 0 = NFS-e regular (leiaute RTC)
    e(inf, "cLocEmi", cmun)
    prest = e(inf, "prest")
    e(prest, "CNPJ", cnpj_prest)
    rt = e(prest, "regTrib")
    e(rt, "opSimpNac", 3 if simples else 1)
    if simples:
        e(rt, "regApTribSN", 1)
    e(rt, "regEspTrib", 0)
    toma = e(inf, "toma")
    e(toma, "CNPJ", tomador_cnpj)
    e(toma, "xNome", tomador_nome)
    serv = e(inf, "serv")
    lp = e(serv, "locPrest")
    e(lp, "cLocPrestacao", cmun)
    cs = e(serv, "cServ")
    e(cs, "cTribNac", ctribnac)
    e(cs, "cNBS", nbs)
    e(cs, "xDescServ", desc)
    val = e(inf, "valores")
    vsp = e(val, "vServPrest")
    e(vsp, "vServ", f"{valor:.2f}")
    trib = e(val, "trib")
    tm = e(trib, "tribMun")
    e(tm, "tribISSQN", 1)
    e(tm, "tpRetISSQN", 1)
    tt = e(trib, "totTrib")
    if simples:
        e(tt, "pTotTribSN", "6.00")  # E0712: ME/EPP informa o percentual aproximado do Simples
    else:
        e(tt, "indTotTrib", 0)
    return raiz, id_dps


def assinar(raiz, alvo, chave, cert, alg="sha256"):
    sig_m, dig_m, h, hl = ALG[alg]
    ref_id = alvo.get("Id")
    digest = base64.b64encode(hl(etree.tostring(alvo, method="c14n", exclusive=True)).digest()).decode()
    sig = etree.SubElement(raiz, f"{{{DS}}}Signature", nsmap={None: DS})
    si = etree.SubElement(sig, f"{{{DS}}}SignedInfo")
    etree.SubElement(si, f"{{{DS}}}CanonicalizationMethod", Algorithm=C14N)
    etree.SubElement(si, f"{{{DS}}}SignatureMethod", Algorithm=sig_m)
    ref = etree.SubElement(si, f"{{{DS}}}Reference", URI=f"#{ref_id}")
    tr = etree.SubElement(ref, f"{{{DS}}}Transforms")
    etree.SubElement(tr, f"{{{DS}}}Transform", Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
    etree.SubElement(tr, f"{{{DS}}}Transform", Algorithm=C14N)
    etree.SubElement(ref, f"{{{DS}}}DigestMethod", Algorithm=dig_m)
    etree.SubElement(ref, f"{{{DS}}}DigestValue").text = digest
    assinatura = chave.sign(etree.tostring(si, method="c14n", exclusive=True), padding.PKCS1v15(), h)
    etree.SubElement(sig, f"{{{DS}}}SignatureValue").text = base64.b64encode(assinatura).decode()
    ki = etree.SubElement(sig, f"{{{DS}}}KeyInfo")
    xd = etree.SubElement(ki, f"{{{DS}}}X509Data")
    etree.SubElement(xd, f"{{{DS}}}X509Certificate").text = base64.b64encode(
        cert.public_bytes(serialization.Encoding.DER)).decode()


def validar_xsd(raiz, arquivo="DPS_v1.01.xsd"):
    schema = etree.XMLSchema(etree.parse(str(XSD / arquivo)))
    if not schema.validate(raiz):
        for err in schema.error_log:
            print("XSD:", err.line, err.message)
        raise SystemExit("XML inválido no XSD")
    print("XSD ok")


def chave_e_cert():
    pfx, senha, doc, contab = carregar()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        k, c, _ = pkcs12.load_key_and_certificates(pfx, senha.encode())
    return k, c, doc, contab


def compactar(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode()


def descompactar(b64: str) -> bytes:
    return gzip.decompress(base64.b64decode(b64))


if __name__ == "__main__":
    alg = sys.argv[1] if len(sys.argv) > 1 else "sha256"
    tomador_cnpj, tomador_nome = sys.argv[2], sys.argv[3]
    k, c, doc, contab = chave_e_cert()
    ndps = datetime.now(BRT).strftime("%y%m%d%H%M%S")
    raiz, id_dps = montar(cnpj_prest=doc, cmun="5300108", serie="1", ndps=ndps, tomador_cnpj=tomador_cnpj,
                          tomador_nome=tomador_nome, valor=1.00, ctribnac="171901", nbs="113022100",
                          desc="Servicos de contabilidade - TESTE DE HOMOLOGACAO, SEM VALOR FISCAL", simples=True)
    validar_xsd(raiz)  # antes da assinatura (Signature é opcional no XSD? valida de novo depois)
    assinar(raiz, raiz.find(f"{{{NS}}}infDPS"), k, c, alg)
    validar_xsd(raiz)
    xml = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")
    SAIDA.mkdir(exist_ok=True)
    (SAIDA / f"{id_dps}.xml").write_bytes(xml)
    print("Id", id_dps, "alg", alg)
    with cliente() as http:
        r = http.post("/nfse", json={"dpsXmlGZipB64": compactar(xml)}, headers={"Accept": "application/json"})
    print("HTTP", r.status_code)
    try:
        d = r.json()
    except ValueError:
        print(r.text[:2000]); raise SystemExit(1)
    if d.get("nfseXmlGZipB64"):
        nfse = descompactar(d.pop("nfseXmlGZipB64"))
        (SAIDA / f"NFSe_{d.get('chaveAcesso')}.xml").write_bytes(nfse)
        print("NFS-e salva:", len(nfse), "bytes")
    print(json.dumps(d, ensure_ascii=False, indent=1))
