import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Pencil, Plus, Search, Trash2, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input, Select } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { apenasDigitos, mascararCep, useAtualizarEmissor, type ConsultaTomador, type Tomador } from "@/lib/emissor";
import { formatarDoc, mascararCnpj, UFS } from "@/lib/formato";
import { AbasEmissor } from "./Abas";

const VAZIO: Tomador = { documento: "", nome: "", inscricao_municipal: "", cep: "", cod_municipio: "", municipio: "", uf: "",
  logradouro: "", numero: "", complemento: "", bairro: "", telefone: "", email: "" };

function mascararDocumento(v: string) {
  const d = apenasDigitos(v).slice(0, 14);
  if (d.length <= 11) return d.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  return mascararCnpj(d);
}

/** Cadastro/edição de tomador. Ao digitar um CNPJ novo, busca os dados na BrasilAPI. */
export function TomadorDialog({ tomador, aberto, aoFechar, aoSalvar }: {
  tomador: Tomador | null; aberto: boolean; aoFechar: () => void; aoSalvar?: (t: Tomador) => void;
}) {
  const atualizar = useAtualizarEmissor();
  const [f, setF] = useState<Tomador>(VAZIO);
  const [aviso, setAviso] = useState<string | null>(null);
  useEffect(() => {
    if (aberto) { setF(tomador ? { ...VAZIO, ...Object.fromEntries(Object.entries(tomador).map(([k, v]) => [k, v ?? ""])) } as Tomador : VAZIO); setAviso(null); }
  }, [aberto, tomador]);

  const consultar = useMutation({
    mutationFn: (doc: string) => api<ConsultaTomador>(`/api/emissor/tomadores/consulta/${doc}`),
    onSuccess: (r) => {
      setF((a) => ({ ...a, ...Object.fromEntries(Object.entries(r.tomador).map(([k, v]) => [k, v ?? ""])) }));
      setAviso(r.origem === "salvo" ? "Este tomador já estava salvo: os dados abaixo são os que estão no cadastro." : r.aviso);
    },
  });
  const salvar = useMutation({
    mutationFn: () => tomador?.id
      ? api<Tomador>(`/api/emissor/tomadores/${tomador.id}`, { method: "PUT", body: JSON.stringify(f) })
      : api<Tomador>("/api/emissor/tomadores", { method: "POST", body: JSON.stringify(f) }),
    onSuccess: (t) => { atualizar(); toast.success("Tomador salvo."); aoSalvar?.(t); aoFechar(); },
  });

  const doc = apenasDigitos(f.documento);
  const set = (k: keyof Tomador) => (ev: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: ev.target.value });

  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && aoFechar()}>
      <DialogContent largo titulo={tomador?.id ? "Editar tomador" : "Novo tomador"} descricao="Quem contrata o serviço. Fica salvo para as próximas notas.">
        <form className="grid grid-cols-6 gap-3" onSubmit={(ev) => { ev.preventDefault(); salvar.mutate(); }}>
          <Campo rotulo="CNPJ ou CPF" obrigatorio className="col-span-3" ajuda={!tomador?.id ? "Com CNPJ, os dados vêm da Receita (BrasilAPI)." : undefined}>
            {(p) => (
              <div className="flex gap-2">
                <Input {...p} value={mascararDocumento(f.documento)} inputMode="numeric"
                  onChange={(ev) => setF({ ...f, documento: apenasDigitos(ev.target.value) })}
                  onBlur={() => { if (!tomador?.id && doc.length === 14) consultar.mutate(doc); }} />
                {!tomador?.id && (
                  <Button type="button" onClick={() => consultar.mutate(doc)} disabled={![11, 14].includes(doc.length) || consultar.isPending} aria-label="Buscar dados do CNPJ">
                    {consultar.isPending ? <Loader2 className="animate-spin" /> : <Search />}
                  </Button>
                )}
              </div>
            )}
          </Campo>
          <Campo rotulo="Inscrição municipal" className="col-span-3">
            {(p) => <Input {...p} value={f.inscricao_municipal ?? ""} maxLength={15} onChange={set("inscricao_municipal")} placeholder="Opcional" />}
          </Campo>
          {(aviso || consultar.isError) && (
            <div className="col-span-6"><Aviso tom={consultar.isError ? "erro" : "info"}>{consultar.isError ? (consultar.error as Error).message : aviso}</Aviso></div>
          )}
          <Campo rotulo="Nome ou razão social" obrigatorio className="col-span-6">
            {(p) => <Input {...p} value={f.nome} maxLength={300} onChange={set("nome")} />}
          </Campo>
          <Campo rotulo="CEP" className="col-span-2">
            {(p) => <Input {...p} value={mascararCep(f.cep)} inputMode="numeric" onChange={(ev) => setF({ ...f, cep: apenasDigitos(ev.target.value) })} />}
          </Campo>
          <Campo rotulo="Município" className="col-span-2">
            {(p) => <Input {...p} value={f.municipio ?? ""} onChange={set("municipio")} />}
          </Campo>
          <Campo rotulo="UF" className="col-span-1">
            {(p) => <Select {...p} value={f.uf ?? ""} onChange={set("uf")}><option value="">—</option>{UFS.map((u) => <option key={u}>{u}</option>)}</Select>}
          </Campo>
          <Campo rotulo="Cód. IBGE" className="col-span-1">
            {(p) => <Input {...p} value={f.cod_municipio ?? ""} inputMode="numeric" maxLength={7} onChange={(ev) => setF({ ...f, cod_municipio: apenasDigitos(ev.target.value) })} />}
          </Campo>
          <Campo rotulo="Logradouro" className="col-span-4">
            {(p) => <Input {...p} value={f.logradouro ?? ""} maxLength={255} onChange={set("logradouro")} />}
          </Campo>
          <Campo rotulo="Número" className="col-span-2">
            {(p) => <Input {...p} value={f.numero ?? ""} maxLength={60} onChange={set("numero")} />}
          </Campo>
          <Campo rotulo="Complemento" className="col-span-3">
            {(p) => <Input {...p} value={f.complemento ?? ""} maxLength={156} onChange={set("complemento")} />}
          </Campo>
          <Campo rotulo="Bairro" className="col-span-3">
            {(p) => <Input {...p} value={f.bairro ?? ""} maxLength={60} onChange={set("bairro")} />}
          </Campo>
          <Campo rotulo="Telefone" className="col-span-2">
            {(p) => <Input {...p} value={f.telefone ?? ""} inputMode="tel" onChange={(ev) => setF({ ...f, telefone: apenasDigitos(ev.target.value) })} placeholder="DDD + número" />}
          </Campo>
          <Campo rotulo="E-mail" className="col-span-4" ajuda="Para onde a nota vai ser enviada, quando o envio por e-mail existir.">
            {(p) => <Input {...p} type="email" value={f.email ?? ""} maxLength={80} onChange={set("email")} />}
          </Campo>
          {salvar.isError && <div className="col-span-6"><Aviso tom="erro">{(salvar.error as Error).message}</Aviso></div>}
          <div className="col-span-6 flex justify-end gap-2 pt-1">
            <Button type="button" variante="fantasma" onClick={aoFechar}>Cancelar</Button>
            <Button type="submit" variante="primario" disabled={![11, 14].includes(doc.length) || !f.nome.trim() || salvar.isPending}>
              {salvar.isPending && <Loader2 className="animate-spin" />} Salvar tomador
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function Tomadores() {
  const [q, setQ] = useState("");
  const [termo, setTermo] = useState("");
  useEffect(() => { const t = setTimeout(() => setTermo(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  const lista = useQuery({
    queryKey: ["emissor", "tomadores", termo],
    queryFn: () => api<Tomador[]>(`/api/emissor/tomadores?${new URLSearchParams({ q: termo })}`),
    placeholderData: (ant) => ant,
  });
  const atualizar = useAtualizarEmissor();
  const [dialogo, setDialogo] = useState<{ aberto: boolean; tomador: Tomador | null }>({ aberto: false, tomador: null });
  const excluir = useMutation({
    mutationFn: (t: Tomador) => api<void>(`/api/emissor/tomadores/${t.id}`, { method: "DELETE" }),
    onSuccess: () => { atualizar(); toast.success("Tomador excluído."); },
    onError: (err) => toast.error((err as Error).message),
  });

  return (
    <>
      <Cabecalho titulo="Emissor de NFS-e" descricao="Tomadores salvos do escritório, reaproveitados na emissão."
        acoes={<Button variante="primario" onClick={() => setDialogo({ aberto: true, tomador: null })}><Plus /> Novo tomador</Button>} />
      <AbasEmissor />
      <div className="relative mb-4 w-80">
        <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-2" aria-hidden />
        <Input value={q} onChange={(ev) => setQ(ev.target.value)} placeholder="Nome, CNPJ ou CPF" className="pl-9" aria-label="Filtrar tomadores" />
      </div>
      {lista.isLoading && <Esqueleto className="h-48 w-full" />}
      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.data?.length === 0 && (
        <EstadoVazio icone={Users} titulo={termo ? "Nenhum tomador encontrado" : "Nenhum tomador salvo"}
          acao={!termo && <Button variante="primario" onClick={() => setDialogo({ aberto: true, tomador: null })}><Plus /> Cadastrar tomador</Button>}>
          {termo ? "Tente outro nome ou documento." : "Os tomadores também são salvos sozinhos quando você emite uma nota."}
        </EstadoVazio>
      )}
      {lista.data && lista.data.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-borda bg-superficie">
          <table className="w-full text-sm">
            <thead className="border-b border-borda bg-fundo text-left text-xs text-texto-2">
              <tr>
                <th className="px-4 py-2.5 font-medium">Tomador</th>
                <th className="px-3 py-2.5 font-medium">Município</th>
                <th className="px-3 py-2.5 font-medium">E-mail</th>
                <th className="w-24 px-2" aria-label="Ações" />
              </tr>
            </thead>
            <tbody>
              {lista.data.map((t) => (
                <tr key={t.id} className="border-b border-borda last:border-0 hover:bg-superficie-2/60">
                  <td className="px-4 py-2.5">
                    <div className="font-medium">{t.nome}</div>
                    <div className="font-mono text-xs text-texto-2">{formatarDoc(t.documento)}</div>
                  </td>
                  <td className="px-3 py-2.5 text-texto-2">{[t.municipio, t.uf].filter(Boolean).join(" / ") || "—"}</td>
                  <td className="px-3 py-2.5 text-texto-2">{t.email || "—"}</td>
                  <td className="px-2 py-2.5">
                    <div className="flex justify-end gap-1">
                      <Button tamanho="icone" variante="fantasma" aria-label={`Editar ${t.nome}`} onClick={() => setDialogo({ aberto: true, tomador: t })}><Pencil /></Button>
                      <Button tamanho="icone" variante="fantasma" aria-label={`Excluir ${t.nome}`} disabled={excluir.isPending}
                        onClick={() => { if (window.confirm(`Excluir o tomador ${t.nome}?`)) excluir.mutate(t); }}><Trash2 /></Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <TomadorDialog tomador={dialogo.tomador} aberto={dialogo.aberto} aoFechar={() => setDialogo({ aberto: false, tomador: null })} />
    </>
  );
}
