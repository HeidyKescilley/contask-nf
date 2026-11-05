import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Copiar } from "@/components/Copiar";
import { AcoesBuscaEmpresa } from "@/features/buscas/CentralBuscas";
import { EstadoErro, Esqueleto } from "@/components/estados";
import { SeloAcesso, SeloBusca, SeloCertificado } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input, Select } from "@/components/ui/campos";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { api, apiForm, type Empresa, type EmpresaCriada } from "@/lib/api";
import { nomeExibicao, useAtualizarEmpresas, useContabilidade } from "@/lib/empresas";
import { formatarData, formatarDataHora, formatarDoc, limparCnpj, UFS } from "@/lib/formato";
import { type CertificadoEscolhido } from "./CertificadoUpload";
import { EscolhaCertificado, type Modo } from "./NovaEmpresa";
import { LinhaResumo, Painel } from "./Passos";

export function DetalheEmpresa() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["empresa", Number(id)], queryFn: () => api<Empresa>(`/api/empresas/${id}`) });
  if (q.isLoading) return <Esqueleto className="h-96 w-full" />;
  if (q.isError) return <EstadoErro mensagem={(q.error as Error).message} tentarDeNovo={() => q.refetch()} />;
  return <Detalhe key={q.data!.id} e={q.data!} />;
}

function Detalhe({ e }: { e: Empresa }) {
  const atualizar = useAtualizarEmpresas();
  return (
    <div className="max-w-4xl space-y-5">
      <div>
        <Link to="/empresas" className="mb-3 inline-flex items-center gap-1.5 text-sm text-texto-2 hover:text-texto">
          <ArrowLeft className="size-4" aria-hidden /> Empresas
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-xl font-semibold tracking-tight">{nomeExibicao(e)}</h1>
          {e.is_contabilidade && <span className="rounded bg-destaque-suave px-1.5 py-0.5 text-xs font-medium text-destaque">Contabilidade</span>}
          {!e.ativa && <span className="rounded bg-superficie-2 px-1.5 py-0.5 text-xs text-texto-2">Inativa</span>}
        </div>
        <div className="mt-1 flex items-center gap-3 text-sm text-texto-2">
          <Copiar texto={e.cnpj} exibir={formatarDoc(e.cnpj)} />
          <span>·</span>
          <span>{e.razao_social}</span>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <SeloAcesso acesso={e.acesso} />
          <SeloCertificado cert={e.certificado} />
          <SeloBusca situacao={e.busca.situacao} pendente={e.busca.job_pendente} />
        </div>
      </div>

      <Painel titulo="Busca de notas">
        <dl>
          <LinhaResumo rotulo="Situação"><SeloBusca situacao={e.busca.situacao} pendente={e.busca.job_pendente} /></LinhaResumo>
          <LinhaResumo rotulo="Última busca">{formatarDataHora(e.busca.ultima_busca_em)}</LinhaResumo>
          <LinhaResumo rotulo="Último NSU"><span className="font-mono">{e.busca.ultimo_nsu}</span></LinhaResumo>
          <LinhaResumo rotulo="Notas no sistema"><span className="font-mono">{e.total_notas.toLocaleString("pt-BR")}</span></LinhaResumo>
          {e.busca.ultimo_erro && <LinhaResumo rotulo="Último erro"><span className="text-cancelada">{e.busca.ultimo_erro}</span></LinhaResumo>}
        </dl>
        <div className="mt-4"><AcoesBuscaEmpresa empresaId={e.id} ativa={e.ativa} /></div>
      </Painel>

      <FormDados e={e} aoSalvar={atualizar} />
      {e.is_contabilidade ? <CertContabilidade e={e} /> : <TrocaCertificado e={e} aoSalvar={atualizar} />}
      {!e.is_contabilidade && <ZonaPerigo e={e} aoSalvar={atualizar} />}
    </div>
  );
}

function FormDados({ e, aoSalvar }: { e: Empresa; aoSalvar: () => void }) {
  const [d, setD] = useState({
    razao_social: e.razao_social, nome_fantasia: e.nome_fantasia ?? "", apelido: e.apelido ?? "",
    uf: e.uf ?? "", municipio: e.municipio ?? "",
  });
  const salvar = useMutation({
    mutationFn: () => api<Empresa>(`/api/empresas/${e.id}`, { method: "PATCH", body: JSON.stringify(d) }),
    onSuccess: () => { aoSalvar(); toast.success("Dados salvos."); },
  });
  const mudou = d.razao_social !== e.razao_social || d.nome_fantasia !== (e.nome_fantasia ?? "") ||
    d.apelido !== (e.apelido ?? "") || d.uf !== (e.uf ?? "") || d.municipio !== (e.municipio ?? "");
  const set = (k: keyof typeof d) => (ev: { target: { value: string } }) => setD({ ...d, [k]: ev.target.value });

  return (
    <Painel titulo="Dados" descricao={e.situacao_cadastral ? `Situação cadastral: ${e.situacao_cadastral}` : undefined}>
      <form onSubmit={(ev) => { ev.preventDefault(); salvar.mutate(); }} className="grid grid-cols-2 gap-4">
        <Campo rotulo="Razão social" obrigatorio className="col-span-2" erro={!d.razao_social.trim() ? "Informe a razão social." : undefined}>
          {(p) => <Input {...p} value={d.razao_social} onChange={set("razao_social")} />}
        </Campo>
        <Campo rotulo="Nome fantasia">{(p) => <Input {...p} value={d.nome_fantasia} onChange={set("nome_fantasia")} />}</Campo>
        <Campo rotulo="Apelido">{(p) => <Input {...p} value={d.apelido} onChange={set("apelido")} />}</Campo>
        <div className="grid grid-cols-[110px_1fr] gap-4">
          <Campo rotulo="UF">
            {(p) => <Select {...p} value={d.uf} onChange={set("uf")}><option value="">—</option>{UFS.map((u) => <option key={u}>{u}</option>)}</Select>}
          </Campo>
          <Campo rotulo="Município">{(p) => <Input {...p} value={d.municipio} onChange={set("municipio")} />}</Campo>
        </div>
        <div className="flex items-end justify-end gap-3">
          {salvar.isError && <span className="text-sm text-cancelada">{(salvar.error as Error).message}</span>}
          <Button type="submit" variante="primario" disabled={!mudou || !d.razao_social.trim() || salvar.isPending}>
            {salvar.isPending && <Loader2 className="animate-spin" />} Salvar dados
          </Button>
        </div>
      </form>
    </Painel>
  );
}

function CertContabilidade({ e }: { e: Empresa }) {
  const c = e.certificado;
  return (
    <Painel titulo="Certificado da contabilidade" descricao="Usado nas buscas por procuração de todas as empresas.">
      {c && (
        <dl>
          <LinhaResumo rotulo="Titular">{c.titular_nome} <span className="font-mono text-texto-2">· {formatarDoc(c.titular_doc)}</span></LinhaResumo>
          <LinhaResumo rotulo="Tipo">{c.tipo}</LinhaResumo>
          <LinhaResumo rotulo="Validade"><span className="inline-flex items-center gap-2">{formatarData(c.validade)} <SeloCertificado cert={c} /></span></LinhaResumo>
        </dl>
      )}
      <div className="mt-4"><Button asChild><Link to="/contabilidade">Enviar certificado renovado</Link></Button></div>
    </Painel>
  );
}

function TrocaCertificado({ e, aoSalvar }: { e: Empresa; aoSalvar: () => void }) {
  const { data: contab } = useContabilidade();
  const [aberto, setAberto] = useState(false);
  const [modo, setModo] = useState<Modo>(e.modo_certificado);
  const [cert, setCert] = useState<CertificadoEscolhido | null>(null);
  const salvar = useMutation({
    mutationFn: () => apiForm<EmpresaCriada>(`/api/empresas/${e.id}/certificado`,
      { modo_certificado: modo, ...(modo === "proprio" && cert ? { arquivo: cert.arquivo, senha: cert.senha } : {}) }, "PUT"),
    onSuccess: (r) => {
      aoSalvar();
      toast.success("Certificado atualizado.");
      r.avisos.forEach((a) => toast.warning(a));
      setAberto(false);
      setCert(null);
    },
  });
  const pode = modo === "contabilidade" ? modo !== e.modo_certificado : !!cert && cert.info.situacao !== "vencido";

  return (
    <Painel titulo="Certificado usado na busca">
      <dl>
        <LinhaResumo rotulo="Origem">{e.modo_certificado === "contabilidade" ? "Da contabilidade (procuração)" : "Próprio da empresa"}</LinhaResumo>
        {e.certificado && (
          <LinhaResumo rotulo="Titular">
            <span className="inline-flex flex-wrap items-center gap-2">
              {e.certificado.titular_nome} <span className="font-mono text-texto-2">{formatarDoc(e.certificado.titular_doc)}</span>
              <SeloCertificado cert={e.certificado} />
            </span>
          </LinhaResumo>
        )}
      </dl>
      {!aberto ? (
        <div className="mt-4"><Button onClick={() => setAberto(true)}>Trocar certificado</Button></div>
      ) : (
        <div className="mt-4 space-y-4">
          <EscolhaCertificado contab={contab ?? null} cnpj={e.cnpj} modo={modo} setModo={setModo} cert={cert} setCert={setCert} />
          {salvar.isError && <Aviso tom="erro">{(salvar.error as Error).message}</Aviso>}
          <div className="flex justify-end gap-2">
            <Button variante="fantasma" onClick={() => { setAberto(false); setModo(e.modo_certificado); setCert(null); }}>Cancelar</Button>
            <Button variante="primario" disabled={!pode || salvar.isPending} onClick={() => salvar.mutate()}>
              {salvar.isPending && <Loader2 className="animate-spin" />} Salvar certificado
            </Button>
          </div>
        </div>
      )}
    </Painel>
  );
}

function ZonaPerigo({ e, aoSalvar }: { e: Empresa; aoSalvar: () => void }) {
  const [confirmacao, setConfirmacao] = useState("");
  const navegar = useNavigate();
  const alternar = useMutation({
    mutationFn: () => api<Empresa>(`/api/empresas/${e.id}`, { method: "PATCH", body: JSON.stringify({ ativa: !e.ativa }) }),
    onSuccess: (r) => { aoSalvar(); toast.success(r.ativa ? "Empresa reativada." : "Empresa desativada: ela sai das buscas automáticas."); },
  });
  const excluir = useMutation({
    mutationFn: () => api<void>(`/api/empresas/${e.id}?confirmacao=${encodeURIComponent(confirmacao)}`, { method: "DELETE" }),
    onSuccess: () => { aoSalvar(); toast.success("Empresa excluída."); navegar("/empresas", { replace: true }); },
  });
  const confere = limparCnpj(confirmacao) === e.cnpj;

  return (
    <Painel titulo="Ações">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-borda pb-4">
        <div className="text-sm">
          <div className="font-medium">{e.ativa ? "Desativar empresa" : "Reativar empresa"}</div>
          <div className="text-texto-2">{e.ativa ? "Para de buscar notas automaticamente. Nada é apagado." : "Volta a entrar nas buscas automáticas."}</div>
        </div>
        <Button onClick={() => alternar.mutate()} disabled={alternar.isPending}>{e.ativa ? "Desativar" : "Reativar"}</Button>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 pt-4">
        <div className="text-sm">
          <div className="font-medium text-cancelada">Excluir empresa</div>
          <div className="text-texto-2">Apaga a empresa, as notas e os arquivos dela neste computador. Os XMLs podem ser baixados de novo do ADN.</div>
        </div>
        <Dialog onOpenChange={() => { setConfirmacao(""); excluir.reset(); }}>
          <DialogTrigger asChild>
            <Button className="border-cancelada/40 text-cancelada hover:bg-cancelada-suave"><Trash2 /> Excluir</Button>
          </DialogTrigger>
          <DialogContent titulo="Excluir empresa" descricao={<>Para confirmar, digite o CNPJ de <strong>{e.razao_social}</strong>: <span className="font-mono">{formatarDoc(e.cnpj)}</span></>}>
            <form onSubmit={(ev) => { ev.preventDefault(); if (confere) excluir.mutate(); }} className="space-y-4">
              <Campo rotulo="CNPJ">{(p) => <Input {...p} value={confirmacao} onChange={(ev) => setConfirmacao(ev.target.value)} className="font-mono" autoFocus autoComplete="off" />}</Campo>
              {excluir.isError && <Aviso tom="erro">{(excluir.error as Error).message}</Aviso>}
              <div className="flex justify-end gap-2">
                <DialogClose asChild><Button type="button" variante="fantasma">Cancelar</Button></DialogClose>
                <Button type="submit" disabled={!confere || excluir.isPending} className="border-transparent bg-cancelada text-destaque-texto hover:bg-cancelada/90">
                  {excluir.isPending && <Loader2 className="animate-spin" />} Excluir definitivamente
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </Painel>
  );
}
