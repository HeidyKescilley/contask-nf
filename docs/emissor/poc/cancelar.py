"""POC: cancela (evento 101101) uma NFS-e da PRODUÇÃO RESTRITA."""
import json, sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dps import (BRT, NS, SAIDA, assinar, chave_e_cert, cliente, compactar, descompactar, etree, validar_xsd)  # noqa: E402

chave_nfse = sys.argv[1]
k, c, doc, _ = chave_e_cert()
agora = datetime.now(BRT).replace(microsecond=0) - timedelta(minutes=1)

raiz = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS}, versao="1.01")
inf = etree.SubElement(raiz, f"{{{NS}}}infPedReg", Id=f"PRE{chave_nfse}101101")
for tag, val in [("tpAmb", 2), ("verAplic", "ContaskNF-0.1"), ("dhEvento", agora.isoformat()),
                 ("CNPJAutor", doc), ("chNFSe", chave_nfse)]:
    etree.SubElement(inf, f"{{{NS}}}{tag}").text = str(val)
ev = etree.SubElement(inf, f"{{{NS}}}e101101")
etree.SubElement(ev, f"{{{NS}}}xDesc").text = "Cancelamento de NFS-e"
etree.SubElement(ev, f"{{{NS}}}cMotivo").text = "1"  # 1 = erro na emissão
etree.SubElement(ev, f"{{{NS}}}xMotivo").text = "Teste de homologacao do Contask NF, nota sem valor fiscal"

validar_xsd(raiz, "pedRegEvento_v1.01.xsd")
assinar(raiz, inf, k, c, "sha256")
validar_xsd(raiz, "pedRegEvento_v1.01.xsd")
xml = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")
(SAIDA / f"PRE_{chave_nfse}.xml").write_bytes(xml)
with cliente() as http:
    r = http.post(f"/nfse/{chave_nfse}/eventos", json={"pedidoRegistroEventoXmlGZipB64": compactar(xml)})
print("HTTP", r.status_code)
d = r.json()
if d.get("eventoXmlGZipB64"):
    evx = descompactar(d.pop("eventoXmlGZipB64"))
    (SAIDA / f"EVT_{chave_nfse}_101101.xml").write_bytes(evx)
    print("evento salvo:", len(evx), "bytes")
print(json.dumps(d, ensure_ascii=False, indent=1))
