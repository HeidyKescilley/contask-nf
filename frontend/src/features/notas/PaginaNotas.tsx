import { ArrowDownToLine, ArrowUpFromLine, ChevronLeft, ChevronRight, Download, Eye, FileCode2, Lock, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Copiar } from "@/components/Copiar";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/campos";
import { Dica } from "@/components/ui/tooltip";
import { useEmpresaSelecionada } from "@/lib/empresas";
import { useTesteGratis } from "@/lib/sessao";
import { formatarDoc } from "@/lib/formato";
import { dataHoraXml, moeda, periodo, useNotas, type Nota, type Papel } from "@/lib/notas";
import { cn } from "@/lib/utils";
import { EstadoSemEmpresa } from "@/pages/paginas";
import { PainelNota, type ModoPainel } from "./PainelNota";
import { SeloNota } from "./SeloNota";

const STATUS = [
  { id: "", rotulo: "Todas" }, { id: "autorizada", rotulo: "Autorizadas" },
  { id: "cancelada", rotulo: "Canceladas" }, { id: "rejeitada", rotulo: "Rejeitadas" },
];
const ATALHOS = [
  { id: "mes", rotulo: "Este mês" }, { id: "mes_passado", rotulo: "Mês passado" },
  { id: "trimestre", rotulo: "Trimestre" }, { id: "ano", rotulo: "Ano" },
] as const;

function useFiltrosUrl() {
  const [p, setP] = useSearchParams();
  const definir = (mud: Record<string, string | null>, manterPagina = false) =>
    setP((atual) => {
      const n = new URLSearchParams(atual);
      for (const [k, v] of Object.entries(mud)) v ? n.set(k, v) : n.delete(k);
      if (!manterPagina) n.delete("page");
      return n;
    }, { replace: true });
  return {
    q: p.get("q") ?? "", inicio: p.get("inicio") ?? "", fim: p.get("fim") ?? "",
    campo_data: (p.get("campo_data") as "emissao" | "competencia") || "emissao",
    status: p.get("status") ?? "", page: Number(p.get("page")) || 1, ordem: p.get("ordem") ?? "emissao_desc",
    definir,
  };
}

export function PaginaNotas({ papel }: { papel: Papel }) {
  const { empresa, carregando } = useEmpresaSelecionada();
  const f = useFiltrosUrl();
  const [busca, setBusca] = useState(f.q);
  const [painel, setPainel] = useState<ModoPainel>(null);

  // Busca com espera curta para não consultar a cada tecla
  useEffect(() => setBusca(f.q), [f.q]);
  useEffect(() => {
    const t = setTimeout(() => { if (busca !== f.q) f.definir({ q: busca.trim() || null }); }, 300);
    return () => clearTimeout(t);
  }, [busca]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtros = useMemo(() => ({
    q: f.q, inicio: f.inicio, fim: f.fim, campo_data: f.campo_data, status: f.status, page: f.page, ordem: f.ordem,
  }), [f.q, f.inicio, f.fim, f.campo_data, f.status, f.page, f.ordem]);
  const lista = useNotas(empresa?.id, papel, filtros);

  const titulo = papel === "prestada" ? "Serviços Prestados" : "Serviços Tomados";
  const descricao = papel === "prestada" ? "Notas emitidas pela empresa (saídas)." : "Notas recebidas pela empresa (entradas).";
  const icone = papel === "prestada" ? ArrowUpFromLine : ArrowDownToLine;

  if (carregando) return <><Cabecalho titulo={titulo} descricao={descricao} /><Esqueleto className="h-96 w-full" /></>;
  if (!empresa) return <><Cabecalho titulo={titulo} descricao={descricao} /><EstadoSemEmpresa icone={icone} /></>;

  const temFiltro = !!(f.q || f.inicio || f.fim || f.status);
  const d = lista.data;
  const atalhoAtivo = ATALHOS.find((a) => { const [i, fi] = periodo(a.id); return i === f.inicio && fi === f.fim; })?.id;

  return (
    <>
      <Cabecalho titulo={titulo} descricao={descricao} />

      <div className="sticky top-14 z-20 -mx-6 mb-4 space-y-3 border-b border-borda bg-fundo/95 px-6 pb-3 pt-1 backdrop-blur">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-[340px]">
            <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-2" aria-hidden />
            <Input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Chave, número, valor (1.234,56) ou nome"
              className="pl-9 pr-8" aria-label="Buscar notas" />
            {busca && (
              <button onClick={() => { setBusca(""); f.definir({ q: null }); }} className="absolute right-2 top-2 rounded p-0.5 text-texto-2 hover:text-texto" aria-label="Limpar busca">
                <X className="size-4" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <select value={f.campo_data} onChange={(e) => f.definir({ campo_data: e.target.value === "emissao" ? null : e.target.value })}
              aria-label="Data usada no período" className="h-9 rounded-xl border border-borda bg-superficie px-2 text-sm">
              <option value="emissao">Emissão</option>
              <option value="competencia">Competência</option>
            </select>
            <Input type="date" value={f.inicio} onChange={(e) => f.definir({ inicio: e.target.value || null })} className="w-[150px]" aria-label="Início" />
            <span className="text-texto-2">a</span>
            <Input type="date" value={f.fim} onChange={(e) => f.definir({ fim: e.target.value || null })} className="w-[150px]" aria-label="Fim" />
          </div>
          <div className="flex gap-1" role="group" aria-label="Atalhos de período">
            {ATALHOS.map((a) => (
              <button key={a.id} aria-pressed={atalhoAtivo === a.id}
                onClick={() => { const [i, fi] = periodo(a.id); f.definir({ inicio: i, fim: fi }); }}
                className={cn("h-8 rounded-lg px-2 text-[13px]", atalhoAtivo === a.id ? "bg-destaque-suave font-medium text-destaque" : "text-texto-2 hover:bg-superficie-2 hover:text-texto")}>
                {a.rotulo}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 rounded-xl border border-borda bg-superficie p-1" role="group" aria-label="Status">
            {STATUS.map((s) => (
              <button key={s.id} onClick={() => f.definir({ status: s.id || null })} aria-pressed={f.status === s.id}
                className={cn("h-7 rounded-lg px-2.5 text-[13px]", f.status === s.id ? "bg-destaque-suave font-medium text-destaque" : "text-texto-2 hover:text-texto")}>
                {s.rotulo}
              </button>
            ))}
          </div>
          {temFiltro && (
            <button onClick={() => { setBusca(""); f.definir({ q: null, inicio: null, fim: null, status: null }); }} className="text-[13px] text-destaque hover:underline">
              Limpar filtros
            </button>
          )}
          <div className="ml-auto text-sm text-texto-2" aria-live="polite">
            {d && (
              <>
                <span className="font-mono tabular-nums text-texto">{d.total.toLocaleString("pt-BR")}</span> nota{d.total === 1 ? "" : "s"}
                {" · "}<span className="font-mono tabular-nums text-texto">{moeda(d.totais.valor_autorizado)}</span> autorizado
                {d.totais.canceladas > 0 && <> · {d.totais.canceladas} cancelada{d.totais.canceladas === 1 ? "" : "s"}</>}
                {d.totais.rejeitadas > 0 && <> · {d.totais.rejeitadas} rejeitada{d.totais.rejeitadas === 1 ? "" : "s"}</>}
              </>
            )}
          </div>
        </div>
      </div>

      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.isLoading && <TabelaEsqueleto />}
      {d && d.total === 0 && (
        <EstadoVazio icone={icone} titulo={temFiltro ? "Nenhuma nota com esses filtros" : "Nenhuma nota ainda"}>
          {temFiltro ? "Tente outro período, status ou termo de busca."
            : empresa.busca.situacao === "buscando" || empresa.busca.job_pendente
              ? "A busca está em andamento: as notas aparecem aqui conforme chegam."
              : `Nenhuma nota ${papel === "prestada" ? "emitida" : "recebida"} encontrada no ADN para esta empresa.`}
        </EstadoVazio>
      )}
      {d && d.total > 0 && (
        <>
          <Tabela itens={d.itens} papel={papel} ordem={f.ordem} aoOrdenar={(o) => f.definir({ ordem: o === "emissao_desc" ? null : o }, true)}
            carregando={lista.isFetching} abrir={setPainel} />
          <Paginacao pagina={d.pagina} paginas={d.paginas} total={d.total} limite={d.limite} ir={(p) => f.definir({ page: p > 1 ? String(p) : null }, true)} />
        </>
      )}
      <PainelNota modo={painel} aoFechar={() => setPainel(null)} aoTrocar={setPainel} />
    </>
  );
}

function TabelaEsqueleto() {
  return (
    <div className="space-y-px overflow-hidden rounded-xl border border-borda bg-superficie" aria-label="Carregando notas">
      {Array.from({ length: 8 }).map((_, i) => <div key={i} className="flex gap-4 px-4 py-3"><Esqueleto className="h-9 flex-1" /><Esqueleto className="h-9 w-24" /><Esqueleto className="h-9 w-28" /></div>)}
    </div>
  );
}

function CabecalhoOrdenavel({ rotulo, campo, ordem, aoOrdenar, className }: { rotulo: string; campo: string; ordem: string; aoOrdenar: (o: string) => void; className?: string }) {
  const ativo = ordem === campo || ordem === `${campo}_desc`;
  const desc = ordem === `${campo}_desc`;
  return (
    <th className={cn("px-3 py-2.5 font-medium", className)} aria-sort={ativo ? (desc ? "descending" : "ascending") : "none"}>
      <button onClick={() => aoOrdenar(desc ? campo : `${campo}_desc`)} className={cn("inline-flex items-center gap-1 hover:text-texto", ativo && "text-texto")}>
        {rotulo}<span aria-hidden className="text-[10px]">{ativo ? (desc ? "▼" : "▲") : ""}</span>
      </button>
    </th>
  );
}

function Tabela({ itens, papel, ordem, aoOrdenar, carregando, abrir }: {
  itens: Nota[]; papel: Papel; ordem: string; aoOrdenar: (o: string) => void; carregando: boolean; abrir: (m: ModoPainel) => void;
}) {
  return (
    <div className={cn("overflow-hidden rounded-xl border border-borda bg-superficie transition-opacity duration-150", carregando && "opacity-70")}>
      <table className="w-full table-fixed text-sm">
        <colgroup>
          <col /><col className="w-12" /><col className="w-[130px]" /><col className="w-[130px]" /><col className="w-[140px]" /><col className="w-[150px]" /><col className="w-0" />
        </colgroup>
        <thead className="whitespace-nowrap border-b border-borda bg-fundo text-left text-xs text-texto-2">
          <tr>
            <th className="px-4 py-2.5 font-medium">{papel === "prestada" ? "Tomador" : "Emitente"}</th>
            <th className="px-3 py-2.5 font-medium">UF</th>
            <CabecalhoOrdenavel rotulo="Número / Série" campo="numero" ordem={ordem} aoOrdenar={aoOrdenar} />
            <CabecalhoOrdenavel rotulo="Valor" campo="valor" ordem={ordem} aoOrdenar={aoOrdenar} className="text-right [&_button]:justify-end" />
            <CabecalhoOrdenavel rotulo="Emissão" campo="emissao" ordem={ordem} aoOrdenar={aoOrdenar} />
            <th className="px-3 py-2.5 font-medium">Status</th>
            <th className="p-0"><span className="sr-only">Ações</span></th>
          </tr>
        </thead>
        <tbody>
          {itens.map((n) => <LinhaNota key={n.id} n={n} papel={papel} abrir={abrir} />)}
        </tbody>
      </table>
    </div>
  );
}

function LinhaNota({ n, papel, abrir }: { n: Nota; papel: Papel; abrir: (m: ModoPainel) => void }) {
  const { emTeste } = useTesteGratis();
  const nome = papel === "prestada" ? (n.tomador_nome ?? (n.tomador_doc ? "—" : "Tomador não informado")) : (n.emitente_nome ?? "—");
  const doc = papel === "prestada" ? n.tomador_doc : n.emitente_doc;
  const cancelada = n.status === "cancelada";
  return (
    <tr tabIndex={0} onClick={() => abrir({ tipo: "detalhe", id: n.id })}
      onKeyDown={(e) => { if (e.key === "Enter" && e.target === e.currentTarget) abrir({ tipo: "detalhe", id: n.id }); }}
      aria-label={`Nota ${n.numero ?? ""}, ${nome}, ${moeda(n.valor_servico)}`}
      className="group/linha relative cursor-pointer border-b border-borda outline-none last:border-0 hover:bg-superficie-2 focus-visible:bg-superficie-2 focus-within:bg-superficie-2 focus-visible:[box-shadow:inset_2px_0_0_var(--foco)]">
      <td className="min-w-0 px-4 py-2">
        <div className={cn("truncate font-medium", !n.tomador_nome && papel === "prestada" && "font-normal italic text-texto-2")}>{nome}</div>
        <div className="flex min-w-0 items-center gap-2 text-xs text-texto-2">
          {doc && <span className="shrink-0 font-mono">{formatarDoc(doc)}</span>}
          <span onClick={(e) => e.stopPropagation()} className="min-w-0 truncate"><Copiar texto={n.chave} className="max-w-full truncate text-[11px]" /></span>
        </div>
      </td>
      <td className="px-3 py-2 text-texto-2">{n.emitente_uf ?? "—"}</td>
      <td className="truncate px-3 py-2 font-mono text-[13px] tabular-nums">{n.numero ?? "—"}<span className="text-texto-2"> / {n.serie ?? "—"}</span></td>
      <td className={cn("px-3 py-2 text-right font-mono text-[13px] tabular-nums", cancelada && "text-texto-2 line-through")}>{moeda(n.valor_servico)}</td>
      <td className="whitespace-nowrap px-3 py-2 font-mono text-[13px] tabular-nums text-texto-2">{dataHoraXml(n.data_emissao)}</td>
      <td className="px-3 py-2"><SeloNota n={n} /></td>
      {/* Ações: dentro da própria linha (célula sem largura), sem cobrir a linha de baixo */}
      <td className="relative w-0 p-0">
        <div onClick={(e) => e.stopPropagation()}
          className="acoes-linha absolute inset-y-0 right-0 flex items-center gap-1 bg-gradient-to-l from-superficie-2 from-70% to-transparent pl-10 pr-3 opacity-0 transition-opacity duration-150 group-hover/linha:opacity-100 group-focus-within/linha:opacity-100">
          <Dica texto="Ver PDF" lado="top">
            <button onClick={() => abrir({ tipo: "pdf", id: n.id })} className="rounded-lg p-1.5 text-texto-2 hover:bg-superficie hover:text-destaque" aria-label={`Ver PDF da nota ${n.numero ?? ""}`}><Eye className="size-4" /></button>
          </Dica>
          {emTeste ? (
            <Dica texto="Download do PDF e do XML: disponível no plano" lado="top">
              <span className="rounded-lg p-1.5 text-texto-2" aria-label="Download disponível no plano"><Lock className="size-4" /></span>
            </Dica>
          ) : (
            <>
              <Dica texto="Baixar PDF" lado="top">
                <a href={`/api/notas/${n.id}/pdf?download=1`} className="rounded-lg p-1.5 text-texto-2 hover:bg-superficie hover:text-destaque" aria-label={`Baixar PDF da nota ${n.numero ?? ""}`}><Download className="size-4" /></a>
              </Dica>
              <Dica texto="Baixar XML" lado="top">
                <a href={`/api/notas/${n.id}/xml`} className="rounded-lg p-1.5 text-texto-2 hover:bg-superficie hover:text-destaque" aria-label={`Baixar XML da nota ${n.numero ?? ""}`}><FileCode2 className="size-4" /></a>
              </Dica>
            </>
          )}
        </div>
      </td>
    </tr>
  );
}

function Paginacao({ pagina, paginas, total, limite, ir }: { pagina: number; paginas: number; total: number; limite: number; ir: (p: number) => void }) {
  const ini = (pagina - 1) * limite + 1;
  const fim = Math.min(pagina * limite, total);
  return (
    <nav className="mt-3 flex items-center justify-between text-sm text-texto-2" aria-label="Paginação">
      <span>Mostrando <span className="font-mono tabular-nums">{ini}–{fim}</span> de <span className="font-mono tabular-nums">{total.toLocaleString("pt-BR")}</span></span>
      <div className="flex items-center gap-2">
        <Button tamanho="pequeno" disabled={pagina <= 1} onClick={() => ir(pagina - 1)} aria-label="Página anterior"><ChevronLeft /></Button>
        <span className="font-mono tabular-nums">{pagina} / {paginas}</span>
        <Button tamanho="pequeno" disabled={pagina >= paginas} onClick={() => ir(pagina + 1)} aria-label="Próxima página"><ChevronRight /></Button>
      </div>
    </nav>
  );
}
