import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, BadgeCheck, Ban, Building2, CircleDollarSign, FlaskConical, History, KeyRound, Loader2, Pencil, Play, Plus,
  ShieldCheck, UserPlus, UserRoundCheck, UserRoundX,
} from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { Copiar } from "@/components/Copiar";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input, Select } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { formatarDataHora } from "@/lib/formato";
import { moeda } from "@/lib/notas";
import { useSessao } from "@/lib/sessao";
import { cn } from "@/lib/utils";

interface UsuarioAdm {
  id: number;
  escritorio_id: number;
  email: string;
  nome: string;
  ativo: boolean;
  trocar_senha: boolean;
  admin_sistema: boolean;
  criado_em: string;
  ultimo_acesso_em: string | null;
}
type Situacao = "teste" | "ativo" | "suspenso";
interface EscritorioAdm {
  id: number;
  nome: string;
  empresas: number;
  usuarios: UsuarioAdm[];
  situacao: Situacao;
  teste_ate: string | null;
  /** motivo do bloqueio (suspenso ou teste vencido); null = acesso liberado */
  bloqueio: string | null;
  limite_xmls_mes: number | null;
  limite_efetivo: number;
  xmls_no_mes: number;
  mensalidade: number | null;
  dia_vencimento: number | null;
  proximo_vencimento: string | null;
  dias_atraso: number;
  observacoes: string | null;
  criado_em: string | null;
}
interface ComSenha { usuario: UsuarioAdm; senha_inicial: string }
interface Evento { id: number; momento: string; tipo: string; descricao: string; valor: number | null; por: string | null }

const CHAVE = ["admin", "escritorios"];
const dataBR = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

function SeloSituacao({ e }: { e: EscritorioAdm }) {
  if (e.situacao === "suspenso") return <Selo tom="erro" icone={Ban}>Suspenso</Selo>;
  if (e.situacao === "teste") {
    return e.bloqueio ? <Selo tom="erro" icone={FlaskConical}>Teste encerrado</Selo>
      : <Selo tom="destaque" icone={FlaskConical}>Em teste{e.teste_ate ? ` até ${dataBR(e.teste_ate)}` : ""}</Selo>;
  }
  return e.dias_atraso > 0
    ? <Selo tom="alerta" icone={AlertTriangle}>Atrasado há {e.dias_atraso} dia{e.dias_atraso === 1 ? "" : "s"}</Selo>
    : <Selo tom="ok" icone={BadgeCheck}>Ativo</Selo>;
}

/** Painel do suporte do Contask: escritórios, usuários, situação e mensalidade. Não mostra dados fiscais. */
export function Administracao() {
  const sessao = useSessao();
  const admin = !!sessao.data?.usuario?.admin_sistema;
  const lista = useQuery({ queryKey: CHAVE, queryFn: () => api<EscritorioAdm[]>("/api/admin/escritorios"), enabled: admin });
  const [novoEsc, setNovoEsc] = useState(false);
  const [novoUsu, setNovoUsu] = useState<EscritorioAdm | null>(null);
  const [plano, setPlano] = useState<EscritorioAdm | null>(null);
  const [pagamento, setPagamento] = useState<EscritorioAdm | null>(null);
  const [historico, setHistorico] = useState<EscritorioAdm | null>(null);
  const [senha, setSenha] = useState<ComSenha | null>(null);

  if (sessao.isLoading) return <Esqueleto className="h-64 w-full" />;
  if (!admin) {
    return <EstadoVazio icone={ShieldCheck} titulo="Área restrita">Só o administrador do sistema acessa esta página.</EstadoVazio>;
  }

  const d = lista.data ?? [];
  const conta = (f: (e: EscritorioAdm) => boolean) => d.filter(f).length;
  const receita = d.filter((e) => e.situacao === "ativo").reduce((s, e) => s + (e.mensalidade ?? 0), 0);
  // Quem pede atenção primeiro: atrasados, testes vencidos, depois o resto
  const ordenada = [...d].sort((a, b) => (b.dias_atraso - a.dias_atraso) || (Number(!!b.bloqueio && b.situacao === "teste") - Number(!!a.bloqueio && a.situacao === "teste")) || a.nome.localeCompare(b.nome));

  return (
    <>
      <Cabecalho titulo="Administração" descricao="Escritórios, usuários, situação e mensalidade. A senha inicial aparece uma única vez: envie por um canal privado."
        acoes={<Button variante="primario" onClick={() => setNovoEsc(true)}><Plus /> Novo escritório</Button>} />
      {lista.isLoading && <Esqueleto className="h-64 w-full" />}
      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.data?.length === 0 && (
        <EstadoVazio icone={Building2} titulo="Nenhum escritório" acao={<Button variante="primario" onClick={() => setNovoEsc(true)}><Plus /> Criar o primeiro</Button>}>
          Crie o escritório e o primeiro usuário dele.
        </EstadoVazio>
      )}
      {d.length > 0 && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Indicador rotulo="Ativos" valor={conta((e) => e.situacao === "ativo")} />
            <Indicador rotulo="Em teste" valor={conta((e) => e.situacao === "teste")} />
            <Indicador rotulo="Em atraso" valor={conta((e) => e.dias_atraso > 0)} alerta={conta((e) => e.dias_atraso > 0) > 0} />
            <Indicador rotulo="Suspensos" valor={conta((e) => e.situacao === "suspenso")} />
            <Indicador rotulo="Mensalidades (ativos)" valor={moeda(receita)} />
          </div>
          <ul className="space-y-3">
            {ordenada.map((e) => (
              <CartaoEscritorio key={e.id} e={e} euId={sessao.data?.usuario?.id} aoSenha={setSenha} aoNovoUsuario={() => setNovoUsu(e)}
                aoPlano={() => setPlano(e)} aoPagamento={() => setPagamento(e)} aoHistorico={() => setHistorico(e)} />
            ))}
          </ul>
        </>
      )}
      <NovoEscritorio aberto={novoEsc} aoFechar={() => setNovoEsc(false)} aoCriar={setSenha} />
      <NovoUsuario escritorio={novoUsu} aoFechar={() => setNovoUsu(null)} aoCriar={setSenha} />
      <PlanoDialog escritorio={plano} aoFechar={() => setPlano(null)} />
      <PagamentoDialog escritorio={pagamento} aoFechar={() => setPagamento(null)} />
      <HistoricoDialog escritorio={historico} aoFechar={() => setHistorico(null)} />
      <SenhaInicial dados={senha} aoFechar={() => setSenha(null)} />
    </>
  );
}

function Indicador({ rotulo, valor, alerta }: { rotulo: string; valor: ReactNode; alerta?: boolean }) {
  return (
    <div className={cn("rounded-xl border bg-superficie px-4 py-3", alerta ? "border-rejeitada/40" : "border-borda")}>
      <p className="text-xs text-texto-2">{rotulo}</p>
      <p className={cn("mt-0.5 font-mono text-lg font-semibold tabular-nums", alerta && "text-rejeitada")}>{valor}</p>
    </div>
  );
}

function corpoPlano(e: EscritorioAdm, situacao: Situacao = e.situacao) {
  return {
    nome: e.nome, situacao, teste_ate: e.teste_ate, limite_xmls_mes: e.limite_xmls_mes,
    mensalidade: e.mensalidade, dia_vencimento: e.dia_vencimento, proximo_vencimento: e.proximo_vencimento, observacoes: e.observacoes,
  };
}

function CartaoEscritorio({ e, euId, aoSenha, aoNovoUsuario, aoPlano, aoPagamento, aoHistorico }: {
  e: EscritorioAdm; euId?: number; aoSenha: (s: ComSenha) => void; aoNovoUsuario: () => void;
  aoPlano: () => void; aoPagamento: () => void; aoHistorico: () => void;
}) {
  const qc = useQueryClient();
  const temAdmin = e.usuarios.some((u) => u.admin_sistema);
  const mudar = useMutation({
    mutationFn: (s: Situacao) => api<EscritorioAdm>(`/api/admin/escritorios/${e.id}`, { method: "PUT", body: JSON.stringify(corpoPlano(e, s)) }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: CHAVE });
      toast.success(r.situacao === "suspenso" ? `${r.nome} suspenso: ninguém do escritório entra e as buscas param.` : `${r.nome} reativado.`);
    },
    onError: (err) => toast.error((err as Error).message),
  });
  const pct = e.limite_efetivo > 0 ? Math.min(100, Math.round((e.xmls_no_mes / e.limite_efetivo) * 100)) : null;

  return (
    <li className={cn("rounded-xl border bg-superficie", e.situacao === "suspenso" ? "border-cancelada/40" : "border-borda")}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-borda px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-medium">{e.nome}</h2>
            <SeloSituacao e={e} />
          </div>
          <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-texto-2">
            <span>{e.empresas} empresa(s)</span>
            <span>XMLs no mês: <span className="font-mono">{e.xmls_no_mes}{e.limite_efetivo > 0 ? ` / ${e.limite_efetivo}` : ""}</span>{pct !== null && ` (${pct}%)`}</span>
            <span>Mensalidade: {e.mensalidade !== null ? moeda(e.mensalidade) : "—"}</span>
            <span>Próximo vencimento: {dataBR(e.proximo_vencimento)}</span>
          </p>
          {e.observacoes && <p className="mt-1 text-xs text-texto-2">{e.observacoes}</p>}
        </div>
        <div className="flex flex-wrap gap-1">
          <Button tamanho="pequeno" onClick={aoPagamento}><CircleDollarSign /> Pagamento</Button>
          <Button tamanho="pequeno" variante="fantasma" onClick={aoPlano}><Pencil /> Plano</Button>
          <Button tamanho="pequeno" variante="fantasma" onClick={aoHistorico}><History /> Histórico</Button>
          {!temAdmin && (e.situacao === "suspenso" ? (
            <Button tamanho="pequeno" variante="fantasma" disabled={mudar.isPending} onClick={() => mudar.mutate("ativo")}><Play /> Reativar</Button>
          ) : (
            <Button tamanho="pequeno" variante="fantasma" disabled={mudar.isPending} className="text-cancelada"
              onClick={() => { if (window.confirm(`Suspender ${e.nome}? Ninguém do escritório entra e as buscas e notas recorrentes param até reativar. Nada é apagado.`)) mudar.mutate("suspenso"); }}>
              <Ban /> Suspender
            </Button>
          ))}
          <Button tamanho="pequeno" variante="fantasma" onClick={aoNovoUsuario}><UserPlus /> Usuário</Button>
        </div>
      </div>
      {e.usuarios.length === 0 ? <p className="px-4 py-3 text-sm text-texto-2">Sem usuários.</p> : (
        <ul className="divide-y divide-borda">
          {e.usuarios.map((u) => <LinhaUsuario key={u.id} u={u} eu={u.id === euId} aoSenha={aoSenha} />)}
        </ul>
      )}
    </li>
  );
}

function LinhaUsuario({ u, eu, aoSenha }: { u: UsuarioAdm; eu: boolean; aoSenha: (s: ComSenha) => void }) {
  const qc = useQueryClient();
  const atualizar = () => qc.invalidateQueries({ queryKey: CHAVE });
  const senha = useMutation({
    mutationFn: () => api<ComSenha>(`/api/admin/usuarios/${u.id}/senha`, { method: "POST" }),
    onSuccess: (r) => { atualizar(); aoSenha(r); },
    onError: (err) => toast.error((err as Error).message),
  });
  const ativo = useMutation({
    mutationFn: () => api<UsuarioAdm>(`/api/admin/usuarios/${u.id}/ativo`, { method: "PUT", body: JSON.stringify({ ativo: !u.ativo }) }),
    onSuccess: (r) => { atualizar(); toast.success(r.ativo ? "Acesso reativado." : "Acesso desativado: a pessoa saiu do sistema."); },
    onError: (err) => toast.error((err as Error).message),
  });
  return (
    <li className={cn("flex flex-wrap items-center gap-3 px-4 py-2.5", !u.ativo && "opacity-60")}>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {u.nome || u.email}
          {u.admin_sistema && <Selo tom="destaque" icone={ShieldCheck}>Admin</Selo>}
          {!u.ativo && <Selo tom="erro" icone={UserRoundX}>Desativado</Selo>}
          {u.ativo && u.trocar_senha && <Selo tom="alerta" icone={KeyRound}>Senha inicial</Selo>}
        </p>
        <p className="text-xs text-texto-2">{u.email} · último acesso: {u.ultimo_acesso_em ? formatarDataHora(u.ultimo_acesso_em) : "nunca"}</p>
      </div>
      {!eu && (
        <div className="flex gap-1">
          <Button tamanho="pequeno" variante="fantasma" disabled={senha.isPending}
            onClick={() => { if (window.confirm(`Gerar nova senha inicial para ${u.email}? A atual deixa de valer.`)) senha.mutate(); }}>
            {senha.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Nova senha
          </Button>
          <Button tamanho="pequeno" variante="fantasma" disabled={ativo.isPending}
            onClick={() => { if (u.ativo ? window.confirm(`Desativar o acesso de ${u.email}?`) : true) ativo.mutate(); }}>
            {u.ativo ? <><UserRoundX /> Desativar</> : <><UserRoundCheck /> Reativar</>}
          </Button>
        </div>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Campos do plano (usados na criação e na edição)
// ---------------------------------------------------------------------------

interface FormPlano {
  situacao: Situacao; teste_ate: string; limite: string; mensalidade: string; dia: string; vencimento: string; obs: string;
}

const planoVazio = (): FormPlano => ({ situacao: "ativo", teste_ate: "", limite: "", mensalidade: "", dia: "", vencimento: "", obs: "" });

function planoDe(e: EscritorioAdm): FormPlano {
  return {
    situacao: e.situacao, teste_ate: e.teste_ate ?? "", limite: e.limite_xmls_mes?.toString() ?? "",
    mensalidade: e.mensalidade !== null ? e.mensalidade.toFixed(2).replace(".", ",") : "", dia: e.dia_vencimento?.toString() ?? "",
    vencimento: e.proximo_vencimento ?? "", obs: e.observacoes ?? "",
  };
}

const numero = (s: string) => { const t = s.trim().replace(/\./g, "").replace(",", "."); return t ? Number(t) : null; };

function corpoDoForm(p: FormPlano) {
  return {
    situacao: p.situacao, teste_ate: p.situacao === "teste" && p.teste_ate ? p.teste_ate : null,
    limite_xmls_mes: p.limite.trim() ? Number(p.limite) : null, mensalidade: numero(p.mensalidade),
    dia_vencimento: p.dia.trim() ? Number(p.dia) : null, proximo_vencimento: p.vencimento || null, observacoes: p.obs.trim() || null,
  };
}

function problemasPlano(p: FormPlano): string | null {
  if (p.mensalidade.trim() && (numero(p.mensalidade) === null || isNaN(numero(p.mensalidade)!))) return "Mensalidade inválida. Use o formato 79,90.";
  if (p.dia.trim() && !(Number(p.dia) >= 1 && Number(p.dia) <= 31)) return "O dia de vencimento vai de 1 a 31.";
  if (p.limite.trim() && !(Number(p.limite) >= 0)) return "Limite de XMLs inválido.";
  return null;
}

function CamposPlano({ p, setP, comSuspenso }: { p: FormPlano; setP: (p: FormPlano) => void; comSuspenso: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <Campo rotulo="Situação">
        {(a) => (
          <Select {...a} value={p.situacao} onChange={(ev) => setP({ ...p, situacao: ev.target.value as Situacao })}>
            <option value="ativo">Ativo</option>
            <option value="teste">Em teste (1 empresa e poucos XMLs)</option>
            {comSuspenso && <option value="suspenso">Suspenso</option>}
          </Select>
        )}
      </Campo>
      {p.situacao === "teste" ? (
        <Campo rotulo="Teste até" ajuda="Depois dessa data, o acesso fica bloqueado.">
          {(a) => <Input {...a} type="date" value={p.teste_ate} onChange={(ev) => setP({ ...p, teste_ate: ev.target.value })} />}
        </Campo>
      ) : (
        <Campo rotulo="Limite de XMLs por mês" ajuda="Vazio = padrão do sistema; 0 = sem limite.">
          {(a) => <Input {...a} value={p.limite} inputMode="numeric" onChange={(ev) => setP({ ...p, limite: ev.target.value.replace(/\D/g, "") })} />}
        </Campo>
      )}
      <Campo rotulo="Mensalidade (R$)">
        {(a) => <Input {...a} value={p.mensalidade} inputMode="decimal" placeholder="79,90" className="font-mono" onChange={(ev) => setP({ ...p, mensalidade: ev.target.value })} />}
      </Campo>
      <Campo rotulo="Dia do vencimento">
        {(a) => <Input {...a} value={p.dia} inputMode="numeric" maxLength={2} onChange={(ev) => setP({ ...p, dia: ev.target.value.replace(/\D/g, "") })} />}
      </Campo>
      <Campo rotulo="Próximo vencimento" ajuda="Vazio: calculado pelo dia do vencimento." className="col-span-2 sm:col-span-1">
        {(a) => <Input {...a} type="date" value={p.vencimento} onChange={(ev) => setP({ ...p, vencimento: ev.target.value })} />}
      </Campo>
      <Campo rotulo="Observações" className="col-span-2">
        {(a) => <Input {...a} value={p.obs} maxLength={2000} placeholder="Ex.: paga por Pix, contato do financeiro…" onChange={(ev) => setP({ ...p, obs: ev.target.value })} />}
      </Campo>
    </div>
  );
}

function NovoEscritorio({ aberto, aoFechar, aoCriar }: { aberto: boolean; aoFechar: () => void; aoCriar: (s: ComSenha) => void }) {
  const qc = useQueryClient();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [pessoa, setPessoa] = useState("");
  const [p, setP] = useState<FormPlano>(planoVazio());
  const erro = problemasPlano(p);
  const criar = useMutation({
    mutationFn: () => api<ComSenha>("/api/admin/escritorios", { method: "POST", body: JSON.stringify({ nome, email, nome_usuario: pessoa, ...corpoDoForm(p) }) }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: CHAVE }); fechar(); aoCriar(r); },
  });
  const fechar = () => { setNome(""); setEmail(""); setPessoa(""); setP(planoVazio()); criar.reset(); aoFechar(); };
  const enviar = (ev: FormEvent) => { ev.preventDefault(); if (!erro) criar.mutate(); };
  return (
    <Dialog open={aberto} onOpenChange={(v) => !v && !criar.isPending && fechar()}>
      <DialogContent titulo="Novo escritório" descricao="Cria o escritório e o primeiro usuário, com senha inicial de troca obrigatória.">
        <form className="space-y-4" onSubmit={enviar}>
          <Campo rotulo="Nome do escritório" obrigatorio>{(a) => <Input {...a} value={nome} onChange={(e) => setNome(e.target.value)} autoFocus required />}</Campo>
          <div className="grid grid-cols-2 gap-3">
            <Campo rotulo="E-mail do primeiro usuário" obrigatorio>{(a) => <Input {...a} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />}</Campo>
            <Campo rotulo="Nome da pessoa">{(a) => <Input {...a} value={pessoa} onChange={(e) => setPessoa(e.target.value)} />}</Campo>
          </div>
          <CamposPlano p={p} setP={setP} comSuspenso={false} />
          {(erro || criar.isError) && <Aviso tom="erro">{erro ?? (criar.error as Error).message}</Aviso>}
          <div className="flex justify-end gap-2">
            <Button type="button" variante="fantasma" onClick={fechar} disabled={criar.isPending}>Cancelar</Button>
            <Button type="submit" variante="primario" disabled={criar.isPending || nome.trim().length < 2 || !email || !!erro}>
              {criar.isPending && <Loader2 className="animate-spin" />} Criar escritório
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PlanoDialog({ escritorio, aoFechar }: { escritorio: EscritorioAdm | null; aoFechar: () => void }) {
  return (
    <Dialog open={!!escritorio} onOpenChange={(v) => !v && aoFechar()}>
      <DialogContent titulo={`Plano de ${escritorio?.nome ?? ""}`} descricao="Situação, limite de XMLs e mensalidade. Toda mudança fica no histórico.">
        {escritorio && <FormPlanoEdicao key={escritorio.id} e={escritorio} aoFechar={aoFechar} />}
      </DialogContent>
    </Dialog>
  );
}

function FormPlanoEdicao({ e, aoFechar }: { e: EscritorioAdm; aoFechar: () => void }) {
  const qc = useQueryClient();
  const [nome, setNome] = useState(e.nome);
  const [p, setP] = useState<FormPlano>(planoDe(e));
  const erro = problemasPlano(p);
  const temAdmin = e.usuarios.some((u) => u.admin_sistema);
  const salvar = useMutation({
    mutationFn: () => api<EscritorioAdm>(`/api/admin/escritorios/${e.id}`, { method: "PUT", body: JSON.stringify({ nome, ...corpoDoForm(p) }) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: CHAVE }); toast.success("Plano salvo."); aoFechar(); },
  });
  return (
    <form className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); if (!erro) salvar.mutate(); }}>
      <Campo rotulo="Nome do escritório" obrigatorio>{(a) => <Input {...a} value={nome} onChange={(ev) => setNome(ev.target.value)} required />}</Campo>
      <CamposPlano p={p} setP={setP} comSuspenso={!temAdmin} />
      {p.situacao === "suspenso" && e.situacao !== "suspenso" && (
        <Aviso tom="alerta">Ao suspender, ninguém do escritório entra e as buscas e notas recorrentes param. Nada é apagado: ao reativar, tudo volta de onde parou.</Aviso>
      )}
      {(erro || salvar.isError) && <Aviso tom="erro">{erro ?? (salvar.error as Error).message}</Aviso>}
      <div className="flex justify-end gap-2">
        <Button type="button" variante="fantasma" onClick={aoFechar} disabled={salvar.isPending}>Cancelar</Button>
        <Button type="submit" variante="primario" disabled={salvar.isPending || nome.trim().length < 2 || !!erro}>
          {salvar.isPending && <Loader2 className="animate-spin" />} Salvar
        </Button>
      </div>
    </form>
  );
}

function PagamentoDialog({ escritorio, aoFechar }: { escritorio: EscritorioAdm | null; aoFechar: () => void }) {
  const qc = useQueryClient();
  const hoje = new Date();
  const hojeIso = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}-${String(hoje.getDate()).padStart(2, "0")}`;
  const [valor, setValor] = useState("");
  const [data, setData] = useState(hojeIso);
  const [obs, setObs] = useState("");
  const registrar = useMutation({
    mutationFn: () => api<EscritorioAdm>(`/api/admin/escritorios/${escritorio!.id}/pagamento`, {
      method: "POST", body: JSON.stringify({ valor: numero(valor), data, observacao: obs.trim() || null }),
    }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: CHAVE });
      toast.success(r.proximo_vencimento ? `Pagamento registrado. Próximo vencimento: ${dataBR(r.proximo_vencimento)}.` : "Pagamento registrado.");
      fechar();
    },
  });
  const fechar = () => { setValor(""); setData(hojeIso); setObs(""); registrar.reset(); aoFechar(); };
  const e = escritorio;
  return (
    <Dialog open={!!e} onOpenChange={(v) => !v && !registrar.isPending && fechar()}>
      <DialogContent titulo={`Registrar pagamento · ${e?.nome ?? ""}`}
        descricao={e?.proximo_vencimento ? <>Referente ao vencimento de <strong>{dataBR(e.proximo_vencimento)}</strong>. O próximo vencimento passa para o mês seguinte.</> : "Sem vencimento definido: o pagamento só fica no histórico."}>
        <form className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); registrar.mutate(); }}>
          <div className="grid grid-cols-2 gap-3">
            <Campo rotulo="Valor (R$)" ajuda={e?.mensalidade !== null && e?.mensalidade !== undefined ? `Vazio = mensalidade (${moeda(e.mensalidade)})` : undefined}>
              {(a) => <Input {...a} value={valor} inputMode="decimal" className="font-mono" onChange={(ev) => setValor(ev.target.value)} />}
            </Campo>
            <Campo rotulo="Data do pagamento">{(a) => <Input {...a} type="date" value={data} onChange={(ev) => setData(ev.target.value)} />}</Campo>
          </div>
          <Campo rotulo="Observação">{(a) => <Input {...a} value={obs} maxLength={300} placeholder="Ex.: Pix" onChange={(ev) => setObs(ev.target.value)} />}</Campo>
          {registrar.isError && <Aviso tom="erro">{(registrar.error as Error).message}</Aviso>}
          <div className="flex justify-end gap-2">
            <Button type="button" variante="fantasma" onClick={fechar} disabled={registrar.isPending}>Cancelar</Button>
            <Button type="submit" variante="primario" disabled={registrar.isPending}>
              {registrar.isPending && <Loader2 className="animate-spin" />} Registrar pagamento
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function HistoricoDialog({ escritorio, aoFechar }: { escritorio: EscritorioAdm | null; aoFechar: () => void }) {
  const q = useQuery({
    queryKey: ["admin", "historico", escritorio?.id],
    queryFn: () => api<Evento[]>(`/api/admin/escritorios/${escritorio!.id}/historico`),
    enabled: !!escritorio,
  });
  return (
    <Dialog open={!!escritorio} onOpenChange={(v) => !v && aoFechar()}>
      <DialogContent titulo={`Histórico · ${escritorio?.nome ?? ""}`} descricao="Situação, plano e pagamentos, do mais recente para o mais antigo.">
        {q.isLoading && <Esqueleto className="h-32 w-full" />}
        {q.isError && <EstadoErro mensagem={(q.error as Error).message} tentarDeNovo={() => q.refetch()} />}
        {q.data?.length === 0 && <p className="text-sm text-texto-2">Nada registrado ainda.</p>}
        {q.data && q.data.length > 0 && (
          <ul className="max-h-96 divide-y divide-borda overflow-y-auto rounded-xl border border-borda">
            {q.data.map((ev) => (
              <li key={ev.id} className="px-3 py-2 text-sm">
                <div className="flex justify-between gap-3">
                  <span>{ev.descricao}</span>
                  {ev.valor !== null && <span className="shrink-0 font-mono">{moeda(ev.valor)}</span>}
                </div>
                <p className="text-xs text-texto-2">{formatarDataHora(ev.momento)}{ev.por && ` · ${ev.por}`}</p>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}

function NovoUsuario({ escritorio, aoFechar, aoCriar }: { escritorio: EscritorioAdm | null; aoFechar: () => void; aoCriar: (s: ComSenha) => void }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const criar = useMutation({
    mutationFn: () => api<ComSenha>(`/api/admin/escritorios/${escritorio!.id}/usuarios`, { method: "POST", body: JSON.stringify({ email, nome }) }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: CHAVE }); fechar(); aoCriar(r); },
  });
  const fechar = () => { setEmail(""); setNome(""); criar.reset(); aoFechar(); };
  return (
    <Dialog open={!!escritorio} onOpenChange={(v) => !v && !criar.isPending && fechar()}>
      <DialogContent titulo="Adicionar usuário" descricao={<>Novo acesso ao escritório <strong>{escritorio?.nome}</strong>. Ele vê todas as empresas do escritório.</>}>
        <form className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); criar.mutate(); }}>
          <Campo rotulo="E-mail" obrigatorio>{(a) => <Input {...a} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required />}</Campo>
          <Campo rotulo="Nome">{(a) => <Input {...a} value={nome} onChange={(e) => setNome(e.target.value)} />}</Campo>
          {criar.isError && <Aviso tom="erro">{(criar.error as Error).message}</Aviso>}
          <div className="flex justify-end gap-2">
            <Button type="button" variante="fantasma" onClick={fechar} disabled={criar.isPending}>Cancelar</Button>
            <Button type="submit" variante="primario" disabled={criar.isPending || !email}>
              {criar.isPending && <Loader2 className="animate-spin" />} Adicionar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SenhaInicial({ dados, aoFechar }: { dados: ComSenha | null; aoFechar: () => void }) {
  const endereco = window.location.origin;
  return (
    <Dialog open={!!dados} onOpenChange={(v) => !v && aoFechar()}>
      <DialogContent titulo="Senha inicial" descricao="Ela aparece só agora. Envie por um canal privado (WhatsApp direto, nunca em grupo). A pessoa troca no primeiro acesso.">
        {dados && (
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3"><dt className="text-texto-2">Endereço</dt><dd><Copiar texto={endereco} exibir={endereco} /></dd></div>
            <div className="flex justify-between gap-3"><dt className="text-texto-2">E-mail</dt><dd><Copiar texto={dados.usuario.email} exibir={dados.usuario.email} /></dd></div>
            <div className="flex justify-between gap-3"><dt className="text-texto-2">Senha inicial</dt><dd><Copiar texto={dados.senha_inicial} exibir={dados.senha_inicial} className="font-mono" /></dd></div>
          </dl>
        )}
        <div className="mt-5 flex justify-end"><Button variante="primario" onClick={aoFechar}>Pronto, já enviei</Button></div>
      </DialogContent>
    </Dialog>
  );
}
