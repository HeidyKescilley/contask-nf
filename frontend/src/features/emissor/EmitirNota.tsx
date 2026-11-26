import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle, Building2, CheckCircle2, Download, FileSearch, FileText, Loader2, Pencil, Plus, ShieldCheck, ReceiptText, Repeat, RotateCcw, Save, Search, Send,
} from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Copiar } from "@/components/Copiar";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input, Select } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Painel } from "@/features/empresas/Passos";
import { api } from "@/lib/api";
import {
  TEXTO_PROCON, TEXTO_SIMPLES, VARIAVEIS, abrirPrevia, aplicarVariaveis, apenasDigitos, arredondar, codigosIguais, escreverValor, lerValor, mascararCep,
  proximaData, useAtualizarEmissor, useEmpresasEmissoras, useServicos, variaveisDesconhecidas,
  MOTIVOS_SUBSTITUICAO,
  type CodigosServico, type ConsultaTomador, type CorpoEmissao, type EmpresaEmissora, type ModeloAdn, type NotaEmitida, type Rascunho,
  type Recorrente, type Servico, type Tomador,
} from "@/lib/emissor";
import { nomeExibicao, useEmpresaSelecionada } from "@/lib/empresas";
import { CONTRATE, useTesteGratis } from "@/lib/sessao";
import { EstadoSemEmpresa } from "@/pages/paginas";
import { formatarDoc, mascararCnpj, UFS } from "@/lib/formato";
import { moeda } from "@/lib/notas";
import { cn } from "@/lib/utils";
import { AbasEmissor } from "./Abas";
import { CamposIbsCbs } from "./CamposIbsCbs";
import { ValidacaoDialog, validarNota, type ResultadoValidacao } from "./ValidacaoNota";
import {
  CamposComercioExterior, CamposTomadorExterior, comexCorpo, comexDe, comexVazio, ehExterior, problemasComex, problemasExterior,
  type ComexForm,
} from "./TomadorExterior";
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

export interface DadosRecorrencia {
  nome: string; dia: string; competencia: "atual" | "anterior"; ativa: boolean;
  /** envio por e-mail assim que a nota for autorizada */
  email_enviar: boolean; email_para: string; email_mensagem: string;
}

export interface Form {
  servicoId: number | null;
  /** códigos da nota duplicada: usados quando não há serviço cadastrado igual */
  servicoNota: CodigosServico | null;
  localPrestacao: string;
  descricao: string;
  competencia: string;
  valor: string;
  desconto: string;
  semTomador: boolean;
  /** tomador no exterior (NIF, país e endereço no exterior; a nota leva o grupo de comércio exterior) */
  exterior: boolean;
  comex: ComexForm;
  tomador: Tomador;
  salvarTomador: boolean;
  issRetido: boolean;
  aliquota: string;
  ret: Record<IdRet, string>;
  info: string;
  textoSimples: boolean;
  textoProcon: boolean;
  /** texto fixo da empresa (cadastro do emissor) */
  textoFixo: boolean;
  /** IBS/CBS escolhidos nesta nota; em branco, valem os do serviço */
  cindop: string;
  cclasstrib: string;
}

export function hoje() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function vazio(): Form {
  return { servicoId: null, servicoNota: null, localPrestacao: "", descricao: "", competencia: hoje(), valor: "", desconto: "", semTomador: false,
    exterior: false, comex: comexVazio(), tomador: TOMADOR_VAZIO, salvarTomador: true, issRetido: false, aliquota: "",
    ret: { ret_pis: "", ret_cofins: "", ret_csll: "", ret_irrf: "", ret_cp: "" }, info: "", textoSimples: true, textoProcon: true, textoFixo: true,
    cindop: "", cclasstrib: "" };
}

const doTomador = (t: Partial<Tomador> | null | undefined): Tomador =>
  t ? { ...TOMADOR_VAZIO, ...Object.fromEntries(Object.entries(t).map(([k, v]) => [k, v ?? ""])) } as Tomador : TOMADOR_VAZIO;
const v2 = (x: number | null | undefined) => (x ? escreverValor(x) : "");

type CodigosSoltos = { [K in keyof CodigosServico]?: CodigosServico[K] | null };
function codigosDe(x: CodigosSoltos | null | undefined): CodigosServico | null {
  if (!x?.ctribnac || !x.cnbs) return null;
  return { ctribnac: x.ctribnac, cnbs: x.cnbs, ctribmun: x.ctribmun || null, cindop: x.cindop || null, cclasstrib: x.cclasstrib || null,
    ctribnac_formatado: x.ctribnac_formatado ?? null, ctribnac_descricao: x.ctribnac_descricao ?? null,
    cnbs_formatado: x.cnbs_formatado ?? null, cnbs_descricao: x.cnbs_descricao ?? null };
}

/** Nota já emitida -> formulário. Para duplicar, a competência volta para hoje. */
export function daNota(n: NotaEmitida | ModeloAdn, duplicar = false): Form {
  // Nota sem nenhum texto legal (anterior a eles ou de outro emissor): ao duplicar, vale o padrão (marcados)
  const padrao = duplicar && !n.texto_simples && !n.texto_procon;
  return { servicoId: n.servico_id, servicoNota: codigosDe(n), localPrestacao: n.cod_municipio_prestacao ?? "",
    descricao: n.descricao, competencia: duplicar || !n.competencia ? hoje() : n.competencia,
    valor: escreverValor(n.valor_servico), desconto: v2(n.desconto), semTomador: !n.tomador, tomador: doTomador(n.tomador),
    exterior: ehExterior(n.tomador), comex: comexDe(n.comercio_exterior),
    salvarTomador: true, issRetido: n.iss_retido, aliquota: n.aliquota_iss ? escreverValor(n.aliquota_iss) : "",
    ret: { ret_pis: v2(n.ret_pis), ret_cofins: v2(n.ret_cofins), ret_csll: v2(n.ret_csll), ret_irrf: v2(n.ret_irrf), ret_cp: v2(n.ret_cp) },
    info: n.info_usuario ?? "", textoSimples: padrao || n.texto_simples, textoProcon: padrao || n.texto_procon,
    // Duplicar: o texto fixo vale (inclusive de notas anteriores a ele); corrigir ou substituir: como estava
    textoFixo: duplicar || (n.texto_fixo ?? true),
    // os códigos IBS/CBS da nota original (inclusive os escolhidos só nela)
    cindop: n.cindop ?? "", cclasstrib: n.cclasstrib ?? "" };
}

/** Corpo salvo (rascunho ou recorrência) -> formulário. */
export function doCorpo(d: CorpoEmissao): Form {
  const base = vazio();
  const v = (x: string | null | undefined) => {
    const n = lerValor(x ?? "");
    return isNaN(n) || n === 0 ? "" : escreverValor(n);
  };
  return {
    ...base, servicoId: d.servico_id ?? null, servicoNota: codigosDe(d.servico), localPrestacao: d.cod_municipio_prestacao ?? "",
    descricao: d.descricao ?? "", competencia: d.competencia ?? base.competencia,
    valor: v(d.valor), desconto: v(d.desconto), semTomador: d.tomador === null, tomador: doTomador(d.tomador),
    exterior: ehExterior(d.tomador), comex: comexDe(d.comercio_exterior),
    salvarTomador: d.salvar_tomador ?? true, issRetido: !!d.iss_retido, aliquota: v(d.aliquota_iss),
    ret: { ret_pis: v(d.ret_pis), ret_cofins: v(d.ret_cofins), ret_csll: v(d.ret_csll), ret_irrf: v(d.ret_irrf), ret_cp: v(d.ret_cp) },
    info: d.info_complementar ?? "", textoSimples: d.texto_simples ?? true, textoProcon: d.texto_procon ?? true,
    textoFixo: d.texto_fixo ?? true,
    cindop: d.cindop ?? "", cclasstrib: d.cclasstrib ?? "",
  };
}

const num = (s: string) => { const n = lerValor(s); return isNaN(n) ? 0 : n; };

/** Nota que a emissão vai substituir (grupo subst da DPS). */
export interface AlvoSubstituicao {
  nota_id?: number;
  nota_adn_id?: number;
  numero_nfse: string | null;
  chave: string | null;
  situacao: string | null;
}

export function EmitirNota() {
  const [params] = useSearchParams();
  const id = (k: string) => Number(params.get(k)) || null;
  const notaId = id("nota");          // rejeitada/pendente: corrigir e reenviar com o mesmo número
  const duplicarId = id("duplicar");  // nota do Contask
  const duplicarAdn = id("duplicar_adn");
  const rascunhoId = id("rascunho");
  const substituirId = id("substituir");          // substituir nota do Contask
  const substituirAdn = id("substituir_adn");     // substituir nota emitida fora do Contask (ADN)
  const { empresa: selecionada, carregando } = useEmpresaSelecionada();
  const empresas = useEmpresasEmissoras();

  const fonteId = notaId ?? duplicarId ?? substituirId;
  const adnId = duplicarAdn ?? substituirAdn;
  const original = useQuery({
    queryKey: ["emissor", "nota", fonteId],
    queryFn: () => api<NotaEmitida>(`/api/emissor/notas/${fonteId}`),
    enabled: fonteId !== null,
  });
  const modelo = useQuery({
    queryKey: ["emissor", "modelo-adn", selecionada?.id, adnId],
    queryFn: () => api<ModeloAdn>(`/api/emissor/empresas/${selecionada!.id}/notas/adn/${adnId}/modelo`),
    enabled: adnId !== null && !!selecionada,
  });
  const rascunho = useQuery({
    queryKey: ["emissor", "rascunho", rascunhoId],
    queryFn: () => api<Rascunho>(`/api/emissor/rascunhos/${rascunhoId}`),
    enabled: rascunhoId !== null,
  });

  // O prestador é a empresa da nota/rascunho de origem ou, numa nota nova, a selecionada no topo
  const empresaId = original.data?.empresa_id ?? rascunho.data?.empresa_id ?? modelo.data?.empresa_id ?? selecionada?.id ?? null;
  const empresa = empresas.data?.find((e) => e.id === empresaId) ?? null;
  const fontes = [original, modelo, rascunho];
  const carregandoFonte = fontes.some((q) => q.isLoading);
  const erroFonte = fontes.find((q) => q.isError);

  const inicial = useMemo(() => {
    if (original.data) return daNota(original.data, !!duplicarId);
    // Na substituição vem tudo da original, inclusive a competência
    if (modelo.data) return daNota(modelo.data, !substituirAdn);
    if (rascunho.data) return doCorpo(rascunho.data.dados);
    return vazio();
  }, [original.data, modelo.data, rascunho.data, duplicarId, substituirAdn]);

  const substituir: AlvoSubstituicao | null =
    substituirId && original.data ? { nota_id: original.data.id, numero_nfse: original.data.numero_nfse, chave: original.data.chave, situacao: original.data.situacao }
    : substituirAdn && modelo.data ? { nota_adn_id: substituirAdn, numero_nfse: modelo.data.numero_nfse, chave: modelo.data.chave ?? null, situacao: modelo.data.situacao ?? null }
    : null;

  const chave = `${notaId}-${duplicarId}-${duplicarAdn}-${substituirId}-${substituirAdn}-${rascunhoId}-${empresaId}`;
  const titulo = notaId ? "Corrigir e reenviar" : rascunhoId ? "Continuar rascunho" : duplicarId || duplicarAdn ? "Duplicar nota"
    : substituir ? `Substituir a NFS-e nº ${substituir.numero_nfse ?? "-"}: confira os dados, corrija o que precisar e emita a substituta.` : undefined;

  return (
    <>
      <Cabecalho titulo="Emissor de NFS-e" descricao={titulo ?? "Emita a nota pelo Sistema Nacional da NFS-e em poucos passos."} />
      <AbasEmissor empresaId={empresaId} />
      {(empresas.isLoading || carregando || carregandoFonte) && <Esqueleto className="h-96 w-full" />}
      {empresas.isError && <EstadoErro mensagem={(empresas.error as Error).message} tentarDeNovo={() => empresas.refetch()} />}
      {erroFonte && <EstadoErro mensagem={(erroFonte.error as Error).message} />}
      {empresas.data && !carregando && !carregandoFonte && !erroFonte && (
        !empresa || !empresa.emite_nfse ? <SemEmpresa id={empresaId} /> : (
          <Formulario key={chave} empresa={empresa} inicial={inicial} notaInicial={notaId ? original.data ?? null : null}
            rascunhoId={rascunhoId} substituir={substituir} />
        )
      )}
    </>
  );
}

function SemEmpresa({ id }: { id: number | null }) {
  if (!id) return <EstadoSemEmpresa icone={ReceiptText} />;
  return (
    <EstadoVazio icone={ReceiptText} titulo={id ? "A empresa selecionada não emite NFS-e pelo Contask" : "Escolha uma empresa"}
      acao={<Button variante="primario" asChild><Link to={id ? `/emissor/empresas/${id}?empresa=${id}` : "/emissor/empresas"}>{id ? "Configurar emissão" : "Escolher empresas emissoras"}</Link></Button>}>
      {id ? "Escolha outra empresa no topo da página ou marque esta como emissora." : "Selecione no topo da página a empresa que vai emitir a nota."}
    </EstadoVazio>
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

const CLASSE_TEXTO = "w-full rounded-xl border border-borda bg-superficie px-3 py-2 text-sm outline-none hover:border-borda-forte focus-visible:border-destaque focus-visible:ring-2 focus-visible:ring-destaque/25";
const dataBR = (d: Date) => d.toLocaleDateString("pt-BR");

export function Formulario({ empresa, inicial, notaInicial = null, rascunhoId = null, recorrencia, substituir = null }: {
  empresa: EmpresaEmissora;
  inicial: Form;
  notaInicial?: NotaEmitida | null;
  rascunhoId?: number | null;
  /** a nota sai como substituta desta */
  substituir?: AlvoSubstituicao | null;
  /** modo recorrência: dados da agenda e a recorrência em edição (se houver) */
  recorrencia?: { dados: DadosRecorrencia; existente: Recorrente | null };
}) {
  const [f, setF] = useState<Form>(inicial);
  const [rec, setRec] = useState<DadosRecorrencia | null>(recorrencia?.dados ?? null);
  const [nota, setNota] = useState<NotaEmitida | null>(notaInicial);  // rejeitada/pendente: reenvio com o mesmo número
  const [rascunho, setRascunho] = useState<number | null>(rascunhoId);
  const [resultado, setResultado] = useState<NotaEmitida | null>(null);
  const [revisar, setRevisar] = useState(false);
  const [novoServico, setNovoServico] = useState(false);
  const [editarServico, setEditarServico] = useState(false);
  const atualizar = useAtualizarEmissor();
  const navegar = useNavigate();
  const modoRec = !!recorrencia;
  const teste = useTesteGratis();
  const [sub, setSub] = useState({ motivo: "99", justificativa: "" });
  // No teste grátis só uma nota pode ser emitida; corrigir e reenviar ou substituir a mesma continua valendo
  const semEmissao = !modoRec && !nota && !substituir?.nota_id && teste.emTeste && teste.emissoesRestantes === 0;

  const producao = empresa.ambiente === 1;
  const servicos = useServicos(empresa.id);
  const cfg = empresa.config;
  const mei = cfg?.op_simples === "2";
  const simples = !!cfg?.simples;
  const precisaAliquota = !!cfg && cfg.op_simples === "3" && cfg.reg_ap_trib_sn === "1" && cfg.reg_esp_trib === "0" && f.issRetido;

  // Serviço único já vem escolhido. Na nota duplicada, o serviço cadastrado só vale se tiver os mesmos códigos dela;
  // senão a nota sai com os códigos da original, sem precisar cadastrar
  useEffect(() => {
    if (!servicos.data) return;
    const nota = f.servicoNota;
    if (nota) {
      const atual = servicos.data.find((s) => s.id === f.servicoId);
      if (!atual || !codigosIguais(atual, nota)) {
        const igual = servicos.data.find((s) => codigosIguais(s, nota));
        setF((a) => ({ ...a, servicoId: igual?.id ?? null }));
      }
      return;
    }
    if (f.servicoId) return;
    if (servicos.data.length === 1 && !f.descricao) escolherServico(servicos.data[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [servicos.data]);

  function escolherServico(s: Servico | undefined) {
    setF((a) => ({ ...a, servicoId: s?.id ?? null, descricao: s?.descricao ?? "", cindop: "", cclasstrib: "" }));
  }
  const DA_NOTA = "nota";
  const usaNota = !f.servicoId && !!f.servicoNota;
  const servicoAtual = f.servicoId ? servicos.data?.find((x) => x.id === f.servicoId) ?? null : null;
  const codigosAtuais: Partial<CodigosServico> | null = f.servicoId ? servicoAtual : f.servicoNota;
  // Grupo IBS/CBS na nota: empresa fora do Simples (Sefin) ou ISSNet do DF
  const mostraIbs = !!cfg?.exige_ibscbs || empresa.canal === "issnet_df";
  const cindopFinal = f.cindop || codigosAtuais?.cindop || "";
  const cclasstribFinal = f.cclasstrib || codigosAtuais?.cclasstrib || "";

  const valor = num(f.valor);
  const desconto = num(f.desconto);
  const federais = mei ? 0 : RETENCOES.reduce((s, r) => s + num(f.ret[r.id]), 0);
  const issEstimado = f.issRetido && precisaAliquota && num(f.aliquota) ? arredondar(valor * num(f.aliquota) / 100) : null;
  const liquido = arredondar(valor - desconto - federais - (issEstimado ?? 0));

  const t = f.tomador;
  const doc = apenasDigitos(t.documento);
  const enderecoCompleto = !!(apenasDigitos(t.cep).length === 8 && apenasDigitos(t.cod_municipio ?? "").length === 7 && t.logradouro && t.numero && t.bairro);
  const enderecoParcial = !!(t.cep || t.cod_municipio || t.logradouro || t.numero || t.bairro) && !enderecoCompleto;

  const diaRec = Number(rec?.dia) || 0;
  const proxima = modoRec && diaRec >= 1 && diaRec <= 31 ? proximaData(diaRec) : null;
  const desconhecidas = modoRec ? variaveisDesconhecidas(`${f.descricao} ${f.info}`) : [];

  const problemas: string[] = [];
  if (empresa.pendencias.length) problemas.push(...empresa.pendencias);
  if (semEmissao) problemas.push(`A emissão do teste grátis já foi usada. ${CONTRATE}`);
  if (modoRec && teste.emTeste) problemas.push(`As notas recorrentes não fazem parte do teste grátis. ${CONTRATE}`);
  if (modoRec) {
    if (!rec?.nome.trim()) problemas.push("Dê um nome à recorrência.");
    if (!proxima) problemas.push("Informe o dia da emissão (1 a 31).");
    if (desconhecidas.length) problemas.push(`Variável desconhecida: ${desconhecidas.map((x) => `{${x}}`).join(", ")}.`);
  }
  if (!f.servicoId && !f.servicoNota) problemas.push("Escolha o serviço.");
  else if (mostraIbs && (!cindopFinal || !cclasstribFinal)) problemas.push("Escolha o cIndOp e o cClassTrib (IBS/CBS) da nota.");
  if (f.localPrestacao && apenasDigitos(f.localPrestacao).length !== 7) problemas.push("O local da prestação deve ter o código IBGE de 7 dígitos.");
  if (!f.descricao.trim()) problemas.push("Informe a descrição do serviço.");
  if (!(valor > 0)) problemas.push("Informe o valor do serviço.");
  if (f.valor && isNaN(lerValor(f.valor))) problemas.push("Valor do serviço inválido. Use o formato 1.234,56.");
  if (desconto >= valor && desconto > 0) problemas.push("O desconto deve ser menor que o valor.");
  const exterior = !f.semTomador && f.exterior;
  if (exterior) {
    problemas.push(...problemasExterior(t), ...problemasComex(f.comex));
    if (f.issRetido) problemas.push("Tomador no exterior não retém ISS: desmarque o ISS retido.");
  } else if (!f.semTomador) {
    if (![11, 14].includes(doc.length)) problemas.push("Informe o CNPJ ou CPF do tomador.");
    if (!t.nome.trim()) problemas.push("Informe o nome do tomador.");
    if (enderecoParcial) problemas.push("Complete o endereço do tomador (CEP, código IBGE, logradouro, número e bairro) ou deixe em branco.");
  }
  if (f.issRetido && !exterior && (f.semTomador || !enderecoCompleto)) problemas.push("Com ISS retido, o endereço do tomador é obrigatório.");
  if (precisaAliquota && !(num(f.aliquota) > 0 && num(f.aliquota) <= 5)) problemas.push("Informe a alíquota efetiva de ISS do Simples (até 5%).");
  if (federais + desconto >= valor && valor > 0) problemas.push("As retenções não podem chegar ao valor do serviço.");
  if (!modoRec && f.competencia > hoje()) problemas.push("A competência não pode ser futura.");
  const chaveOriginal = substituir?.chave ?? nota?.subst_chave ?? null;
  const justificativa = sub.justificativa.trim().replace(/\s+/g, " ");
  if (substituir && !nota) {
    if (substituir.situacao && substituir.situacao !== "autorizada") problemas.push("A nota a substituir não está autorizada.");
    if (justificativa.length < 15) problemas.push("Explique o motivo da substituição (mínimo de 15 caracteres).");
  }

  const fixo = (s: string) => { const n = lerValor(s); return isNaN(n) ? "" : n.toFixed(2); };
  const corpo = (): CorpoEmissao & { empresa_id: number } => ({
    empresa_id: empresa.id, servico_id: f.servicoId, competencia: f.competencia, descricao: f.descricao,
    servico: f.servicoId || !f.servicoNota ? null : { ctribnac: f.servicoNota.ctribnac, cnbs: f.servicoNota.cnbs,
      ctribmun: f.servicoNota.ctribmun, cindop: f.servicoNota.cindop, cclasstrib: f.servicoNota.cclasstrib },
    cod_municipio_prestacao: apenasDigitos(f.localPrestacao) || null,
    cindop: mostraIbs ? f.cindop || null : null, cclasstrib: mostraIbs ? f.cclasstrib || null : null,
    valor: fixo(f.valor), desconto: desconto.toFixed(2),
    tomador: f.semTomador ? null : exterior
      ? { ...t, documento: "", nif: t.nif?.trim() || null, nao_nif: t.nif?.trim() ? null : t.nao_nif || null }
      : { ...t, documento: doc, pais: null, nif: null, nao_nif: null, cod_postal: null, cidade: null, estado_provincia: null },
    comercio_exterior: exterior ? comexCorpo(f.comex) : null,
    salvar_tomador: f.salvarTomador, iss_retido: f.issRetido,
    aliquota_iss: precisaAliquota && num(f.aliquota) ? num(f.aliquota).toFixed(2) : null,
    ...Object.fromEntries(RETENCOES.map((r) => [r.id, mei ? "0" : num(f.ret[r.id]).toFixed(2)])),
    info_complementar: f.info.trim() || null,
    texto_simples: simples && f.textoSimples, texto_procon: f.textoProcon, texto_fixo: f.textoFixo,
  });

  const emitir = useMutation({
    mutationFn: () => nota
      ? api<NotaEmitida>(`/api/emissor/notas/${nota.id}/reenviar`, { method: "POST", body: JSON.stringify(corpo()) })
      : api<NotaEmitida>("/api/emissor/notas", { method: "POST", body: JSON.stringify({ ...corpo(), rascunho_id: rascunho,
          substituicao: substituir ? { nota_id: substituir.nota_id ?? null, nota_adn_id: substituir.nota_adn_id ?? null,
            motivo: sub.motivo, justificativa } : null }) }),
    onSuccess: (n) => {
      atualizar();
      setRevisar(false);
      setRascunho(null);  // o rascunho virou nota
      if (n.situacao === "autorizada") { setResultado(n); setNota(null); window.scrollTo({ top: 0 }); }
      else setNota(n);
    },
    onError: () => setRevisar(false),
  });

  const salvarRascunho = useMutation({
    mutationFn: () => {
      const { empresa_id, ...dados } = corpo();
      const body = JSON.stringify({ empresa_id, dados });
      return rascunho
        ? api<Rascunho>(`/api/emissor/rascunhos/${rascunho}`, { method: "PUT", body })
        : api<Rascunho>("/api/emissor/rascunhos", { method: "POST", body });
    },
    onSuccess: (r) => { atualizar(); setRascunho(r.id); toast.success("Rascunho salvo. Ele fica na página de notas para emitir depois."); },
    onError: (err) => toast.error((err as Error).message),
  });

  // Validar: confere sem transmitir; numa nota nova, salva antes como rascunho e guarda nele o resultado
  const [validacaoAberta, setValidacaoAberta] = useState(false);
  const guardaRascunho = !nota && !substituir;
  const validar = useMutation({
    mutationFn: async (): Promise<ResultadoValidacao> => {
      const c = corpo();
      if (!guardaRascunho) return validarNota(c);
      const { empresa_id, ...dados } = c;
      const body = JSON.stringify({ empresa_id, dados });
      const r = rascunho
        ? await api<Rascunho>(`/api/emissor/rascunhos/${rascunho}`, { method: "PUT", body })
        : await api<Rascunho>("/api/emissor/rascunhos", { method: "POST", body });
      setRascunho(r.id);
      return validarNota({ ...c, rascunho_id: r.id });
    },
    onMutate: () => setValidacaoAberta(true),
    onSettled: () => atualizar(),
  });

  const previa = useMutation({
    mutationFn: () => abrirPrevia(corpo()),
    onError: (err) => toast.error((err as Error).message),
  });

  const salvarRecorrencia = useMutation({
    mutationFn: () => {
      const { empresa_id, competencia: _c, ...dados } = corpo();
      const body = JSON.stringify({ empresa_id, nome: rec!.nome.trim(), dia: diaRec, competencia: rec!.competencia, ativa: rec!.ativa, dados,
        email_enviar: rec!.email_enviar, email_para: rec!.email_para.trim() || null, email_mensagem: rec!.email_mensagem.trim() || null });
      const id = recorrencia?.existente?.id;
      return id ? api<Recorrente>(`/api/emissor/recorrentes/${id}`, { method: "PUT", body })
        : api<Recorrente>("/api/emissor/recorrentes", { method: "POST", body });
    },
    onSuccess: (r) => {
      atualizar(); setRevisar(false);
      toast.success(r.proxima_em ? `Recorrência salva. Próxima emissão em ${r.proxima_em.split("-").reverse().join("/")}.` : "Recorrência salva (pausada).");
      navegar(`/emissor/recorrentes?empresa=${empresa.id}`);
    },
    onError: () => setRevisar(false),
  });

  const consultar = useMutation({
    mutationFn: (d: string) => api<ConsultaTomador>(`/api/emissor/tomadores/consulta/${d}`),
    onSuccess: (r) => setF((a) => ({ ...a, tomador: doTomador(r.tomador) })),
  });

  const setT = (k: keyof Tomador) => (ev: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF({ ...f, tomador: { ...t, [k]: ev.target.value } });

  const inserirVariavel = (nome: string) => setF((a) => ({ ...a, descricao: `${a.descricao}${a.descricao && !a.descricao.endsWith(" ") ? " " : ""}{${nome}}` }));

  if (resultado) {
    return (
      <Painel>
        <div className="flex flex-col items-center py-6 text-center">
          <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-autorizada-suave text-autorizada">
            <CheckCircle2 className="size-6" aria-hidden />
          </div>
          <h2 className="text-lg font-semibold">NFS-e nº {resultado.numero_nfse} autorizada{resultado.homologacao && " (homologação)"}</h2>
          {resultado.subst_chave && (
            <p className="mt-1 text-sm text-texto-2">
              Substitui a NFS-e{resultado.substitui?.numero_nfse ? ` nº ${resultado.substitui.numero_nfse}` : ""}, que a Sefin cancelou por substituição.
            </p>
          )}
          <p className="mt-1 text-sm text-texto-2">{resultado.empresa_nome} · {resultado.tomador?.nome ?? "sem tomador"} · {moeda(resultado.valor_servico)}</p>
          {resultado.chave && <div className="mt-3 text-sm"><Copiar texto={resultado.chave} exibir={resultado.chave} className="font-mono text-xs" /></div>}
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <Button asChild variante="primario"><a href={`/api/emissor/notas/${resultado.id}/danfse`} target="_blank" rel="noreferrer"><FileText /> Abrir DANFSe</a></Button>
            {!teste.emTeste && <Button asChild><a href={`/api/emissor/notas/${resultado.id}/xml`}><Download /> Baixar XML</a></Button>}
            <Button onClick={() => { setResultado(null); setF({ ...vazio(), servicoId: f.servicoId, servicoNota: f.servicoNota, localPrestacao: f.localPrestacao, descricao: f.descricao, cindop: f.cindop, cclasstrib: f.cclasstrib }); }}><Plus /> Emitir outra nota</Button>
            <Button variante="fantasma" onClick={() => navegar(`/emissor?empresa=${empresa.id}`)}>Ver notas</Button>
          </div>
        </div>
      </Painel>
    );
  }

  let n = 0;
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

        {(substituir || nota?.subst_chave) && (
          <Secao n={++n} titulo="Substituição">
            <p className="text-sm text-texto-2">
              Esta nota substitui a NFS-e{" "}
              <strong className="text-texto">nº {(substituir?.numero_nfse ?? nota?.substitui?.numero_nfse) || "-"}</strong>.
              Quando a substituta for autorizada, a Sefin cancela a original sozinha (cancelamento por substituição).
              Os dados abaixo vieram da nota original: corrija só o que precisar.
            </p>
            {chaveOriginal && (
              <p className="mt-2 text-xs text-texto-2">Chave da original: <Copiar texto={chaveOriginal} exibir={chaveOriginal} className="font-mono" /></p>
            )}
            {substituir && !nota ? (
              <div className="mt-4 grid gap-4">
                {substituir.situacao && substituir.situacao !== "autorizada" && (
                  <Aviso tom="erro">A nota original está {substituir.situacao}: só dá para substituir uma nota autorizada.</Aviso>
                )}
                <Campo rotulo="Motivo">
                  {(p) => (
                    <Select {...p} value={sub.motivo} onChange={(ev) => setSub({ ...sub, motivo: ev.target.value })}>
                      {MOTIVOS_SUBSTITUICAO.map((m) => <option key={m.codigo} value={m.codigo}>{m.codigo} – {m.rotulo}</option>)}
                    </Select>
                  )}
                </Campo>
                <Campo rotulo="Justificativa" ajuda={`Vai na nota substituta e no evento de cancelamento da original. ${justificativa.length}/255 caracteres (mínimo 15).`}>
                  {(p) => <textarea {...p} rows={2} maxLength={255} value={sub.justificativa} placeholder="Ex.: CNPJ do tomador informado errado na nota original."
                    onChange={(ev) => setSub({ ...sub, justificativa: ev.target.value })} className={CLASSE_TEXTO} />}
                </Campo>
              </div>
            ) : nota?.subst_justificativa && (
              <p className="mt-2 text-sm">Justificativa: {nota.subst_justificativa}</p>
            )}
          </Secao>
        )}

        {teste.emTeste && !modoRec && (
          <Aviso tom={semEmissao ? "alerta" : "info"}>
            <strong>Teste grátis:</strong>{" "}
            {semEmissao
              ? <>a nota de demonstração já foi emitida. Dá para salvar rascunhos. <strong>{CONTRATE}</strong></>
              : `você pode emitir ${teste.emissoesRestantes} nota para conhecer o emissor. ${CONTRATE}`}
          </Aviso>
        )}

        <Secao n={++n} titulo="Prestador">
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-superficie-2 text-texto-2"><Building2 className="size-4" aria-hidden /></span>
            <div className="min-w-0">
              <p className="font-medium">{empresa.razao_social}</p>
              <p className="text-sm text-texto-2"><span className="font-mono">{formatarDoc(empresa.cnpj)}</span>
                {nomeExibicao(empresa) !== empresa.razao_social && <> · {nomeExibicao(empresa)}</>}</p>
              <p className="mt-1 text-xs text-texto-2">Para emitir por outra empresa, troque a empresa no topo da página.</p>
            </div>
          </div>
          {empresa.pendencias.length > 0 && (
            <div className="mt-3">
              <Aviso tom="alerta">
                <ul className="list-disc space-y-0.5 pl-5">{empresa.pendencias.map((x) => <li key={x}>{x}</li>)}</ul>
                <Link to={`/emissor/empresas/${empresa.id}?empresa=${empresa.id}`} className="mt-1.5 inline-block font-medium text-destaque hover:underline">Resolver na configuração da empresa</Link>
              </Aviso>
            </div>
          )}
        </Secao>

        {modoRec && rec && (
          <Secao n={++n} titulo="Recorrência">
            <div className="grid grid-cols-6 gap-3">
              <Campo rotulo="Nome" obrigatorio className="col-span-6 sm:col-span-3" ajuda="Para você reconhecer na lista. Não vai na nota.">
                {(p) => <Input {...p} value={rec.nome} maxLength={120} placeholder="Ex.: Honorários mensais" onChange={(ev) => setRec({ ...rec, nome: ev.target.value })} />}
              </Campo>
              <Campo rotulo="Dia da emissão" obrigatorio className="col-span-3 sm:col-span-1" ajuda="1 a 31.">
                {(p) => <Input {...p} value={rec.dia} inputMode="numeric" maxLength={2} onChange={(ev) => setRec({ ...rec, dia: apenasDigitos(ev.target.value) })} />}
              </Campo>
              <Campo rotulo="Competência" className="col-span-3 sm:col-span-2">
                {(p) => (
                  <Select {...p} value={rec.competencia} onChange={(ev) => setRec({ ...rec, competencia: ev.target.value as DadosRecorrencia["competencia"] })}>
                    <option value="atual">Dia da emissão</option>
                    <option value="anterior">Último dia do mês anterior</option>
                  </Select>
                )}
              </Campo>
              <div className="col-span-6 flex flex-wrap items-center justify-between gap-3 text-sm">
                <label className="flex items-center gap-2 text-texto-2">
                  <input type="checkbox" className="size-4 accent-destaque" checked={rec.ativa} onChange={(ev) => setRec({ ...rec, ativa: ev.target.checked })} />
                  Ativa (desmarque para pausar sem apagar)
                </label>
                {proxima && rec.ativa && (
                  <span className="text-texto-2">Próxima emissão: <strong className="text-texto">{dataBR(proxima)}</strong>{diaRec > 28 && " (em meses mais curtos, no último dia)"}</span>
                )}
              </div>
              <div className="col-span-6 border-t border-borda pt-3">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="size-4 accent-destaque" checked={rec.email_enviar} onChange={(ev) => setRec({ ...rec, email_enviar: ev.target.checked })} />
                  Enviar a nota por e-mail assim que for autorizada
                </label>
                {rec.email_enviar && (
                  <div className="mt-3 grid grid-cols-6 gap-3">
                    <Campo rotulo="Para" className="col-span-6"
                      ajuda={t.email ? `Vazio: vai para o e-mail do tomador (${t.email}). Até 5 e-mails, separados por vírgula.`
                        : "Até 5 e-mails, separados por vírgula. Vazio: vai para o e-mail do tomador (preencha no tomador abaixo)."}>
                      {(p) => <Input {...p} value={rec.email_para} maxLength={1200} placeholder={t.email || "financeiro@cliente.com.br"}
                        onChange={(ev) => setRec({ ...rec, email_para: ev.target.value })} />}
                    </Campo>
                    <Campo rotulo="Mensagem (opcional)" className="col-span-6" ajuda="Vai no corpo do e-mail, junto com os dados da nota. O DANFSe (PDF) e o XML seguem em anexo.">
                      {(p) => <textarea {...p} rows={2} maxLength={2000} value={rec.email_mensagem} className={CLASSE_TEXTO}
                        onChange={(ev) => setRec({ ...rec, email_mensagem: ev.target.value })} />}
                    </Campo>
                  </div>
                )}
              </div>
            </div>
          </Secao>
        )}

        <Secao n={++n} titulo="Tomador do serviço"
          acao={<label className="flex items-center gap-2 text-sm text-texto-2">
            <input type="checkbox" className="size-4 accent-destaque" checked={f.semTomador} onChange={(ev) => setF({ ...f, semTomador: ev.target.checked })} />
            Nota sem tomador
          </label>}>
          {!f.semTomador && (
            <div className="mb-3 inline-flex rounded-lg border border-borda p-0.5" role="radiogroup" aria-label="Onde está o tomador">
              {([[false, "No Brasil"], [true, "No exterior"]] as const).map(([v, rot]) => (
                <button key={rot} type="button" role="radio" aria-checked={f.exterior === v}
                  onClick={() => setF((a) => ({ ...a, exterior: v, issRetido: v ? false : a.issRetido,
                    comex: v && !a.comex.valorMoeda ? comexVazio(empresa.canal === "issnet_df") : a.comex,
                    tomador: v ? { ...a.tomador, pais: a.tomador.pais && a.tomador.pais !== "BR" ? a.tomador.pais : "" } : { ...a.tomador, pais: null } }))}
                  className={cn("rounded-md px-3 py-1.5 text-sm", f.exterior === v ? "bg-destaque text-white" : "text-texto-2 hover:text-texto")}>
                  {rot}
                </button>
              ))}
            </div>
          )}
          {f.semTomador ? <p className="text-sm text-texto-2">A nota sai sem identificar quem contratou o serviço.</p> : f.exterior ? (
            <div className="grid grid-cols-6 gap-3">
              <TomadoresExterior escolher={(x) => setF((a) => ({ ...a, tomador: doTomador(x) }))} />
              <CamposTomadorExterior t={t} mudar={(c) => setF((a) => ({ ...a, tomador: { ...a.tomador, ...c } }))} />
              <Campo rotulo="E-mail" className="col-span-6 sm:col-span-4">
                {(p) => <Input {...p} type="email" value={t.email ?? ""} maxLength={80} onChange={setT("email")} />}
              </Campo>
              <Campo rotulo="Telefone" className="col-span-6 sm:col-span-2">
                {(p) => <Input {...p} value={t.telefone ?? ""} inputMode="tel" onChange={(ev) => setF({ ...f, tomador: { ...t, telefone: apenasDigitos(ev.target.value) } })} />}
              </Campo>
              <CamposComercioExterior c={f.comex} issnet={empresa.canal === "issnet_df"} mudar={(x) => setF((a) => ({ ...a, comex: { ...a.comex, ...x } }))} />
              {!modoRec && (
                <label className="col-span-6 flex items-center gap-2 text-sm text-texto-2">
                  <input type="checkbox" className="size-4 accent-destaque" checked={f.salvarTomador} onChange={(ev) => setF({ ...f, salvarTomador: ev.target.checked })} />
                  Salvar ou atualizar este tomador para as próximas notas
                </label>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-6 gap-3">
              <Campo rotulo="CNPJ ou CPF" obrigatorio className="col-span-6 sm:col-span-3" ajuda="Com CNPJ, os dados vêm do cadastro salvo ou da Receita (BrasilAPI).">
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
              <Campo rotulo="Inscrição municipal" className="col-span-6 sm:col-span-3">
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
              <Campo rotulo="CEP" className="col-span-3 sm:col-span-2" ajuda={f.issRetido ? "Endereço obrigatório com ISS retido." : "Endereço opcional."}>
                {(p) => <Input {...p} value={mascararCep(t.cep)} inputMode="numeric" onChange={(ev) => setF({ ...f, tomador: { ...t, cep: apenasDigitos(ev.target.value) } })} />}
              </Campo>
              <Campo rotulo="Município" className="col-span-3 sm:col-span-2">
                {(p) => <Input {...p} value={t.municipio ?? ""} onChange={setT("municipio")} />}
              </Campo>
              <Campo rotulo="UF" className="col-span-3 sm:col-span-1">
                {(p) => <Select {...p} value={t.uf ?? ""} onChange={setT("uf")}><option value="">—</option>{UFS.map((u) => <option key={u}>{u}</option>)}</Select>}
              </Campo>
              <Campo rotulo="Cód. IBGE" className="col-span-3 sm:col-span-1">
                {(p) => <Input {...p} value={t.cod_municipio ?? ""} inputMode="numeric" maxLength={7} onChange={(ev) => setF({ ...f, tomador: { ...t, cod_municipio: apenasDigitos(ev.target.value) } })} />}
              </Campo>
              <Campo rotulo="Logradouro" className="col-span-6 sm:col-span-4">
                {(p) => <Input {...p} value={t.logradouro ?? ""} maxLength={255} onChange={setT("logradouro")} />}
              </Campo>
              <Campo rotulo="Número" className="col-span-6 sm:col-span-2">
                {(p) => <Input {...p} value={t.numero ?? ""} maxLength={60} onChange={setT("numero")} />}
              </Campo>
              <Campo rotulo="Complemento" className="col-span-6 sm:col-span-3">
                {(p) => <Input {...p} value={t.complemento ?? ""} maxLength={156} onChange={setT("complemento")} />}
              </Campo>
              <Campo rotulo="Bairro" className="col-span-6 sm:col-span-3">
                {(p) => <Input {...p} value={t.bairro ?? ""} maxLength={60} onChange={setT("bairro")} />}
              </Campo>
              <Campo rotulo="E-mail" className="col-span-6 sm:col-span-4">
                {(p) => <Input {...p} type="email" value={t.email ?? ""} maxLength={80} onChange={setT("email")} />}
              </Campo>
              <Campo rotulo="Telefone" className="col-span-6 sm:col-span-2">
                {(p) => <Input {...p} value={t.telefone ?? ""} inputMode="tel" onChange={(ev) => setF({ ...f, tomador: { ...t, telefone: apenasDigitos(ev.target.value) } })} />}
              </Campo>
              {!modoRec && (
                <label className="col-span-6 flex items-center gap-2 text-sm text-texto-2">
                  <input type="checkbox" className="size-4 accent-destaque" checked={f.salvarTomador} onChange={(ev) => setF({ ...f, salvarTomador: ev.target.checked })} />
                  Salvar ou atualizar este tomador para as próximas notas
                </label>
              )}
            </div>
          )}
        </Secao>

        <Secao n={++n} titulo="Serviço"
          acao={<Button tamanho="pequeno" variante="fantasma" onClick={() => setNovoServico(true)}><Plus /> Novo serviço</Button>}>
          {servicos.isLoading ? <Esqueleto className="h-9 w-full" />
            : servicos.isError ? <EstadoErro mensagem={(servicos.error as Error).message} tentarDeNovo={() => servicos.refetch()} />
            : servicos.data?.length === 0 && !f.servicoNota ? (
              <EstadoVazio icone={FileText} titulo="Esta empresa ainda não tem serviços"
                acao={<Button variante="primario" onClick={() => setNovoServico(true)}><Plus /> Cadastrar serviço</Button>}>
                Cadastre a descrição e os códigos uma vez e reaproveite nas próximas notas.
              </EstadoVazio>
            ) : (
              <div className="space-y-3">
                <Campo rotulo="Serviço" obrigatorio
                  ajuda={usaNota ? "Códigos da nota original. Não precisa cadastrar o serviço para emitir." : undefined}>
                  {(p) => (
                    <Select {...p} value={f.servicoId ?? (usaNota ? DA_NOTA : "")} onChange={(ev) => ev.target.value === DA_NOTA
                      ? setF((a) => ({ ...a, servicoId: null }))
                      : escolherServico(servicos.data?.find((s) => s.id === Number(ev.target.value)))}>
                      {!f.servicoId && !usaNota && <option value="">Escolha o serviço…</option>}
                      {f.servicoNota && (
                        <option value={DA_NOTA}>Da nota original · {f.servicoNota.ctribnac_formatado ?? f.servicoNota.ctribnac}</option>
                      )}
                      {servicos.data?.map((s) => <option key={s.id} value={s.id}>{s.ctribnac_formatado} · {s.descricao.slice(0, 90)}</option>)}
                    </Select>
                  )}
                </Campo>
                {codigosAtuais && (
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs text-texto-2">
                      Item <span className="font-mono">{codigosAtuais.ctribnac_formatado ?? codigosAtuais.ctribnac}</span>
                      {codigosAtuais.ctribnac_descricao && <> · {codigosAtuais.ctribnac_descricao}</>}
                      {" "}· NBS <span className="font-mono">{codigosAtuais.cnbs_formatado ?? codigosAtuais.cnbs}</span>
                      {codigosAtuais.ctribmun && <> · Municipal <span className="font-mono">{codigosAtuais.ctribmun}</span></>}
                      {codigosAtuais.cclasstrib && <> · cClassTrib <span className="font-mono">{codigosAtuais.cclasstrib}</span></>}
                    </p>
                    {usaNota && !modoRec && (
                      <Button type="button" tamanho="pequeno" variante="fantasma" onClick={() => setNovoServico(true)}>
                        <Save /> Salvar como serviço
                      </Button>
                    )}
                    {servicoAtual && (
                      <Button type="button" tamanho="pequeno" variante="fantasma" onClick={() => setEditarServico(true)}>
                        <Pencil /> Editar serviço
                      </Button>
                    )}
                  </div>
                )}
                {mostraIbs && codigosAtuais && (
                  <div className="rounded-xl border border-borda p-3">
                    <p className="mb-2 text-xs text-texto-2">
                      IBS/CBS desta nota. {f.servicoId ? "Mude aqui só para esta nota; para todas, edite o serviço." : "Vieram da nota original."}
                    </p>
                    <CamposIbsCbs ctribnac={codigosAtuais.ctribnac} cnbs={codigosAtuais.cnbs} obrigatorio
                      cindop={f.cindop} cclasstrib={f.cclasstrib}
                      padraoCindop={f.servicoId ? codigosAtuais.cindop : null} padraoCclasstrib={f.servicoId ? codigosAtuais.cclasstrib : null}
                      aoMudar={(c) => setF((a) => ({ ...a, ...c }))} />
                  </div>
                )}
                <Campo rotulo="Descrição nesta nota" obrigatorio
                  ajuda={modoRec ? "Use as variáveis abaixo para o texto mudar a cada mês." : "Pode ajustar só para esta nota (mês de referência, contrato…). O cadastro do serviço não muda."}>
                  {(p) => <textarea {...p} rows={3} maxLength={2000} value={f.descricao} onChange={(ev) => setF({ ...f, descricao: ev.target.value })} className={CLASSE_TEXTO} />}
                </Campo>
                <Campo rotulo="Local da prestação (código IBGE)" className="max-w-xs"
                  ajuda={`Em branco: município da empresa${empresa.config?.cod_municipio ? ` (${empresa.config.cod_municipio})` : ""}.`}>
                  {(p) => <Input {...p} value={f.localPrestacao} inputMode="numeric" maxLength={7} placeholder={empresa.config?.cod_municipio ?? ""}
                    onChange={(ev) => setF({ ...f, localPrestacao: apenasDigitos(ev.target.value) })} />}
                </Campo>
                {modoRec && (
                  <div>
                    <p className="mb-1.5 text-xs font-medium text-texto-2">Variáveis (clique para inserir na descrição)</p>
                    <div className="flex flex-wrap gap-1.5">
                      {VARIAVEIS.map((v) => (
                        <button key={v.nome} type="button" onClick={() => inserirVariavel(v.nome)} title={v.descricao}
                          className="rounded-md border border-borda bg-superficie-2 px-2 py-1 font-mono text-xs text-texto hover:border-destaque hover:text-destaque">
                          {`{${v.nome}}`}
                        </button>
                      ))}
                    </div>
                    {proxima && f.descricao && (
                      <p className="mt-2 rounded-lg bg-superficie-2 px-3 py-2 text-sm">
                        <span className="text-texto-2">Na emissão de {dataBR(proxima)}: </span>{aplicarVariaveis(f.descricao, proxima)}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
        </Secao>

        <Secao n={++n} titulo="Valores e retenções">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {!modoRec && (
              <Campo rotulo="Competência" obrigatorio ajuda="Data em que o serviço foi prestado.">
                {(p) => <Input {...p} type="date" value={f.competencia} max={hoje()} onChange={(ev) => setF({ ...f, competencia: ev.target.value })} />}
              </Campo>
            )}
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
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
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
        </Secao>

        <Secao n={++n} titulo="Informações complementares">
          <Campo rotulo="Texto livre" ajuda="Opcional. Aparece no DANFSe, antes dos textos marcados abaixo.">
            {(p) => <textarea {...p} rows={2} maxLength={1700} value={f.info} onChange={(ev) => setF({ ...f, info: ev.target.value })} className={CLASSE_TEXTO} />}
          </Campo>
          <div className="mt-4 space-y-3">
            {cfg?.texto_fixo ? (
              <TextoLegal marcado={f.textoFixo} aoMudar={(v) => setF({ ...f, textoFixo: v })} titulo="Texto fixo da empresa" texto={cfg.texto_fixo} />
            ) : (
              <p className="text-xs text-texto-2">
                Dados bancários ou observações que vão em toda nota? Cadastre o texto fixo em{" "}
                <Link to={`/emissor/empresas/${empresa.id}?empresa=${empresa.id}`} className="text-destaque hover:underline">Dados do prestador</Link>.
              </p>
            )}
            {simples && (
              <TextoLegal marcado={f.textoSimples} aoMudar={(v) => setF({ ...f, textoSimples: v })} titulo="Texto do Simples Nacional" texto={TEXTO_SIMPLES} />
            )}
            <TextoLegal marcado={f.textoProcon} aoMudar={(v) => setF({ ...f, textoProcon: v })} titulo="Informações do PROCON-DF" texto={TEXTO_PROCON} />
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
          {salvarRecorrencia.isError && <div className="mt-3"><Aviso tom="erro">{(salvarRecorrencia.error as Error).message}</Aviso></div>}
          {modoRec ? (
            <Button variante="primario" className="mt-4 w-full" disabled={salvarRecorrencia.isPending} onClick={() => setRevisar(true)}>
              <Repeat /> Salvar recorrência
            </Button>
          ) : (
            <>
              <Button variante="primario" className="mt-4 w-full" disabled={emitir.isPending} onClick={() => setRevisar(true)}>
                {nota ? <><RotateCcw /> Revisar e reenviar</> : substituir ? <><Send /> Revisar e substituir</> : <><Send /> Revisar e emitir</>}
              </Button>
              <Button className="mt-2 w-full" disabled={validar.isPending} onClick={() => validar.mutate()}>
                {validar.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />} {guardaRascunho ? "Validar e salvar rascunho" : "Validar nota"}
              </Button>
              {!nota && !substituir && (
                <Button className="mt-2 w-full" disabled={salvarRascunho.isPending} onClick={() => salvarRascunho.mutate()}>
                  {salvarRascunho.isPending ? <Loader2 className="animate-spin" /> : <Save />} {rascunho ? "Atualizar rascunho" : "Salvar rascunho"}
                </Button>
              )}
              <Button className="mt-2 w-full" variante="fantasma" disabled={previa.isPending} onClick={() => previa.mutate()}>
                {previa.isPending ? <><Loader2 className="animate-spin" /> Gerando a prévia…</> : <><FileSearch /> Ver prévia em PDF</>}
              </Button>
            </>
          )}
          {producao
            ? <p className="mt-2 text-center text-xs font-medium text-rejeitada">Produção: {modoRec ? "as notas terão" : "a nota terá"} valor fiscal.</p>
            : <p className="mt-2 text-center text-xs text-texto-2">Homologação: sem valor fiscal.</p>}
        </Painel>
      </aside>

      <Dialog open={revisar} onOpenChange={(v) => !emitir.isPending && !salvarRecorrencia.isPending && setRevisar(v)}>
        <DialogContent titulo={modoRec ? "Salvar a recorrência?" : nota ? "Reenviar a nota?" : substituir ? "Emitir a nota substituta?" : "Emitir a nota?"}
          descricao={modoRec
            ? (producao ? `Produção: todo mês, no dia ${diaRec}, uma nota com valor fiscal será emitida sem nova confirmação.` : `Homologação: todo mês, no dia ${diaRec}, uma nota de teste será emitida.`)
            : producao ? "Produção: a nota terá valor fiscal. Confira antes de emitir." : "Ambiente de homologação: a nota não tem valor fiscal."}>
          <dl className="space-y-1.5 text-sm">
            {substituir && !nota && <Linha rotulo="Substitui" valor={`NFS-e nº ${substituir.numero_nfse ?? "-"} (será cancelada)`} />}
            <Linha rotulo="Prestador" valor={`${empresa.razao_social} (${formatarDoc(empresa.cnpj)})`} />
            <Linha rotulo="Tomador" valor={f.semTomador ? "Sem tomador" : exterior
              ? `${t.nome} (${t.pais}${t.nif ? ` · NIF ${t.nif}` : " · sem NIF"})` : `${t.nome} (${formatarDoc(doc)})`} />
            {exterior && <Linha rotulo="Comércio exterior" valor={`${f.comex.valorMoeda || "-"} (moeda ${comexCorpo(f.comex).moeda})${f.comex.exportacao ? " · exportação" : ""}`} />}
            {modoRec
              ? <Linha rotulo="Próxima emissão" valor={proxima && rec?.ativa ? dataBR(proxima) : "Pausada"} />
              : <Linha rotulo="Competência" valor={f.competencia.split("-").reverse().join("/")} />}
            <Linha rotulo="Valor" valor={moeda(valor)} />
            <Linha rotulo="ISS" valor={f.issRetido ? "Retido pelo tomador" : "Não retido"} />
            {mostraIbs && <Linha rotulo="IBS/CBS" valor={`cIndOp ${cindopFinal || "-"} · cClassTrib ${cclasstribFinal || "-"}`} />}
            {federais > 0 && <Linha rotulo="Retenções federais" valor={moeda(federais)} />}
          </dl>
          {problemas.length > 0 && (
            <div className="mt-3">
              <Aviso tom="alerta">
                <strong>Confira antes de enviar:</strong>
                <ul className="mt-1 list-disc space-y-0.5 pl-5">{problemas.map((x) => <li key={x}>{x}</li>)}</ul>
                Você pode enviar mesmo assim: a Sefin valida a nota e o resultado aparece aqui.
              </Aviso>
            </div>
          )}
          {emitir.isError && <div className="mt-3"><Aviso tom="erro">{(emitir.error as Error).message}</Aviso></div>}
          {salvarRecorrencia.isError && <div className="mt-3"><Aviso tom="erro">{(salvarRecorrencia.error as Error).message}</Aviso></div>}
          {modoRec && proxima && (
            <p className="mt-3 rounded-lg bg-superficie-2 px-3 py-2 text-sm">{aplicarVariaveis(f.descricao, proxima)}</p>
          )}
          <div className="mt-5 flex justify-end gap-2">
            <Button variante="fantasma" onClick={() => setRevisar(false)} disabled={emitir.isPending || salvarRecorrencia.isPending}>Voltar</Button>
            {modoRec ? (
              <Button variante="primario" onClick={() => salvarRecorrencia.mutate()} disabled={salvarRecorrencia.isPending}>
                {salvarRecorrencia.isPending && <Loader2 className="animate-spin" />} Salvar recorrência
              </Button>
            ) : (
              <Button variante="primario" onClick={() => emitir.mutate()} disabled={emitir.isPending}>
                {emitir.isPending ? <><Loader2 className="animate-spin" /> Enviando à Sefin…</> : nota ? "Reenviar agora" : "Emitir agora"}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <ValidacaoDialog aberto={validacaoAberta} aoFechar={() => setValidacaoAberta(false)} carregando={validar.isPending}
        erro={validar.isError ? (validar.error as Error).message : null} resultado={validar.data ?? null} salvaEmRascunho={guardaRascunho}
        acoes={<>
          <Button variante="fantasma" onClick={() => setValidacaoAberta(false)} disabled={validar.isPending}>Fechar</Button>
          {validar.data?.pronta && !modoRec && (
            <Button variante="primario" onClick={() => { setValidacaoAberta(false); setRevisar(true); }}><Send /> Revisar e emitir</Button>
          )}
        </>} />
      <ServicoDialog empresaId={empresa.id} servico={null} aberto={novoServico} canal={empresa.canal}
        exigeIbsCbs={!!empresa.config?.exige_ibscbs} aoFechar={() => setNovoServico(false)}
        modelo={usaNota && f.servicoNota ? { ...f.servicoNota, descricao: f.descricao } : null}
        aoSalvar={(s) => setF((a) => ({ ...a, servicoId: s.id, descricao: usaNota ? a.descricao : s.descricao }))} />
      <ServicoDialog empresaId={empresa.id} servico={servicoAtual} aberto={editarServico && !!servicoAtual} canal={empresa.canal}
        exigeIbsCbs={!!empresa.config?.exige_ibscbs} aoFechar={() => setEditarServico(false)} />
    </div>
  );
}

function TextoLegal({ marcado, aoMudar, titulo, texto }: { marcado: boolean; aoMudar: (v: boolean) => void; titulo: string; texto: string }) {
  return (
    <label className={cn("flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors duration-150",
      marcado ? "border-destaque/40 bg-destaque-suave/40" : "border-borda")}>
      <input type="checkbox" className="mt-0.5 size-4 accent-destaque" checked={marcado} onChange={(ev) => aoMudar(ev.target.checked)} />
      <span>
        <span className="block text-sm font-medium">{titulo}</span>
        <span className="mt-0.5 block text-xs text-texto-2">{texto}</span>
      </span>
    </label>
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

/** Tomadores do exterior já salvos: escolher preenche os campos. */
function TomadoresExterior({ escolher }: { escolher: (t: Tomador) => void }) {
  const q = useQuery({
    queryKey: ["emissor", "tomadores", "exterior"],
    queryFn: () => api<Tomador[]>("/api/emissor/tomadores?q="),
    select: (lista) => lista.filter((x) => ehExterior(x)),
  });
  if (!q.data?.length) return null;
  return (
    <Campo rotulo="Tomador do exterior já salvo" className="col-span-6">
      {(p) => (
        <Select {...p} value="" onChange={(ev) => { const x = q.data!.find((t) => String(t.id) === ev.target.value); if (x) escolher(x); }}>
          <option value="">Escolha para preencher, ou digite abaixo…</option>
          {q.data.map((t) => <option key={t.id} value={t.id}>{t.nome} · {t.pais}{t.nif ? ` · ${t.nif}` : ""}</option>)}
        </Select>
      )}
    </Campo>
  );
}
