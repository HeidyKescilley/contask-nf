"""POC: CONTELB (certificado) emite como PRESTADOR a empresa cliente (procuração). Produção restrita."""
import json, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from dps import *  # noqa
prest, tomador, nome_tom, ctrib, nbs = sys.argv[1:6]
k, c, doc, _ = chave_e_cert()
ndps = datetime.now(BRT).strftime("%y%m%d%H%M%S")
raiz, id_dps = montar(cnpj_prest=prest, cmun="5300108", serie="1", ndps=ndps, tomador_cnpj=tomador, tomador_nome=nome_tom,
                      valor=1.00, ctribnac=ctrib, nbs=nbs, desc="TESTE DE HOMOLOGACAO SEM VALOR FISCAL", simples=True)
assinar(raiz, raiz.find(f"{{{NS}}}infDPS"), k, c, "sha256")
validar_xsd(raiz)
xml = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")
(SAIDA / f"{id_dps}.xml").write_bytes(xml)
with cliente() as http:
    r = http.post("/nfse", json={"dpsXmlGZipB64": compactar(xml)})
d = r.json()
if d.get("nfseXmlGZipB64"):
    (SAIDA / f"NFSe_{d.get('chaveAcesso')}.xml").write_bytes(descompactar(d.pop("nfseXmlGZipB64")))
print("HTTP", r.status_code, json.dumps(d, ensure_ascii=False, indent=1))
