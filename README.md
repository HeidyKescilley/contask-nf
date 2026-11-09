# Contask NF

Aplicação local (Windows) para baixar, consultar e exportar as **NFS-e do Padrão Nacional** de várias empresas, usando o certificado da contabilidade por **procuração eletrônica** ou o certificado da própria empresa.

Tudo roda neste computador: a API escuta só em `127.0.0.1`, e os dados ficam na pasta `dados/`.

## Como usar

1. Copie `.env.example` para `.env` e preencha `CONTASK_CHAVE_MESTRA` (sem ela a API não sobe).
2. Dê **duplo clique em `iniciar.bat`**. Na primeira vez, ele prepara o Python e compila a interface.
3. O navegador abre em `http://127.0.0.1:8765`. Entre ou cadastre o escritório (nome, e-mail e senha).
4. No primeiro uso, cadastre a **contabilidade** e o certificado dela. Depois, cadastre as empresas pelo CNPJ, e a busca de todo o histórico começa sozinha.

Para encerrar, feche a janela minimizada **"Contask NF - servidor"**.

### Telas

| Tela | Para quê |
|---|---|
| Dashboard | Mês por **competência**: total de XMLs e de NFS-e, valor autorizado, prestados e tomados com os últimos 6 meses, canceladas e rejeitadas |
| Serviços Tomados / Prestados | Lista com filtros (chave, número, valor `1.234,56`, nome, período, status), DANFSe, XML e histórico de eventos |
| Exportações | ZIP com os XMLs (e, se quiser, os eventos) e relatório em XLSX ou PDF, com prévia ao vivo e histórico. Opção **Todas as empresas**: um único ZIP com uma pasta `<CNPJ> <razão social>` por empresa e `resumo_empresas` na raiz |
| Empresas | Cadastro, certificados, procurações, filtro "Procuração pendente", "Buscar agora" e "Refazer do zero". **Importar planilha** (XLSX/CSV com CNPJ, Razão social e Apelido): todas entram por procuração e com busca agendada |
| Emissor NFS-e | Emissão pelo Sistema Nacional (homologação até `CONTASK_EMISSOR_PRODUCAO=true`): tela de emissão com tomador pela BrasilAPI, serviço cadastrado, ISS retido e retenções federais; lista de notas emitidas com DANFSe, XML, cancelamento e "corrigir e reenviar" com o mesmo número. Empresas emissoras (checkbox em lote), dados do prestador (regime, série e numeração), serviços por empresa (descrição, item da LC 116, NBS e código municipal, com busca nas tabelas oficiais) e tomadores salvos (CNPJ preenchido pela BrasilAPI). Para emitir, a empresa precisa do próprio certificado A1. Detalhes técnicos em [docs/emissor/NOTAS_TECNICAS.md](docs/emissor/NOTAS_TECNICAS.md) |
| Central de Buscas | Botão "Buscas" no topo: andamento, contadores, log, pausar e retomar |

## Como funciona (o essencial)

- **Busca no ADN** (`GET /contribuintes/DFe/{NSU}`, lote de até 50): o NSU é **exclusivo**, então a próxima chamada usa o maior NSU recebido, nunca `+1` (somar 1 perde uma nota por página).
- **Sempre envia `cnpjConsulta`**, até para a própria empresa. Sem ele, o ADN recusa.
- **Fim da fila**: HTTP 404 com `NENHUM_DOCUMENTO_LOCALIZADO` (E2220) significa que não há mais documentos, não é erro.
- **Gravação de cada página**: primeiro os arquivos, depois banco e NSU numa só transação. Se algo falhar, o NSU não avança e a página é refeita, sem duplicar.
- **Erros do ADN**:
  - E2245 vira "Procuração pendente", sem repetir sozinho.
  - E2210–E2214 e falhas de TLS viram erro de certificado. Com certificado vencido, o ADN derruba a conexão em vez de responder; por isso a validade é conferida antes de chamar.
- **Status da nota vem só dos eventos** (Anexo II), recalculado por chave e em qualquer ordem de chegada. Prioridade: Cancelada > Rejeitada > Autorizada.

  | Código | Efeito |
  |---|---|
  | 101101, 105102 (substituição), 105104 (deferido em análise), 305101 (de ofício) | Cancelada |
  | 101103 / 105105 | Põe / tira o selo "Em análise" (não cancela) |
  | 202205, 203206, 204207 | Rejeitada. Desfeita por 205208 (anulação). Rejeição não é cancelamento |
  | 305102 / 305103 | Põe / tira o selo "Bloqueada" |
  | Confirmações e códigos desconhecidos | Só histórico |

- **DANFSe gerado localmente** a partir do XML, conforme a NT SE/CGNFS-e 008/2026 (v1.02). A API de DANFSe do ADN foi suspensa em 03/08/2026.
  - Quando o prestador é o emitente, os dados que faltam na DPS vêm do grupo `emit` do mesmo XML.
  - A marca d'água CANCELADA/SUBSTITUÍDA vem do status.
- **Valores**: os totais em R$ somam só notas autorizadas.
- **Datas**: o dashboard e a exportação usam a **competência** por padrão; a lista de notas usa a emissão, com opção de competência.
- **Limites da busca**: no máximo 2 buscas por escritório e 1 por certificado, com pausa de 1,5 s entre páginas. Respeita o 429 e tenta de novo até 6 vezes em erros 5xx ou de rede. A fila periódica varre todos os escritórios no mesmo processo.
- **Quando busca**: ao cadastrar, ao abrir o sistema e a cada 6 horas, para todas as empresas ativas.

## Segurança

- O `.pfx` e a senha ficam **cifrados** (Fernet). A chave-mestra é `CONTASK_CHAVE_MESTRA` no ambiente ou no `.env`, nunca no disco do banco e nunca em log. Sem ela a API não sobe. Certificado cifrado com outra chave não abre: as notas e os XMLs ficam, e o `.pfx` é enviado de novo.
- A senha de acesso nunca aparece em log nem em resposta da API.
- O servidor recusa `Host` e `Origin` que não sejam o próprio computador ou um domínio listado em `CONTASK_HOSTS`.
- No ADN, só são feitas chamadas de **leitura**: o sistema não emite, não cancela e não manifesta notas.

## Servidor na internet

Vários escritórios usam o mesmo banco. O cadastro público cria o escritório e o primeiro usuário. A hospedagem (VPS, HTTPS, contrato) fica fora deste recorte; o guia antigo de uma instância por cliente está em [deploy/LEIA-ME.md](deploy/LEIA-ME.md).

- **Login** é obrigatório também em `127.0.0.1`. A sessão fica num cookie `HttpOnly` e na tabela `sessao_usuario`.
- **Chave-mestra** em `CONTASK_CHAVE_MESTRA`. Sem ela a API não sobe.
- **Domínio público** em `CONTASK_HOSTS` (separado por vírgula): libera Host e Origin `https://<domínio>`. `CONTASK_COOKIE_SECURE=true` marca o cookie como `Secure` (HTTPS).
- **Limite do plano** em `CONTASK_LIMITE_XMLS_MES`:
  - conta os XMLs das buscas incrementais do mês;
  - a carga inicial do histórico não conta;
  - avisa a partir de 80%;
  - ao atingir, as buscas param até o mês seguinte.

- **Teste grátis** (`CONTASK_TESTE=true`, padrão de todo escritório novo na VPS):
  - aceita 1 empresa, além da contabilidade, que entra só pelo certificado;
  - baixa no máximo 5 XMLs;
  - depois da assinatura, `cliente.sh <cliente> liberar`: a busca continua do NSU salvo, e o restante do histórico não conta no limite do mês.

No uso local (`iniciar.bat`) o login e a chave-mestra valem do mesmo jeito. Limite mensal e teste grátis só entram se as variáveis correspondentes estiverem ligadas; a contagem é por escritório.

## Backup

```bat
backup.bat
```

Gera `backups\contask_backup_<data>.zip` com o banco (copiado de forma consistente, mesmo com o sistema aberto), os XMLs, os eventos e os certificados cifrados. PDFs e exportações ficam de fora, porque podem ser gerados de novo.

**Para restaurar:** feche o sistema, extraia a pasta `dados` do ZIP sobre a atual e abra o `iniciar.bat`.

**Limitação:** os certificados do backup só abrem com a mesma `CONTASK_CHAVE_MESTRA`. Sem ela, envie os certificados de novo pela tela. As notas continuam disponíveis, e os XMLs também podem ser baixados de novo do ADN.

## Site público

A landing page fica em `site/` e é HTML estático. A Cloudflare Pages publica só essa pasta. A API e a interface do aplicativo não entram nesse deploy.

No painel da Cloudflare Pages, crie um projeto a partir deste repositório:

- Diretório de saída: `site`
- Comando de build: vazio
- Framework: nenhum

O endereço inicial é `https://contask-nf.pages.dev`. Ele está no `canonical`, no Open Graph de `site/index.html` e em `site/sitemap.xml`. Com um domínio próprio, troque esse endereço nesses três pontos e ligue o domínio no painel.

O WhatsApp e o e-mail ficam em `CONTATO`, no final de `site/index.html`. O número é só dígitos, com 55 e DDD. Sem o número, o botão de WhatsApp não abre conversa. Sem o e-mail, o botão some.

Cada push na branch ligada ao projeto republica a pasta.

## Desenvolvimento

| | Comando |
|---|---|
| Testes do backend | `.venv\Scripts\python -m pytest` |
| Backend em modo dev | `.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8765 --reload` |
| Frontend em modo dev | `cd frontend && npm run dev` (http://127.0.0.1:5173, com proxy para o backend) |
| Compilar o frontend | `cd frontend && npm run build` |
| Nova migração do banco | `cd backend && ..\.venv\Scripts\alembic revision --autogenerate -m "..."` |

**Stack:**
- Backend: Python 3.14, FastAPI, SQLAlchemy 2 + Alembic e SQLite em modo WAL.
- Bibliotecas: httpx (mTLS), lxml, reportlab, openpyxl.
- Frontend: React 19, Vite, Tailwind 4, TanStack Query e Radix.

**Nunca vão para o git:** `dados/`, `backups/`, `*.pfx`, `.env` e os XMLs de clientes (veja o `.gitignore`).
