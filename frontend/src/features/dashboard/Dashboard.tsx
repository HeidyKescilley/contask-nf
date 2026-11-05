import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowDownToLine, ArrowRight, ArrowUpFromLine, Ban, ChevronLeft, ChevronRight, FileStack, FileText,
  Hourglass, LayoutDashboard, Loader2, ShieldX, Wallet, XCircle,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Dica } from "@/components/ui/tooltip";
import { api, type Empresa } from "@/lib/api";
import { useCentral } from "@/lib/buscas";
import { nomeExibicao, useEmpresaSelecionada } from "@/lib/empresas";
import { moeda } from "@/lib/notas";
import { cn } from "@/lib/utils";
import { EstadoSemEmpresa } from "@/pages/paginas";

interface Ponto { mes: string; quantidade: number; valor: number }
interface Bloco { quantidade: number; valor: number; canceladas: number; rejeitadas: number; serie: Ponto[] }
interface Especial { quantidade: number; valor: number; prestadas: number; tomadas: number }
interface DadosDashboard {
  mes: string; base: string; inicio: string; fim: string;
  total_xmls: number; total_nfse: number; eventos_mes: number; valor_autorizado: number;
  prestados: Bloco; tomados: Bloco; canceladas: Especial; rejeitadas: Especial;
  em_analise: number; outras: number; ultimo_mes_com_notas: string | null;
}

const nomeMes = (am: string, formato: "long" | "short" = "long") => {
  const [a, m] = am.split("-").map(Number);
  const s = new Date(a, m - 1, 1).toLocaleDateString("pt-BR", { month: formato, ...(formato === "long" ? { year: "numeric" } : {}) });
  return s.charAt(0).toUpperCase() + s.slice(1).replace(".", "");
};
const mesAtual = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
const deslocar = (am: string, n: number) => {
  const [a, m] = am.split("-").map(Number);
  const d = new Date(a, m - 1 + n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
const num = (n: number) => n.toLocaleString("pt-BR");

/** Link para a lista já filtrada pelo mesmo critério do card (competência, mês e status). */
function linkLista(papel: "prestados" | "tomados", d: DadosDashboard, empresaId: number, status?: string) {
  const p = new URLSearchParams({ empresa: String(empresaId), campo_data: "competencia", inicio: d.inicio, fim: d.fim });
  if (status) p.set("status", status);
  return `/${papel}?${p}`;
}

export function Dashboard() {
  const { empresa, carregando } = useEmpresaSelecionada();
  const [params, setParams] = useSearchParams();
  const mes = params.get("mes") || mesAtual();
  const irPara = (m: string) => setParams((p) => { const n = new URLSearchParams(p); m === mesAtual() ? n.delete("mes") : n.set("mes", m); return n; }, { replace: true });

  const q = useQuery({
    queryKey: ["dashboard", empresa?.id, mes],
    queryFn: () => api<DadosDashboard>(`/api/empresas/${empresa!.id}/dashboard?mes=${mes}`),
    enabled: !!empresa,
    placeholderData: (ant) => ant,
  });

  const navegacao = (
    <div className="flex items-center gap-1">
      <Button tamanho="icone" variante="fantasma" onClick={() => irPara(deslocar(mes, -1))} aria-label="Mês anterior"><ChevronLeft /></Button>
      <div className="min-w-40 text-center text-sm font-medium tabular-nums" aria-live="polite">{nomeMes(mes)}</div>
      <Button tamanho="icone" variante="fantasma" onClick={() => irPara(deslocar(mes, 1))} aria-label="Próximo mês"><ChevronRight /></Button>
      {mes !== mesAtual() && <Button tamanho="pequeno" variante="fantasma" onClick={() => irPara(mesAtual())}>Mês atual</Button>}
    </div>
  );

  if (carregando) return <><Cabecalho titulo="Visão geral" /><Esqueleto className="h-96 w-full" /></>;
  if (!empresa) return <><Cabecalho titulo="Visão geral" descricao="Indicadores mensais da empresa selecionada." /><EstadoSemEmpresa icone={LayoutDashboard} /></>;

  const d = q.data;
  return (
    <>
      <Cabecalho titulo="Visão geral" descricao={`${nomeExibicao(empresa)} · mês por competência`} acoes={navegacao} />
      <AvisoEmpresa e={empresa} />
      {q.isError && <EstadoErro mensagem={(q.error as Error).message} tentarDeNovo={() => q.refetch()} />}
      {q.isLoading && <EsqueletoDashboard />}
      {d && (
        <div className={cn("space-y-5 transition-opacity duration-150", q.isFetching && "opacity-70")}>
          {d.total_nfse === 0 && (
            <EstadoVazio icone={FileText} titulo={`Nenhuma nota com competência em ${nomeMes(mes).toLowerCase()}`}
              acao={d.ultimo_mes_com_notas && d.ultimo_mes_com_notas !== mes
                ? <Button onClick={() => irPara(d.ultimo_mes_com_notas!)}>Ir para {nomeMes(d.ultimo_mes_com_notas).toLowerCase()}</Button> : undefined}>
              {d.ultimo_mes_com_notas ? `O mês mais recente com notas é ${nomeMes(d.ultimo_mes_com_notas).toLowerCase()}.`
                : empresa.busca.situacao === "em_dia" ? "O ADN não tem notas desta empresa." : "A busca ainda não trouxe notas desta empresa."}
            </EstadoVazio>
          )}

          <div className="grid grid-cols-3 gap-4">
            <Indicador icone={FileStack} rotulo="Total de XMLs" valor={num(d.total_xmls)}
              dica="Notas com competência no mês + eventos (cancelamentos, manifestações…) registrados no mês."
              detalhe={`${num(d.total_nfse)} nota${d.total_nfse === 1 ? "" : "s"} + ${num(d.eventos_mes)} evento${d.eventos_mes === 1 ? "" : "s"}`} />
            <Indicador icone={FileText} rotulo="Total de NFS-e" valor={num(d.total_nfse)}
              dica="Todas as notas com competência no mês, de qualquer status."
              detalhe={[d.canceladas.quantidade && `${d.canceladas.quantidade} cancelada(s)`, d.rejeitadas.quantidade && `${d.rejeitadas.quantidade} rejeitada(s)`,
                d.outras && `${d.outras} de outro papel`].filter(Boolean).join(" · ") || "todas autorizadas"} />
            <Indicador icone={Wallet} rotulo="Valor autorizado" valor={moeda(d.valor_autorizado)} mono
              dica="Soma do valor do serviço das notas autorizadas (prestadas + tomadas). Canceladas e rejeitadas ficam fora."
              detalhe={`${moeda(d.prestados.valor)} prestados · ${moeda(d.tomados.valor)} tomados`} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <CardPapel titulo="Serviços Prestados" icone={ArrowUpFromLine} b={d.prestados} mes={mes}
              href={linkLista("prestados", d, empresa.id, "autorizada")} />
            <CardPapel titulo="Serviços Tomados" icone={ArrowDownToLine} b={d.tomados} mes={mes}
              href={linkLista("tomados", d, empresa.id, "autorizada")} />
          </div>

          <section aria-labelledby="titulo-especiais">
            <h2 id="titulo-especiais" className="mb-2 text-sm font-semibold">Status especiais</h2>
            <div className="grid grid-cols-2 gap-4">
              <CardEspecial titulo="Canceladas" icone={XCircle} tom="cancelada" e={d.canceladas}
                hrefP={linkLista("prestados", d, empresa.id, "cancelada")} hrefT={linkLista("tomados", d, empresa.id, "cancelada")}
                dica="Inclui canceladas por substituição, por análise fiscal e por ofício." />
              <CardEspecial titulo="Rejeitadas" icone={Ban} tom="rejeitada" e={d.rejeitadas}
                hrefP={linkLista("prestados", d, empresa.id, "rejeitada")} hrefT={linkLista("tomados", d, empresa.id, "rejeitada")}
                dica="Rejeição manifestada (prestador, tomador ou intermediário) e não anulada. Não é cancelamento." />
            </div>
            {d.em_analise > 0 && (
              <p className="mt-3 inline-flex items-center gap-2 text-sm text-texto-2">
                <Hourglass className="size-4" aria-hidden /> {d.em_analise} nota(s) do mês com análise fiscal de cancelamento pendente (seguem autorizadas).
              </p>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function AvisoEmpresa({ e }: { e: Empresa }) {
  const { abrir } = useCentral();
  let conteudo: ReactNode = null;
  if (!e.certificado) conteudo = <><ShieldX className="size-4 text-cancelada" /> Esta empresa está sem certificado: as notas não são atualizadas. <Link className="font-medium text-destaque underline" to={`/empresas/${e.id}?empresa=${e.id}`}>Configurar</Link></>;
  else if (e.certificado.situacao === "vencido") conteudo = <><ShieldX className="size-4 text-cancelada" /> O certificado usado na busca venceu: as notas não são atualizadas.</>;
  else if (e.busca.situacao === "sem_procuracao") conteudo = <><AlertTriangle className="size-4 text-rejeitada" /> Procuração pendente: a empresa precisa outorgar procuração com o serviço da NFS-e. <Link className="font-medium text-destaque underline" to={`/empresas/${e.id}?empresa=${e.id}`}>Ver instruções</Link></>;
  else if (e.busca.situacao === "buscando" || e.busca.job_pendente) conteudo = <><Loader2 className="size-4 animate-spin text-destaque" /> Busca em andamento: os números podem mudar. <button className="font-medium text-destaque underline" onClick={() => abrir(e.id)}>Acompanhar</button></>;
  else if (e.busca.situacao === "erro" || e.busca.situacao === "erro_certificado") conteudo = <><AlertTriangle className="size-4 text-cancelada" /> A última busca terminou com erro: os números podem estar desatualizados. <button className="font-medium text-destaque underline" onClick={() => abrir(e.id)}>Ver detalhes</button></>;
  if (!conteudo) return null;
  return <div role="status" className="mb-4 flex items-center gap-2 rounded-xl border border-borda bg-superficie px-4 py-2.5 text-sm">{conteudo}</div>;
}

function Indicador({ icone: Icone, rotulo, valor, detalhe, dica, mono }: { icone: typeof FileText; rotulo: string; valor: string; detalhe: string; dica: string; mono?: boolean }) {
  return (
    <div className="rounded-xl border border-borda bg-superficie p-4">
      <Dica texto={dica} lado="top">
        <div tabIndex={0} className="inline-flex items-center gap-2 rounded text-[13px] text-texto-2">
          <Icone className="size-4" aria-hidden /> {rotulo}
        </div>
      </Dica>
      <div className={cn("mt-2 text-2xl font-semibold tabular-nums tracking-tight", mono && "font-mono text-[22px]")}>{valor}</div>
      <div className="mt-1 truncate text-xs text-texto-2" title={detalhe}>{detalhe}</div>
    </div>
  );
}

/** Minigráfico de barras (6 meses, valor autorizado). Série única: uma cor; mês atual em destaque. */
function MiniBarras({ serie, mes, rotulo }: { serie: Ponto[]; mes: string; rotulo: string }) {
  const [foco, setFoco] = useState<number | null>(null);
  const max = Math.max(...serie.map((p) => p.valor), 0);
  const W = 240, H = 56, gap = 6, bw = (W - gap * (serie.length - 1)) / serie.length;
  const ativo = foco !== null ? serie[foco] : null;
  return (
    <figure className="relative">
      <svg viewBox={`0 0 ${W} ${H + 16}`} className="w-full overflow-visible" role="img"
        aria-label={`${rotulo}, valor autorizado nos últimos 6 meses: ${serie.map((p) => `${nomeMes(p.mes, "short")} ${moeda(p.valor)}`).join("; ")}`}
        onMouseLeave={() => setFoco(null)}>
        <line x1={0} x2={W} y1={H + 0.5} y2={H + 0.5} stroke="var(--borda)" />
        {serie.map((p, i) => {
          const h = max > 0 ? Math.max(p.valor > 0 ? 3 : 0, (p.valor / max) * (H - 4)) : 0;
          const x = i * (bw + gap);
          const atual = p.mes === mes;
          return (
            <g key={p.mes}>
              {h > 0 && (
                <path d={`M${x},${H} v${-(h - 4)} q0,-4 4,-4 h${bw - 8} q4,0 4,4 v${h - 4} z`}
                  fill="var(--destaque)" opacity={atual || foco === i ? 1 : 0.45} />
              )}
              <text x={x + bw / 2} y={H + 13} textAnchor="middle" fontSize="10" fill={atual ? "var(--texto)" : "var(--texto-2)"} fontWeight={atual ? 600 : 400}>
                {nomeMes(p.mes, "short")}
              </text>
              {/* área de toque maior que a barra */}
              <rect x={x - gap / 2} y={0} width={bw + gap} height={H + 16} fill="transparent" onMouseEnter={() => setFoco(i)}
                tabIndex={0} onFocus={() => setFoco(i)} onBlur={() => setFoco(null)} aria-label={`${nomeMes(p.mes)}: ${p.quantidade} nota(s), ${moeda(p.valor)}`} />
            </g>
          );
        })}
      </svg>
      {ativo && (
        <div className="pointer-events-none absolute -top-2 right-0 rounded-lg border border-borda bg-superficie px-2.5 py-1.5 text-xs shadow-[0_8px_24px_-12px_rgb(0_0_0/0.3)]">
          <div className="font-medium">{nomeMes(ativo.mes)}</div>
          <div className="font-mono tabular-nums text-texto-2">{num(ativo.quantidade)} nota(s) · {moeda(ativo.valor)}</div>
        </div>
      )}
    </figure>
  );
}

function CardPapel({ titulo, icone: Icone, b, mes, href }: { titulo: string; icone: typeof FileText; b: Bloco; mes: string; href: string }) {
  const extras = [b.canceladas && `${b.canceladas} cancelada(s)`, b.rejeitadas && `${b.rejeitadas} rejeitada(s)`].filter(Boolean).join(" · ");
  return (
    <div className="flex flex-col rounded-xl border border-borda bg-superficie p-4">
      <div className="flex items-center gap-2 text-sm font-semibold"><Icone className="size-4 text-texto-2" aria-hidden /> {titulo}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-2xl font-semibold tabular-nums">{num(b.quantidade)}</span>
        <span className="text-sm text-texto-2">nota{b.quantidade === 1 ? "" : "s"} autorizada{b.quantidade === 1 ? "" : "s"} ·</span>
        <span className="font-mono text-lg tabular-nums">{moeda(b.valor)}</span>
      </div>
      <div className="h-4 text-xs text-texto-2">{extras && `Fora do valor: ${extras}`}</div>
      <div className="mt-3"><MiniBarras serie={b.serie} mes={mes} rotulo={titulo} /></div>
      <Link to={href} className="mt-3 inline-flex items-center gap-1 self-start text-sm font-medium text-destaque hover:underline">
        Ver notas <ArrowRight className="size-4" aria-hidden />
      </Link>
    </div>
  );
}

function CardEspecial({ titulo, icone: Icone, tom, e, hrefP, hrefT, dica }: {
  titulo: string; icone: typeof FileText; tom: "cancelada" | "rejeitada"; e: Especial; hrefP: string; hrefT: string; dica: string;
}) {
  return (
    <div className="rounded-xl border border-borda bg-superficie p-4">
      <Dica texto={dica} lado="top">
        <div tabIndex={0} className={cn("inline-flex items-center gap-2 rounded text-sm font-semibold", tom === "cancelada" ? "text-cancelada" : "text-rejeitada")}>
          <Icone className="size-4" aria-hidden /> {titulo}
        </div>
      </Dica>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-2xl font-semibold tabular-nums">{num(e.quantidade)}</span>
        <span className="text-sm text-texto-2">nota{e.quantidade === 1 ? "" : "s"} ·</span>
        <span className="font-mono text-lg tabular-nums">{moeda(e.valor)}</span>
      </div>
      <div className="mt-3 flex gap-4 text-sm">
        <Link to={hrefP} className="inline-flex items-center gap-1 font-medium text-destaque hover:underline">{num(e.prestadas)} prestada(s) <ArrowRight className="size-3.5" aria-hidden /></Link>
        <Link to={hrefT} className="inline-flex items-center gap-1 font-medium text-destaque hover:underline">{num(e.tomadas)} tomada(s) <ArrowRight className="size-3.5" aria-hidden /></Link>
      </div>
    </div>
  );
}

function EsqueletoDashboard() {
  return (
    <div className="space-y-4" aria-label="Carregando indicadores">
      <div className="grid grid-cols-3 gap-4">{[0, 1, 2].map((i) => <Esqueleto key={i} className="h-28" />)}</div>
      <div className="grid grid-cols-2 gap-4">{[0, 1].map((i) => <Esqueleto key={i} className="h-56" />)}</div>
      <div className="grid grid-cols-2 gap-4">{[0, 1].map((i) => <Esqueleto key={i} className="h-28" />)}</div>
    </div>
  );
}
