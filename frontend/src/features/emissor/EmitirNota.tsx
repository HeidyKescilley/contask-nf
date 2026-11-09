import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, CheckCircle2, Download, FileText, Loader2, Plus, ReceiptText, RotateCcw, Search, Send,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Copiar } from "@/components/Copiar";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input, Select } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Painel } from "@/features/empresas/Passos";
import { api } from "@/lib/api";
import {
  apenasDigitos, arredondar, escreverValor, lerValor, mascararCep, useAmbienteEmissor, useAtualizarEmissor,
  useEmpresasEmissoras, useServicos, type ConsultaTomador, type EmpresaEmissora, type NotaEmitida, type Servico, type Tomador,
} from "@/lib/emissor";
import { nomeExibicao } from "@/lib/empresas";
import { formatarDoc, mascararCnpj, UFS } from "@/lib/formato";
import { moeda } from "@/lib/notas";
import { cn } from "@/lib/utils";
import { AbasEmissor } from "./Abas";
import { ServicoDialog } from "./ServicoDialog";

const RETENCOES = [
  { id: "ret_pis", rotulo: "PIS", padrao: 0.65 },
  { id: "ret_cofins", rotulo: "COFINS", padrao: 3 },
  { id: "ret_csll", rotulo: "CSLL", padrao: 1 },
  { id: "ret_irrf", rotulo: "IRRF", padrao: 1.5 },
  { id: "ret_cp", rotulo: "INSS", padrao: 11 },
] as const;
type IdRet = (typeof RETENCOES)[number]["id"];

const TOMADOR_VAZIO: Tomador = { documento: "", nome: "", inscricao_municipal: "", cep: "", cod_municipio: "", municipio: "",
  uf: "", logradouro: "", numero: "", complemento: "", bairro: "", telefone: "", email: "" };

interface Form {
  empresaId: number | null;
  servicoId: number | null;
  descricao: string;
  competencia: string;
  valor: string;
  desconto: string;
  semTomador: boolean;
  tomador: Tomador;
  salvarTomador: boolean;
  issRetido: boolean;
  aliquota: string;
  ret: Record<IdRet, string>;
  info: string;
}

function hoje() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function vazio(empresaId: number | null): Form {
  return { empresaId, servicoId: null, descricao: "", competencia: hoje(), valor: "", desconto: "", semTomador: false,
    tomador: TOMADOR_VAZIO, salvarTomador: true, issRetido: false, aliquota: "",
    ret: { ret_pis: "", ret_cofins: "", ret_csll: "", ret_irrf: "", ret_cp: "" }, info: "" };
}

function daNota(n: NotaEmitida): Form {
  const t = n.tomador ? { ...TOMADOR_VAZIO, ...Object.fromEntries(Object.entries(n.tomador).map(([k, v]) => [k, v ?? ""])) } as Tomador : TOMADOR_VAZIO;
  const v = (x: number) => (x ? escreverValor(x) : "");
  return { empresaId: n.empresa_id, servicoId: n.servico_id, descricao: n.descricao, competencia: n.competencia,
    valor: escreverValor(n.valor_servico), desconto: v(n.desconto), semTomador: !n.tomador, tomador: t, salvarTomador: true,
    issRetido: n.iss_retido, aliquota: n.aliquota_iss ? escreverValor(n.aliquota_iss) : "",
    ret: { ret_pis: v(n.ret_pis), ret_cofins: v(n.ret_cofins), ret_csll: v(n.ret_csll), ret_irrf: v(n.ret_irrf), ret_cp: v(n.ret_cp) },
    info: n.info_complementar ?? "" };
}

const num = (s: string) => { const n = lerValor(s); return isNaN(n) ? 0 : n; };

export function EmitirNota() {
  const [params] = useSearchParams();
  const notaId = Number(params.get("nota")) || null;
  const empresaParam = Number(params.get("empresa")) || null;
  const empresas = useEmpresasEmissoras();
  const original = useQuery({
    queryKey: ["emissor", "nota", notaId],
    queryFn: () => api<NotaEmitida>(`/api/emissor/notas/${notaId}`),
    enabled: notaId !== null,
  });

  const emissoras = useMemo(() => (empresas.data ?? []).filter((e) => e.emite_nfse), [empresas.data]);

  return (
    <>
      <Cabecalho titulo="Emissor de NFS-e" descricao="Emita a nota pelo Sistema Nacional da NFS-e em poucos passos." />
      <AbasEmissor />
      {(empresas.isLoading || original.isLoading) && <Esqueleto className="h-96 w-full" />}
      {empresas.isError && <EstadoErro mensagem={(empresas.error as Error).message} tentarDeNovo={() => empresas.refetch()} />}
      {original.isError && <EstadoErro mensagem={(original.error as Error).message} />}
      {empresas.data && emissoras.length === 0 && (
        <EstadoVazio icone={ReceiptText} titulo="Nenhuma empresa emite NFS-e pelo Contask"
          acao={<Button variante="primario" asChild><Link to="/emissor/empresas">Escolher empresas emissoras</Link></Button>}>
          Marque as empresas que emitem nota e cadastre o certificado e os serviços de cada uma.
        </EstadoVazio>
      )}
      {empresas.data && emissoras.length > 0 && (!notaId || original.data) && (
        <Formulario key={notaId ?? "nova"} emissoras={emissoras}
          inicial={original.data ? daNota(original.data) : vazio(emissoras.find((e) => e.id === empresaParam)?.id ?? (emissoras.length === 1 ? emissoras[0].id : null))}
          notaInicial={original.data ?? null} />
      )}
    </>
  );
}

function Secao({ n, titulo, children, acao }: { n: number; titulo: string; children: ReactNode; acao?: ReactNode }) {
  return (
    <section className="rounded-xl border border-borda bg-superficie p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2.5 text-[15px] font-semibold">
          <span className="flex size-6 items-center justify-center rounded-full bg-destaque-suave text-xs font-semibold text-destaque">{n}</span>
          {titulo}
        </h2>
        {acao}
      </div>
      {children}
    </section>
  );
}

function Formulario({ emissoras, inicial, notaInicial }: { emissoras: EmpresaEmissora[]; inicial: Form; notaInicial: NotaEmitida | null }) {
  const [f, setF] = useState<Form>(inicial);
  const [nota, setNota] = useState<NotaEmitida | null>(notaInicial);  // rejeitada/pendente: reenvio com o mesmo número
  const [resultado, setResultado] = useState<NotaEmitida | null>(null);
  const [revisar, setRevisar] = useState(false);
  const [novoServico, setNovoServico] = useState(false);
  const atualizar = useAtualizarEmissor();
  const amb = useAmbienteEmissor();
  const navegar = useNavigate();

  const empresa = emissoras.find((e) => e.id === f.empresaId) ?? null;
  const servicos = useServicos(f.empresaId ?? 0);
  const cfg = empresa?.config;
  const mei = cfg?.op_simples === "2";
  const precisaAliquota = !!cfg && cfg.op_simples === "3" && cfg.reg_ap_trib_sn === "1" && cfg.reg_esp_trib === "0" && f.issRetido;

  // Serviço escolhido preenche a descrição (que pode ser ajustada só nesta nota)
  useEffect(() => {
    if (!servicos.data || f.servicoId) return;
    if (servicos.data.length === 1) escolherServico(servicos.data[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servicos.data]);

  function escolherServico(s: Servico | undefined) {
    setF((a) => ({ ...a, servicoId: s?.id ?? null, descricao: s?.descricao ?? "" }));
  }

  const valor = num(f.valor);
  const desconto = num(f.desconto);
  const federais = mei ? 0 : RETENCOES.reduce((s, r) => s + num(f.ret[r.id]), 0);
  const issEstimado = f.issRetido && precisaAliquota && num(f.aliquota) ? arredondar(valor * num(f.aliquota) / 100) : null;
  const liquido = arredondar(valor - desconto - federais - (issEstimado ?? 0));

  const t = f.tomador;
  const doc = apenasDigitos(t.documento);
  const enderecoCompleto = !!(apenasDigitos(t.cep).length === 8 && apenasDigitos(t.cod_municipio ?? "").length === 7 && t.logradouro && t.numero && t.bairro);
  const enderecoParcial = !!(t.cep || t.cod_municipio || t.logradouro || t.numero || t.bairro) && !enderecoCompleto;

  const problemas: string[] = [];
  if (!empresa) problemas.push("Escolha a empresa que vai emitir.");
  else if (empresa.pendencias.length) problemas.push(...empresa.pendencias);
  if (!f.servicoId) problemas.push("Escolha o serviço.");
  if (!f.descricao.trim()) problemas.push("Informe a descrição do serviço.");
  if (!(valor > 0)) problemas.push("Informe o valor do serviço.");
  if (f.valor && isNaN(lerValor(f.valor))) problemas.push("Valor do serviço inválido. Use o formato 1.234,56.");
  if (desconto >= valor && desconto > 0) problemas.push("O desconto deve ser menor que o valor.");
  if (!f.semTomador) {
    if (![11, 14].includes(doc.length)) problemas.push("Informe o CNPJ ou CPF do tomador.");
    if (!t.nome.trim()) problemas.push("Informe o nome do tomador.");
    if (enderecoParcial) problemas.push("Complete o endereço do tomador (CEP, código IBGE, logradouro, número e bairro) ou deixe em branco.");
  }
  if (f.issRetido && (f.semTomador || !enderecoCompleto)) problemas.push("Com ISS retido, o endereço do tomador é obrigatório.");
  if (precisaAliquota && !(num(f.aliquota) > 0 && num(f.aliquota) <= 5)) problemas.push("Informe a alíquota efetiva de ISS do Simples (até 5%).");
  if (federais + desconto >= valor && valor > 0) problemas.push("As retenções não podem chegar ao valor do serviço.");
  if (f.competencia > hoje()) problemas.push("A competência não pode ser futura.");

  const corpo = () => ({
    empresa_id: f.empresaId, servico_id: f.servicoId, descricao: f.descricao, competencia: f.competencia,
    valor: lerValor(f.valor).toFixed(2), desconto: desconto.toFixed(2),
    tomador: f.semTomador ? null : { ...t, documento: doc },
    salvar_tomador: f.salvarTomador, iss_retido: f.issRetido,
    aliquota_iss: precisaAliquota ? num(f.aliquota).toFixed(2) : null,
    ...Object.fromEntries(RETENCOES.map((r) => [r.id, mei ? "0" : num(f.ret[r.id]).toFixed(2)])),
    info_complementar: f.info.trim() || null,
  });

  const emitir = useMutation({
    mutationFn: () => nota
      ? api<NotaEmitida>(`/api/emissor/notas/${nota.id}/reenviar`, { method: "POST", body: JSON.stringify(corpo()) })
      : api<NotaEmitida>("/api/emissor/notas", { method: "POST", body: JSON.stringify(corpo()) }),
    onSuccess: (n) => {
      atualizar();
      setRevisar(false);
      if (n.situacao === "autorizada") { setResultado(n); setNota(null); window.scrollTo({ top: 0 }); }
      else setNota(n);
    },
    onError: () => setRevisar(false),
  });

  const consultar = useMutation({
    mutationFn: (d: string) => api<ConsultaTomador>(`/api/emissor/tomadores/consulta/${d}`),
    onSuccess: (r) => setF((a) => ({ ...a, tomador: { ...TOMADOR_VAZIO, ...Object.fromEntries(Object.entries(r.tomador).map(([k, v]) => [k, v ?? ""])) } as Tomador })),
  });

  const setT = (k: keyof Tomador) => (ev: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, tomador: { ...t, [k]: ev.target.value } });

  if (resultado) {
    return (
      <Painel>
        <div className="flex flex-col items-center py-6 text-center">
          <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-autorizada-suave text-autorizada">
            <CheckCircle2 className="size-6" aria-hidden />
          </div>
          <h2 className="text-lg font-semibold">NFS-e nº {resultado.numero_nfse} autorizada{resultado.homologacao && " (homologação)"}</h2>
          <p className="mt-1 text-sm text-texto-2">{resultado.empresa_nome} · {resultado.tomador?.nome ?? "sem tomador"} · {moeda(resultado.valor_servico)}</p>
          {resultado.chave && <div className="mt-3 text-sm"><Copiar texto={resultado.chave} exibir={resultado.chave} className="font-mono text-xs" /></div>}
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <Button asChild variante="primario"><a href={`/api/emissor/notas/${resultado.id}/danfse`} target="_blank" rel="noreferrer"><FileText /> Abrir DANFSe</a></Button>
            <Button asChild><a href={`/api/emissor/notas/${resultado.id}/xml`}><Download /> Baixar XML</a></Button>
            <Button onClick={() => { setResultado(null); setF({ ...vazio(f.empresaId), servicoId: f.servicoId, descricao: f.descricao }); }}><Plus /> Emitir outra nota</Button>
            <Button variante="fantasma" onClick={() => navegar("/emissor")}>Ver notas emitidas</Button>
          </div>
        </div>
      </Painel>
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
      <div className="space-y-5">
        {nota && (
          <Aviso tom={nota.situacao === "pendente" ? "alerta" : "erro"}>
            <p className="font-medium">
              {nota.situacao === "pendente" ? "Resultado pendente" : "A Sefin recusou a nota"} (DPS nº {nota.numero})
            </p>
            {nota.erros.length > 0 ? (
              <ul className="mt-1 list-disc space-y-0.5 pl-5">
                {nota.erros.map((e, i) => <li key={i}><span className="font-mono">{e.codigo}</span>: {e.descricao}{e.complemento && ` (${e.complemento})`}</li>)}
              </ul>
            ) : <p className="mt-1">{nota.mensagem}</p>}
            <p className="mt-2 text-texto-2">Corrija abaixo e envie de novo: a nota usa o mesmo número da DPS.</p>
          </Aviso>
        )}

        <Secao n={1} titulo="Empresa emissora">
          <Campo rotulo="Prestador do serviço" obrigatorio>
            {(p) => (
              <Select {...p} value={f.empresaId ?? ""} disabled={!!nota}
                onChange={(ev) => setF({ ...vazio(Number(ev.target.value) || null), competencia: f.competencia })}>
                <option value="">Escolha a empresa…</option>
                {emissoras.map((e) => (
                  <option key={e.id} value={e.id}>{nomeExibicao(e)} · {formatarDoc(e.cnpj)}{e.pronta ? "" : " (com pendência)"}</option>
                ))}
              </Select>
            )}
          </Campo>
          {empresa && empresa.pendencias.length > 0 && (
            <div className="mt-3">
              <Aviso tom="alerta">
                <ul className="list-disc space-y-0.5 pl-5">{empresa.pendencias.map((x) => <li key={x}>{x}</li>)}</ul>
                <Link to={`/emissor/empresas/${empresa.id}`} className="mt-1.5 inline-block font-medium text-destaque hover:underline">Resolver na configuração da empresa</Link>
              </Aviso>
            </div>
          )}
        </Secao>

        <Secao n={2} titulo="Tomador do serviço"
          acao={<label className="flex items-center gap-2 text-sm text-texto-2">
            <input type="checkbox" className="size-4 accent-destaque" checked={f.semTomador} onChange={(ev) => setF({ ...f, semTomador: ev.target.checked })} />
            Nota sem tomador
          </label>}>
          {f.semTomador ? <p className="text-sm text-texto-2">A nota sai sem identificar quem contratou o serviço.</p> : (
            <div className="grid grid-cols-6 gap-3">
              <Campo rotulo="CNPJ ou CPF" obrigatorio className="col-span-3" ajuda="Com CNPJ, os dados vêm do cadastro salvo ou da Receita (BrasilAPI).">
                {(p) => (
                  <div className="flex gap-2">
                    <Input {...p} value={doc.length <= 11 ? doc.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2") : mascararCnpj(doc)}
                      inputMode="numeric" onChange={(ev) => setF({ ...f, tomador: { ...t, documento: apenasDigitos(ev.target.value).slice(0, 14) } })}
                      onBlur={() => { if ([11, 14].includes(doc.length) && !t.nome) consultar.mutate(doc); }} />
                    <Button type="button" onClick={() => consultar.mutate(doc)} disabled={![11, 14].includes(doc.length) || consultar.isPending} aria-label="Buscar dados do tomador">
                      {consultar.isPending ? <Loader2 className="animate-spin" /> : <Search />}
                    </Button>
                  </div>
                )}
              </Campo>
              <Campo rotulo="Inscrição municipal" className="col-span-3">
                {(p) => <Input {...p} value={t.inscricao_municipal ?? ""} maxLength={15} onChange={setT("inscricao_municipal")} placeholder="Opcional" />}
              </Campo>
              {(consultar.data?.aviso || consultar.isError || consultar.data?.origem === "salvo") && (
                <div className="col-span-6">
                  <Aviso tom={consultar.isError ? "erro" : "info"}>
                    {consultar.isError ? (consultar.error as Error).message
                      : consultar.data?.origem === "salvo" ? "Tomador já salvo: os dados abaixo vêm do cadastro." : consultar.data?.aviso}
                  </Aviso>
                </div>
              )}
              <Campo rotulo="Nome ou razão social" obrigatorio className="col-span-6">
                {(p) => <Input {...p} value={t.nome} maxLength={300} onChange={setT("nome")} />}
              </Campo>
              <Campo rotulo="CEP" className="col-span-2" ajuda={f.issRetido ? "Endereço obrigatório com ISS retido." : "Endereço opcional."}>
                {(p) => <Input {...p} value={mascararCep(t.cep)} inputMode="numeric" onChange={(ev) => setF({ ...f, tomador: { ...t, cep: apenasDigitos(ev.target.value) } })} />}
              </Campo>
              <Campo rotulo="Município" className="col-span-2">
                {(p) => <Input {...p} value={t.municipio ?? ""} onChange={setT("municipio")} />}
              </Campo>
              <Campo rotulo="UF" className="col-span-1">
                {(p) => <Select {...p} value={t.uf ?? ""} onChange={setT("uf")}><option value="">—</option>{UFS.map((u) => <option key={u}>{u}</option>)}</Select>}
              </Campo>
              <Campo rotulo="Cód. IBGE" className="col-span-1">
                {(p) => <Input {...p} value={t.cod_municipio ?? ""} inputMode="numeric" maxLength={7} onChange={(ev) => setF({ ...f, tomador: { ...t, cod_municipio: apenasDigitos(ev.target.value) } })} />}
              </Campo>
              <Campo rotulo="Logradouro" className="col-span-4">
                {(p) => <Input {...p} value={t.logradouro ?? ""} maxLength={255} onChange={setT("logradouro")} />}
              </Campo>
              <Campo rotulo="Número" className="col-span-2">
                {(p) => <Input {...p} value={t.numero ?? ""} maxLength={60} onChange={setT("numero")} />}
              </Campo>
              <Campo rotulo="Complemento" className="col-span-3">
                {(p) => <Input {...p} value={t.complemento ?? ""} maxLength={156} onChange={setT("complemento")} />}
              </Campo>
              <Campo rotulo="Bairro" className="col-span-3">
                {(p) => <Input {...p} value={t.bairro ?? ""} maxLength={60} onChange={setT("bairro")} />}
              </Campo>
              <Campo rotulo="E-mail" className="col-span-4">
                {(p) => <Input {...p} type="email" value={t.email ?? ""} maxLength={80} onChange={setT("email")} />}
              </Campo>
              <Campo rotulo="Telefone" className="col-span-2">
                {(p) => <Input {...p} value={t.telefone ?? ""} inputMode="tel" onChange={(ev) => setF({ ...f, tomador: { ...t, telefone: apenasDigitos(ev.target.value) } })} />}
              </Campo>
              <label className="col-span-6 flex items-center gap-2 text-sm text-texto-2">
                <input type="checkbox" className="size-4 accent-destaque" checked={f.salvarTomador} onChange={(ev) => setF({ ...f, salvarTomador: ev.target.checked })} />
                Salvar ou atualizar este tomador para as próximas notas
              </label>
            </div>
          )}
        </Secao>

        <Secao n={3} titulo="Serviço"
          acao={empresa && <Button tamanho="pequeno" variante="fantasma" onClick={() => setNovoServico(true)}><Plus /> Novo serviço</Button>}>
          {!empresa ? <p className="text-sm text-texto-2">Escolha a empresa primeiro.</p>
            : servicos.isLoading ? <Esqueleto className="h-9 w-full" />
            : servicos.data?.length === 0 ? (
              <EstadoVazio icone={FileText} titulo="Esta empresa ainda não tem serviços"
                acao={<Button variante="primario" onClick={() => setNovoServico(true)}><Plus /> Cadastrar serviço</Button>}>
                Cadastre a descrição e os códigos uma vez e reaproveite nas próximas notas.
              </EstadoVazio>
            ) : (
              <div className="space-y-3">
                <Campo rotulo="Serviço cadastrado" obrigatorio>
                  {(p) => (
                    <Select {...p} value={f.servicoId ?? ""} onChange={(ev) => escolherServico(servicos.data?.find((s) => s.id === Number(ev.target.value)))}>
                      <option value="">Escolha o serviço…</option>
                      {servicos.data?.map((s) => <option key={s.id} value={s.id}>{s.ctribnac_formatado} · {s.descricao.slice(0, 90)}</option>)}
                    </Select>
                  )}
                </Campo>
                {f.servicoId && (() => {
                  const s = servicos.data?.find((x) => x.id === f.servicoId);
                  return s ? <p className="text-xs text-texto-2">Item <span className="font-mono">{s.ctribnac_formatado}</span> · {s.ctribnac_descricao} · NBS <span className="font-mono">{s.cnbs_formatado}</span></p> : null;
                })()}
                <Campo rotulo="Descrição nesta nota" obrigatorio ajuda="Pode ajustar só para esta nota (mês de referência, contrato…). O cadastro do serviço não muda.">
                  {(p) => (
                    <textarea {...p} rows={3} maxLength={2000} value={f.descricao} onChange={(ev) => setF({ ...f, descricao: ev.target.value })}
                      className="w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none hover:border-borda-forte focus-visible:border-destaque focus-visible:ring-2 focus-visible:ring-destaque/25" />
                  )}
                </Campo>
              </div>
            )}
        </Secao>

        <Secao n={4} titulo="Valores e retenções">
          <div className="grid grid-cols-3 gap-3">
            <Campo rotulo="Competência" obrigatorio ajuda="Data em que o serviço foi prestado.">
              {(p) => <Input {...p} type="date" value={f.competencia} max={hoje()} onChange={(ev) => setF({ ...f, competencia: ev.target.value })} />}
            </Campo>
            <Campo rotulo="Valor do serviço (R$)" obrigatorio>
              {(p) => <Input {...p} value={f.valor} inputMode="decimal" placeholder="0,00" className="text-right font-mono"
                onChange={(ev) => setF({ ...f, valor: ev.target.value })} onBlur={() => !isNaN(lerValor(f.valor)) && setF({ ...f, valor: escreverValor(lerValor(f.valor)) })} />}
            </Campo>
            <Campo rotulo="Desconto incondicionado (R$)">
              {(p) => <Input {...p} value={f.desconto} inputMode="decimal" placeholder="0,00" className="text-right font-mono"
                onChange={(ev) => setF({ ...f, desconto: ev.target.value })} onBlur={() => !isNaN(lerValor(f.desconto)) && setF({ ...f, desconto: escreverValor(lerValor(f.desconto)) })} />}
            </Campo>
          </div>

          <div className="mt-5 rounded-xl border border-borda p-4">
            <label className="flex cursor-pointer items-start gap-3">
              <input type="checkbox" className="mt-0.5 size-4 accent-destaque" checked={f.issRetido} onChange={(ev) => setF({ ...f, issRetido: ev.target.checked })} />
              <span>
                <span className="block text-sm font-medium">ISS retido pelo tomador</span>
                <span className="block text-sm text-texto-2">O tomador recolhe o ISS. Exige o endereço do tomador.</span>
              </span>
            </label>
            {precisaAliquota && (
              <div className="mt-3 max-w-xs">
                <Campo rotulo="Alíquota efetiva do ISS no Simples (%)" obrigatorio ajuda="Empresa do Simples com ISS retido informa a alíquota efetiva da faixa.">
                  {(p) => <Input {...p} value={f.aliquota} inputMode="decimal" placeholder="2,00" className="text-right font-mono" onChange={(ev) => setF({ ...f, aliquota: ev.target.value })} />}
                </Campo>
              </div>
            )}
            {f.issRetido && !precisaAliquota && <p className="mt-2 text-xs text-texto-2">A alíquota do ISS vem da parametrização do município na Sefin.</p>}
          </div>

          {!mei && (
            <div className="mt-4">
              <p className="mb-2 text-sm font-medium">Retenções federais <span className="font-normal text-texto-2">(deixe em branco se não houver)</span></p>
              <div className="grid grid-cols-5 gap-3">
                {RETENCOES.map((r) => (
                  <Campo key={r.id} rotulo={`${r.rotulo} (R$)`}>
                    {(p) => (
                      <div>
                        <Input {...p} value={f.ret[r.id]} inputMode="decimal" placeholder="0,00" className="text-right font-mono"
                          onChange={(ev) => setF({ ...f, ret: { ...f.ret, [r.id]: ev.target.value } })} />
                        <button type="button" disabled={!(valor > 0)} onClick={() => setF({ ...f, ret: { ...f.ret, [r.id]: escreverValor(arredondar(valor * r.padrao / 100)) } })}
                          className="mt-1 text-xs text-destaque hover:underline disabled:text-texto-2 disabled:no-underline">
                          {String(r.padrao).replace(".", ",")}% do valor
                        </button>
                      </div>
                    )}
                  </Campo>
                ))}
              </div>
            </div>
          )}

          <div className="mt-4">
            <Campo rotulo="Informações complementares" ajuda="Opcional. Aparece no DANFSe.">
              {(p) => (
                <textarea {...p} rows={2} maxLength={2000} value={f.info} onChange={(ev) => setF({ ...f, info: ev.target.value })}
                  className="w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none hover:border-borda-forte focus-visible:border-destaque focus-visible:ring-2 focus-visible:ring-destaque/25" />
              )}
            </Campo>
          </div>
        </Secao>
      </div>

      <aside className="lg:sticky lg:top-20 lg:self-start">
        <Painel titulo="Resumo">
          <dl className="space-y-1.5 text-sm">
            <Linha rotulo="Valor do serviço" valor={moeda(valor || 0)} />
            {desconto > 0 && <Linha rotulo="(−) Desconto" valor={moeda(desconto)} />}
            {federais > 0 && <Linha rotulo="(−) Retenções federais" valor={moeda(federais)} />}
            {f.issRetido && <Linha rotulo="(−) ISS retido" valor={issEstimado !== null ? moeda(issEstimado) : "pela Sefin"} />}
            <div className="border-t border-borda pt-2"><Linha rotulo="Valor líquido estimado" valor={moeda(liquido > 0 ? liquido : 0)} forte /></div>
          </dl>
          {problemas.length > 0 && (
            <ul className="mt-4 space-y-1 text-xs text-texto-2">
              {problemas.slice(0, 4).map((x) => <li key={x} className="flex gap-1.5"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-rejeitada" aria-hidden />{x}</li>)}
            </ul>
          )}
          {emitir.isError && <div className="mt-3"><Aviso tom="erro">{(emitir.error as Error).message}</Aviso></div>}
          <Button variante="primario" className="mt-4 w-full" disabled={problemas.length > 0 || emitir.isPending} onClick={() => setRevisar(true)}>
            {nota ? <><RotateCcw /> Revisar e reenviar</> : <><Send /> Revisar e emitir</>}
          </Button>
          {amb.data && !amb.data.producao && <p className="mt-2 text-center text-xs text-texto-2">Homologação: sem valor fiscal.</p>}
        </Painel>
      </aside>

      <Dialog open={revisar} onOpenChange={(v) => !emitir.isPending && setRevisar(v)}>
        <DialogContent titulo={nota ? "Reenviar a nota?" : "Emitir a nota?"}
          descricao={amb.data?.producao ? "A nota terá valor fiscal. Confira antes de emitir." : "Ambiente de homologação: a nota não tem valor fiscal."}>
          <dl className="space-y-1.5 text-sm">
            <Linha rotulo="Prestador" valor={empresa ? nomeExibicao(empresa) : "—"} />
            <Linha rotulo="Tomador" valor={f.semTomador ? "Sem tomador" : `${t.nome} (${formatarDoc(doc)})`} />
            <Linha rotulo="Competência" valor={f.competencia.split("-").reverse().join("/")} />
            <Linha rotulo="Valor" valor={moeda(valor)} />
            <Linha rotulo="ISS" valor={f.issRetido ? "Retido pelo tomador" : "Não retido"} />
            {federais > 0 && <Linha rotulo="Retenções federais" valor={moeda(federais)} />}
          </dl>
          <div className="mt-5 flex justify-end gap-2">
            <Button variante="fantasma" onClick={() => setRevisar(false)} disabled={emitir.isPending}>Voltar</Button>
            <Button variante="primario" onClick={() => emitir.mutate()} disabled={emitir.isPending}>
              {emitir.isPending ? <><Loader2 className="animate-spin" /> Enviando à Sefin…</> : nota ? "Reenviar agora" : "Emitir agora"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {empresa && (
        <ServicoDialog empresaId={empresa.id} servico={null} aberto={novoServico} aoFechar={() => setNovoServico(false)}
          aoSalvar={(s) => escolherServico(s)} />
      )}
    </div>
  );
}

function Linha({ rotulo, valor, forte }: { rotulo: string; valor: ReactNode; forte?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-texto-2">{rotulo}</dt>
      <dd className={cn("text-right font-mono tabular-nums", forte && "font-semibold text-texto")}>{valor}</dd>
    </div>
  );
}
