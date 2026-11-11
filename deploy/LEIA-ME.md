# Contask NF na internet (Hostinger KVM 2)

Uma instância só atende todos os escritórios. Cada escritório vê só os próprios dados, e o escritório vem do login.

```
Internet ──443──> Caddy (HTTPS automático) ─┬─> site de vendas   https://<dominio>
                                            └─> contask-app      https://app.<dominio>
```

- **Contas:** não há cadastro pela tela no servidor (`CADASTRO=fechado`). Escritório e usuário são criados só com o `contask.sh`, que roda como root por SSH. O SSH aceita apenas chave, então só quem tem a chave cadastrada (Heidy e Vit) cria ou libera contas.
- **Emissor de NFS-e:** no servidor, fica todo na homologação (`EMISSOR_PRODUCAO=false`). Emissão real continua só na instalação local da CONTELB, até haver liberação expressa.

## 1. Contratar

| Item | Escolha | Custo |
|---|---|---|
| VPS | Hostinger **KVM 2**, plano mensal, datacenter **Brasil (São Paulo)**, sistema **Ubuntu 24.04** | conforme a Hostinger |
| Domínio | o que já foi comprado | — |
| DNS | Cloudflare, plano grátis | grátis |
| Backup externo | Cloudflare R2 (até 10 GB grátis) | grátis no início |

Na compra, a Hostinger pede uma senha de root e, opcionalmente, uma **chave SSH**. Cadastre a chave (passo 2). Se não der na compra, cadastre depois no painel em VPS > Configurações > Chaves SSH.

**Por que no Brasil:** serviços do governo podem bloquear IPs do exterior. O teste do passo 6 confirma se o ADN aceita o IP da VPS.

## 2. Chaves SSH (Heidy e Vit, uma vez cada)

No PowerShell de cada um:

```powershell
ssh-keygen -t ed25519 -C "heidy-contask"
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

Copie a linha que começa com `ssh-ed25519` e cole no painel da Hostinger (ou em `/root/.ssh/authorized_keys` na VPS, uma linha por pessoa). A chave privada (`id_ed25519`, sem `.pub`) nunca sai do computador de cada um.

Para entrar: `ssh root@<IP da VPS>`.

## 3. DNS (Cloudflare)

1. Adicione o domínio na Cloudflare e troque os servidores DNS no Registro.br pelos que a Cloudflare indicar.
2. Crie os registros apontando para o IP da VPS, com a nuvem **cinza** ("DNS only"), para o próprio Caddy emitir o HTTPS:
   - `A  @    <IP da VPS>` (site de vendas)
   - `A  www  <IP da VPS>`
   - `A  app  <IP da VPS>` (o sistema)

## 4. Instalar (uma vez)

O repositório é privado. Na VPS, gere uma chave só de leitura e cadastre no GitHub em *Settings > Deploy keys* do repositório (sem marcar "Allow write access"):

```bash
ssh-keygen -t ed25519 -f /root/.ssh/github_contask -N "" -C "vps-contask"
cat /root/.ssh/github_contask.pub
printf "Host github.com\n  IdentityFile /root/.ssh/github_contask\n" >> /root/.ssh/config
```

Depois:

```bash
apt-get update && apt-get install -y git
git clone git@github.com:HeidyKescilley/contask-nf.git /opt/contask/codigo
bash /opt/contask/codigo/deploy/instalar_vps.sh <seu-dominio> <seu-email>
```

O script:
- instala Docker, firewall (só 22, 80 e 443), fail2ban, swap de 2 GB e atualizações automáticas de segurança;
- desliga o login por senha no SSH, se já houver chave cadastrada;
- gera a chave-mestra em `/opt/contask/segredos/chave.env` (só root lê);
- gera a imagem, sobe o sistema e o Caddy e agenda o backup diário.

**Guarde a chave-mestra** no gerenciador de senhas: `cat /opt/contask/segredos/chave.env`. Sem ela, os certificados salvos não abrem.

## 5. Primeiro escritório: o seu

```bash
cd /opt/contask/codigo/deploy
bash contask.sh escritorio novo "CONTELB" seu@email.com "Seu Nome"
```

A senha inicial aparece **uma única vez**. Entre em `https://app.<dominio>` e troque a senha.

## 6. Teste do ADN e da Sefin a partir da VPS (antes de chamar os escritórios)

1. Cadastre a contabilidade com o certificado e uma empresa.
2. Confira na Central de Buscas que as notas chegam do ADN.
3. No emissor, emita uma nota na homologação.

Se o ADN ou a Sefin recusarem a conexão vinda da VPS, pare aqui.

## 7. Escritórios do teste

Para cada escritório:

```bash
bash contask.sh escritorio novo "Contábil Silva" ana@silva.com "Ana Silva"
```

Envie o endereço `https://app.<dominio>`, o e-mail e a senha inicial por um canal privado (WhatsApp direto, nunca em grupo). Antes, combine com o escritório um termo simples de teste: os certificados A1 dos clientes dele ficam guardados (cifrados) no servidor.

## 8. Dia a dia

Sempre em `cd /opt/contask/codigo/deploy`:

| Tarefa | Comando |
|---|---|
| Novo escritório | `bash contask.sh escritorio novo "<nome>" <email> "<pessoa>"` |
| Listar escritórios (com id) | `bash contask.sh escritorio lista` |
| Mais um usuário num escritório | `bash contask.sh usuario novo <email> "<nome>" <id do escritório>` |
| Listar usuários | `bash contask.sh usuario lista` |
| Esqueceu a senha | `bash contask.sh usuario senha <email>` |
| Bloquear / desbloquear acesso | `bash contask.sh usuario desativar <email>` / `reativar <email>` |
| Estado, memória e disco | `bash contask.sh estado` |
| Log | `bash contask.sh logs 200` |
| Publicar nova versão | `bash atualizar.sh` (faz backup antes) |
| Backup agora | `bash backup.sh` |

Configurações em `/opt/contask/contask.conf` (cadastro, emissão em produção, limite de XMLs, destino do backup). Depois de mudar, rode `bash contask.sh reiniciar`.

## 9. Backup

- **Diário às 03:30** e antes de cada atualização, em `/opt/contask/backups/`, por 14 dias. Inclui banco, XMLs e certificados **cifrados**.
- **Cópia fora da VPS (recomendado):** crie um bucket no Cloudflare R2, rode `rclone config` (tipo S3, provedor Cloudflare) e preencha `RCLONE_DESTINO=r2:<bucket>` no `contask.conf`.
- **A chave-mestra não vai no backup**, de propósito: um backup vazado não abre os certificados.

**Restaurar:**
1. `bash contask.sh parar`
2. Extraia a pasta `dados` do ZIP sobre `/opt/contask/dados` e rode `chown -R 1000:1000 /opt/contask/dados`.
3. `bash contask.sh iniciar`

## 10. Monitoramento

No UptimeRobot (grátis), crie um monitor HTTP para `https://app.<dominio>/api/ping`. Ele avisa por e-mail se o sistema sair do ar.

## Segurança: o que já está ligado

- Login obrigatório:
  - senha com scrypt;
  - cookie HttpOnly, Secure e SameSite=Strict;
  - bloqueio temporário após tentativas erradas;
  - troca de senha obrigatória no primeiro acesso.
- Sem cadastro pela tela; contas só pelo `contask.sh`.
- SSH só com chave, fail2ban e firewall.
- Somente HTTPS (HSTS). O sistema recusa endereços (Host) e origens que não sejam o próprio domínio.
- O contêiner roda sem root, com limite de memória, e a porta do sistema não fica exposta: só o Caddy acessa.
- Certificados cifrados com a chave-mestra, que fica fora da imagem e fora do backup.
- No ADN, o sistema só faz chamadas de leitura. O emissor fica na homologação.
