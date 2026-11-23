import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, Clock, Download, Inbox, Loader2, Mail, MailCheck, MailX, MessageCircle, NotebookPen, RotateCw, Tag, FileText,
  Search, ShieldCheck, UserRoundCheck, UserRoundX,
} from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Input, Select } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Dica } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { formatarDataHora } from "@/lib/formato";
import { useSessao } from "@/lib/sessao";

type Etapa = "novo" | "em_contato" | "cliente" | "perdido";
const ETAPAS: { valor: Etapa; rotulo: string }[] = [
  { valor: "novo", rotulo: "Novo" },
  { valor: "em_contato", rotulo: "Em contato" },
  { valor: "cliente", rotulo: "Cliente" },
  { valor: "perdido", rotulo: "Perdido" },
];

interface Lead {
  id: number;
  criado_em: string;
  nome: string;
  segmento: string;
  segmento_rotulo: string;
  email: string;
  telefone: string;
  origem: string | null;
  resultado: "conta_criada" | "email_existente" | "oferta" | "plano_personalizado";
  etapa: Etapa;
  observacoes: string | null;
  email_status: "pendente" | "enviado" | "erro" | "sem_envio";
  email_enviado_em: string | null;
  email_erro: string | null;
  escritorio_id: number | null;
  campanha: string | null;
  campanha_rotulo: string | null;
  contato: string | null;
  notas_mes: string | null;
  notas_mes_rotulo: string | null;
  aceita_whatsapp: boolean;
  escritorio: { nome: string; tipo: "contador" | "empresa"; situacao: "teste" | "ativo" | "suspenso"; teste_ate: string | null; bloqueio: string | null } | null;
  primeiro_acesso_feito: boolean | null;
  ultimo_acesso_em: string | null;
}

const CHAVE = ["admin", "leads"];
const dataBR = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");
const telefoneBR = (t: string) => (t.length === 11 ? `(${t.slice(0, 2)}) ${t.slice(2, 7)}-${t.slice(7)}` : t.length === 10 ? `(${t.slice(0, 2)}) ${t.slice(2, 6)}-${t.slice(6)}` : t);

function diasAte(iso: string) {
  const hoje = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
  hoje.setHours(0, 0, 0, 0);
  const [a, m, d] = iso.split("-").map(Number);
  return Math.round((new Date(a, m - 1, d).getTime() - hoje.getTime()) / 86400000) + 1;
}

function SituacaoConta({ l }: { l: Lead }) {
  if (l.resultado === "plano_personalizado") return <Selo tom="alerta" icone={MessageCircle}>Plano personalizado: chamar</Selo>;
  if (l.resultado === "oferta") return <Selo tom="destaque" icone={Clock}>Aguardando pagamento</Selo>;
  if (l.resultado === "email_existente") return <Selo tom="neutro" icone={UserRoundCheck}>Conta já existia</Selo>;
  const e = l.escritorio;
  if (!e) return <Selo tom="neutro" icone={UserRoundX}>Conta removida</Selo>;
  if (e.situacao === "ativo") return <Selo tom="ok" icone={CheckCircle2}>Assinante</Selo>;
  if (e.situacao === "suspenso") return <Selo tom="erro" icone={UserRoundX}>Suspenso</Selo>;
  if (e.bloqueio) return <Selo tom="alerta" icone={Clock}>Teste encerrado em {dataBR(e.teste_ate)}</Selo>;
  const dias = e.teste_ate ? diasAte(e.teste_ate) : null;
  return <Selo tom="destaque" icone={Clock}>Teste até {dataBR(e.teste_ate)}{dias !== null && ` (${dias === 1 ? "último dia" : `${dias} dias`})`}</Selo>;
}

function SeloEmail({ l }: { l: Lead }) {
  if (l.resultado !== "conta_criada") return null;
  const m = {
    enviado: <Selo tom="ok" icone={MailCheck}>Acesso enviado</Selo>,
    pendente: <Selo tom="neutro" icone={Mail}>Enviando</Selo>,
    sem_envio: <Selo tom="alerta" icone={MailX}>Acesso não enviado</Selo>,
    erro: <Selo tom="erro" icone={MailX}>Erro no envio</Selo>,
  }[l.email_status];
  const dica = l.email_status === "enviado" ? `Enviado em ${formatarDataHora(l.email_enviado_em)}` : l.email_erro;
  return dica ? <Dica texto={dica} lado="top"><span tabIndex={0} className="rounded-md">{m}</span></Dica> : m;
}

export function Leads() {
  const sessao = useSessao();
  const admin = !!sessao.data?.usuario?.admin_sistema;
  const lista = useQuery({ queryKey: CHAVE, queryFn: () => api<{ leads: Lead[]; email_configurado: boolean }>("/api/admin/leads"), enabled: admin });
  const [busca, setBusca] = useState("");
  const [etapa, setEtapa] = useState<"" | Etapa>("");
  const [campanha, setCampanha] = useState("");
  const [notas, setNotas] = useState<Lead | null>(null);
  const [reenviar, setReenviar] = useState<Lead | null>(null);

  const leads = lista.data?.leads ?? [];
  const filtrados = useMemo(() => {
    const t = busca.trim().toLowerCase();
    const digitos = t.replace(/\D/g, "");
    return leads.filter((l) => (!etapa || l.etapa === etapa) && (!campanha || (l.campanha ?? "teste") === campanha) && (!t || l.nome.toLowerCase().includes(t) || l.email.includes(t)
      || (digitos.length >= 3 && l.telefone.includes(digitos)) || (l.contato ?? "").toLowerCase().includes(t)));
  }, [leads, busca, etapa, campanha]);

  if (sessao.isLoading) return <Esqueleto className="h-64 w-full" />;
  if (!admin) return <EstadoVazio icone={ShieldCheck} titulo="Área restrita">Só o administrador do sistema acessa esta página.</EstadoVazio>;

  const semana = Date.now() - 7 * 86400000;
  const conta = (f: (l: Lead) => boolean) => leads.filter(f).length;
  const emTeste = conta((l) => l.escritorio?.situacao === "teste" && !l.escritorio.bloqueio);

  return (
    <>
      <Cabecalho titulo="Leads" descricao="Pedidos feitos nos formulários do site: teste grátis (a conta de 30 dias é criada na hora e o acesso vai por e-mail) e ofertas de campanha, como a Black Friday."
        acoes={leads.length > 0 && <Button asChild><a href="/api/admin/leads/exportar" download><Download /> Exportar planilha</a></Button>} />
      {lista.data && !lista.data.email_configurado && (
        <div className="mb-4"><Aviso tom="alerta">O e-mail do sistema não está configurado no servidor: as contas são criadas, mas o acesso não é enviado. Configure e use Reenviar acesso em cada lead.</Aviso></div>
      )}
      {lista.isLoading && <Esqueleto className="h-64 w-full" />}
      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.data && leads.length === 0 && (
        <EstadoVazio icone={Inbox} titulo="Nenhum lead ainda">Os pedidos feitos em contasknf.com.br/30-dias-gratis e /black-friday aparecem aqui.</EstadoVazio>
      )}
      {leads.length > 0 && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Indicador rotulo="Leads" valor={leads.length} />
            <Indicador rotulo="Últimos 7 dias" valor={conta((l) => new Date(l.criado_em).getTime() >= semana)} />
            <Indicador rotulo="Em teste agora" valor={emTeste} />
            <Indicador rotulo="Black Friday" valor={conta((l) => l.campanha === "black_friday")} />
          </div>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row">
            <div className="relative sm:w-80">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-texto-2" aria-hidden />
              <Input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nome, e-mail ou WhatsApp" className="pl-9" aria-label="Buscar lead" />
            </div>
            <Select value={etapa} onChange={(e) => setEtapa(e.target.value as "" | Etapa)} aria-label="Etapa" className="sm:w-44">
              <option value="">Todas as etapas</option>
              {ETAPAS.map((x) => <option key={x.valor} value={x.valor}>{x.rotulo}</option>)}
            </Select>
            <Select value={campanha} onChange={(e) => setCampanha(e.target.value)} aria-label="Origem do pedido" className="sm:w-44">
              <option value="">Todos os pedidos</option>
              <option value="teste">Teste grátis</option>
              <option value="black_friday">Black Friday</option>
            </Select>
          </div>
          {filtrados.length === 0 ? (
            <EstadoVazio icone={Search} titulo="Nada encontrado">Nenhum lead com esse filtro.</EstadoVazio>
          ) : (
            <ul className="space-y-3">
              {filtrados.map((l) => <CartaoLead key={l.id} l={l} aoNotas={() => setNotas(l)} aoReenviar={() => setReenviar(l)} podeEnviar={!!lista.data?.email_configurado} />)}
            </ul>
          )}
        </>
      )}
      <NotasDialog lead={notas} aoFechar={() => setNotas(null)} />
      <ReenviarDialog lead={reenviar} aoFechar={() => setReenviar(null)} />
    </>
  );
}

function Indicador({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <div className="rounded-xl border border-borda bg-superficie px-4 py-3">
      <div className="text-xs text-texto-2">{rotulo}</div>
      <div className="font-mono text-xl font-semibold tabular-nums">{valor.toLocaleString("pt-BR")}</div>
    </div>
  );
}

function CartaoLead({ l, aoNotas, aoReenviar, podeEnviar }: { l: Lead; aoNotas: () => void; aoReenviar: () => void; podeEnviar: boolean }) {
  const qc = useQueryClient();
  const mudar = useMutation({
    mutationFn: (etapa: Etapa) => api(`/api/admin/leads/${l.id}`, { method: "PUT", body: JSON.stringify({ etapa }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: CHAVE }),
    onError: (e) => toast.error((e as Error).message),
  });
  const saudacao = l.contato ? `Olá, ${l.contato.split(" ")[0]}!` : "Olá!";
  const zap = `https://wa.me/55${l.telefone}?text=${encodeURIComponent(l.campanha === "black_friday"
    ? `${saudacao} Aqui é do Contask NF. Recebemos seu pedido da oferta de Black Friday para ${l.nome}.`
    : `Olá! Aqui é do Contask NF. Vi que você pediu o teste grátis para ${l.nome}.`)}`;
  return (
    <li className="rounded-xl border border-borda bg-superficie p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{l.nome}</span>
            {l.campanha_rotulo
              ? <Selo tom="destaque" icone={Tag}>{l.campanha_rotulo}</Selo>
              : <Selo tom="neutro" icone={l.segmento === "nenhum" ? UserRoundCheck : ShieldCheck}>{l.segmento_rotulo}</Selo>}
            {l.notas_mes_rotulo && <Selo tom="neutro" icone={FileText}>{l.notas_mes_rotulo}</Selo>}
          </div>
          {l.contato && <div className="text-sm">{l.contato}{l.campanha && !l.aceita_whatsapp && <span className="text-texto-2"> · não aceitou mensagens no WhatsApp</span>}</div>}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-texto-2">
            <a href={`mailto:${l.email}`} className="break-all hover:text-texto hover:underline">{l.email}</a>
            <a href={zap} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-texto hover:underline">
              <MessageCircle className="size-3.5" aria-hidden /> {telefoneBR(l.telefone)}
            </a>
            <span>Pedido em {formatarDataHora(l.criado_em)}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <SituacaoConta l={l} />
            <SeloEmail l={l} />
            {l.primeiro_acesso_feito === true && <Selo tom="ok" icone={UserRoundCheck}>Já entrou{l.ultimo_acesso_em && ` · ${formatarDataHora(l.ultimo_acesso_em)}`}</Selo>}
            {l.primeiro_acesso_feito === false && <Selo tom="neutro" icone={AlertTriangle}>Ainda não entrou</Selo>}
          </div>
          {l.origem && <div className="truncate text-xs text-texto-2" title={l.origem}>Origem: {l.origem}</div>}
          {l.observacoes && <p className="whitespace-pre-line rounded-lg bg-superficie-2 px-3 py-2 text-sm">{l.observacoes}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Select value={l.etapa} onChange={(e) => mudar.mutate(e.target.value as Etapa)} disabled={mudar.isPending} aria-label={`Etapa de ${l.nome}`} className="w-36">
            {ETAPAS.map((x) => <option key={x.valor} value={x.valor}>{x.rotulo}</option>)}
          </Select>
          <Button tamanho="pequeno" onClick={aoNotas}><NotebookPen /> Anotações</Button>
          {l.resultado === "conta_criada" && l.escritorio && (
            <Button tamanho="pequeno" onClick={aoReenviar} disabled={!podeEnviar}><RotateCw /> Reenviar acesso</Button>
          )}
        </div>
      </div>
    </li>
  );
}

function NotasDialog({ lead, aoFechar }: { lead: Lead | null; aoFechar: () => void }) {
  return (
    <Dialog open={!!lead} onOpenChange={(a) => !a && aoFechar()}>
      {lead && <FormNotas key={lead.id} lead={lead} aoFechar={aoFechar} />}
    </Dialog>
  );
}

function FormNotas({ lead, aoFechar }: { lead: Lead; aoFechar: () => void }) {
  const qc = useQueryClient();
  const [texto, setTexto] = useState(lead.observacoes ?? "");
  const salvar = useMutation({
    mutationFn: () => api(`/api/admin/leads/${lead.id}`, { method: "PUT", body: JSON.stringify({ observacoes: texto }) }),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: CHAVE }); toast.success("Anotações salvas."); aoFechar(); },
  });
  return (
    <DialogContent titulo="Anotações" descricao={lead.nome}>
      <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={6} maxLength={4000} aria-label="Anotações"
        placeholder="Ex.: liguei em 24/11, pediu retorno depois do fechamento."
        className="w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none focus:border-destaque focus:ring-2 focus:ring-destaque/20" />
      {salvar.isError && <div className="mt-3"><Aviso tom="erro">{(salvar.error as Error).message}</Aviso></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variante="fantasma" onClick={aoFechar}>Cancelar</Button>
        <Button variante="primario" onClick={() => salvar.mutate()} disabled={salvar.isPending}>{salvar.isPending && <Loader2 className="animate-spin" />} Salvar</Button>
      </div>
    </DialogContent>
  );
}

function ReenviarDialog({ lead, aoFechar }: { lead: Lead | null; aoFechar: () => void }) {
  const qc = useQueryClient();
  const enviar = useMutation({
    mutationFn: () => api(`/api/admin/leads/${lead!.id}/reenviar`, { method: "POST" }),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: CHAVE }); toast.success(`Acesso enviado para ${lead!.email}.`); aoFechar(); },
    onSettled: () => qc.invalidateQueries({ queryKey: CHAVE }),
  });
  return (
    <Dialog open={!!lead} onOpenChange={(a) => { if (!a) { enviar.reset(); aoFechar(); } }}>
      {lead && (
        <DialogContent titulo="Reenviar acesso" descricao={`${lead.nome} · ${lead.email}`}>
          <p className="text-sm text-texto-2">
            O sistema cria uma senha provisória nova e envia por e-mail. A senha atual deixa de valer
            {lead.primeiro_acesso_feito ? ", inclusive a que a pessoa já criou," : ""} e ela troca a senha no próximo acesso.
          </p>
          {enviar.isError && <div className="mt-3"><Aviso tom="erro">{(enviar.error as Error).message}</Aviso></div>}
          <div className="mt-4 flex justify-end gap-2">
            <Button variante="fantasma" onClick={aoFechar}>Cancelar</Button>
            <Button variante="primario" onClick={() => enviar.mutate()} disabled={enviar.isPending}>{enviar.isPending && <Loader2 className="animate-spin" />} Enviar</Button>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}
