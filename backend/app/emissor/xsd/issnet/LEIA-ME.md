# XSD do ISSNet do DF

- `schema_v101.xsd`: schema da Nota Control (manual v1.01 de 03/08/2026), baixado em 15/11/2026.
- `xmldsig-core-schema.xsd`: cópia do mesmo arquivo usado nos XSD da Sefin.

Ajuste local: o tipo `TSSerieDPS` vinha com `^0{0,4}\d{1,5}$`. Em XSD, `^` e `$` não são âncoras, são
caracteres literais, e o lxml recusava qualquer série. Trocado por `0{0,4}\d{1,5}`, que é o que o ISSNet aceita.
