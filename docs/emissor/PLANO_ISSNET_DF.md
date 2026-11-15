# Plano: emissão pelo ISSNet do DF (Lucro Presumido e Real)

Plano aprovado em 15/11/2026.

**Andamento (15/11/2026): emissão em produção funcionando.** Primeira nota real: VCS TRANSPORTES (Lucro
Presumido), NFS-e nº 179, R$ 1,00, RPS série 3 nº 1, emitida pela API do Contask com os dados confirmados.

Pronto: canal por empresa, DPS no leiaute do ISSNet (`dps.montar_issnet`), envio/recuperação/cancelamento no
motor, monitoramento dos RPS (tabelas, sincronização, reserva, "usado fora", alertas), tela de RPS, cTribMun do
DF (`issnet/ctribmun_df.json`, da planilha de correlação) e testes com o ISSNet simulado.

O que a produção mostrou e o manual não diz (ver `issnet/soap.py`, `motor.py` e `dps.py`):
- envelope: XML de dados e cabeçalho EMBUTIDOS (não escapados), `nfseDadosMsg` antes de `nfseCabecMsg`, prefixo
  `ws` declarado no Envelope; a resposta vem direto em `{Metodo}Response`; métodos `ConsultarNfseDps` e
  `ConsultarNfsePorFaixa` (nomes do WSDL);
- assinatura: o perfil do manual (C14N inclusiva + RSA-SHA1) volta E0714; vale o da Sefin (C14N exclusiva +
  RSA-SHA256). O motor tenta o outro perfil uma vez se vier E0714 (não gera nota);
- acentos vão como referência numérica (`&#231;`);
- `dhEmi` 2 minutos no passado (E0008), `pTotTrib` para não optante (E0713), endereço obrigatório para tomador
  com CNPJ (E0235);
- `ConsultarDpsDisponivel` além da última página responde E319 (fim da lista);
- `ValidarXml` valida só o schema, não a assinatura.

Sem homologação (decisão de 15/11/2026): empresa do ISSNet emite sempre em produção. Pendente: confirmar se as notas do ISSNet
chegam ao ADN (fase 6).

A emissão continua barrada (E0084) até a fase 3 ser testada na homologação.

## 1. Escopo

- Vale **só** para empresas com endereço no DF (`cod_municipio = 5300108`) e regime **Lucro Presumido ou Lucro Real**.
- O Simples e o MEI continuam no Emissor Nacional (Sefin), como hoje.
- Hoje essas empresas são barradas com a mensagem do E0084 (`bloqueio_municipio` em `motor.py`). Com o plano, o sistema passa a escolher sozinho o canal certo:

| Empresa | Canal |
|---|---|
| DF fora do Simples | ISSNet DF |
| Qualquer outra | Sefin Nacional |

- A pessoa usa as mesmas telas de emitir, rascunho, duplicar, recorrentes, cancelar e corrigir e reenviar. O que muda é o canal por trás.

## 2. O que o estudo mostrou

Fonte principal: *Manual de Integração Webservice – NFS-e Padrão Nacional*, v1.01 de 03/08/2026, da Nota Control (empresa do ISSNet). A Receita do DF indica esse manual no Portal de Serviços.

### 2.1 O ABRASF 2.04 acabou no DF

- Desde **01/10/2026** o DF só aceita, pelo webservice, documentos no **Padrão Nacional**. O ABRASF 2.04 foi desligado.
- Por isso o leiaute antigo (RPS ABRASF, `GerarNfseEnvio` 2.04) não entra no plano.

| Ambiente | Endereço |
|---|---|
| Produção | `https://nfse.fazenda.df.gov.br/wsnfsenacional/nfse.asmx` |
| Homologação | `https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/nfse.asmx` (compartilhada por todos os municípios do ISSNet) |
| Validador de XML | `https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/validarxml` |

### 2.2 É quase a mesma DPS que já montamos

O XML é a **DPS nacional**: mesmo namespace `http://www.sped.fazenda.gov.br/nfse`, mesmo `infDPS`, mesmo Id de 45 posições. Dá para reaproveitar boa parte de `app/emissor/dps.py`.

As diferenças são estas:

| Ponto | Sefin Nacional (hoje) | ISSNet DF |
|---|---|---|
| Transporte | REST, JSON com DPS em gzip+base64 | **SOAP 1.1** document/literal, XML como texto, com um `cabecalho` (`versao`/`versaoDados` 1.00 ou 1.01) |
| Assinatura | exc-c14n + RSA-SHA256 | **C14N inclusiva + RSA-SHA1** (DigestMethod sha1) |
| Lote | não existe | lote opcional. O lote também é assinado. Um erro rejeita o lote inteiro |
| `cTribMun` | opcional, 3 dígitos | **obrigatório**, até 10 dígitos. É o código de tributação municipal do DF |
| Inscrição municipal | dá E0120 no DF | **obrigatória**: identifica o prestador em todas as consultas (CNPJ + IM) |
| Grupo IBSCBS | opcional no leiaute de produção | o manual o torna **obrigatório para competência após 01/10/2026** (cabeçalho 1.01) |
| Alíquota do ISS | informada | **não informar**, porque o ISSNet calcula. Só se informa quando o ISS é devido fora do DF |
| Numeração da DPS | o emitente controla (`proximo_numero`) | **o fisco controla**: a empresa usa os números liberados para ela (ver 2.4) |

### 2.3 Métodos do webservice

| Método | Tipo | Uso no Contask |
|---|---|---|
| `GerarNfse` | síncrono, 1 DPS | **emissão** (é o que usaremos) |
| `RecepcionarLoteDpsSincrono` | síncrono, lote | não usar no início |
| `RecepcionarLoteDps` + `ConsultarLoteDps` | assíncrono, com protocolo | não usar no início |
| `ConsultarNfsePorDps` | síncrono | recuperar o resultado depois de falha de rede, antes de reenviar |
| `CancelarNfse` | síncrono | cancelamento. Usa o mesmo `pedRegEvento` (e101101) da Sefin |
| `ConsultarDpsDisponivel` | síncrono, 50 por página | **monitoramento dos RPS** |
| `ConsultarDadosCadastrais` | síncrono | conferir CNPJ + IM e o cadastro no ISSNet |
| `ConsultarNfseServicoPrestado` / `ServicoTomado` / `Faixa` | síncrono, 50 por página | trazer notas, caso não cheguem pelo ADN |
| `ConsultarUrlNfse` | síncrono | link oficial de visualização e autenticidade |

A substituição é uma DPS com o grupo `subst` (chave da nota substituída). O ISSNet cancela a antiga e gera a nova.

### 2.4 RPS / DPS: numeração do fisco

- O manual diz: *"A numeração das DPS é de responsabilidade da prefeitura"*.
- `ConsultarDpsDisponivel` devolve a lista de **série + número** que a empresa ainda pode usar.
- Ou seja, a empresa precisa ter números liberados no ISSNet. Quando acabam, ela não emite até pedir mais.

O monitoramento dos RPS (seção 4) parte disso. Eu entendi "manter o monitoramento" assim:

- saber quantos números a empresa ainda tem;
- avisar antes de acabarem;
- acompanhar cada RPS usado até virar nota, ou até ser rejeitado ou ficar pendente.

### 2.5 Certificado e procuração

São usados dois certificados ICP-Brasil, A1 ou A3, e o tipo S não é aceito:

| Uso | De quem pode ser |
|---|---|
| **Transmissão** (mTLS) | CNPJ de quem transmite, que **pode ser outro** (a contabilidade). Precisa de "Autenticação Cliente" |
| **Assinatura** da DPS | **CNPJ do próprio prestador** ou da matriz |

- Na prática, a emissão no ISSNet precisa do **certificado A1 da empresa** para assinar.
- A procuração da contabilidade, que funciona na Sefin, não deve servir aqui. Vou confirmar isso na homologação.

### 2.6 Homologação

- O acesso é **pedido ao suporte da Nota Control**: (67) 3041-2075 ou suporte@notaeletronica.com.br, de segunda a sexta, das 8h30 às 18h30.
- Pelos relatos de outros integradores, o ambiente é único para todos os municípios, e o cadastro de teste às vezes aparece com outro município (houve casos com Campo Grande/MS). O cancelamento ficou um tempo indisponível ali.
- Sem certificado, o WSDL responde 403, igual ao swagger da Sefin.

## 3. Como fica no código

```
backend/app/emissor/
  provedores.py        canal da empresa: "nacional" (Sefin) ou "issnet_df"; interface comum
  issnet/
    soap.py            cliente httpx com mTLS, envelope SOAP, timeouts e novas tentativas
    mensagens.py       monta GerarNfse/CancelarNfse/Consultar* e lê CompNfse e ListaMensagemRetorno
    assinatura.py      C14N inclusiva + SHA1 (a de hoje fica intacta para a Sefin)
    rps.py             sincronização e reserva de RPS disponíveis
    xsd/schema_v101.xsd
```

- **`dps.py`** ganha um terceiro leiaute, `issnet`: `cTribMun` obrigatório, sem `pAliq`, grupo IBSCBS e `cLocEmi = 5300108`. A validação XSD é feita antes de enviar.
- **`motor.py`** chama o canal da empresa em vez da Sefin direto. As regras de segurança continuam:
  - o número é reservado e gravado **antes** do envio;
  - depois de falha de rede, primeiro `ConsultarNfsePorDps`, depois reenvio;
  - nunca reaproveita um número que possa ter virado nota.
- **`bloqueio_municipio`** deixa de barrar. Passa a só exigir o que o ISSNet pede (IM, `cTribMun` do DF e certificado da empresa).

**Banco** (uma migração):
- `emissor_empresa.canal` (calculado e mostrado na tela).
- `nota_emitida.canal`.
- `ctribmun` passa de `String(3)` para `String(10)` em `nota_emitida` e `servico_emissor`.
- Tabela nova `rps_disponivel`:
  - colunas: `empresa_id`, `ambiente`, `serie`, `numero`, `situacao`, `sincronizado_em`, `nota_id`;
  - situações: disponível | reservado | usado | usado fora do Contask.

**Tabelas oficiais:**
- `cTribMun` do DF, da planilha de correlação Tributação Municipal × Nacional (área de Downloads do ISSNet DF). Fica no cadastro do serviço, com busca, igual ao item da LC 116.
- `cClassTrib`, CST e `cIndOp` do IBS/CBS, da planilha de correlação da Nota Control. Parte disso já está em `tabelas.json` pelo Anexo VIII.

**DANFSe:**
- A resposta traz a NFS-e no leiaute nacional (`CompNfse`), então o gerador local deve servir.
- Se algum campo do ISSNet não couber, usar o link de `ConsultarUrlNfse`.

## 4. Monitoramento dos RPS

1. **Sincronização** com `ConsultarDpsDisponivel`, lendo todas as páginas:
   - ao marcar a empresa como emissora;
   - antes de cada emissão, se a última sincronização tiver mais de 1 h;
   - a cada 6 h, junto com a fila que já existe.
2. **Reserva:**
   - a emissão pega o menor número disponível e o marca como *reservado* na mesma transação que cria a nota;
   - duas emissões ao mesmo tempo nunca pegam o mesmo número (trava por empresa, como hoje).
3. **Ciclo de cada RPS:**
   - disponível → reservado → usado (nota autorizada);
   - ou reservado → rejeitado (o RPS volta a ficar disponível se o ISSNet não o consumiu);
   - ou pendente, quando o resultado é desconhecido (consulta por DPS até resolver).
4. **Uso fora do Contask:** se um número some da lista sem nota nossa, ele foi usado no portal do ISSNet. Ele vira *usado fora do Contask* e aparece no painel.
5. **Painel na página da empresa:**
   - quantos RPS restam, a série e a faixa;
   - última sincronização;
   - pendentes;
   - usados fora.
6. **Alertas:**
   - aviso no emissor e no dashboard quando restarem menos que o consumo de 30 dias (mínimo 10);
   - com zero, a emissão é barrada com uma explicação de como pedir mais RPS no ISSNet;
   - as notas recorrentes também avisam antes do dia da emissão.

## 5. Fases

| Fase | O quê | Onde |
|---|---|---|
| 0 | Acesso à homologação, tabela `cTribMun` do DF, XSD e WSDL | você + eu |
| 1 | Cliente SOAP, assinatura SHA1 e XSD, mais as primeiras chamadas de **leitura**: `ConsultarDadosCadastrais` e `ConsultarDpsDisponivel` | homologação |
| 2 | Monitoramento dos RPS: tabela, sincronização, painel e alertas | homologação |
| 3 | Emissão `GerarNfse`, recuperação por DPS, cancelamento, substituição e "corrigir e reenviar" | homologação |
| 4 | Telas: canal visível, `cTribMun` do DF no serviço, IBS/CBS, mensagens de erro do ISSNet em português; rascunho, duplicar e recorrentes | homologação |
| 5 | **Piloto em produção**: uma nota real com os dados que você confirmar antes do envio, depois cancelada se você quiser | produção, com sua liberação |
| 6 | Notas emitidas e recebidas: conferir se as notas do ISSNet chegam ao ADN. Se não chegarem, trazer por `ConsultarNfseServicoPrestado`/`Tomado` | produção, só leitura |

Cada fase fecha com testes automáticos (XMLs de exemplo, SOAP simulado, assinatura conferida) e com o deploy de sempre.

## 6. Riscos e pontos em aberto

- **Procuração:** é provável que o ISSNet exija a assinatura com o certificado da própria empresa. Se for assim, a empresa do Presumido ou Real precisa enviar o A1 dela.
- **IBS/CBS:** o manual diz que é obrigatório desde 01/10/2026, mas um relato de fórum fala em 2027. Vamos montar o grupo de qualquer forma e testar com e sem ele.
- **Homologação instável**, com suporte lento, segundo os relatos. Pode atrasar as fases 1 a 3.
- **Notas no ADN:** ainda não sei se as notas emitidas no ISSNet DF são compartilhadas com o ADN. Isso define se a fase 6 é necessária.
- **Limites de uso** do webservice não constam no manual. Vamos seguir as mesmas pausas e novas tentativas da Sefin.
