import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BadgeCheck, Building2, ChevronRight, Loader2, Search, ShieldCheck, ShieldX } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/campos";
import { Dica } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useAtualizarEmissor, useEmpresasEmissoras, type EmpresaEmissora } from "@/lib/emissor";
import { nomeExibicao } from "@/lib/empresas";
import { formatarData, formatarDoc, limparCnpj } from "@/lib/formato";
import { cn } from "@/lib/utils";
import { AbasEmissor } from "./Abas";

const FILTROS = [
  { id: "todas", rotulo: "Todas" },
  { id: "emitem", rotulo: "Emitem" },
  { id: "nao", rotulo: "Não emitem" },
  { id: "pendentes", rotulo: "Emitem com pendência" },
] as const;
type Filtro = (typeof FILTROS)[number]["id"];

export function SeloCertEmissor({ e }: { e: EmpresaEmissora }) {
  if (!e.certificado) return <Selo tom="erro" icone={ShieldX}>Sem certificado próprio</Selo>;
  if (e.certificado.situacao === "vencido") return <Selo tom="erro" icone={ShieldX}>Vencido em {formatarData(e.certificado.validade)}</Selo>;
  const tom = e.certificado.situacao === "ok" ? "ok" : "alerta";
  return <Selo tom={tom} icone={ShieldCheck}>Válido até {formatarData(e.certificado.validade)}</Selo>;
}

export function SeloSituacaoEmissor({ e }: { e: EmpresaEmissora }) {
  if (!e.emite_nfse) return <span className="text-texto-2">—</span>;
  if (e.pronta) return <Selo tom="ok" icone={BadgeCheck}>Pronta para emitir</Selo>;
  return (
    <Dica texto={e.pendencias.join(" ")} lado="left">
      <span><Selo tom="alerta" icone={AlertTriangle}>{e.pendencias.length} pendência{e.pendencias.length > 1 ? "s" : ""}</Selo></span>
    </Dica>
  );
}

export function EmpresasEmissoras() {
  const lista = useEmpresasEmissoras();
  const atualizar = useAtualizarEmissor();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todas");

  const marcar = useMutation({
    mutationFn: (v: { ids: number[]; emite: boolean }) =>
      api<{ atualizadas: number }>("/api/emissor/empresas/emissao", { method: "PUT", body: JSON.stringify({ empresa_ids: v.ids, emite: v.emite }) }),
    // Atualização otimista: o checkbox responde na hora, mesmo marcando muitas de uma vez
    onMutate: ({ ids, emite }) => {
      qc.setQueryData<EmpresaEmissora[]>(["emissor", "empresas"], (ant) =>
        ant?.map((e) => (ids.includes(e.id) ? { ...e, emite_nfse: emite } : e)));
    },
    onSuccess: (r, v) => { if (v.ids.length > 1) toast.success(`${r.atualizadas} empresa(s) ${v.emite ? "marcadas como emissoras" : "desmarcadas"}.`); },
    onError: (err) => toast.error((err as Error).message),
    onSettled: () => atualizar(),
  });

  const visiveis = useMemo(() => {
    const termo = q.trim().toLowerCase();
    const doc = limparCnpj(q);
    return (lista.data ?? []).filter((e) => {
      if (filtro === "emitem" && !e.emite_nfse) return false;
      if (filtro === "nao" && e.emite_nfse) return false;
      if (filtro === "pendentes" && !(e.emite_nfse && !e.pronta)) return false;
      if (!termo) return true;
      return [e.razao_social, e.nome_fantasia, e.apelido].some((t) => t?.toLowerCase().includes(termo)) ||
        (doc.length > 0 && e.cnpj.includes(doc));
    });
  }, [lista.data, q, filtro]);

  const total = lista.data?.length ?? 0;
  const emitem = lista.data?.filter((e) => e.emite_nfse).length ?? 0;
  const todasMarcadas = visiveis.length > 0 && visiveis.every((e) => e.emite_nfse);
  const algumaMarcada = visiveis.some((e) => e.emite_nfse);

  return (
    <>
      <Cabecalho titulo="Emissor de NFS-e" descricao="Escolha quais empresas emitem nota pelo Contask e configure cada uma." />
      <AbasEmissor />

      {lista.isLoading && <Esqueleto className="h-64 w-full" />}
      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.data && total === 0 && (
        <EstadoVazio icone={Building2} titulo="Nenhuma empresa cadastrada"
          acao={<Button variante="primario" asChild><Link to="/empresas/nova">Cadastrar empresa</Link></Button>}>
          As empresas do cadastro aparecem aqui para você marcar quais emitem NFS-e.
        </EstadoVazio>
      )}

      {lista.data && total > 0 && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative w-80">
              <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-2" aria-hidden />
              <Input value={q} onChange={(ev) => setQ(ev.target.value)} placeholder="Nome, apelido ou CNPJ" className="pl-9" aria-label="Filtrar empresas" />
            </div>
            <div className="flex gap-1 rounded-xl border border-borda bg-superficie p-1" role="group" aria-label="Filtro rápido">
              {FILTROS.map((f) => (
                <button key={f.id} onClick={() => setFiltro(f.id)} aria-pressed={filtro === f.id}
                  className={cn("h-7 rounded-lg px-2.5 text-[13px]", filtro === f.id ? "bg-destaque-suave font-medium text-destaque" : "text-texto-2 hover:text-texto")}>
                  {f.rotulo}
                </button>
              ))}
            </div>
            <span className="ml-auto text-sm text-texto-2">{emitem} de {total} emitem NFS-e</span>
          </div>

          {visiveis.length === 0 ? (
            <EstadoVazio icone={Search} titulo="Nenhuma empresa neste filtro">Tente outro filtro ou termo.</EstadoVazio>
          ) : (
            <div className="overflow-hidden rounded-xl border border-borda bg-superficie">
              <table className="w-full text-sm">
                <thead className="border-b border-borda bg-fundo text-left text-xs text-texto-2">
                  <tr>
                    <th className="w-24 px-4 py-2.5 font-medium">
                      <label className="flex cursor-pointer items-center gap-2">
                        <input type="checkbox" className="size-4 cursor-pointer accent-destaque"
                          checked={todasMarcadas}
                          ref={(el) => { if (el) el.indeterminate = algumaMarcada && !todasMarcadas; }}
                          disabled={marcar.isPending}
                          onChange={() => marcar.mutate({ ids: visiveis.map((e) => e.id), emite: !todasMarcadas })}
                          aria-label={todasMarcadas ? "Desmarcar todas as empresas listadas" : "Marcar todas as empresas listadas"} />
                        Emite
                      </label>
                    </th>
                    <th className="px-3 py-2.5 font-medium">Empresa</th>
                    <th className="px-3 py-2.5 font-medium">Certificado para emitir</th>
                    <th className="px-3 py-2.5 text-right font-medium">Serviços</th>
                    <th className="px-3 py-2.5 font-medium">Situação</th>
                    <th className="w-10 px-2" aria-label="Configurar" />
                  </tr>
                </thead>
                <tbody>
                  {visiveis.map((e) => (
                    <tr key={e.id} className={cn("border-b border-borda last:border-0 hover:bg-superficie-2/60", !e.ativa && "opacity-60")}>
                      <td className="px-4 py-2.5">
                        <input type="checkbox" className="size-4 cursor-pointer accent-destaque" checked={e.emite_nfse}
                          onChange={() => marcar.mutate({ ids: [e.id], emite: !e.emite_nfse })}
                          aria-label={`${nomeExibicao(e)} emite NFS-e`} />
                      </td>
                      <td className="px-3 py-2.5">
                        <Link to={`/emissor/empresas/${e.id}`} className="font-medium hover:text-destaque">{nomeExibicao(e)}</Link>
                        {e.is_contabilidade && <span className="ml-2 rounded bg-destaque-suave px-1.5 py-0.5 text-[11px] font-medium text-destaque">Contabilidade</span>}
                        {!e.ativa && <span className="ml-2 text-xs text-texto-2">(inativa)</span>}
                        <div className="font-mono text-xs text-texto-2">{formatarDoc(e.cnpj)}</div>
                      </td>
                      <td className="px-3 py-2.5"><SeloCertEmissor e={e} /></td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">{e.servicos}</td>
                      <td className="px-3 py-2.5"><SeloSituacaoEmissor e={e} /></td>
                      <td className="px-2 py-2.5">
                        <Link to={`/emissor/empresas/${e.id}`} aria-label={`Configurar ${nomeExibicao(e)}`}
                          className="flex size-8 items-center justify-center rounded-lg text-texto-2 hover:bg-superficie-2 hover:text-texto">
                          <ChevronRight className="size-4" aria-hidden />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {marcar.isPending && <p className="mt-2 flex items-center gap-2 text-xs text-texto-2"><Loader2 className="size-3.5 animate-spin" /> Salvando…</p>}
        </>
      )}
    </>
  );
}
