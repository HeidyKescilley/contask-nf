import * as D from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, ChevronDown, Clock, Loader2, Pause, Play, RefreshCw, ShieldX, X, XCircle,
  Gauge,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { acaoBusca, novaBusca, rotuloAcesso, useBuscas, useCentral, useLogBusca, type Job } from "@/lib/buscas";
import { nomeExibicao } from "@/lib/empresas";
import { formatarDataHora, formatarDoc } from "@/lib/formato";
import { cn } from "@/lib/utils";

function useAcoes() {
  const qc = useQueryClient();
  const atualizar = () => {
    qc.invalidateQueries({ queryKey: ["buscas"] });
    qc.invalidateQueries({ queryKey: ["empresas"] });
    qc.invalidateQueries({ queryKey: ["empresa"] });
  };
  const acao = useMutation({
    mutationFn: ({ id, a }: { id: number; a: "pausar" | "retomar" | "cancelar" }) => acaoBusca(id, a),
    onSuccess: atualizar,
    onError: (e) => toast.error((e as Error).message),
  });
  return { acao };
}

function StatusJob({ j }: { j: Job }) {
  if (j.status === "rodando") return <Selo tom="destaque" icone={Loader2} className="[&_svg]:animate-spin">Buscando</Selo>;
  if (j.status === "fila") return <Selo tom="neutro" icone={Clock}>Na fila</Selo>;
  if (j.status === "pausado") return <Selo tom="alerta" icone={Pause}>Pausada</Selo>;
  if (j.status === "concluido") return <Selo tom="ok" icone={CheckCircle2}>Concluída</Selo>;
  if (j.status === "cancelado") return <Selo tom="neutro" icone={XCircle}>Cancelada</Selo>;
  if (j.situacao_empresa === "sem_procuracao") return <Selo tom="alerta" icone={AlertTriangle}>Procuração pendente</Selo>;
  if (j.situacao_empresa === "limite_mes") return <Selo tom="alerta" icone={Gauge}>Limite do mês</Selo>;
  if (j.situacao_empresa === "erro_certificado") return <Selo tom="erro" icone={ShieldX}>Erro de certificado</Selo>;
  return <Selo tom="erro" icone={AlertTriangle}>Erro</Selo>;
}

function Metrica({ rotulo, valor, tom }: { rotulo: string; valor: number | string; tom?: "alerta" | "erro" }) {
  return (
    <div className="rounded-lg bg-fundo px-2.5 py-2">
      <div className="text-[11px] leading-tight text-texto-2">{rotulo}</div>
      <div className={cn("mt-0.5 font-mono text-sm tabular-nums", tom === "erro" && "text-cancelada", tom === "alerta" && "text-rejeitada")}>
        {typeof valor === "number" ? valor.toLocaleString("pt-BR") : valor}
      </div>
    </div>
  );
}

function Log({ j }: { j: Job }) {
  const [aberto, setAberto] = useState(false);
  const log = useLogBusca(j.id, aberto);
  return (
    <div className="mt-3">
      <button onClick={() => setAberto((a) => !a)} aria-expanded={aberto}
        className="inline-flex items-center gap-1 text-xs text-texto-2 hover:text-texto">
        <ChevronDown className={cn("size-3.5 transition-transform", aberto && "rotate-180")} aria-hidden /> Log detalhado
      </button>
      {aberto && (
        <div className="mt-2 max-h-48 overflow-auto rounded-lg border border-borda bg-fundo p-2 font-mono text-[11px] leading-relaxed">
          {log.isLoading && <div className="text-texto-2">Carregando…</div>}
          {log.data?.length === 0 && <div className="text-texto-2">Sem registros.</div>}
          {log.data?.map((l, i) => (
            <div key={i} className={cn(l.nivel === "erro" && "text-cancelada", l.nivel === "aviso" && "text-rejeitada")}>
              <span className="text-texto-2">{new Date(l.momento).toLocaleTimeString("pt-BR")}</span> {l.mensagem}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CartaoJob({ j, destaque }: { j: Job; destaque?: boolean }) {
  const { acao } = useAcoes();
  const nome = j.empresa ? nomeExibicao(j.empresa) : `Empresa ${j.empresa_id}`;
  const ocupado = acao.isPending;
  const ativo = ["fila", "rodando", "pausado"].includes(j.status);
  return (
    <article className={cn("rounded-xl border bg-superficie p-3.5", destaque ? "border-destaque ring-1 ring-destaque/40" : "border-borda")}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <Link to={`/empresas/${j.empresa_id}?empresa=${j.empresa_id}`} className="block truncate text-sm font-medium hover:text-destaque">{nome}</Link>
          <div className="mt-0.5 font-mono text-xs text-texto-2">{j.empresa && formatarDoc(j.empresa.cnpj)}</div>
          <div className="mt-1 text-xs text-texto-2">
            {rotuloAcesso(j.tipo_consulta, j.modo_certificado)}
            {j.certificado && <> · {j.certificado.titular_nome}</>}
            {" · "}{j.tipo === "refazer" ? "Refazer do zero" : j.tipo === "inicial" ? "Busca inicial" : "Incremental"}
          </div>
        </div>
        <StatusJob j={j} />
      </header>

      {j.status === "rodando" && (
        <div className="barra-indeterminada mt-3" role="progressbar" aria-label="Busca em andamento (total desconhecido)" />
      )}

      {(j.status !== "fila" || j.docs_recebidos > 0) && (
        <div className="mt-3 grid grid-cols-3 gap-1.5">
          <Metrica rotulo="Documentos recebidos" valor={j.docs_recebidos} />
          <Metrica rotulo="Notas recebidas" valor={j.notas_ok} />
          <Metrica rotulo="Eventos aplicados" valor={j.eventos_ok} />
          <Metrica rotulo="Com erro" valor={j.docs_com_erro} tom={j.docs_com_erro ? "erro" : undefined} />
          <Metrica rotulo="Eventos aguardando nota" valor={j.eventos_sem_nota} tom={j.eventos_sem_nota ? "alerta" : undefined} />
          <Metrica rotulo={j.docs_por_min ? `Último NSU · ${j.docs_por_min}/min` : "Último NSU"} valor={j.ultimo_nsu ?? "—"} />
        </div>
      )}

      {j.status === "erro" && j.situacao_empresa === "sem_procuracao" && (
        <div className="mt-3 rounded-lg border border-rejeitada/30 bg-rejeitada-suave p-3 text-xs leading-relaxed">
          <strong className="text-sm">A empresa não deu procuração ao titular do certificado.</strong>
          <ol className="mt-1.5 list-decimal space-y-0.5 pl-4">
            <li>O cliente acessa o e-CAC (Receita Federal) com o certificado dele.</li>
            <li>Em "Senhas e Procurações", cadastra uma procuração eletrônica para <strong>{j.certificado?.titular_nome ?? "a contabilidade"}</strong>.</li>
            <li>Marca o serviço da <strong>NFS-e</strong> (ou "todos os serviços").</li>
            <li>Depois, clique em "Tentar de novo".</li>
          </ol>
        </div>
      )}
      {j.status === "erro" && j.situacao_empresa !== "sem_procuracao" && j.mensagem && (
        <p className="mt-3 rounded-lg bg-cancelada-suave px-3 py-2 text-xs">{j.mensagem}</p>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-1.5">
        {j.status === "rodando" || j.status === "fila" ? (
          <Button tamanho="pequeno" disabled={ocupado} onClick={() => acao.mutate({ id: j.id, a: "pausar" })}><Pause /> Pausar</Button>
        ) : null}
        {j.status === "pausado" && <Button tamanho="pequeno" variante="primario" disabled={ocupado} onClick={() => acao.mutate({ id: j.id, a: "retomar" })}><Play /> Retomar</Button>}
        {j.status === "erro" && <Button tamanho="pequeno" variante="primario" disabled={ocupado} onClick={() => acao.mutate({ id: j.id, a: "retomar" })}><RefreshCw /> Tentar de novo</Button>}
        {ativo && <Button tamanho="pequeno" variante="fantasma" disabled={ocupado} onClick={() => acao.mutate({ id: j.id, a: "cancelar" })}>Cancelar</Button>}
        <span className="ml-auto text-[11px] text-texto-2">
          {j.finalizado_em ? `Terminou ${formatarDataHora(j.finalizado_em)}` : j.iniciado_em ? `Começou ${formatarDataHora(j.iniciado_em)}` : `Na fila desde ${formatarDataHora(j.criado_em)}`}
        </span>
      </footer>
      <Log j={j} />
    </article>
  );
}

export function CentralBuscas() {
  const { aberta, fechar, foco } = useCentral();
  const { data, isLoading, isError, error, refetch } = useBuscas();
  const ativas = data?.ativas ?? [];
  const recentes = data?.recentes ?? [];
  return (
    <D.Root open={aberta} onOpenChange={(a) => !a && fechar()}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/25" />
        <D.Content className="fixed inset-y-0 right-0 z-50 flex w-[min(520px,100vw)] flex-col border-l border-borda bg-fundo text-texto shadow-[-12px_0_32px_-16px_rgb(0_0_0/0.3)]"
          aria-describedby={undefined}>
          <div className="flex items-center justify-between border-b border-borda bg-superficie px-5 py-3.5">
            <div>
              <D.Title className="text-base font-semibold">Central de Buscas</D.Title>
              <p className="text-xs text-texto-2">
                {data ? `${data.rodando} em andamento · ${data.na_fila} na fila` : "Carregando…"}
                {data && !data.fila_ativa && " · motor de busca desligado"}
              </p>
            </div>
            <D.Close className="rounded-lg p-1.5 text-texto-2 hover:bg-superficie-2" aria-label="Fechar"><X className="size-4" /></D.Close>
          </div>
          <div className="flex-1 space-y-5 overflow-auto p-4">
            <p className="text-xs leading-relaxed text-texto-2">
              O ADN não informa quantos documentos existem, então não há porcentagem nem previsão: os contadores mostram o
              que já chegou, e as notas aparecem nas telas conforme chegam.
            </p>
            {isLoading && <div className="h-40 animate-pulse rounded-xl bg-superficie-2" />}
            {isError && (
              <div className="rounded-xl bg-cancelada-suave p-3 text-sm">
                {(error as Error).message} <button className="font-medium text-destaque" onClick={() => refetch()}>Tentar de novo</button>
              </div>
            )}
            {data && (
              <section>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-texto-2">Em andamento e na fila</h3>
                {ativas.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-borda-forte bg-superficie px-4 py-6 text-center text-sm text-texto-2">
                    Nenhuma busca em andamento.
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {[...ativas].sort((a, b) => Number(b.empresa_id === foco) - Number(a.empresa_id === foco)).map((j) => (
                      <CartaoJob key={j.id} j={j} destaque={j.empresa_id === foco} />
                    ))}
                  </div>
                )}
              </section>
            )}
            {recentes.length > 0 && (
              <section>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-texto-2">Últimas 24 horas</h3>
                <div className="space-y-2.5">{recentes.map((j) => <CartaoJob key={j.id} j={j} />)}</div>
              </section>
            )}
          </div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

/** Botões "Buscar agora" e "Refazer do zero" (tela da empresa). */
export function AcoesBuscaEmpresa({ empresaId, ativa }: { empresaId: number; ativa: boolean }) {
  const qc = useQueryClient();
  const { abrir } = useCentral();
  const [confirmar, setConfirmar] = useState(false);
  const m = useMutation({
    mutationFn: (tipo: "incremental" | "refazer") => novaBusca(empresaId, tipo),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["buscas"] });
      qc.invalidateQueries({ queryKey: ["empresas"] });
      qc.invalidateQueries({ queryKey: ["empresa"] });
      setConfirmar(false);
      abrir(empresaId);
    },
    onError: (e) => toast.error((e as Error).message),
  });
  if (!ativa) return <p className="text-sm text-texto-2">Empresa inativa: reative para buscar notas.</p>;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variante="primario" onClick={() => m.mutate("incremental")} disabled={m.isPending}>
        {m.isPending && !confirmar ? <Loader2 className="animate-spin" /> : <RefreshCw />} Buscar agora
      </Button>
      {!confirmar ? (
        <Button variante="fantasma" onClick={() => setConfirmar(true)}>Refazer do zero</Button>
      ) : (
        <span className="flex items-center gap-2 rounded-xl border border-rejeitada/30 bg-rejeitada-suave px-3 py-1.5 text-sm">
          Recomeçar do NSU 0? Nada é apagado nem duplicado.
          <Button tamanho="pequeno" onClick={() => m.mutate("refazer")} disabled={m.isPending}>Confirmar</Button>
          <Button tamanho="pequeno" variante="fantasma" onClick={() => setConfirmar(false)}>Não</Button>
        </span>
      )}
    </div>
  );
}
