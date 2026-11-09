import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle, BadgeCheck, Ban, Clock, Download, FileText, Loader2, MoreHorizontal, Plus, ReceiptText, RotateCcw, XCircle,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Select } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dica } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useAtualizarEmissor, useEmpresasEmissoras, useNotasEmitidas, type NotaEmitida, type SituacaoEmitida } from "@/lib/emissor";
import { nomeExibicao } from "@/lib/empresas";
import { formatarDataHora, formatarDoc } from "@/lib/formato";
import { moeda } from "@/lib/notas";
import { AbasEmissor } from "./Abas";

const SITUACOES: { id: SituacaoEmitida | ""; rotulo: string }[] = [
  { id: "", rotulo: "Todas" },
  { id: "autorizada", rotulo: "Autorizadas" },
  { id: "rejeitada", rotulo: "Rejeitadas" },
  { id: "pendente", rotulo: "Pendentes" },
  { id: "cancelada", rotulo: "Canceladas" },
];

export function SeloEmitida({ n }: { n: NotaEmitida }) {
  switch (n.situacao) {
    case "autorizada": return <Selo tom="ok" icone={BadgeCheck}>Autorizada</Selo>;
    case "cancelada": return <Selo tom="erro" icone={Ban}>Cancelada</Selo>;
    case "rejeitada":
      return <Dica texto={n.mensagem ?? "Recusada pela Sefin."} lado="left"><span><Selo tom="erro" icone={XCircle}>Rejeitada</Selo></span></Dica>;
    case "pendente":
      return <Dica texto={n.mensagem ?? "Resultado não confirmado."} lado="left"><span><Selo tom="alerta" icone={AlertTriangle}>Pendente</Selo></span></Dica>;
    default: return <Selo tom="neutro" icone={Clock}>Enviando</Selo>;
  }
}

const dataBR = (iso: string) => iso.split("-").reverse().join("/");

export function NotasEmitidas() {
  const [params, setParams] = useSearchParams();
  const empresaId = Number(params.get("emissora")) || null;
  const situacao = params.get("situacao") ?? "";
  const notas = useNotasEmitidas({ empresa_id: empresaId, situacao: situacao || null });
  const empresas = useEmpresasEmissoras();
  const emissoras = (empresas.data ?? []).filter((e) => e.emite_nfse);
  const [cancelando, setCancelando] = useState<NotaEmitida | null>(null);
  const navegar = useNavigate();

  const definir = (k: string, v: string) => setParams((p) => {
    const n = new URLSearchParams(p);
    if (v) n.set(k, v); else n.delete(k);
    return n;
  }, { replace: true });

  return (
    <>
      <Cabecalho titulo="Emissor de NFS-e" descricao="Notas emitidas pelo Contask, com DANFSe, XML e cancelamento."
        acoes={<Button variante="primario" asChild><Link to="/emissor/emitir"><Plus /> Emitir nota</Link></Button>} />
      <AbasEmissor />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Select value={empresaId ?? ""} onChange={(ev) => definir("emissora", ev.target.value)} className="w-72" aria-label="Filtrar por empresa">
          <option value="">Todas as empresas emissoras</option>
          {emissoras.map((e) => <option key={e.id} value={e.id}>{nomeExibicao(e)}</option>)}
        </Select>
        <div className="flex gap-1 rounded-xl border border-borda bg-superficie p-1" role="group" aria-label="Situação">
          {SITUACOES.map((s) => (
            <button key={s.id} onClick={() => definir("situacao", s.id)} aria-pressed={situacao === s.id}
              className={`h-7 rounded-lg px-2.5 text-[13px] ${situacao === s.id ? "bg-destaque-suave font-medium text-destaque" : "text-texto-2 hover:text-texto"}`}>
              {s.rotulo}
            </button>
          ))}
        </div>
      </div>

      {notas.isLoading && <Esqueleto className="h-64 w-full" />}
      {notas.isError && <EstadoErro mensagem={(notas.error as Error).message} tentarDeNovo={() => notas.refetch()} />}
      {notas.data?.length === 0 && (
        <EstadoVazio icone={ReceiptText} titulo={empresaId || situacao ? "Nenhuma nota neste filtro" : "Nenhuma nota emitida ainda"}
          acao={!(empresaId || situacao) && <Button variante="primario" asChild><Link to="/emissor/emitir"><Plus /> Emitir a primeira nota</Link></Button>}>
          {empresaId || situacao ? "Tente outro filtro." : "As notas emitidas pelo Contask aparecem aqui."}
        </EstadoVazio>
      )}
      {notas.data && notas.data.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-borda bg-superficie">
          <table className="w-full text-sm">
            <thead className="border-b border-borda bg-fundo text-left text-xs text-texto-2">
              <tr>
                <th className="px-4 py-2.5 font-medium">NFS-e</th>
                <th className="px-3 py-2.5 font-medium">Prestador</th>
                <th className="px-3 py-2.5 font-medium">Tomador</th>
                <th className="px-3 py-2.5 font-medium">Competência</th>
                <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                <th className="px-3 py-2.5 font-medium">Situação</th>
                <th className="w-12 px-2" aria-label="Ações" />
              </tr>
            </thead>
            <tbody>
              {notas.data.map((n) => (
                <tr key={n.id} className="border-b border-borda last:border-0 hover:bg-superficie-2/60">
                  <td className="px-4 py-2.5">
                    <div className="font-mono font-medium">{n.numero_nfse ? `nº ${n.numero_nfse}` : "—"}</div>
                    <div className="text-xs text-texto-2">DPS {n.serie}/{n.numero}{n.homologacao && " · homologação"}</div>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="max-w-56 truncate">{n.empresa_nome}</div>
                    <div className="font-mono text-xs text-texto-2">{formatarDoc(n.empresa_cnpj)}</div>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="max-w-56 truncate">{n.tomador?.nome ?? "Sem tomador"}</div>
                    {n.tomador && <div className="font-mono text-xs text-texto-2">{formatarDoc(n.tomador.documento)}</div>}
                  </td>
                  <td className="px-3 py-2.5 text-texto-2">{dataBR(n.competencia)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{moeda(n.valor_servico)}</td>
                  <td className="px-3 py-2.5"><SeloEmitida n={n} /></td>
                  <td className="px-2 py-2.5">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button tamanho="icone" variante="fantasma" aria-label={`Ações da nota ${n.numero_nfse ?? n.numero}`}><MoreHorizontal /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {n.chave && (
                          <>
                            <DropdownMenuItem asChild><a href={`/api/emissor/notas/${n.id}/danfse`} target="_blank" rel="noreferrer"><FileText /> Abrir DANFSe</a></DropdownMenuItem>
                            <DropdownMenuItem asChild><a href={`/api/emissor/notas/${n.id}/xml`}><Download /> Baixar XML da NFS-e</a></DropdownMenuItem>
                          </>
                        )}
                        {n.situacao === "cancelada" && (
                          <DropdownMenuItem asChild><a href={`/api/emissor/notas/${n.id}/xml?tipo=cancelamento`}><Download /> XML do cancelamento</a></DropdownMenuItem>
                        )}
                        {(n.situacao === "rejeitada" || n.situacao === "pendente") && (
                          <DropdownMenuItem onSelect={() => navegar(`/emissor/emitir?nota=${n.id}`)}><RotateCcw /> Corrigir e reenviar</DropdownMenuItem>
                        )}
                        {n.situacao === "autorizada" && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onSelect={() => setCancelando(n)} className="text-cancelada"><Ban /> Cancelar nota</DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                    <span className="sr-only">Emitida em {formatarDataHora(n.autorizado_em ?? n.criado_em)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <CancelarDialog nota={cancelando} aoFechar={() => setCancelando(null)} />
    </>
  );
}

const MOTIVOS = [
  { id: "1", rotulo: "Erro na emissão" },
  { id: "2", rotulo: "Serviço não prestado" },
  { id: "9", rotulo: "Outros" },
];

function CancelarDialog({ nota, aoFechar }: { nota: NotaEmitida | null; aoFechar: () => void }) {
  const [motivo, setMotivo] = useState("1");
  const [just, setJust] = useState("");
  const atualizar = useAtualizarEmissor();
  const cancelar = useMutation({
    mutationFn: () => api<NotaEmitida>(`/api/emissor/notas/${nota!.id}/cancelar`, { method: "POST", body: JSON.stringify({ motivo, justificativa: just }) }),
    onSuccess: (n) => { atualizar(); toast.success(`NFS-e nº ${n.numero_nfse} cancelada.`); fechar(); },
  });
  const fechar = () => { setMotivo("1"); setJust(""); cancelar.reset(); aoFechar(); };
  const tam = just.trim().replace(/\s+/g, " ").length;

  return (
    <Dialog open={!!nota} onOpenChange={(v) => !v && !cancelar.isPending && fechar()}>
      <DialogContent titulo={`Cancelar a NFS-e nº ${nota?.numero_nfse ?? ""}`}
        descricao={<>O cancelamento é enviado à Sefin e não pode ser desfeito. {nota?.tomador?.nome && <>Tomador: <strong>{nota.tomador.nome}</strong>, </>}valor de {moeda(nota?.valor_servico)}.</>}>
        <form className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); if (tam >= 15) cancelar.mutate(); }}>
          <Campo rotulo="Motivo" obrigatorio>
            {(p) => <Select {...p} value={motivo} onChange={(ev) => setMotivo(ev.target.value)}>{MOTIVOS.map((m) => <option key={m.id} value={m.id}>{m.rotulo}</option>)}</Select>}
          </Campo>
          <Campo rotulo="Justificativa" obrigatorio ajuda={`${tam}/255. Mínimo de 15 caracteres.`}>
            {(p) => (
              <textarea {...p} rows={3} maxLength={255} value={just} onChange={(ev) => setJust(ev.target.value)}
                className="w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none hover:border-borda-forte focus-visible:border-destaque focus-visible:ring-2 focus-visible:ring-destaque/25" />
            )}
          </Campo>
          {cancelar.isError && <Aviso tom="erro">{(cancelar.error as Error).message}</Aviso>}
          <div className="flex justify-end gap-2">
            <Button type="button" variante="fantasma" onClick={fechar} disabled={cancelar.isPending}>Voltar</Button>
            <Button type="submit" disabled={tam < 15 || cancelar.isPending} className="border-transparent bg-cancelada text-destaque-texto hover:bg-cancelada/90">
              {cancelar.isPending && <Loader2 className="animate-spin" />} Cancelar a nota
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
