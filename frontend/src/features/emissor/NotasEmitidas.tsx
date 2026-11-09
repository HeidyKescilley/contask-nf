import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle, BadgeCheck, Ban, Building2, ChevronLeft, ChevronRight, Clock, Copy, Download, FilePen, FileText, Loader2,
  MoreHorizontal, Plus, ReceiptText, Repeat, RotateCcw, Search, Trash2, X, XCircle,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input, Select } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dica } from "@/components/ui/tooltip";
import { Painel } from "@/features/empresas/Passos";
import { api } from "@/lib/api";
import {
  lerValor, useAtualizarEmissor, useEmpresasEmissoras, useNotasEmpresa, useRascunhos,
  type FiltrosNotas, type ItemNota, type NotaEmitida, type Rascunho,
} from "@/lib/emissor";
import { nomeExibicao, useEmpresaSelecionada } from "@/lib/empresas";
import { formatarData, formatarDataHora, formatarDoc } from "@/lib/formato";
import { moeda } from "@/lib/notas";
import { cn } from "@/lib/utils";
import { AbasEmissor } from "./Abas";

const SITUACOES = [
  { id: "", rotulo: "Todas as situações" },
  { id: "autorizada", rotulo: "Autorizadas" },
  { id: "cancelada", rotulo: "Canceladas" },
  { id: "rejeitada", rotulo: "Rejeitadas" },
  { id: "pendente", rotulo: "Pendentes" },
];

export function SeloEmitida({ n }: { n: { situacao: string; mensagem: string | null } }) {
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

// ---------------------------------------------------------------------------
// Período: mês inteiro por padrão, com setas para trocar de mês
// ---------------------------------------------------------------------------

const p2 = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

function mes(ano: number, m0: number) {
  return { inicio: iso(new Date(ano, m0, 1)), fim: iso(new Date(ano, m0 + 1, 0)) };
}

function mesAtual() {
  const h = new Date();
  return mes(h.getFullYear(), h.getMonth());
}

/** "novembro de 2026" quando o período é um mês inteiro; null quando é personalizado. */
function nomeDoMes(inicio: string, fim: string) {
  const [a, m] = inicio.split("-").map(Number);
  const certo = mes(a, m - 1);
  return certo.inicio === inicio && certo.fim === fim ? `${MESES[m - 1]} de ${a}` : null;
}

function useAtraso<T>(valor: T, ms = 300) {
  const [v, setV] = useState(valor);
  useEffect(() => { const t = setTimeout(() => setV(valor), ms); return () => clearTimeout(t); }, [valor, ms]);
  return v;
}

export function NotasEmitidas() {
  const [params, setParams] = useSearchParams();
  // A lista segue a empresa escolhida no seletor do topo
  const { empresa: selecionada, carregando } = useEmpresaSelecionada();
  const empresas = useEmpresasEmissoras();
  const empresa = (empresas.data ?? []).find((e) => e.id === selecionada?.id) ?? null;
  const pronta = !!empresa?.emite_nfse;

  const padrao = mesAtual();
  const filtros: FiltrosNotas = {
    inicio: params.get("inicio") ?? padrao.inicio,
    fim: params.get("fim") ?? padrao.fim,
    q: params.get("q") ?? "",
    numero: params.get("numero") ?? "",
    situacao: params.get("situacao") ?? "",
  };
  const [busca, setBusca] = useState(filtros.q);
  const [numero, setNumero] = useState(filtros.numero);
  const buscaAtrasada = useAtraso(busca);
  const numeroAtrasado = useAtraso(numero);

  const definir = (valores: Partial<FiltrosNotas>) => setParams((p) => {
    const n = new URLSearchParams(p);
    for (const [k, v] of Object.entries(valores)) {
      if (v) n.set(k, v); else n.delete(k);
    }
    return n;
  }, { replace: true });

  useEffect(() => {
    if (buscaAtrasada !== filtros.q || numeroAtrasado !== filtros.numero) definir({ q: buscaAtrasada.trim(), numero: numeroAtrasado.trim() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buscaAtrasada, numeroAtrasado]);

  const notas = useNotasEmpresa(pronta ? empresa!.id : null, filtros);
  const rascunhos = useRascunhos(pronta ? empresa!.id : null);
  const [cancelando, setCancelando] = useState<NotaEmitida | null>(null);
  const navegar = useNavigate();

  const nomeMes = nomeDoMes(filtros.inicio, filtros.fim);
  const andar = (passo: number) => {
    const [a, m] = filtros.inicio.split("-").map(Number);
    definir(mes(a, m - 1 + passo));
  };
  const ehMesAtual = filtros.inicio === padrao.inicio && filtros.fim === padrao.fim;
  const filtrando = !!(filtros.q || filtros.numero || filtros.situacao);
  const comEmpresa = (rota: string) => `${rota}${rota.includes("?") ? "&" : "?"}empresa=${empresa?.id ?? ""}`;

  return (
    <>
      <Cabecalho titulo="Emissor de NFS-e"
        descricao={empresa ? `Notas de ${nomeExibicao(empresa)}: emitidas pelo Contask e, em produção, também as que vieram do ADN.` : "Notas emitidas, com DANFSe, XML, duplicar e cancelamento."}
        acoes={pronta && <Button variante="primario" asChild><Link to={comEmpresa("/emissor/emitir")}><Plus /> Emitir nota</Link></Button>} />
      <AbasEmissor />

      {(carregando || empresas.isLoading) && <Esqueleto className="h-64 w-full" />}
      {empresas.isError && <EstadoErro mensagem={(empresas.error as Error).message} tentarDeNovo={() => empresas.refetch()} />}
      {!carregando && empresas.data && !selecionada && (
        <EstadoVazio icone={Building2} titulo="Escolha uma empresa">Selecione a empresa no topo da página para ver as notas dela.</EstadoVazio>
      )}
      {empresas.data && selecionada && !pronta && (
        <EstadoVazio icone={Building2} titulo={`${nomeExibicao(selecionada)} não emite NFS-e pelo Contask`}
          acao={<Button variante="primario" asChild><Link to={`/emissor/empresas/${selecionada.id}?empresa=${selecionada.id}`}>Configurar emissão</Link></Button>}>
          Escolha outra empresa no topo da página ou marque esta como emissora.
        </EstadoVazio>
      )}

      {pronta && (
        <div className="space-y-5">
          {rascunhos.data && rascunhos.data.length > 0 && <Rascunhos itens={rascunhos.data} empresaId={empresa!.id} />}
          {rascunhos.isError && <Aviso tom="erro">Não foi possível carregar os rascunhos: {(rascunhos.error as Error).message}</Aviso>}

          <div className="rounded-xl border border-borda bg-superficie p-3">
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <span className="mb-1.5 block text-xs font-medium text-texto-2">Mês de emissão</span>
                <div className="flex items-center gap-1">
                  <Button tamanho="icone" variante="fantasma" aria-label="Mês anterior" onClick={() => andar(-1)}><ChevronLeft /></Button>
                  <span className="min-w-40 text-center text-sm font-medium first-letter:uppercase" aria-live="polite">
                    {nomeMes ?? "Período personalizado"}
                  </span>
                  <Button tamanho="icone" variante="fantasma" aria-label="Próximo mês" onClick={() => andar(1)}><ChevronRight /></Button>
                </div>
              </div>
              <Campo rotulo="De" className="w-40">
                {(p) => <Input {...p} type="date" value={filtros.inicio} max={filtros.fim} onChange={(ev) => ev.target.value && definir({ inicio: ev.target.value })} />}
              </Campo>
              <Campo rotulo="Até" className="w-40">
                {(p) => <Input {...p} type="date" value={filtros.fim} min={filtros.inicio} onChange={(ev) => ev.target.value && definir({ fim: ev.target.value })} />}
              </Campo>
              {!ehMesAtual && <Button variante="fantasma" onClick={() => definir(padrao)}>Mês atual</Button>}
            </div>
            <div className="mt-3 flex flex-wrap items-end gap-3 border-t border-borda pt-3">
              <Campo rotulo="Tomador ou descrição" className="min-w-56 flex-1">
                {(p) => (
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-2" aria-hidden />
                    <Input {...p} value={busca} onChange={(ev) => setBusca(ev.target.value)} placeholder="Nome, CNPJ/CPF ou parte da descrição" className="pl-9" />
                  </div>
                )}
              </Campo>
              <Campo rotulo="Número" className="w-36">
                {(p) => <Input {...p} value={numero} inputMode="numeric" onChange={(ev) => setNumero(ev.target.value.replace(/\D/g, ""))} placeholder="NFS-e ou DPS" />}
              </Campo>
              <Campo rotulo="Situação" className="w-48">
                {(p) => (
                  <Select {...p} value={filtros.situacao} onChange={(ev) => definir({ situacao: ev.target.value })}>
                    {SITUACOES.map((s) => <option key={s.id} value={s.id}>{s.rotulo}</option>)}
                  </Select>
                )}
              </Campo>
              {filtrando && (
                <Button variante="fantasma" onClick={() => { setBusca(""); setNumero(""); definir({ q: "", numero: "", situacao: "" }); }}><X /> Limpar</Button>
              )}
            </div>
          </div>

          {notas.isLoading && <Esqueleto className="h-64 w-full" />}
          {notas.isError && <EstadoErro mensagem={(notas.error as Error).message} tentarDeNovo={() => notas.refetch()} />}
          {notas.data && (
            <p className="flex items-center gap-2 text-sm text-texto-2" aria-live="polite">
              {notas.isFetching && <Loader2 className="size-4 animate-spin" aria-hidden />}
              <span><strong className="text-texto">{notas.data.totais.quantidade}</strong> {notas.data.totais.quantidade === 1 ? "nota" : "notas"} no período</span>
              <span aria-hidden>·</span>
              <span>{notas.data.totais.autorizadas} autorizada{notas.data.totais.autorizadas === 1 ? "" : "s"}: <strong className="font-mono text-texto">{moeda(notas.data.totais.valor_autorizado)}</strong></span>
            </p>
          )}
          {notas.data?.notas.length === 0 && (
            <EstadoVazio icone={ReceiptText} titulo={filtrando ? "Nenhuma nota com esses filtros" : `Nenhuma nota em ${nomeMes ?? "este período"}`}
              acao={!filtrando && <Button variante="primario" asChild><Link to={comEmpresa("/emissor/emitir")}><Plus /> Emitir nota</Link></Button>}>
              {filtrando ? "Mude a busca ou limpe os filtros." : "Use as setas para ver outros meses."}
            </EstadoVazio>
          )}
          {notas.data && notas.data.notas.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-borda bg-superficie">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="border-b border-borda bg-fundo text-left text-xs text-texto-2">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">NFS-e</th>
                    <th className="px-3 py-2.5 font-medium">Emissão</th>
                    <th className="px-3 py-2.5 font-medium">Tomador</th>
                    <th className="px-3 py-2.5 font-medium">Competência</th>
                    <th className="px-3 py-2.5 text-right font-medium">Valor</th>
                    <th className="px-3 py-2.5 font-medium">Situação</th>
                    <th className="w-12 px-2" aria-label="Ações" />
                  </tr>
                </thead>
                <tbody>
                  {notas.data.notas.map((n) => (
                    <Linha key={`${n.origem}-${n.id}`} n={n} comEmpresa={comEmpresa} navegar={navegar} aoCancelar={setCancelando} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      <CancelarDialog nota={cancelando} aoFechar={() => setCancelando(null)} />
    </>
  );
}

function Linha({ n, comEmpresa, navegar, aoCancelar }: {
  n: ItemNota; comEmpresa: (r: string) => string; navegar: (r: string) => void; aoCancelar: (n: NotaEmitida) => void;
}) {
  const adn = n.origem === "adn";
  const duplicar = adn ? `duplicar_adn=${n.id}` : `duplicar=${n.id}`;
  const danfse = adn ? `/api/notas/${n.id}/pdf` : `/api/emissor/notas/${n.id}/danfse`;
  const xml = adn ? `/api/notas/${n.id}/xml` : `/api/emissor/notas/${n.id}/xml`;
  const temXml = adn ? n.tem_xml : !!n.chave;
  return (
    <tr className="border-b border-borda last:border-0 hover:bg-superficie-2/60">
      <td className="px-4 py-2.5">
        <div className="font-mono font-medium">{n.numero_nfse ? `nº ${n.numero_nfse}` : "—"}</div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-texto-2">
          {n.numero !== null && <span>DPS {n.serie}/{n.numero}</span>}
          {adn && <Dica texto="Emitida fora do Contask e baixada do ADN."><span className="rounded bg-superficie-2 px-1.5 py-0.5">Fora do Contask</span></Dica>}
          {!adn && n.recorrente_id && <span className="inline-flex items-center gap-1 rounded bg-destaque-suave px-1.5 py-0.5 text-destaque"><Repeat className="size-3" aria-hidden /> Recorrente</span>}
        </div>
      </td>
      <td className="px-3 py-2.5 whitespace-nowrap text-texto-2">{formatarData(n.data)}</td>
      <td className="px-3 py-2.5">
        <div className="max-w-56 truncate">{n.tomador?.nome ?? "Sem tomador"}</div>
        {n.tomador?.documento && <div className="font-mono text-xs text-texto-2">{formatarDoc(n.tomador.documento)}</div>}
      </td>
      <td className="px-3 py-2.5 text-texto-2">{n.competencia ? n.competencia.split("-").reverse().join("/") : "—"}</td>
      <td className="px-3 py-2.5 text-right font-mono tabular-nums">{n.valor_servico !== null ? moeda(n.valor_servico) : "—"}</td>
      <td className="px-3 py-2.5"><SeloEmitida n={n} /></td>
      <td className="px-2 py-2.5">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button tamanho="icone" variante="fantasma" aria-label={`Ações da nota ${n.numero_nfse ?? n.numero ?? ""}`}><MoreHorizontal /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {temXml && (
              <>
                <DropdownMenuItem asChild><a href={danfse} target="_blank" rel="noreferrer"><FileText /> Abrir DANFSe</a></DropdownMenuItem>
                <DropdownMenuItem asChild><a href={xml}><Download /> Baixar XML da NFS-e</a></DropdownMenuItem>
              </>
            )}
            {!adn && n.situacao === "cancelada" && (
              <DropdownMenuItem asChild><a href={`/api/emissor/notas/${n.id}/xml?tipo=cancelamento`}><Download /> XML do cancelamento</a></DropdownMenuItem>
            )}
            {!adn && (n.situacao === "rejeitada" || n.situacao === "pendente") && (
              <DropdownMenuItem onSelect={() => navegar(comEmpresa(`/emissor/emitir?nota=${n.id}`))}><RotateCcw /> Corrigir e reenviar</DropdownMenuItem>
            )}
            {(!adn || n.tem_xml) && (
              <>
                <DropdownMenuItem onSelect={() => navegar(comEmpresa(`/emissor/emitir?${duplicar}`))}><Copy /> Duplicar</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => navegar(comEmpresa(`/emissor/recorrentes/nova?${duplicar}`))}><Repeat /> Criar recorrência</DropdownMenuItem>
              </>
            )}
            {!adn && n.situacao === "autorizada" && (
              <>
                <DropdownMenuSeparator />
                {n.cancela_pela_api ? (
                  <DropdownMenuItem onSelect={() => aoCancelar(n)} className="text-cancelada"><Ban /> Cancelar nota</DropdownMenuItem>
                ) : (
                  // Por procuração a Sefin recusa o cancelamento (E0812/E0813): só pelo Emissor Nacional Web
                  <DropdownMenuItem asChild title="Emitida por procuração: a Sefin só aceita o cancelamento pelo Emissor Nacional Web (Procuração/Representação) ou com o certificado da empresa.">
                    <a href="https://www.nfse.gov.br/EmissorNacional/" target="_blank" rel="noreferrer" className="text-cancelada"><Ban /> Cancelar no Emissor Nacional</a>
                  </DropdownMenuItem>
                )}
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </td>
    </tr>
  );
}

function Rascunhos({ itens, empresaId }: { itens: Rascunho[]; empresaId: number }) {
  const atualizar = useAtualizarEmissor();
  const excluir = useMutation({
    mutationFn: (r: Rascunho) => api<void>(`/api/emissor/rascunhos/${r.id}`, { method: "DELETE" }),
    onSuccess: () => { atualizar(); toast.success("Rascunho excluído."); },
    onError: (err) => toast.error((err as Error).message),
  });
  return (
    <Painel titulo={`Rascunhos (${itens.length})`} descricao="Notas preenchidas e guardadas para emitir depois.">
      <ul className="divide-y divide-borda rounded-xl border border-borda">
        {itens.map((r) => {
          const valor = r.valor ? lerValor(r.valor) : NaN;
          return (
            <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
              <FilePen className="size-4 shrink-0 text-texto-2" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{r.tomador_nome ?? "Sem tomador"}{!isNaN(valor) && <span className="ml-2 font-mono font-normal text-texto-2">{moeda(valor)}</span>}</p>
                <p className="truncate text-xs text-texto-2">{r.descricao || "Sem descrição"} · salvo em {formatarDataHora(r.atualizado_em)}</p>
              </div>
              <div className="flex gap-1">
                <Button tamanho="pequeno" asChild><Link to={`/emissor/emitir?rascunho=${r.id}&empresa=${empresaId}`}>Continuar</Link></Button>
                <Button tamanho="icone" variante="fantasma" aria-label="Excluir rascunho" disabled={excluir.isPending}
                  onClick={() => { if (window.confirm("Excluir este rascunho?")) excluir.mutate(r); }}><Trash2 /></Button>
              </div>
            </li>
          );
        })}
      </ul>
    </Painel>
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
            <Button type="submit" disabled={tam < 15 || cancelar.isPending} className={cn("border-transparent bg-cancelada text-destaque-texto hover:bg-cancelada/90")}>
              {cancelar.isPending && <Loader2 className="animate-spin" />} Cancelar a nota
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
