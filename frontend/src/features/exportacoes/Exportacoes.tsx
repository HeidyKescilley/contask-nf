import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock, Download, FileArchive, FileSpreadsheet, FileText, Loader2, Lock, XCircle } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Cabecalho, EstadoErro, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Input } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { nomeExibicao, useEmpresaSelecionada } from "@/lib/empresas";
import { useTesteGratis } from "@/lib/sessao";
import { formatarDataHora } from "@/lib/formato";
import { moeda, periodo } from "@/lib/notas";
import { cn } from "@/lib/utils";
import { EstadoSemEmpresa } from "@/pages/paginas";

interface Filtros {
  tipo: "prestados" | "tomados" | "ambos";
  inicio: string;
  fim: string;
  campo_data: "competencia" | "emissao";
  status: "todas" | "autorizada" | "cancelada" | "rejeitada";
  relatorio: "xlsx" | "pdf";
  incluir_xml: boolean;
  incluir_eventos: boolean;
  escopo: "empresa" | "todas";
}
interface Previa {
  total: number; prestadas: number; tomadas: number; eventos: number; arquivos_xml: number;
  por_status: Record<"autorizada" | "cancelada" | "rejeitada", { quantidade: number; valor: number }>;
  empresas?: { id: number; cnpj: string; nome: string; pasta: string; total: number; arquivos_xml: number; valor_autorizado: number }[];
  empresas_com_notas?: number;
}
interface ItemHistorico {
  id: number; status: "fila" | "gerando" | "concluido" | "erro"; descricao: [string, string][]; total_notas: number | null;
  erro: string | null; criado_em: string; arquivo: string | null; disponivel: boolean; filtros: Filtros; escopo: "empresa" | "todas";
}

const PADRAO = (): Filtros => {
  const [ini, fim] = periodo("mes_passado");
  return { tipo: "ambos", inicio: ini, fim, campo_data: "competencia", status: "autorizada", relatorio: "xlsx", incluir_xml: true, incluir_eventos: false, escopo: "empresa" };
};

/** Dias do período, contando o primeiro e o último (null sem as duas datas). */
function diasDoPeriodo(f: Filtros): number | null {
  if (!f.inicio || !f.fim) return null;
  return Math.round((Date.parse(f.fim) - Date.parse(f.inicio)) / 86_400_000) + 1;
}

function corpo(f: Filtros) {
  return JSON.stringify({ ...f, inicio: f.inicio || null, fim: f.fim || null });
}

function Grupo({ rotulo, children, ajuda }: { rotulo: string; children: ReactNode; ajuda?: ReactNode }) {
  return (
    <fieldset className="space-y-2 border-b border-borda py-4 first:pt-0 last:border-0 last:pb-0">
      <legend className="mb-2 text-[13px] font-medium">{rotulo}</legend>
      {children}
      {ajuda && <p className="text-xs text-texto-2">{ajuda}</p>}
    </fieldset>
  );
}

function Opcoes<T extends string>({ valor, opcoes, aoMudar, nome }: { valor: T; opcoes: { id: T; rotulo: string; icone?: typeof FileText }[]; aoMudar: (v: T) => void; nome: string }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={nome}>
      {opcoes.map((o) => (
        <button key={o.id} type="button" role="radio" aria-checked={valor === o.id} onClick={() => aoMudar(o.id)}
          className={cn("inline-flex h-9 items-center gap-2 rounded-xl border px-3 text-sm transition-colors duration-150",
            valor === o.id ? "border-destaque bg-destaque-suave font-medium text-destaque" : "border-borda bg-superficie hover:border-borda-forte")}>
          {o.icone && <o.icone className="size-4" aria-hidden />} {o.rotulo}
        </button>
      ))}
    </div>
  );
}

export function Exportacoes() {
  const { empresa, empresas, carregando } = useEmpresaSelecionada();
  const teste = useTesteGratis();
  const [f, setF] = useState<Filtros>(PADRAO);
  const [verEmpresas, setVerEmpresas] = useState(false);
  const ativas = empresas.filter((e) => e.ativa).length;
  const [fDeb, setFDeb] = useState(f);
  const qc = useQueryClient();
  useEffect(() => { const t = setTimeout(() => setFDeb(f), 250); return () => clearTimeout(t); }, [f]);
  const set = <K extends keyof Filtros>(k: K, v: Filtros[K]) => setF((x) => ({ ...x, [k]: v }));

  const previa = useQuery({
    queryKey: ["exportacoes", "previa", empresa?.id, corpo(fDeb)],
    queryFn: () => api<Previa>(`/api/empresas/${empresa!.id}/exportacoes/previa`, { method: "POST", body: corpo(fDeb) }),
    enabled: !!empresa, placeholderData: keepPreviousData, retry: false,
  });
  const historico = useQuery({
    queryKey: ["exportacoes", "historico", empresa?.id],
    queryFn: () => api<ItemHistorico[]>(`/api/empresas/${empresa!.id}/exportacoes`),
    enabled: !!empresa,
    refetchInterval: (q) => (q.state.data?.some((x) => x.status === "fila" || x.status === "gerando") ? 1500 : false),
  });
  const gerar = useMutation({
    mutationFn: () => api<ItemHistorico>(`/api/empresas/${empresa!.id}/exportacoes`, { method: "POST", body: corpo(f) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["exportacoes", "historico"] }); qc.invalidateQueries({ queryKey: ["uso"] }); toast.success("Exportação na fila. O download aparece no histórico ao terminar."); },
    onError: (e) => toast.error((e as Error).message),
  });

  if (carregando || teste.carregando) return <><Cabecalho titulo="Exportações" /><Esqueleto className="h-96 w-full" /></>;
  if (!empresa) return <><Cabecalho titulo="Exportações" descricao="Gere um ZIP com os XMLs e um relatório em PDF ou XLSX." /><EstadoSemEmpresa icone={FileArchive} /></>;

  const p = previa.data;
  const atalhoAtivo = (["mes", "mes_passado", "trimestre", "ano"] as const).find((a) => { const [i, fi] = periodo(a); return i === f.inicio && fi === f.fim; });
  const desatualizada = corpo(f) !== corpo(fDeb) || previa.isFetching;
  const maxDias = teste.emTeste ? teste.maxDiasExportacao ?? 30 : null;
  const dias = diasDoPeriodo(f);
  const semExportacao = teste.emTeste && teste.exportacoesRestantes === 0;
  const foraDoPeriodo = maxDias !== null && (dias === null || dias > maxDias);

  return (
    <>
      <Cabecalho titulo="Exportações" descricao="Gere um ZIP com os XMLs e um relatório em PDF ou XLSX." />
      {teste.emTeste && (
        <div className="mb-5">
          <Aviso tom={semExportacao ? "alerta" : "info"}>
            {semExportacao
              ? <><Lock className="mr-1 inline size-4 align-[-3px]" aria-hidden />A exportação do teste grátis já foi usada. As exportações ficam liberadas ao assinar o plano: fale com o suporte do Contask NF.</>
              : <><strong>Teste grátis:</strong> você pode fazer 1 exportação, de um período de até {maxDias} dias.</>}
          </Aviso>
        </div>
      )}
      <div className="grid grid-cols-[minmax(0,560px)_minmax(0,1fr)] items-start gap-6">
        <form onSubmit={(e) => { e.preventDefault(); gerar.mutate(); }} className="rounded-xl border border-borda bg-superficie p-5">
          <Grupo rotulo="Empresas" ajuda={f.escopo === "todas" ? "Um único ZIP com uma pasta por empresa (CNPJ seguido do nome), cada uma com os XMLs e o relatório dela, e um resumo geral na raiz." : undefined}>
            <Opcoes nome="Empresas" valor={f.escopo} aoMudar={(v) => set("escopo", v)}
              opcoes={[{ id: "empresa", rotulo: `Só ${nomeExibicao(empresa)}` }, { id: "todas", rotulo: `Todas as empresas (${ativas} ativas)` }]} />
          </Grupo>
          <Grupo rotulo="Tipo">
            <Opcoes nome="Tipo" valor={f.tipo} aoMudar={(v) => set("tipo", v)}
              opcoes={[{ id: "prestados", rotulo: "Prestados (saídas)" }, { id: "tomados", rotulo: "Tomados (entradas)" }, { id: "ambos", rotulo: "Ambos" }]} />
          </Grupo>
          <Grupo rotulo="Período" ajuda={maxDias !== null
            ? (foraDoPeriodo ? <span className="text-cancelada">No teste grátis, escolha um período de até {maxDias} dias, com data inicial e final.</span> : `Até ${maxDias} dias no teste grátis.`)
            : !f.inicio && !f.fim ? "Sem período: exporta todas as notas." : undefined}>
            <div className="flex flex-wrap items-center gap-2">
              <select value={f.campo_data} onChange={(e) => set("campo_data", e.target.value as Filtros["campo_data"])} aria-label="Data usada no período"
                className="h-9 rounded-xl border border-borda bg-superficie px-2 text-sm">
                <option value="competencia">Competência</option><option value="emissao">Emissão</option>
              </select>
              <Input type="date" value={f.inicio} onChange={(e) => set("inicio", e.target.value)} className="w-[150px]" aria-label="Início" />
              <span className="text-texto-2">a</span>
              <Input type="date" value={f.fim} onChange={(e) => set("fim", e.target.value)} className="w-[150px]" aria-label="Fim" />
            </div>
            <div className="flex flex-wrap gap-1">
              {([["mes", "Este mês"], ["mes_passado", "Mês passado"], ["trimestre", "Trimestre"], ["ano", "Ano"]] as const)
                .filter(([id]) => maxDias === null || id === "mes" || id === "mes_passado").map(([id, rot]) => (
                <button key={id} type="button" aria-pressed={atalhoAtivo === id} onClick={() => { const [i, fi] = periodo(id); setF((x) => ({ ...x, inicio: i, fim: fi })); }}
                  className={cn("h-7 rounded-lg px-2 text-[13px]", atalhoAtivo === id ? "bg-destaque-suave font-medium text-destaque" : "text-texto-2 hover:bg-superficie-2 hover:text-texto")}>{rot}</button>
              ))}
              {maxDias === null && <button type="button" onClick={() => setF((x) => ({ ...x, inicio: "", fim: "" }))} className="h-7 rounded-lg px-2 text-[13px] text-texto-2 hover:bg-superficie-2 hover:text-texto">Tudo</button>}
            </div>
          </Grupo>
          <Grupo rotulo="Status">
            <Opcoes nome="Status" valor={f.status} aoMudar={(v) => set("status", v)}
              opcoes={[{ id: "autorizada", rotulo: "Autorizadas" }, { id: "todas", rotulo: "Todas" }, { id: "cancelada", rotulo: "Canceladas" }, { id: "rejeitada", rotulo: "Rejeitadas" }]} />
            {f.status === "todas" && (
              <Aviso>"Todas" inclui notas <strong>canceladas e rejeitadas</strong>. Alguns sistemas importam o XML sem saber do cancelamento; prefira "Autorizadas" para importação.</Aviso>
            )}
          </Grupo>
          <Grupo rotulo="Relatório">
            <Opcoes nome="Relatório" valor={f.relatorio} aoMudar={(v) => set("relatorio", v)}
              opcoes={[{ id: "xlsx", rotulo: "Planilha XLSX", icone: FileSpreadsheet }, { id: "pdf", rotulo: "PDF", icone: FileText }]} />
          </Grupo>
          <Grupo rotulo="Conteúdo do ZIP">
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.incluir_xml} onChange={(e) => set("incluir_xml", e.target.checked)} className="size-4 accent-[var(--destaque)]" /> XMLs das notas</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.incluir_eventos} onChange={(e) => set("incluir_eventos", e.target.checked)} className="size-4 accent-[var(--destaque)]" /> XMLs dos eventos (cancelamentos, manifestações…)</label>
          </Grupo>

          <div className="mt-4 rounded-xl bg-fundo p-4" aria-live="polite">
            {previa.isError ? (
              <p className="text-sm text-cancelada">{(previa.error as Error).message}</p>
            ) : !p ? (
              <Esqueleto className="h-10 w-full" />
            ) : (
              <div className={cn("transition-opacity duration-150", desatualizada && "opacity-60")}>
                <div className="text-sm">
                  <span className="font-mono text-lg font-semibold tabular-nums">{p.total.toLocaleString("pt-BR")}</span> nota{p.total === 1 ? "" : "s"}
                  {f.tipo === "ambos" && <span className="text-texto-2">: {p.prestadas} prestada{p.prestadas === 1 ? "" : "s"} e {p.tomadas} tomada{p.tomadas === 1 ? "" : "s"}</span>}
                </div>
                <div className="mt-1 text-xs text-texto-2">
                  {p.arquivos_xml.toLocaleString("pt-BR")} arquivo(s) XML{f.incluir_eventos && ` (${p.eventos} de eventos)`} + relatório {f.relatorio.toUpperCase()}
                  {p.por_status.autorizada.quantidade > 0 && <> · {moeda(p.por_status.autorizada.valor)} autorizado</>}
                  {p.por_status.cancelada.quantidade > 0 && <> · {p.por_status.cancelada.quantidade} cancelada(s)</>}
                  {p.por_status.rejeitada.quantidade > 0 && <> · {p.por_status.rejeitada.quantidade} rejeitada(s)</>}
                </div>
                {p.empresas && (
                  <div className="mt-2 text-xs">
                    <button type="button" onClick={() => setVerEmpresas((v) => !v)} aria-expanded={verEmpresas} className="font-medium text-destaque hover:underline">
                      {p.empresas_com_notas} de {p.empresas.length} empresa(s) com notas · {verEmpresas ? "ocultar" : "ver por empresa"}
                    </button>
                    {verEmpresas && (
                      <ul className="mt-2 max-h-56 space-y-1 overflow-auto rounded-lg border border-borda bg-superficie p-2">
                        {p.empresas.map((e) => (
                          <li key={e.id} className={cn("flex items-center justify-between gap-3", e.total === 0 && "text-texto-2")}>
                            <span className="truncate font-mono text-[11px]" title={e.pasta}>{e.total ? `${e.pasta}/` : `${e.cnpj} ${e.nome} (sem notas: sem pasta)`}</span>
                            <span className="shrink-0 font-mono tabular-nums">{e.total.toLocaleString("pt-BR")}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
          <Button type="submit" variante="primario" className="mt-4 w-full" disabled={gerar.isPending || !p || p.total === 0 || previa.isError || semExportacao || foraDoPeriodo}>
            {gerar.isPending ? <Loader2 className="animate-spin" /> : semExportacao ? <Lock /> : <FileArchive />}{" "}
            {semExportacao ? "Exportação do teste já usada" : p && p.total === 0 ? "Nenhuma nota para exportar" : "Gerar exportação"}
          </Button>
        </form>

        <section aria-labelledby="titulo-historico">
          <h2 id="titulo-historico" className="mb-2 text-sm font-semibold">Histórico</h2>
          {historico.isLoading && <Esqueleto className="h-40 w-full" />}
          {historico.isError && <EstadoErro mensagem={(historico.error as Error).message} tentarDeNovo={() => historico.refetch()} />}
          {historico.data?.length === 0 && (
            <div className="rounded-xl border border-dashed border-borda-forte bg-superficie px-4 py-8 text-center text-sm text-texto-2">Nenhuma exportação desta empresa ainda.</div>
          )}
          <ul className="space-y-2">
            {historico.data?.map((x) => (
              <li key={x.id} className="rounded-xl border border-borda bg-superficie p-3.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-mono text-[13px]" title={x.arquivo ?? ""}>{x.arquivo}</div>
                    <div className="mt-0.5 text-xs text-texto-2">
                      {formatarDataHora(x.criado_em)}{x.total_notas !== null && <> · {x.total_notas.toLocaleString("pt-BR")} nota(s)</>}
                    </div>
                    <div className="mt-1 text-xs text-texto-2">
                      {x.escopo === "todas" && <span className="mr-1 rounded bg-destaque-suave px-1.5 py-0.5 font-medium text-destaque">Todas as empresas</span>}
                      {x.descricao.filter(([k]) => k !== "Data usada" && k !== "Empresas").map(([, v]) => v).join(" · ")}
                    </div>
                  </div>
                  {x.status === "concluido" ? <Selo tom="ok" icone={CheckCircle2}>Pronta</Selo>
                    : x.status === "erro" ? <Selo tom="erro" icone={XCircle}>Erro</Selo>
                    : x.status === "gerando" ? <Selo tom="destaque" icone={Loader2} className="[&_svg]:animate-spin">Gerando</Selo>
                    : <Selo tom="neutro" icone={Clock}>Na fila</Selo>}
                </div>
                {x.erro && (
                  <p className={cn("mt-2 flex items-start gap-1.5 rounded-lg px-2.5 py-1.5 text-xs", x.status === "erro" ? "bg-cancelada-suave" : "bg-rejeitada-suave")}>
                    <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {x.erro}
                  </p>
                )}
                {x.disponivel && (
                  <Button tamanho="pequeno" className="mt-2.5" asChild><a href={`/api/exportacoes/${x.id}/arquivo`}><Download /> Baixar ZIP</a></Button>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
