import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, BadgeCheck, Building2, Lock, Pause, Pencil, Play, Plus, Repeat, Trash2 } from "lucide-react";
import { useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso } from "@/components/ui/campos";
import { api } from "@/lib/api";
import {
  lerValor, useAtualizarEmissor, useEmpresasEmissoras, useRecorrentes,
  type CorpoEmissao, type EmpresaEmissora, type ModeloAdn, type NotaEmitida, type Recorrente,
} from "@/lib/emissor";
import { nomeExibicao, useEmpresaSelecionada } from "@/lib/empresas";
import { useTesteGratis } from "@/lib/sessao";
import { formatarDoc } from "@/lib/formato";
import { moeda } from "@/lib/notas";
import { cn } from "@/lib/utils";
import { AbasEmissor } from "./Abas";
import { Formulario, daNota, doCorpo, vazio, type DadosRecorrencia } from "./EmitirNota";
import { SeloEmitida } from "./NotasEmitidas";

const dataBR = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

function useEmpresaEmissoraSelecionada() {
  const { empresa: selecionada, carregando } = useEmpresaSelecionada();
  const empresas = useEmpresasEmissoras();
  const empresa = empresas.data?.find((e) => e.id === selecionada?.id) ?? null;
  return { selecionada, empresa, carregando: carregando || empresas.isLoading, erro: empresas.error as Error | null, refetch: empresas.refetch };
}

function SemEmissora({ selecionada }: { selecionada: { id: number } | null }) {
  return selecionada ? (
    <EstadoVazio icone={Building2} titulo="A empresa selecionada não emite NFS-e pelo Contask"
      acao={<Button variante="primario" asChild><Link to={`/emissor/empresas/${selecionada.id}?empresa=${selecionada.id}`}>Configurar emissão</Link></Button>}>
      Escolha outra empresa no topo da página ou marque esta como emissora.
    </EstadoVazio>
  ) : <EstadoVazio icone={Building2} titulo="Escolha uma empresa">Selecione a empresa no topo da página.</EstadoVazio>;
}

export function Recorrentes() {
  const { selecionada, empresa, carregando, erro, refetch } = useEmpresaEmissoraSelecionada();
  const { emTeste } = useTesteGratis();
  const pronta = !!empresa?.emite_nfse && !emTeste;
  const lista = useRecorrentes(pronta ? empresa!.id : null);
  const nova = `/emissor/recorrentes/nova?empresa=${empresa?.id ?? ""}`;

  return (
    <>
      <Cabecalho titulo="Emissor de NFS-e" descricao="Notas recorrentes: emitidas sozinhas todo mês, no dia escolhido."
        acoes={pronta && <Button variante="primario" asChild><Link to={nova}><Plus /> Nova recorrência</Link></Button>} />
      <AbasEmissor />
      {carregando && <Esqueleto className="h-64 w-full" />}
      {erro && <EstadoErro mensagem={erro.message} tentarDeNovo={() => refetch()} />}
      {!carregando && !erro && emTeste && (
        <EstadoVazio icone={Lock} titulo="Notas recorrentes estão no plano">
          No teste grátis dá para emitir uma nota para conhecer o emissor. As notas que saem sozinhas todo mês ficam liberadas ao assinar o plano: fale com o suporte do Contask NF.
        </EstadoVazio>
      )}
      {!carregando && !erro && !emTeste && !pronta && <SemEmissora selecionada={selecionada} />}
      {pronta && (
        <>
          {lista.isLoading && <Esqueleto className="h-48 w-full" />}
          {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
          {lista.data?.length === 0 && (
            <EstadoVazio icone={Repeat} titulo={`${nomeExibicao(empresa!)} não tem notas recorrentes`}
              acao={<Button variante="primario" asChild><Link to={nova}><Plus /> Criar a primeira</Link></Button>}>
              Cadastre uma vez a nota que se repete (honorários, mensalidade…) e o Contask emite todo mês no dia escolhido.
              A descrição pode usar variáveis como {"{mes_anterior}"}.
            </EstadoVazio>
          )}
          {lista.data && lista.data.length > 0 && (
            <ul className="space-y-3">
              {lista.data.map((r) => <Item key={r.id} r={r} empresa={empresa!} />)}
            </ul>
          )}
          <p className="mt-4 text-xs text-texto-2">
            A emissão automática acontece a partir das 7h do dia, com o Contask aberto. Se o sistema estiver desligado o mês todo, a nota daquele mês não sai em atraso.
          </p>
        </>
      )}
    </>
  );
}

function corpoParaPausa(r: Recorrente, ativa: boolean) {
  return JSON.stringify({ empresa_id: r.empresa_id, nome: r.nome, dia: r.dia, competencia: r.competencia, ativa, dados: r.dados });
}

function Item({ r, empresa }: { r: Recorrente; empresa: EmpresaEmissora }) {
  const atualizar = useAtualizarEmissor();
  const pausar = useMutation({
    mutationFn: () => api<Recorrente>(`/api/emissor/recorrentes/${r.id}`, { method: "PUT", body: corpoParaPausa(r, !r.ativa) }),
    onSuccess: (x) => { atualizar(); toast.success(x.ativa ? "Recorrência reativada." : "Recorrência pausada."); },
    onError: (err) => toast.error((err as Error).message),
  });
  const excluir = useMutation({
    mutationFn: () => api<void>(`/api/emissor/recorrentes/${r.id}`, { method: "DELETE" }),
    onSuccess: () => { atualizar(); toast.success("Recorrência excluída. As notas já emitidas continuam na lista."); },
    onError: (err) => toast.error((err as Error).message),
  });
  const valor = r.valor ? lerValor(r.valor) : NaN;

  return (
    <li className={cn("rounded-xl border border-borda bg-superficie p-4", !r.ativa && "opacity-70")}>
      <div className="flex flex-wrap items-start gap-4">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-destaque-suave text-destaque"><Repeat className="size-4" aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-medium">{r.nome}</h2>
            {r.ativa ? <Selo tom="ok" icone={BadgeCheck}>Ativa</Selo> : <Selo tom="neutro" icone={Pause}>Pausada</Selo>}
          </div>
          <p className="mt-0.5 text-sm text-texto-2">
            {r.tomador_nome ?? "Sem tomador"}{r.tomador_documento && <> · <span className="font-mono">{formatarDoc(r.tomador_documento)}</span></>}
            {!isNaN(valor) && <> · <span className="font-mono text-texto">{moeda(valor)}</span></>}
          </p>
          <p className="mt-1 text-sm text-texto-2">
            Todo dia <strong className="text-texto">{r.dia}</strong>{r.dia > 28 && " (ou o último dia do mês)"} · competência {r.competencia === "anterior" ? "no último dia do mês anterior" : "no dia da emissão"}
            {r.ativa && r.proxima_em && <> · próxima em <strong className="text-texto">{dataBR(r.proxima_em)}</strong></>}
          </p>
          {r.previa && r.ativa && (
            <p className="mt-2 rounded-lg bg-superficie-2 px-3 py-2 text-sm"><span className="text-texto-2">Descrição na próxima: </span>{r.previa.descricao}</p>
          )}
          {r.ultima_nota && (
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-texto-2">
              Última: {r.ultima_nota.numero_nfse ? <span className="font-mono">NFS-e nº {r.ultima_nota.numero_nfse}</span> : "nota sem número"}
              {r.ultima_em && <> em {new Date(r.ultima_em).toLocaleDateString("pt-BR")}</>}
              <SeloEmitida n={r.ultima_nota} />
            </div>
          )}
          {r.ultimo_erro && (
            <div className="mt-2"><Aviso tom="alerta"><span className="inline-flex gap-1.5"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />{r.ultimo_erro}</span></Aviso></div>
          )}
        </div>
        <div className="flex shrink-0 gap-1">
          <Button tamanho="pequeno" asChild><Link to={`/emissor/recorrentes/${r.id}?empresa=${empresa.id}`}><Pencil /> Editar</Link></Button>
          <Button tamanho="icone" variante="fantasma" aria-label={r.ativa ? "Pausar" : "Reativar"} disabled={pausar.isPending} onClick={() => pausar.mutate()}>
            {r.ativa ? <Pause /> : <Play />}
          </Button>
          <Button tamanho="icone" variante="fantasma" aria-label="Excluir recorrência" disabled={excluir.isPending}
            onClick={() => { if (window.confirm(`Excluir a recorrência "${r.nome}"? As notas já emitidas não são afetadas.`)) excluir.mutate(); }}><Trash2 /></Button>
        </div>
      </div>
    </li>
  );
}

/** Nova recorrência (em branco ou a partir de uma nota) e edição. */
export function EditarRecorrente() {
  const id = Number(useParams().id) || null;
  const [params] = useSearchParams();
  const duplicar = Number(params.get("duplicar")) || null;
  const duplicarAdn = Number(params.get("duplicar_adn")) || null;
  const { selecionada, empresa: daSelecao, carregando, erro, refetch } = useEmpresaEmissoraSelecionada();
  const empresas = useEmpresasEmissoras();

  const existente = useQuery({
    queryKey: ["emissor", "recorrente", id],
    queryFn: async () => (await api<Recorrente[]>(`/api/emissor/empresas/${selecionada!.id}/recorrentes`)).find((r) => r.id === id) ?? null,
    enabled: id !== null && !!selecionada,
  });
  const nota = useQuery({
    queryKey: ["emissor", "nota", duplicar],
    queryFn: () => api<NotaEmitida>(`/api/emissor/notas/${duplicar}`),
    enabled: duplicar !== null,
  });
  const modelo = useQuery({
    queryKey: ["emissor", "modelo-adn", selecionada?.id, duplicarAdn],
    queryFn: () => api<ModeloAdn>(`/api/emissor/empresas/${selecionada!.id}/notas/adn/${duplicarAdn}/modelo`),
    enabled: duplicarAdn !== null && !!selecionada,
  });

  const empresaId = existente.data?.empresa_id ?? nota.data?.empresa_id ?? daSelecao?.id ?? null;
  const empresa = empresas.data?.find((e) => e.id === empresaId) ?? null;
  const fontes = [existente, nota, modelo];
  const carregandoFonte = fontes.some((q) => q.isLoading);
  const erroFonte = fontes.find((q) => q.isError);

  const inicial = useMemo(() => {
    if (existente.data) return doCorpo(existente.data.dados as CorpoEmissao);
    if (nota.data) return daNota(nota.data, true);
    if (modelo.data) return daNota(modelo.data, true);
    return vazio();
  }, [existente.data, nota.data, modelo.data]);
  const dados: DadosRecorrencia = existente.data
    ? { nome: existente.data.nome, dia: String(existente.data.dia), competencia: existente.data.competencia, ativa: existente.data.ativa }
    : { nome: "", dia: String(new Date().getDate()), competencia: "atual", ativa: true };

  return (
    <>
      <Link to={`/emissor/recorrentes?empresa=${empresaId ?? ""}`} className="mb-3 inline-flex items-center gap-1.5 text-sm text-texto-2 hover:text-texto">
        <ArrowLeft className="size-4" aria-hidden /> Notas recorrentes
      </Link>
      <Cabecalho titulo={id ? "Editar recorrência" : "Nova recorrência"}
        descricao="A nota é emitida sozinha todo mês no dia escolhido, com a descrição montada pelas variáveis." />
      <AbasEmissor empresaId={empresaId} />
      {(carregando || carregandoFonte) && <Esqueleto className="h-96 w-full" />}
      {erro && <EstadoErro mensagem={erro.message} tentarDeNovo={() => refetch()} />}
      {erroFonte && <EstadoErro mensagem={(erroFonte.error as Error).message} />}
      {id && existente.data === null && <EstadoErro mensagem="Recorrência não encontrada para a empresa selecionada." />}
      {!carregando && !carregandoFonte && !erro && !erroFonte && (!id || existente.data) && (
        !empresa || !empresa.emite_nfse ? <SemEmissora selecionada={selecionada} /> : (
          <Formulario key={`${id}-${duplicar}-${duplicarAdn}-${empresa.id}`} empresa={empresa} inicial={inicial}
            servicoOriginal={modelo.data && !modelo.data.servico_id ? modelo.data : null}
            recorrencia={{ dados, existente: existente.data ?? null }} />
        )
      )}
    </>
  );
}
