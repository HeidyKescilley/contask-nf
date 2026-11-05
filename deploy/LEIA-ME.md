# Contask NF na internet (VPS)

Cada escritório roda numa **instância separada** (um contêiner Docker com banco, certificados e chave próprios) e acessa por um endereço próprio, por exemplo `https://contabil-silva.contasknf.com.br`. O Caddy recebe as conexões, emite os certificados HTTPS sozinho e repassa cada endereço à instância certa.

```
Internet ──443──> Caddy ──> contask-contabil-silva   (dados, chave e limite próprios)
                        └─> contask-escritorio-x
```

Cada instância usa cerca de 150 MB de memória. Uma VPS de 8 GB comporta 30 ou mais escritórios.

## 1. O que contratar

| Item | Sugestão | Custo |
|---|---|---|
| VPS | Hostinger KVM 2, datacenter **São Paulo**, Ubuntu 24.04 | ~R$ 44/mês (promoção) |
| Domínio | `contasknf.com.br` (ou outro) no Registro.br | ~R$ 40/ano |
| DNS | Cloudflare, plano gratuito (só DNS, nuvem **cinza**) | grátis |
| Backup externo (opcional) | Cloudflare R2 (10 GB grátis) | grátis no início |

**Por que no Brasil:** serviços do governo podem bloquear IPs do exterior. Antes de pagar o plano longo, faça o teste do passo 4.

## 2. DNS

No Cloudflare (ou no DNS do Registro.br), crie apontando para o IP da VPS:

- `A  *    <IP da VPS>` (curinga: todos os escritórios)
- `A  @    <IP da VPS>` (site de vendas em `https://contasknf.com.br`, servido da pasta `site/`)

Antes de divulgar o site, preencha o WhatsApp e o e-mail de contato no fim de `site/index.html` (objeto `CONTATO`).

Na Cloudflare, deixe a nuvem **cinza** ("DNS only"). Assim o próprio Caddy emite o HTTPS.

## 3. Preparar a VPS (uma vez)

Entre por SSH como root e rode:

```bash
apt-get update && apt-get install -y git
git clone <URL do repositório privado> /opt/contask/codigo
bash /opt/contask/codigo/deploy/instalar_vps.sh contasknf.com.br seu@email.com
```

O script faz o seguinte:
- instala Docker, firewall (só 22, 80 e 443), swap de 2 GB e atualizações automáticas de segurança;
- gera a imagem do sistema e sobe o Caddy;
- agenda o backup diário.

## 4. Teste do ADN a partir da VPS (antes de qualquer cliente)

Crie o seu próprio escritório como primeiro cliente:

```bash
bash /opt/contask/codigo/deploy/novo_cliente.sh piloto seu@email.com "Seu Nome"
```

Depois, faça o seguinte:
1. Abra `https://piloto.contasknf.com.br`, entre com a senha inicial mostrada e crie a sua senha.
2. Cadastre a contabilidade com o certificado e uma empresa.
3. Confira na Central de Buscas que as notas chegam. Se o ADN recusar a conexão vinda da VPS, pare aqui e me avise.

## 5. Dia a dia

| Tarefa | Comando (`cd /opt/contask/codigo/deploy`) |
|---|---|
| Novo escritório | `bash novo_cliente.sh <cliente> <email> "<nome>" [limite]` |
| Listar escritórios | `bash cliente.sh lista` |
| Suspender (falta de pagamento) | `bash cliente.sh <cliente> parar` |
| Reativar | `bash cliente.sh <cliente> iniciar` |
| Mudar o limite de XMLs | `bash cliente.sh <cliente> limite 6000` (0 = sem limite) |
| Novo usuário do escritório | `bash cliente.sh <cliente> usuarios criar <email> "<nome>"` |
| Esqueceu a senha | `bash cliente.sh <cliente> usuarios redefinir <email>` |
| Ver o log | `bash cliente.sh <cliente> logs` |
| Publicar nova versão | `bash atualizar.sh` (faz backup antes) |
| Backup agora | `bash backup.sh` |

A senha inicial aparece **uma única vez** na tela de quem rodou o comando. Envie-a por um canal privado. O sistema obriga a troca no primeiro acesso.

## 6. Backup e chaves

- **Backup diário às 03:30.** Fica em `/opt/contask/backups/<cliente>/` por 7 dias e inclui banco, XMLs e certificados **cifrados**.
- **Cópia fora da VPS:**
  1. Configure o rclone com o R2 (`rclone config`).
  2. Preencha `RCLONE_DESTINO=r2:contask-backups` em `/opt/contask/contask.conf`.
- **A chave de cada cliente não vai no backup, de propósito.** Assim, um backup vazado não abre os certificados.
  - A chave fica em `/opt/contask/clientes/<cliente>/segredos/chave.key`.
  - Guarde uma cópia de cada chave no seu gerenciador de senhas.
  - Sem a chave, as notas continuam acessíveis, mas o cliente precisa reenviar o certificado.

**Para restaurar um cliente:**
1. `bash cliente.sh <cliente> parar`
2. Extraia a pasta `dados` do ZIP sobre `/opt/contask/clientes/<cliente>/dados` e rode `chown -R 1000:1000` nela.
3. `bash cliente.sh <cliente> iniciar`

## 7. Monitoramento

No UptimeRobot (gratuito), crie um monitor HTTP para `https://<cliente>.contasknf.com.br/api/ping` de cada escritório. Ele avisa por e-mail se algum sair do ar.

## Segurança: o que já está ligado

- Login obrigatório:
  - senha com scrypt;
  - sessão em cookie HttpOnly, Secure e SameSite=Strict;
  - bloqueio por 15 minutos após 5 tentativas erradas;
  - troca de senha obrigatória no primeiro acesso.
- Cada escritório tem banco, pasta e chave-mestra próprios. Um não enxerga o outro.
- Somente HTTPS (HSTS). O sistema recusa endereços (Host) e origens que não sejam o próprio domínio.
- O contêiner roda sem root, com limite de memória. A porta do sistema não fica exposta: só o Caddy acessa.
- No ADN, o sistema só faz chamadas de leitura.
