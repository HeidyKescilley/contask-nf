import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Loader2, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { apenasDigitos, useAtualizarEmissor, type CodigoNbs, type CodigoServico, type Servico, type Sugestao } from "@/lib/emissor";
import { cn } from "@/lib/utils";

function useAtraso<T>(valor: T, ms = 250) {
  const [v, setV] = useState(valor);
  useEffect(() => { const t = setTimeout(() => setV(valor), ms); return () => clearTimeout(t); }, [valor, ms]);
  return v;
}

/** Busca com lista de resultados (código ou descrição). */
function BuscaCodigo<T extends { codigo: string; codigo_formatado: string; descricao: string }>({ id, rotulo, url, aoEscolher, placeholder }: {
  id: string; rotulo: string; url: string; aoEscolher: (item: T) => void; placeholder: string;
}) {
  const [q, setQ] = useState("");
  const termo = useAtraso(q.trim());
  const res = useQuery({
    queryKey: ["emissor", "codigos", url, termo],
    queryFn: () => api<T[]>(`${url}?${new URLSearchParams({ q: termo, limite: "12" })}`),
    enabled: termo.length >= 2,
  });
  return (
    <div>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-2" aria-hidden />
        <Input id={id} value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="pl-9" aria-label={rotulo} autoComplete="off" />
      </div>
      {termo.length >= 2 && (
        <div className="mt-1.5 max-h-56 overflow-y-auto rounded-xl border border-borda" role="listbox" aria-label={`Resultados: ${rotulo}`}>
          {res.isLoading && <p className="flex items-center gap-2 px-3 py-2 text-sm text-texto-2"><Loader2 className="size-4 animate-spin" /> Buscando…</p>}
          {res.isError && <p className="px-3 py-2 text-sm text-cancelada">{(res.error as Error).message}</p>}
          {res.data?.length === 0 && <p className="px-3 py-2 text-sm text-texto-2">Nada encontrado. Tente outra palavra ou o código.</p>}
          {res.data?.map((item) => (
            <button key={item.codigo} type="button" role="option" aria-selected={false}
              onClick={() => { aoEscolher(item); setQ(""); }}
              className="flex w-full gap-3 border-b border-borda px-3 py-2 text-left text-sm last:border-0 hover:bg-superficie-2">
              <span className="shrink-0 font-mono text-texto-2">{item.codigo_formatado}</span>
              <span>{item.descricao}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Escolhido({ codigo, descricao, limpar }: { codigo: string; descricao: string | null; limpar: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-destaque/40 bg-destaque-suave/50 px-3 py-2 text-sm">
      <Check className="mt-0.5 size-4 shrink-0 text-destaque" aria-hidden />
      <span className="flex-1"><span className="font-mono">{codigo}</span> · {descricao ?? "—"}</span>
      <button type="button" onClick={limpar} className="rounded p-0.5 text-texto-2 hover:text-texto" aria-label="Trocar código"><X className="size-4" /></button>
    </div>
  );
}

const VAZIO = { descricao: "", ctribnac: "", ctribnac_formatado: "", ctribnac_descricao: null as string | null,
  cnbs: "", cnbs_formatado: "", cnbs_descricao: null as string | null, ctribmun: "", cindop: "", cclasstrib: "", ativo: true };

export function ServicoDialog({ empresaId, servico, aberto, aoFechar, aoSalvar }: {
  empresaId: number; servico: Servico | null; aberto: boolean; aoFechar: () => void; aoSalvar?: (s: Servico) => void;
}) {
  const atualizar = useAtualizarEmissor();
  const [f, setF] = useState(VAZIO);
  useEffect(() => {
    if (aberto) setF(servico ? { ...VAZIO, ...servico, ctribmun: servico.ctribmun ?? "", cindop: servico.cindop ?? "", cclasstrib: servico.cclasstrib ?? "" } : VAZIO);
  }, [aberto, servico]);

  const sugestoes = useQuery({
    queryKey: ["emissor", "sugestoes", f.ctribnac],
    queryFn: () => api<Sugestao[]>(`/api/emissor/codigos/sugestoes/${f.ctribnac}`),
    enabled: f.ctribnac.length === 6,
  });

  const salvar = useMutation({
    mutationFn: () => {
      const corpo = JSON.stringify({ descricao: f.descricao, ctribnac: f.ctribnac, cnbs: f.cnbs, ctribmun: f.ctribmun,
        cindop: f.cindop, cclasstrib: f.cclasstrib, ativo: f.ativo });
      return servico
        ? api<Servico>(`/api/emissor/servicos/${servico.id}`, { method: "PUT", body: corpo })
        : api<Servico>(`/api/emissor/empresas/${empresaId}/servicos`, { method: "POST", body: corpo });
    },
    onSuccess: (s) => { atualizar(); toast.success(servico ? "Serviço atualizado." : "Serviço cadastrado."); aoSalvar?.(s); aoFechar(); },
  });

  const escolherNbs = (s: { nbs: string; nbs_formatado: string; nbs_descricao: string | null; cindop?: string | null; cclasstrib?: string | null }) =>
    setF((a) => ({ ...a, cnbs: s.nbs, cnbs_formatado: s.nbs_formatado, cnbs_descricao: s.nbs_descricao,
      cindop: s.cindop ?? a.cindop, cclasstrib: s.cclasstrib ?? a.cclasstrib }));

  const valido = f.descricao.trim().length > 0 && f.ctribnac.length === 6 && f.cnbs.length === 9 &&
    [0, 3].includes(apenasDigitos(f.ctribmun).length);

  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && aoFechar()}>
      <DialogContent largo titulo={servico ? "Editar serviço" : "Novo serviço"}
        descricao="A descrição e os códigos ficam salvos. Valor, retenções e tributos são informados em cada emissão.">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (valido) salvar.mutate(); }}>
          <Campo rotulo="Descrição do serviço" obrigatorio ajuda={`${f.descricao.length}/2000. Vai no campo "Discriminação" da nota.`}>
            {(p) => (
              <textarea {...p} value={f.descricao} maxLength={2000} rows={3}
                onChange={(e) => setF({ ...f, descricao: e.target.value })}
                className="w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none hover:border-borda-forte focus-visible:border-destaque focus-visible:ring-2 focus-visible:ring-destaque/25"
                placeholder="Ex.: Honorários de serviços contábeis referentes ao mês." />
            )}
          </Campo>

          <Campo rotulo="Código de tributação nacional (item da LC 116)" obrigatorio>
            {(p) => f.ctribnac
              ? <Escolhido codigo={f.ctribnac_formatado} descricao={f.ctribnac_descricao}
                  limpar={() => setF({ ...f, ctribnac: "", ctribnac_formatado: "", ctribnac_descricao: null, cnbs: "", cnbs_formatado: "", cnbs_descricao: null, cindop: "", cclasstrib: "" })} />
              : <BuscaCodigo<CodigoServico> id={p.id} rotulo="Código de tributação nacional" url="/api/emissor/codigos/servicos"
                  placeholder="Digite o código (17.19) ou uma palavra (contabilidade)"
                  aoEscolher={(i) => setF({ ...f, ctribnac: i.codigo, ctribnac_formatado: i.codigo_formatado, ctribnac_descricao: i.descricao })} />}
          </Campo>

          {f.ctribnac && (
            <Campo rotulo="NBS (Nomenclatura Brasileira de Serviços)" obrigatorio
              ajuda={!f.cnbs && sugestoes.data && sugestoes.data.length > 0 ? "Sugestões da tabela oficial para este item (Anexo VIII):" : undefined}>
              {(p) => f.cnbs
                ? <Escolhido codigo={f.cnbs_formatado} descricao={f.cnbs_descricao}
                    limpar={() => setF({ ...f, cnbs: "", cnbs_formatado: "", cnbs_descricao: null })} />
                : (
                  <div className="space-y-2">
                    {sugestoes.data && sugestoes.data.length > 0 && (
                      <div className="flex flex-col gap-1.5">
                        {sugestoes.data.map((s) => (
                          <button key={s.nbs} type="button" onClick={() => escolherNbs(s)}
                            className="flex gap-3 rounded-xl border border-borda px-3 py-2 text-left text-sm hover:border-destaque hover:bg-destaque-suave/40">
                            <span className="shrink-0 font-mono text-texto-2">{s.nbs_formatado}</span>
                            <span>{s.nbs_descricao}</span>
                          </button>
                        ))}
                      </div>
                    )}
                    <BuscaCodigo<CodigoNbs> id={p.id} rotulo="Buscar outra NBS" url="/api/emissor/codigos/nbs"
                      placeholder="Ou busque outra NBS pelo código ou descrição"
                      aoEscolher={(i) => escolherNbs({ nbs: i.codigo, nbs_formatado: i.codigo_formatado, nbs_descricao: i.descricao })} />
                  </div>
                )}
            </Campo>
          )}

          <div className="grid grid-cols-3 gap-3">
            <Campo rotulo="Código municipal" ajuda="Complementar, se o município usar (3 dígitos).">
              {(p) => <Input {...p} value={f.ctribmun} inputMode="numeric" maxLength={3}
                onChange={(e) => setF({ ...f, ctribmun: apenasDigitos(e.target.value) })} placeholder="Opcional" />}
            </Campo>
            <Campo rotulo="cIndOp (IBS/CBS)" ajuda="Sugerido pela NBS.">
              {(p) => <Input {...p} value={f.cindop} inputMode="numeric" maxLength={6}
                onChange={(e) => setF({ ...f, cindop: apenasDigitos(e.target.value) })} placeholder="Opcional" />}
            </Campo>
            <Campo rotulo="cClassTrib (IBS/CBS)" ajuda="Sugerido pela NBS.">
              {(p) => <Input {...p} value={f.cclasstrib} inputMode="numeric" maxLength={6}
                onChange={(e) => setF({ ...f, cclasstrib: apenasDigitos(e.target.value) })} placeholder="Opcional" />}
            </Campo>
          </div>

          {servico && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4 accent-destaque" checked={f.ativo} onChange={(e) => setF({ ...f, ativo: e.target.checked })} />
              Serviço ativo (aparece na emissão)
            </label>
          )}

          {salvar.isError && <Aviso tom="erro">{(salvar.error as Error).message}</Aviso>}
          <div className={cn("flex justify-end gap-2 pt-1")}>
            <Button type="button" variante="fantasma" onClick={aoFechar}>Cancelar</Button>
            <Button type="submit" variante="primario" disabled={!valido || salvar.isPending}>
              {salvar.isPending && <Loader2 className="animate-spin" />} {servico ? "Salvar" : "Cadastrar serviço"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
