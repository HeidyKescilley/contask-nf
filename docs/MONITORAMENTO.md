# Monitoramento do uso

Painel em **Monitoramento** (menu lateral, só para o administrador do sistema), em `/admin/monitoramento`. Serve para análise e desenvolvimento do produto.

## O que é coletado e onde fica

Tudo fica no próprio servidor (tabelas `uso_evento`, `gravacao`, `pesquisa_resposta` e `pedido_suporte`, e os arquivos em `dados/gravacoes/`). Nada é enviado a terceiros.

- **Eventos do navegador** (`frontend/src/lib/monitoramento.ts`, via `POST /api/uso/eventos`):
  - página aberta (rota normalizada, com `/:id` no lugar de números);
  - tempo ativo (15 s por vez, só com a aba visível e interação no último minuto);
  - clique (posição relativa, largura da janela e um rótulo seguro do elemento; "sem resposta" quando nada muda na tela em 800 ms);
  - rolagem máxima por página;
  - erros (servidor 5xx, falta de conexão, erro de script).
- **Ações gravadas pelo servidor** (middleware de `core/seguranca.py`, lista em `api/uso.py`):
  - login;
  - busca, exportação e download;
  - emissão, cancelamento e recorrência;
  - cadastro de empresa e de contabilidade;
  - abertura de DANFSe e de XML.
- **Gravação da sessão** (rrweb 2.2.0):
  - todo texto vira asterisco e todo campo é mascarado no navegador;
  - imagens, canvas e iframes ficam bloqueados;
  - limite de 8 MB por sessão, apagada depois de 30 dias.
- **Rótulo de clique:** só vem de `aria-label`/`title`, ou do texto de botão, link ou aba com até 30 caracteres e sem números. Nunca vem de tabelas, listas de opções ou áreas com `data-privado` (seletor de empresa, busca rápida e menu do usuário).
- **Quem fica de fora:** o administrador do sistema não é medido nem gravado, e fica fora de todas as contas.
- **Eventos antigos:** apagados depois de 400 dias. A limpeza roda junto da busca periódica.

## Métricas

As regras estão em `backend/app/monitoramento.py`.

| Grupo | Métrica | Regra |
|---|---|---|
| Ativação | % que começou a usar em 7 dias (meta 80%) | Usuário com 7+ dias de conta que entrou e cujo escritório fez busca, exportação ou emissão em até 7 dias da criação do login. |
| | Empresas conectadas | Empresa ativa com pelo menos uma busca concluída. |
| | Tempo até a 1ª busca, emissão e exportação | Contado da criação do primeiro login do escritório. Usa o histórico (vale também para quem entrou antes do monitoramento). |
| | Funil | Conta criada → primeiro acesso → certificado → empresa → busca concluída → exportou ou emitiu. "Parou em" é a primeira etapa que falta. |
| Uso | Por função e por usuário | Acessos às telas e ações do servidor. Funções: Dashboard, Notas, Busca, Exportação e relatórios, Emissor, Recorrentes, Empresas. |
| | Notas baixadas por mês | Soma dos documentos recebidos do ADN nas buscas. |
| Frequência | Dias de acesso | Dias distintos com página aberta, no horário de Brasília. |
| | Período do dia | Por hora e por período (madrugada, manhã, tarde, noite). |
| | Sessão | Soma do tempo ativo por aba. |
| | Dias 1 a 10 | % dos dias de acesso que caem do dia 1 ao 10. Sem concentração seria cerca de 33%. |
| Retenção | Voltaram (meta 70%) | Quem usou em pelo menos 2 dias diferentes. |
| | Ativos | Usou no período, entre os que já entraram alguma vez. |
| Pesquisa | Decepção (meta 40% "muito"), horas economizadas, NPS | Resposta mais recente de cada pessoa. |
| Experiência | Calor, rolagem, cliques sem resposta, caminhos e abandono | O mapa de calor abre a tela num iframe com a conta do suporte (por isso `X-Frame-Options: SAMEORIGIN`) e desenha os cliques da largura de janela mais comum. |
| Erros | Falhas | Buscas com erro, por causa (procuração, certificado, comunicação); certificados vencidos; notas rejeitadas; erros na tela. |
| Suporte | Pedidos | Pedidos do botão **Ajuda** do topo, por assunto, com marcar como resolvido. |

## Pesquisa no app

- **Quando aparece:** depois de 7 dias de conta e 3 dias de uso, 20 s após abrir a tela.
- **Repetição:** a cada 90 dias. Se a pessoa clicar em "Responder depois", a pesquisa volta em 14 dias.

## Limites conhecidos

- O que aconteceu antes de 19/11/2026 (páginas, tempo, cliques) não existe.
- A ativação usa as tabelas que já existiam.
- O mapa de calor é aproximado: a tela de fundo é a do suporte, e o layout muda com a largura da janela.
- Um clique feito logo antes de recarregar a página pode se perder.
