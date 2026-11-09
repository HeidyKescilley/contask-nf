# Emissor de NFS-e: notas técnicas (prova de 09/11/2026)

Resultado da Etapa 1, a prova técnica na **produção restrita**: uma NFS-e foi emitida, consultada e cancelada. Os scripts estão em [poc/](poc/). Eles leem o certificado da contabilidade do banco local, só para leitura.

## Endereços e formato

| Ambiente | Sefin Nacional (emissão, consulta, eventos) | Parâmetros municipais |
|---|---|---|
| Produção restrita (`tpAmb=2`) | `https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional` | `https://adn.producaorestrita.nfse.gov.br/parametrizacao` |
| Produção (`tpAmb=1`) | `https://sefin.nfse.gov.br/SefinNacional` | `https://adn.nfse.gov.br/parametrizacao` |

- **Conexão:** todas as rotas exigem mTLS com certificado ICP-Brasil, inclusive o swagger, que fica em `/swagger/docs/v1` (Sefin) e em `/parametrizacao/swagger/v1/swagger.json`.
- **`POST /nfse`:**
  - envio: `{"dpsXmlGZipB64": "<DPS assinada, gzip, base64>"}`;
  - **201**: `chaveAcesso` e `nfseXmlGZipB64`;
  - **400**: `erros[]`, com os campos `Codigo`, `Descricao` e `Complemento`.
- **`HEAD /dps/{idDPS}`:** 200 se a nota existe, 404 se não existe. `GET /dps/{idDPS}` devolve a `chaveAcesso`.
  - **Uso no sistema:** quando a conexão cair no meio do envio, consultar aqui antes de reenviar, para nunca duplicar a nota.
- **`GET /nfse/{chave}`:** devolve o XML da NFS-e.
- **`POST /nfse/{chave}/eventos`:**
  - envio: `{"pedidoRegistroEventoXmlGZipB64": ...}`;
  - **201**: `eventoXmlGZipB64`.

## Regras aprendidas na prática

1. **Assinatura:** XMLDSig envelopada, com a referência `#Id` no `infDPS` (ou no `infPedReg`).
   - A canonicalização tem que ser a **exclusiva** (`http://www.w3.org/2001/10/xml-exc-c14n#`), tanto no método quanto no transform. Com a C14N inclusiva, a Sefin devolve **E0714**, mesmo com a assinatura válida.
   - A Sefin aceita RSA-SHA256 e RSA-SHA1. Vamos usar SHA-256.
2. **A declaração `<?xml ... encoding="UTF-8"?>` é obrigatória.** Sem ela, a Sefin devolve E1229.
3. **Leiautes diferentes por ambiente:**
   - A produção restrita já usa o leiaute da reforma (XSD de 20/10/2026):
     - `finNFSe` vai logo depois de `tpEmit`;
     - em `cServ`, a ordem é `cNBS` e depois `xDescServ`.
   - A produção ainda usa o XSD v1.01 de 09/02/2026, em que `xDescServ` vem antes de `cNBS` e não existe `finNFSe`.
   - O gerador de XML precisa ter o leiaute versionado por ambiente.
4. **Erro no XSD oficial de produção:** o padrão da série é `^0{0,4}\d{1,5}$`, e em XSD os caracteres `^` e `$` são literais. Na validação local, use o padrão sem eles.
5. **Id da DPS:** `DPS` + código IBGE do município (7) + tipo de inscrição (`2` = CNPJ) + CNPJ (14) + série (5, com zeros à esquerda) + número (15).
   - A série vai de 00001 a 49999 para aplicativo próprio.
   - Série, número, município e CNPJ repetidos geram **E0014**.
6. **Prestador emitente:** não informar o `xNome` nem o endereço (**E0121**). Esses dados vêm do cadastro nacional.
7. **Empresa do Simples (ME/EPP):** usar `totTrib/pTotTribSN`, e não `indTotTrib` (**E0712**). Também é obrigatório `regApTribSN`.
8. **Cancelamento (evento 101101):**
   - Id: `PRE` + chave (50) + `101101`;
   - `xDesc` deve ser exatamente "Cancelamento de NFS-e";
   - `cMotivo`: 1 = erro na emissão, 2 = serviço não prestado, 9 = outros;
   - `xMotivo` precisa ter de 15 a 255 caracteres.
9. **Procuração não serve para emitir.** Assinando com o certificado da contabilidade em nome de uma empresa cliente, a Sefin devolve **E0718**: "A assinatura deve ser feita com o certificado digital do emitente da DPS".
   - **Consequência:** toda empresa que emite pelo Contask precisa ter o **próprio certificado A1** cadastrado.

## Motor de emissão (Etapa 3, testado na produção restrita em 09/11/2026)

O código fica em `backend/app/emissor/`:
- `dps.py`: montagem com os dois leiautes e as regras;
- `assinatura.py`;
- `sefin.py`: o cliente da Sefin;
- `motor.py`: numeração, envio, recuperação e cancelamento.

O teste foi feito com a CONTELB (ME/EPP do Simples) emitindo para um tomador do DF:

| Caso | Resultado |
|---|---|
| Sem retenção | Autorizada |
| PIS, COFINS, CSLL e IRRF retidos (`piscofins` com CST `00` + `tpRetPisCofins=3`, `vRetCSLL` = soma das três, `vRetIRRF`) | Autorizada, valor líquido de R$ 938,50 sobre R$ 1.000 |
| Tomador com endereço e desconto incondicionado | Autorizada |
| ISS retido sem endereço do tomador | **E0237**: com ISS retido, o endereço nacional do tomador é obrigatório (a validação local já cobra isso) |
| A mesma DPS reenviada com endereço e **mesmo número** | Autorizada, com ISS de 2% (R$ 4,00) |
| DANFSe local da nota emitida | Gerada |
| Cancelamento (evento 101101) | Aceito |

**Numeração:**
- O número da DPS é reservado e gravado antes do envio.
- Uma nota rejeitada ou pendente é reenviada com o **mesmo** número. Não fica buraco na numeração, e a Sefin não aceita duplicidade (E0014).
- **Se a conexão cair:** o sistema consulta `GET /dps/{id}` antes de qualquer reenvio. Se a nota existe, ela é baixada e marcada como autorizada.

**Ambiente:** o emissor só vai para a produção com `CONTASK_EMISSOR_PRODUCAO=true`. Sem isso, usa a produção restrita, com `tpAmb=2`.

**Alíquota (`pAliq`):** só é informada para ME/EPP do Simples com ISS dentro do Simples e ISS retido.
- Nesse caso, quem emite informa a alíquota efetiva.
- Nos demais casos com convênio ativo, a Sefin usa a parametrização do município, e informar a alíquota gera rejeição (E0617, E0625, E0635).
- MEI e empresa com regime especial nunca informam (E0600, E0604).

**Inscrição municipal do prestador:** só pode ser informada se o município tiver as informações complementares da empresa no CNC. Sem isso, a Sefin devolve E0120. Isso aconteceu com a CONTELB no DF.

**Tela de emissão (Etapa 4, testada na produção restrita em 09/11/2026):**
- emissão completa pela tela: tomador buscado na BrasilAPI, ISS retido com alíquota do Simples e IRRF de 1,5%, NFS-e nº 6;
- cancelamento pela lista de notas emitidas;
- correção de uma nota rejeitada por E0120, reenviada com o mesmo número da DPS e autorizada como NFS-e nº 7.

**Piloto em produção (09/11/2026):** a CONTELB emitiu uma NFS-e real de R$ 20,00 no leiaute v1.01 de produção, que foi autorizada na primeira tentativa (DPS série 1 nº 1, NFS-e nº 2). O número da NFS-e é dado pela Sefin e segue a sequência da empresa, que já incluía notas emitidas fora do Contask. A nota foi cancelada em seguida (evento 101101, motivo 1), e a Sefin de produção aceitou o cancelamento.

**Grupo IBS/CBS:** ainda não é enviado. É opcional nos dois leiautes e foi aceito sem ele. Os códigos `cIndOp` e `cClassTrib` já ficam guardados no serviço para quando o grupo passar a ser exigido.

## Parâmetros municipais (somente leitura, também em produção)

- `GET /parametrizacao/{ibge}/convenio`: o DF (5300108) tem `aderenteEmissorNacional=1`.
- `GET /parametrizacao/{ibge}/{item}/{AAAA-MM-DD}/aliquota`: o item vai no formato **`17.19.01.000`**. Exemplo: 17.19.01 no DF tem alíquota de 5,00%.
  - **Uso no sistema:** preencher a alíquota de ISS automaticamente.
- `GET /parametrizacao/{ibge}/{AAAA-MM-DD}/retencoes`: retenções obrigatórias do município. No DF, devolve 404, porque não há nenhuma cadastrada.

## Tabelas oficiais para o cadastro de serviços

- **Anexo B:** lista dos códigos de tributação nacional (6 dígitos) e das NBS.
- **Anexo VIII** (tabela de correlação, v1.02.00 de 26/10/2026): relaciona item da LC 116, NBS, cIndOp e cClassTrib.
  - **Uso no sistema:** sugerir os códigos de um serviço automaticamente.
