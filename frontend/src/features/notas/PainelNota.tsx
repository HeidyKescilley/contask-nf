import * as D from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, ExternalLink, FileCode2, FileText, Loader2, Lock, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Copiar } from "@/components/Copiar";
import { Button } from "@/components/ui/button";
import { formatarDoc } from "@/lib/formato";
import { dataHoraXml, dataXml, moeda, useDetalheNota } from "@/lib/notas";
import { useTesteGratis } from "@/lib/sessao";
import { cn } from "@/lib/utils";
import { SeloNota } from "./SeloNota";

export type ModoPainel = { tipo: "pdf" | "detalhe"; id: number } | null;

/** Busca o PDF como blob: mostra carregamento na 1ª geração e explica erros (o iframe sozinho não sabe). */
function usePdf(id: number | null, ativo: boolean) {
  const q = useQuery({
    queryKey: ["pdf", id],
    enabled: ativo && id !== null,
    staleTime: Infinity,
    gcTime: 60_000,
    retry: false,
    queryFn: async () => {
      let r: Response;
      try {
        r = await fetch(`/api/notas/${id}/pdf`);
      } catch {
        throw new Error("Não foi possível falar com o servidor local.");
      }
      if (!r.ok) {
        let msg = `Erro ${r.status} ao gerar o DANFSe.`;
        try { msg = (await r.json()).detail ?? msg; } catch { /* sem JSON */ }
        throw new Error(msg);
      }
      return URL.createObjectURL(await r.blob());
    },
  });
  useEffect(() => () => { if (q.data) URL.revokeObjectURL(q.data); }, [q.data]);
  return q;
}

function Linha({ rotulo, children, mono }: { rotulo: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[150px_1fr] gap-3 border-b border-borda py-2 text-sm last:border-0">
      <dt className="text-texto-2">{rotulo}</dt>
      <dd className={cn("min-w-0 break-words", mono && "font-mono text-[13px] tabular-nums")}>{children}</dd>
    </div>
  );
}

export function PainelNota({ modo, aoFechar, aoTrocar }: { modo: ModoPainel; aoFechar: () => void; aoTrocar: (m: ModoPainel) => void }) {
  const { emTeste } = useTesteGratis();
  const id = modo?.id ?? null;
  const det = useDetalheNota(id);
  const pdf = usePdf(id, modo?.tipo === "pdf");
  const [carregouIframe, setCarregouIframe] = useState(false);
  useEffect(() => setCarregouIframe(false), [pdf.data]);
  const n = det.data;

  return (
    <D.Root open={!!modo} onOpenChange={(a) => !a && aoFechar()}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-black/25" />
        <D.Content aria-describedby={undefined}
          className={cn("fixed inset-y-0 right-0 z-50 flex flex-col border-l border-borda bg-fundo text-texto shadow-[-12px_0_32px_-16px_rgb(0_0_0/0.3)]",
            modo?.tipo === "pdf" ? "w-[min(820px,100vw)]" : "w-[min(560px,100vw)]")}>
          <div className="flex items-center gap-3 border-b border-borda bg-superficie px-5 py-3">
            <div className="min-w-0 flex-1">
              <D.Title className="truncate text-base font-semibold">
                {n ? `NFS-e nº ${n.numero ?? "—"}` : "Nota"}{n?.serie ? <span className="font-normal text-texto-2"> · série {n.serie}</span> : null}
              </D.Title>
              {n && <Copiar texto={n.chave} className="text-xs" />}
            </div>
            <div className="flex gap-1" role="tablist" aria-label="Visualização">
              {(["detalhe", "pdf"] as const).map((t) => (
                <button key={t} role="tab" aria-selected={modo?.tipo === t} onClick={() => id && aoTrocar({ tipo: t, id })}
                  className={cn("h-8 rounded-lg px-2.5 text-[13px]", modo?.tipo === t ? "bg-destaque-suave font-medium text-destaque" : "text-texto-2 hover:bg-superficie-2")}>
                  {t === "pdf" ? "DANFSe" : "Detalhes"}
                </button>
              ))}
            </div>
            <D.Close className="rounded-lg p-1.5 text-texto-2 hover:bg-superficie-2" aria-label="Fechar"><X className="size-4" /></D.Close>
          </div>

          <div className="flex items-center gap-2 border-b border-borda bg-superficie px-5 py-2">
            {id && (
              <>
                {emTeste ? (
                  <span className="inline-flex items-center gap-1.5 text-xs text-texto-2"><Lock className="size-3.5" aria-hidden /> Download do PDF e do XML disponível no plano</span>
                ) : (
                  <>
                    <Button tamanho="pequeno" asChild><a href={`/api/notas/${id}/pdf?download=1`}><Download /> Baixar PDF</a></Button>
                    <Button tamanho="pequeno" asChild><a href={`/api/notas/${id}/xml`}><FileCode2 /> Baixar XML</a></Button>
                  </>
                )}
                {!emTeste && modo?.tipo === "pdf" && pdf.data && (
                  <Button tamanho="pequeno" variante="fantasma" asChild><a href={pdf.data} target="_blank" rel="noreferrer"><ExternalLink /> Abrir em nova aba</a></Button>
                )}
              </>
            )}
          </div>

          {modo?.tipo === "pdf" ? (
            <div className="relative flex-1 bg-superficie-2">
              {(pdf.isLoading || (pdf.data && !carregouIframe)) && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-sm text-texto-2">
                  <Loader2 className="size-5 animate-spin text-destaque" aria-hidden />
                  Gerando o DANFSe a partir do XML…
                </div>
              )}
              {pdf.isError && (
                <div className="absolute inset-0 flex items-center justify-center p-6">
                  <div role="alert" className="max-w-md rounded-xl border border-cancelada/30 bg-cancelada-suave p-4 text-sm">
                    <div className="flex items-center gap-2 font-medium"><AlertTriangle className="size-4 text-cancelada" /> Não foi possível abrir o DANFSe</div>
                    <p className="mt-1 text-texto-2">{(pdf.error as Error).message}</p>
                    <Button tamanho="pequeno" className="mt-3" onClick={() => pdf.refetch()}><RefreshCw /> Tentar de novo</Button>
                  </div>
                </div>
              )}
              {pdf.data && (
                <iframe title="DANFSe" src={pdf.data} onLoad={() => setCarregouIframe(true)} className="size-full border-0" />
              )}
              <p className="absolute bottom-2 left-5 rounded bg-superficie/90 px-2 py-0.5 text-[11px] text-texto-2">
                DANFSe gerado neste computador a partir do XML, conforme a NT SE/CGNFS-e 008/2026.
              </p>
            </div>
          ) : (
            <div className="flex-1 overflow-auto p-5">
              {det.isLoading && <div className="h-64 animate-pulse rounded-xl bg-superficie-2" />}
              {det.isError && <p className="text-sm text-cancelada">{(det.error as Error).message}</p>}
              {n && (
                <div className="space-y-5">
                  <div className="flex items-center justify-between rounded-xl border border-borda bg-superficie p-4">
                    <div>
                      <div className="text-xs text-texto-2">Valor do serviço</div>
                      <div className={cn("font-mono text-xl tabular-nums", n.status === "cancelada" && "text-texto-2 line-through")}>{moeda(n.valor_servico)}</div>
                    </div>
                    <SeloNota n={n} />
                  </div>
                  <dl className="rounded-xl border border-borda bg-superficie px-4">
                    <Linha rotulo="Emitente">{n.emitente_nome ?? "—"} <span className="font-mono text-xs text-texto-2">{n.emitente_doc && formatarDoc(n.emitente_doc)}</span></Linha>
                    <Linha rotulo="Tomador">{n.tomador_nome ?? (n.tomador_doc ? "—" : "Não informado")} <span className="font-mono text-xs text-texto-2">{n.tomador_doc && formatarDoc(n.tomador_doc)}</span></Linha>
                    <Linha rotulo="Emissão" mono>{dataHoraXml(n.data_emissao)}</Linha>
                    <Linha rotulo="Competência" mono>{dataXml(n.competencia)}</Linha>
                    <Linha rotulo="Local da prestação">{n.municipio ?? "—"}</Linha>
                    <Linha rotulo="Valor líquido" mono>{moeda(n.valor_liquido)}</Linha>
                    <Linha rotulo="ISSQN" mono>{moeda(n.valor_iss)}</Linha>
                    <Linha rotulo="Nº da DPS" mono>{n.n_dps ?? "—"}</Linha>
                    <Linha rotulo="NSU" mono>{n.nsu ?? "—"}</Linha>
                  </dl>
                  <section>
                    <h3 className="mb-2 text-sm font-semibold">Histórico de eventos</h3>
                    {n.eventos.length === 0 ? (
                      <p className="rounded-xl border border-dashed border-borda-forte px-4 py-4 text-sm text-texto-2">Nenhum evento para esta nota.</p>
                    ) : (
                      <ol className="space-y-2 border-l-2 border-borda pl-4">
                        {n.eventos.map((e, i) => (
                          <li key={i} className="relative">
                            <span className="absolute -left-[21px] top-1.5 size-2.5 rounded-full border-2 border-fundo bg-destaque" aria-hidden />
                            <div className="text-sm font-medium">{e.descricao}{!e.conhecido && <span className="ml-1 text-xs text-rejeitada">(não classificado)</span>}</div>
                            <div className="font-mono text-xs text-texto-2">{e.codigo ?? "—"} · {dataHoraXml(e.data_evento)} · NSU {e.nsu}</div>
                          </li>
                        ))}
                      </ol>
                    )}
                  </section>
                  <Button onClick={() => aoTrocar({ tipo: "pdf", id: n.id })}><FileText /> Ver DANFSe</Button>
                </div>
              )}
            </div>
          )}
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
