# Esquemas XSD oficiais da NFS-e

- `producao/`: NFSe-ESQUEMAS_XSD v1.01 de 09/02/2026 (documentação atual, produção).
- `restrita/`: NFSe-ESQUEMAS_XSD-PRODREST v1.01 de 20/10/2026 (produção restrita, leiaute da reforma).

Fonte: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica

Única alteração local: em `producao/tiposSimples_v1.01.xsd`, o padrão da série estava `^0{0,4}\d{1,5}$`.
Em XSD, `^` e `$` são literais, então o padrão foi trocado por `0{0,4}\d{1,5}`.
