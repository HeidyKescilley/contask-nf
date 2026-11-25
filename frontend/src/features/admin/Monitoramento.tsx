import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, AlertTriangle, BadgeCheck, CheckCircle2, CirclePlay, Film, Gauge, LifeBuoy, Loader2, MessageSquareHeart, MousePointerClick,
  Pause, Play, Route, ShieldAlert, Target, Users, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Selo } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Select } from "@/components/ui/campos";
import { Dica } from "@/components/ui/tooltip";
import { Painel } from "@/features/empresas/Passos";
import { api } from "@/lib/api";
import { formatarData, formatarDataHora } from "@/lib/formato";
import { useSessaoAdmin } from "@/lib/sessaoAdmin";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Tipos (espelham app/monitoramento.py)
// ---------------------------------------------------------------------------

interface Funcao { id: string; rotulo: string }
interface Resumo {
  dias: number; gerado_em: string; desde: string; eventos_desde: string | null;
  ativacao: {
    pct_ativados_7d: number | null; meta_ativacao: number; elegiveis_7d: number; usuarios: number; usuarios_sem_acesso: number;
    mediana_horas: { busca: number | null; emissao: number | null; exportacao: number | null };
    funil: { etapa: string; rotulo: string; escritorios: number; pct: number | null }[];
    escritorios: { id: number; nome: string; tipo: string; situacao: string; criado_em: string | null; usuarios: number; empresas: number;
      conectadas: number; pct_conectadas: number | null; horas_ate_busca: number | null; horas_ate_emissao: number | null;
      horas_ate_exportacao: number | null; parou_em: string | null }[];
  };
  uso: {
    funcoes: Funcao[];
    por_usuario: { usuario_id: number; nome: string; escritorio: string; funcoes: Record<string, number>; nao_usa: string[] }[];
    totais: Record<string, { rotulo: string; usos: number; usuarios: number }>;
    sem_uso: string[];
    notas_por_mes: { meses: string[]; escritorios: { escritorio: string; meses: number[] }[] };
  };
  frequencia: {
    dias_periodo: number; media_dias_acesso: number | null; usuarios: { nome: string; escritorio: string; dias: number }[];
    horas: number[]; periodos: { rotulo: string; acessos: number }[]; sessao_media_min: number | null; sessao_mediana_min: number | null;
    sessoes: number; pct_dias_fechamento: number | null; pct_esperado_fechamento: number;
    pessoas_por_escritorio: { escritorio: string; pessoas: number; cadastradas: number }[];
  };
  retencao: {
    pct_voltaram: number | null; meta_retorno: number; usaram: number; voltaram: number; pct_ativos: number | null; ativos: number; logaram: number;
    funcoes_ativos: { rotulo: string; usuarios: number; pct: number | null }[];
  };
  pesquisa: {
    respostas: number; meta_decepcao: number; decepcao: Record<"muito" | "pouco" | "nada", number>; pct_muito: number | null;
    nps: number | null; nps_respostas: number; nps_distribuicao: number[]; horas_media: number | null; horas_mediana: number | null;
    comentarios: { momento: string; nome: string; escritorio: string; texto: string; nps: number | null; decepcao: string | null }[];
  };
  erros: {
    buscas_com_erro: number; buscas_por_categoria: { categoria: string; vezes: number }[];
    ultimas_falhas: { momento: string; escritorio: string; categoria: string; mensagem: string }[];
    certificados_vencidos: { escritorio: string; titular: string; validade: string }[]; certificados_vencendo: number;
    notas_rejeitadas: number; erros_tela: { mensagem: string; vezes: number }[];
  };
  suporte: {
    abertos: number; por_assunto: { assunto: string; vezes: number }[];
    pedidos: { id: number; momento: string; assunto: string; mensagem: string; pagina: string | null; situacao: string; escritorio: string; usuario: string | null }[];
  };
}
interface Experiencia {
  paginas: { rota: string; acessos: number }[];
  transicoes: { de: string; para: string; vezes: number }[];
  caminhos: { caminho: string; sessoes: number }[];
  abandono: { rota: string; sessoes: number; pct_saidas: number | null }[];
  cliques_mortos: { rota: string; alvo: string; vezes: number }[];
  rota?: { rota: string; cliques: { x: number; y: number; w: number; morto: boolean }[]; alvos: { alvo: string; vezes: number }[];
    rolagem: { ate: number; pct: number | null }[]; visitas_rolagem: number };
}
interface GravacaoItem { id: number; iniciado_em: string; duracao_s: number; usuario: string; escritorio: string; paginas: string[]; tamanho: number }

const ABAS = [
  { id: "geral", rotulo: "Visão geral", icone: Gauge },
  { id: "ativacao", rotulo: "Ativação", icone: Target },
  { id: "uso", rotulo: "Uso", icone: Activity },
  { id: "frequencia", rotulo: "Frequência e retenção", icone: Users },
  { id: "pesquisa", rotulo: "Pesquisa", icone: MessageSquareHeart },
  { id: "experiencia", rotulo: "Experiência", icone: MousePointerClick },
  { id: "gravacoes", rotulo: "Gravações", icone: Film },
  { id: "erros", rotulo: "Erros", icone: ShieldAlert },
  { id: "suporte", rotulo: "Suporte", icone: LifeBuoy },
] as const;
type Aba = (typeof ABAS)[number]["id"];

const num = (n: number | null | undefined, suf = "") => (n === null || n === undefined ? "—" : `${n.toLocaleString("pt-BR")}${suf}`);
function tempo(h: number | null | undefined) {
  if (h === null || h === undefined) return "—";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${h.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} h`;
  return `${Math.round(h / 24)} dias`;
}
const duracao = (s: number) => (s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`);

// ---------------------------------------------------------------------------
// Peças de gráfico (uma série só: a cor de destaque; textos sempre nos tons de texto)
// ---------------------------------------------------------------------------

function Kpi({ rotulo, valor, detalhe, meta }: { rotulo: string; valor: string; detalhe?: ReactNode; meta?: { alvo: number; atual: number | null; suf?: string } }) {
  const bateu = meta && meta.atual !== null && meta.atual >= meta.alvo;
  return (
    <div className="rounded-xl border border-borda bg-superficie p-4">
      <p className="text-xs text-texto-2">{rotulo}</p>
      <p className="mt-1 font-mono text-2xl font-semibold tabular-nums">{valor}</p>
      {meta && (
        <div className="mt-1.5">
          {meta.atual === null ? <span className="text-xs text-texto-2">Meta: {meta.alvo}{meta.suf ?? "%"} (sem dados ainda)</span>
            : bateu ? <Selo tom="ok" icone={BadgeCheck}>Meta de {meta.alvo}{meta.suf ?? "%"} atingida</Selo>
            : <Selo tom="alerta" icone={AlertTriangle}>Abaixo da meta de {meta.alvo}{meta.suf ?? "%"}</Selo>}
        </div>
      )}
      {detalhe && <p className="mt-1.5 text-xs text-texto-2">{detalhe}</p>}
    </div>
  );
}

/** Barras horizontais com rótulo e valor ao lado. */
function Barras({ itens, formato = (v) => num(v), vazio = "Sem dados no período." }: {
  itens: { rotulo: string; valor: number; dica?: string }[]; formato?: (v: number) => string; vazio?: string;
}) {
  const max = Math.max(1, ...itens.map((i) => i.valor));
  if (!itens.length || itens.every((i) => !i.valor)) return <p className="text-sm text-texto-2">{vazio}</p>;
  return (
    <ul className="space-y-2">
      {itens.map((i) => (
        <li key={i.rotulo} className="grid grid-cols-[minmax(5rem,38%)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate text-texto-2" title={i.rotulo}>{i.rotulo}</span>
          <Dica texto={i.dica ?? `${i.rotulo}: ${formato(i.valor)}`} lado="top">
            <span className="block h-5 cursor-default py-1" tabIndex={0}>
              <span className="block h-3 rounded-r bg-destaque" style={{ width: `${Math.max(i.valor ? 1.5 : 0, (i.valor / max) * 100)}%` }} />
            </span>
          </Dica>
          <span className="min-w-10 text-right font-mono tabular-nums">{formato(i.valor)}</span>
        </li>
      ))}
    </ul>
  );
}

/** Colunas verticais (horas do dia, notas 0–10, profundidade de rolagem). */
function Colunas({ valores, rotulos, dica, altura = 120 }: { valores: number[]; rotulos: string[]; dica: (i: number) => string; altura?: number }) {
  const max = Math.max(1, ...valores);
  return (
    <div>
      <div className="flex items-end gap-0.5 border-b border-borda" style={{ height: altura }}>
        {valores.map((v, i) => (
          <Dica key={i} texto={dica(i)} lado="top">
            <span className="flex h-full flex-1 cursor-default items-end px-px" tabIndex={0}>
              <span className="block w-full rounded-t bg-destaque" style={{ height: `${(v / max) * 100}%`, minHeight: v ? 2 : 0 }} />
            </span>
          </Dica>
        ))}
      </div>
      <div className="mt-1 flex gap-0.5 text-[10px] text-texto-2">
        {rotulos.map((r, i) => <span key={i} className="flex-1 text-center tabular-nums">{r}</span>)}
      </div>
    </div>
  );
}

function Tabela({ cabecalho, linhas, vazio = "Nada no período." }: { cabecalho: ReactNode[]; linhas: ReactNode[][]; vazio?: string }) {
  if (!linhas.length) return <p className="text-sm text-texto-2">{vazio}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead><tr className="border-b border-borda text-left text-xs text-texto-2">{cabecalho.map((c, i) => <th key={i} className="px-2 py-2 font-medium">{c}</th>)}</tr></thead>
        <tbody>{linhas.map((l, i) => <tr key={i} className="border-b border-borda last:border-0">{l.map((c, j) => <td key={j} className="px-2 py-2 align-top">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Página
// ---------------------------------------------------------------------------

export function Monitoramento() {
  const sessao = useSessaoAdmin();
  const admin = !!sessao.data?.usuario;
  const [aba, setAba] = useState<Aba>("geral");
  const [dias, setDias] = useState(30);
  const resumo = useQuery({ queryKey: ["monitoramento", "resumo", dias], queryFn: () => api<Resumo>(`/api/admin/monitoramento/resumo?dias=${dias}`), enabled: admin });

  if (sessao.isLoading) return <Esqueleto className="h-96 w-full" />;
  if (!admin) return <EstadoVazio icone={ShieldAlert} titulo="Área do suporte do Contask">Só o administrador do sistema vê o monitoramento.</EstadoVazio>;

  return (
    <>
      <Cabecalho titulo="Monitoramento" descricao="Uso da plataforma para análise e desenvolvimento. O suporte do Contask fica fora das contas."
        acoes={
          <Select aria-label="Período" value={dias} onChange={(e) => setDias(Number(e.target.value))} className="w-44">
            <option value={7}>Últimos 7 dias</option>
            <option value={30}>Últimos 30 dias</option>
            <option value={90}>Últimos 90 dias</option>
            <option value={365}>Últimos 12 meses</option>
          </Select>
        } />
      <nav className="mb-5 flex gap-1 overflow-x-auto border-b border-borda [scrollbar-width:thin]" aria-label="Seções do monitoramento">
        {ABAS.map(({ id, rotulo, icone: I }) => (
          <button key={id} onClick={() => setAba(id)} aria-current={aba === id ? "page" : undefined}
            className={cn("-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition-colors",
              aba === id ? "border-destaque font-medium text-texto" : "border-transparent text-texto-2 hover:text-texto")}>
            <I className="size-4" aria-hidden />{rotulo}
          </button>
        ))}
      </nav>
      {resumo.data?.eventos_desde === null && aba !== "gravacoes" && (
        <div className="mb-4"><Aviso tom="info">A coleta de uso começou agora: páginas, tempo, cliques e caminhos aparecem conforme os clientes usarem. A ativação já usa o histórico das buscas, exportações e emissões.</Aviso></div>
      )}
      {aba === "experiencia" ? <AbaExperiencia dias={dias} />
        : aba === "gravacoes" ? <AbaGravacoes dias={Math.min(dias, 30)} />
        : resumo.isLoading ? <div className="grid gap-4 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <Esqueleto key={i} className="h-28" />)}</div>
        : resumo.isError ? <EstadoErro mensagem={(resumo.error as Error).message} tentarDeNovo={() => resumo.refetch()} />
        : resumo.data && (
          aba === "geral" ? <AbaGeral r={resumo.data} />
          : aba === "ativacao" ? <AbaAtivacao r={resumo.data} />
          : aba === "uso" ? <AbaUso r={resumo.data} />
          : aba === "frequencia" ? <AbaFrequencia r={resumo.data} />
          : aba === "pesquisa" ? <AbaPesquisa r={resumo.data} />
          : aba === "erros" ? <AbaErros r={resumo.data} />
          : <AbaSuporte r={resumo.data} />
        )}
    </>
  );
}

function AbaGeral({ r }: { r: Resumo }) {
  const a = r.ativacao, re = r.retencao, p = r.pesquisa, f = r.frequencia;
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi rotulo="Começaram a usar em 7 dias" valor={num(a.pct_ativados_7d, "%")} meta={{ alvo: a.meta_ativacao, atual: a.pct_ativados_7d }}
          detalhe={`${a.elegiveis_7d} usuário(s) com mais de 7 dias de conta`} />
        <Kpi rotulo="Voltaram depois do primeiro uso" valor={num(re.pct_voltaram, "%")} meta={{ alvo: re.meta_retorno, atual: re.pct_voltaram }}
          detalhe={`${re.voltaram} de ${re.usaram} que já usaram`} />
        <Kpi rotulo="Ficariam muito chateados sem o Contask" valor={num(p.pct_muito, "%")} meta={{ alvo: p.meta_decepcao, atual: p.pct_muito }}
          detalhe={`${p.respostas} resposta(s) · NPS ${num(p.nps)}`} />
        <Kpi rotulo="Ativos no período" valor={num(re.pct_ativos, "%")} detalhe={`${re.ativos} de ${re.logaram} que já entraram`} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi rotulo="Tempo até a 1ª busca (mediana)" valor={tempo(a.mediana_horas.busca)} />
        <Kpi rotulo="Tempo até a 1ª emissão (mediana)" valor={tempo(a.mediana_horas.emissao)} />
        <Kpi rotulo="Tempo até a 1ª exportação (mediana)" valor={tempo(a.mediana_horas.exportacao)} />
        <Kpi rotulo="Sessão média após o login" valor={f.sessao_media_min === null ? "—" : `${num(f.sessao_media_min)} min`} detalhe={`${f.sessoes} sessão(ões) com tempo ativo`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Painel titulo="Funil do cadastro (escritórios)">
          <div className="mt-4"><Barras itens={a.funil.map((e) => ({ rotulo: e.rotulo, valor: e.escritorios, dica: `${e.rotulo}: ${e.escritorios} escritório(s) (${num(e.pct, "%")})` }))} /></div>
        </Painel>
        <Painel titulo="Funções mais usadas (pessoas)">
          <div className="mt-4"><Barras itens={Object.values(r.uso.totais).map((t) => ({ rotulo: t.rotulo, valor: t.usuarios, dica: `${t.rotulo}: ${t.usuarios} pessoa(s), ${t.usos} uso(s)` }))} /></div>
          {r.uso.sem_uso.length > 0 && <p className="mt-3 text-xs text-texto-2">Ninguém usou no período: {r.uso.sem_uso.join(", ")}.</p>}
        </Painel>
      </div>
    </div>
  );
}

function AbaAtivacao({ r }: { r: Resumo }) {
  const a = r.ativacao;
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <Kpi rotulo="Começaram a usar em 7 dias" valor={num(a.pct_ativados_7d, "%")} meta={{ alvo: a.meta_ativacao, atual: a.pct_ativados_7d }}
          detalhe="Entrou e o escritório fez busca, exportação ou emissão em até 7 dias da criação do login." />
        <Kpi rotulo="Usuários que nunca entraram" valor={num(a.usuarios_sem_acesso)} detalhe={`de ${a.usuarios} usuário(s)`} />
        <Kpi rotulo="Escritórios" valor={num(a.escritorios.length)} detalhe="com pelo menos um usuário que não é do suporte" />
      </div>
      <Painel titulo="Funil do cadastro" descricao="Até onde cada escritório chegou. A coluna Parou em, na tabela, mostra a primeira etapa que falta.">
        <div className="mt-4"><Barras itens={a.funil.map((e) => ({ rotulo: e.rotulo, valor: e.escritorios, dica: `${e.escritorios} escritório(s) (${num(e.pct, "%")})` }))} /></div>
      </Painel>
      <Painel titulo="Por escritório" descricao="Tempos contados da criação do primeiro login do escritório. Conectada = empresa com pelo menos uma busca concluída.">
        <div className="mt-3">
          <Tabela cabecalho={["Escritório", "Criado em", "Usuários", "Empresas conectadas", "Até a 1ª busca", "Até a 1ª emissão", "Até a 1ª exportação", "Parou em"]}
            linhas={a.escritorios.map((e) => [
              <span className="font-medium">{e.nome}</span>, formatarData(e.criado_em), num(e.usuarios),
              <span className="font-mono tabular-nums">{e.conectadas}/{e.empresas}{e.pct_conectadas !== null && ` (${num(e.pct_conectadas, "%")})`}</span>,
              tempo(e.horas_ate_busca), tempo(e.horas_ate_emissao), tempo(e.horas_ate_exportacao),
              e.parou_em ? <Selo tom="alerta" icone={AlertTriangle}>{e.parou_em}</Selo> : <Selo tom="ok" icone={CheckCircle2}>Completo</Selo>,
            ])} />
        </div>
      </Painel>
    </div>
  );
}

function AbaUso({ r }: { r: Resumo }) {
  const u = r.uso;
  const mesesBR = u.notas_por_mes.meses.map((m) => m.split("-").reverse().join("/"));
  return (
    <div className="space-y-5">
      <Painel titulo="Uso por função" descricao="Pessoas que usaram cada função no período (acessos à tela mais ações como buscar, exportar e emitir).">
        <div className="mt-4"><Barras itens={Object.values(u.totais).map((t) => ({ rotulo: t.rotulo, valor: t.usuarios, dica: `${t.usuarios} pessoa(s), ${t.usos} uso(s)` }))} /></div>
        {u.sem_uso.length > 0 && <p className="mt-3 text-sm text-texto-2">Ninguém usou: <strong className="text-texto">{u.sem_uso.join(", ")}</strong>.</p>}
      </Painel>
      <Painel titulo="Por usuário" descricao="Número de usos de cada função. Traço = não usou no período.">
        <div className="mt-3">
          <Tabela cabecalho={["Usuário", ...u.funcoes.map((f) => f.rotulo), "Não usa"]}
            linhas={u.por_usuario.map((l) => [
              <div><p className="font-medium">{l.nome}</p><p className="text-xs text-texto-2">{l.escritorio}</p></div>,
              ...u.funcoes.map((f) => <span className={cn("font-mono tabular-nums", !l.funcoes[f.id] && "text-texto-2")}>{l.funcoes[f.id] || "—"}</span>),
              <span className="text-xs text-texto-2">{l.nao_usa.join(", ") || "—"}</span>,
            ])} vazio="Ainda não há uso registrado no período." />
        </div>
      </Painel>
      <Painel titulo="Notas baixadas por mês" descricao="Documentos recebidos do ADN em todas as buscas (inclui a carga inicial).">
        <div className="mt-3">
          <Tabela cabecalho={["Escritório", ...mesesBR.map((m) => m.slice(0, 5).split("/").reverse().join("/"))]}
            linhas={u.notas_por_mes.escritorios.map((e) => [e.escritorio, ...e.meses.map((v) => <span className="font-mono tabular-nums">{num(v)}</span>)])} />
        </div>
      </Painel>
    </div>
  );
}

function AbaFrequencia({ r }: { r: Resumo }) {
  const f = r.frequencia, re = r.retencao;
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi rotulo="Dias de acesso por pessoa" valor={num(f.media_dias_acesso)} detalhe={`média nos últimos ${f.dias_periodo} dias`} />
        <Kpi rotulo="Sessão após o login" valor={f.sessao_media_min === null ? "—" : `${num(f.sessao_media_min)} min`} detalhe={`mediana ${num(f.sessao_mediana_min)} min · só tempo ativo`} />
        <Kpi rotulo="Acessos nos dias 1 a 10" valor={num(f.pct_dias_fechamento, "%")} detalhe={`sem concentração seria ~${num(f.pct_esperado_fechamento, "%")}`} />
        <Kpi rotulo="Voltaram depois do 1º uso" valor={num(re.pct_voltaram, "%")} meta={{ alvo: re.meta_retorno, atual: re.pct_voltaram }} detalhe={`${re.voltaram} de ${re.usaram}`} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Painel titulo="Horário dos acessos" descricao="Páginas abertas por hora do dia (Brasília).">
          <div className="mt-4">
            <Colunas valores={f.horas} rotulos={f.horas.map((_, h) => (h % 3 === 0 ? `${h}h` : ""))} dica={(h) => `${h}h às ${h + 1}h: ${f.horas[h]} acesso(s)`} />
            <div className="mt-4"><Barras itens={f.periodos.map((p) => ({ rotulo: p.rotulo, valor: p.acessos }))} /></div>
          </div>
        </Painel>
        <Painel titulo="Uso de cada função entre os ativos" descricao={`${re.ativos} pessoa(s) ativa(s) no período.`}>
          <div className="mt-4"><Barras itens={re.funcoes_ativos.map((x) => ({ rotulo: x.rotulo, valor: x.pct ?? 0, dica: `${x.usuarios} pessoa(s)` }))} formato={(v) => `${num(v)}%`} /></div>
        </Painel>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Painel titulo="Pessoas por escritório" descricao="Quantas pessoas do mesmo escritório usaram no período.">
          <div className="mt-3"><Tabela cabecalho={["Escritório", "Usaram", "Logins cadastrados"]}
            linhas={f.pessoas_por_escritorio.map((e) => [e.escritorio, <span className="font-mono">{e.pessoas}</span>, <span className="font-mono">{e.cadastradas}</span>])} /></div>
        </Painel>
        <Painel titulo="Dias de acesso por pessoa">
          <div className="mt-3"><Tabela cabecalho={["Usuário", "Escritório", "Dias"]}
            linhas={f.usuarios.map((u) => [u.nome, u.escritorio, <span className="font-mono">{u.dias}</span>])} /></div>
        </Painel>
      </div>
    </div>
  );
}

function AbaPesquisa({ r }: { r: Resumo }) {
  const p = r.pesquisa;
  const total = p.decepcao.muito + p.decepcao.pouco + p.decepcao.nada;
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <Kpi rotulo="Muito chateados sem o Contask" valor={num(p.pct_muito, "%")} meta={{ alvo: p.meta_decepcao, atual: p.pct_muito }} detalhe={`${total} resposta(s)`} />
        <Kpi rotulo="NPS" valor={num(p.nps)} detalhe={`${p.nps_respostas} nota(s) · promotores (9–10) menos detratores (0–6)`} />
        <Kpi rotulo="Horas economizadas por mês" valor={p.horas_media === null ? "—" : `${num(p.horas_media)} h`} detalhe={`média · mediana ${num(p.horas_mediana)} h`} />
      </div>
      <p className="text-xs text-texto-2">A pesquisa aparece no app depois de 7 dias de conta e 3 dias de uso, e repete a cada 90 dias. Conta a resposta mais recente de cada pessoa.</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Painel titulo="Se o Contask deixasse de existir…">
          <div className="mt-4"><Barras itens={[
            { rotulo: "Muito chateado", valor: p.decepcao.muito }, { rotulo: "Um pouco chateado", valor: p.decepcao.pouco },
            { rotulo: "Não ficaria chateado", valor: p.decepcao.nada }]} vazio="Nenhuma resposta ainda." /></div>
        </Painel>
        <Painel titulo="Notas de recomendação (0 a 10)">
          <div className="mt-4">{p.nps_respostas ? <Colunas valores={p.nps_distribuicao} rotulos={p.nps_distribuicao.map((_, i) => String(i))} dica={(i) => `Nota ${i}: ${p.nps_distribuicao[i]} pessoa(s)`} />
            : <p className="text-sm text-texto-2">Nenhuma nota ainda.</p>}</div>
        </Painel>
      </div>
      <Painel titulo="Comentários">
        <div className="mt-3"><Tabela cabecalho={["Quando", "Quem", "Comentário"]} vazio="Nenhum comentário ainda."
          linhas={p.comentarios.map((c) => [formatarData(c.momento), <div><p>{c.nome}</p><p className="text-xs text-texto-2">{c.escritorio}{c.nps !== null && ` · nota ${c.nps}`}</p></div>, c.texto])} /></div>
      </Painel>
    </div>
  );
}

function AbaErros({ r }: { r: Resumo }) {
  const e = r.erros;
  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi rotulo="Buscas que falharam" valor={num(e.buscas_com_erro)} />
        <Kpi rotulo="Certificados vencidos" valor={num(e.certificados_vencidos.length)} detalhe={`${e.certificados_vencendo} vencem em 30 dias`} />
        <Kpi rotulo="Notas rejeitadas pela Sefin" valor={num(e.notas_rejeitadas)} />
        <Kpi rotulo="Erros na tela" valor={num(e.erros_tela.reduce((s, x) => s + x.vezes, 0))} detalhe="falhas do servidor, de conexão e de script" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Painel titulo="Buscas com erro, por causa"><div className="mt-4"><Barras itens={e.buscas_por_categoria.map((c) => ({ rotulo: c.categoria, valor: c.vezes }))} vazio="Nenhuma busca falhou no período." /></div></Painel>
        <Painel titulo="Erros na tela"><div className="mt-3"><Tabela cabecalho={["Erro", "Vezes"]} vazio="Nenhum erro registrado."
          linhas={e.erros_tela.map((x) => [<span className="font-mono text-xs">{x.mensagem}</span>, x.vezes])} /></div></Painel>
      </div>
      <Painel titulo="Últimas buscas que falharam">
        <div className="mt-3"><Tabela cabecalho={["Quando", "Escritório", "Causa", "Mensagem"]}
          linhas={e.ultimas_falhas.map((x) => [formatarDataHora(x.momento), x.escritorio, x.categoria, <span className="text-xs">{x.mensagem}</span>])} /></div>
      </Painel>
      <Painel titulo="Certificados vencidos">
        <div className="mt-3"><Tabela cabecalho={["Escritório", "Titular", "Venceu em"]} vazio="Nenhum certificado vencido."
          linhas={e.certificados_vencidos.map((c) => [c.escritorio, c.titular, formatarData(c.validade)])} /></div>
      </Painel>
    </div>
  );
}

function AbaSuporte({ r }: { r: Resumo }) {
  const s = r.suporte;
  const qc = useQueryClient();
  const resolver = useMutation({
    mutationFn: ({ id, resolvido }: { id: number; resolvido: boolean }) =>
      api(`/api/admin/monitoramento/suporte/${id}?resolvido=${resolvido}`, { method: "PUT" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["monitoramento", "resumo"] }),
  });
  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
        <Kpi rotulo="Pedidos abertos" valor={num(s.abertos)} detalhe="Os clientes pedem pelo botão Ajuda, no topo." />
        <Painel titulo="Assuntos no período"><div className="mt-4"><Barras itens={s.por_assunto.map((a) => ({ rotulo: a.assunto, valor: a.vezes }))} vazio="Nenhum pedido no período." /></div></Painel>
      </div>
      <Painel titulo="Pedidos">
        <div className="mt-3"><Tabela cabecalho={["Quando", "Quem", "Assunto", "Mensagem", "Situação"]} vazio="Nenhum pedido de suporte ainda."
          linhas={s.pedidos.map((p) => [
            formatarDataHora(p.momento), <div><p>{p.usuario ?? "—"}</p><p className="text-xs text-texto-2">{p.escritorio}</p></div>, p.assunto,
            <div><p className="whitespace-pre-wrap">{p.mensagem}</p>{p.pagina && <p className="mt-0.5 font-mono text-xs text-texto-2">{p.pagina}</p>}</div>,
            <Button tamanho="pequeno" variante={p.situacao === "aberto" ? "primario" : "secundario"} disabled={resolver.isPending}
              onClick={() => resolver.mutate({ id: p.id, resolvido: p.situacao === "aberto" })}>
              {p.situacao === "aberto" ? "Marcar resolvido" : "Reabrir"}
            </Button>,
          ])} /></div>
      </Painel>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Experiência: mapa de calor, rolagem, cliques sem resposta, caminhos e abandono
// ---------------------------------------------------------------------------

function AbaExperiencia({ dias }: { dias: number }) {
  const [rota, setRota] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["monitoramento", "experiencia", dias, rota],
    queryFn: () => api<Experiencia>(`/api/admin/monitoramento/experiencia?dias=${dias}${rota ? `&rota=${encodeURIComponent(rota)}` : ""}`),
    placeholderData: (ant) => ant,
  });
  useEffect(() => {
    if (!rota && q.data?.paginas[0]) setRota(q.data.paginas[0].rota);
  }, [q.data, rota]);
  if (q.isLoading) return <Esqueleto className="h-96 w-full" />;
  if (q.isError) return <EstadoErro mensagem={(q.error as Error).message} tentarDeNovo={() => q.refetch()} />;
  const x = q.data!;
  if (!x.paginas.length) return <EstadoVazio icone={Route} titulo="Sem navegação registrada no período">Os mapas aparecem quando os clientes começarem a usar a plataforma.</EstadoVazio>;
  const pr = x.rota;
  return (
    <div className="space-y-5">
      <Painel titulo="Mapa de calor e de rolagem" descricao="Escolha a tela. Os cliques são desenhados sobre a tela aberta com a sua conta (o layout é o mesmo; os dados, não).">
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Select aria-label="Tela" value={rota ?? ""} onChange={(e) => setRota(e.target.value)} className="w-80">
            {x.paginas.map((p) => <option key={p.rota} value={p.rota}>{p.rota} ({p.acessos} acesso{p.acessos === 1 ? "" : "s"})</option>)}
          </Select>
          {q.isFetching && <Loader2 className="size-4 animate-spin text-texto-2" aria-label="Carregando" />}
        </div>
        {pr && (
          <div className="mt-4 grid gap-5 xl:grid-cols-[1fr_18rem]">
            <MapaDeCalor rota={pr.rota} cliques={pr.cliques} />
            <div className="space-y-5">
              <div>
                <h3 className="mb-2 text-sm font-medium">Até onde rolam</h3>
                {pr.visitas_rolagem ? (
                  <Barras itens={pr.rolagem.filter((r) => r.ate > 0).map((r) => ({ rotulo: `${r.ate}% da página`, valor: r.pct ?? 0, dica: `${num(r.pct, "%")} das visitas chegaram a ${r.ate}%` }))}
                    formato={(v) => `${num(Math.round(v))}%`} />
                ) : <p className="text-sm text-texto-2">Sem medição de rolagem nesta tela.</p>}
              </div>
              <div>
                <h3 className="mb-2 text-sm font-medium">Onde mais clicam</h3>
                <Tabela cabecalho={["Elemento", "Cliques"]} linhas={pr.alvos.map((a) => [a.alvo, <span className="font-mono">{a.vezes}</span>])} vazio="Sem cliques nesta tela." />
              </div>
            </div>
          </div>
        )}
      </Painel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Painel titulo="Cliques sem resposta" descricao="Clicou em algo que não é botão e nada mudou na tela.">
          <div className="mt-3"><Tabela cabecalho={["Tela", "Onde", "Vezes"]} vazio="Nenhum no período."
            linhas={x.cliques_mortos.map((c) => [<span className="font-mono text-xs">{c.rota}</span>, c.alvo, <span className="font-mono">{c.vezes}</span>])} /></div>
        </Painel>
        <Painel titulo="Pontos de abandono" descricao="Última tela das sessões. % = saídas sobre os acessos à tela.">
          <div className="mt-3"><Tabela cabecalho={["Tela", "Sessões que acabaram nela", "% das visitas"]}
            linhas={x.abandono.map((a) => [<span className="font-mono text-xs">{a.rota}</span>, <span className="font-mono">{a.sessoes}</span>, num(a.pct_saidas, "%")])} /></div>
        </Painel>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Painel titulo="Caminhos mais comuns" descricao="As primeiras quatro telas de cada sessão.">
          <div className="mt-3"><Tabela cabecalho={["Caminho", "Sessões"]} linhas={x.caminhos.map((c) => [<span className="font-mono text-xs">{c.caminho}</span>, <span className="font-mono">{c.sessoes}</span>])} /></div>
        </Painel>
        <Painel titulo="De uma tela para outra">
          <div className="mt-3"><Tabela cabecalho={["De", "Para", "Vezes"]} linhas={x.transicoes.map((t) => [<span className="font-mono text-xs">{t.de}</span>, <span className="font-mono text-xs">{t.para}</span>, <span className="font-mono">{t.vezes}</span>])} /></div>
        </Painel>
      </div>
    </div>
  );
}

function MapaDeCalor({ rota, cliques }: { rota: string; cliques: { x: number; y: number; w: number; morto: boolean }[] }) {
  const caixa = useRef<HTMLDivElement>(null);
  const tela = useRef<HTMLCanvasElement>(null);
  const [largura, setLargura] = useState(800);
  const [alturaDoc, setAlturaDoc] = useState(900);
  // largura de janela mais comum entre os cliques: o iframe abre nela e é reduzido para caber
  const larguraBase = useMemo(() => {
    const c = new Map<number, number>();
    for (const k of cliques) { const b = Math.round((k.w || 1280) / 10) * 10; c.set(b, (c.get(b) ?? 0) + 1); }
    return [...c.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || 1280;
  }, [cliques]);
  const comId = rota.includes(":id");
  const escala = Math.min(1, largura / larguraBase);
  const doGrupo = cliques.filter((k) => Math.abs((k.w || 1280) - larguraBase) <= 160);
  const altura = Math.max(alturaDoc, ...doGrupo.map((k) => k.y + 40));

  useEffect(() => {
    const el = caixa.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setLargura(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const c = tela.current;
    if (!c) return;
    c.width = larguraBase; c.height = altura;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, c.width, c.height);
    const cor = getComputedStyle(document.documentElement).getPropertyValue("--destaque").trim() || "#1d4ed8";
    const critico = getComputedStyle(document.documentElement).getPropertyValue("--cancelada").trim() || "#b91c1c";
    for (const k of doGrupo) {
      const x = k.x * larguraBase, y = k.y;
      if (k.morto) {
        ctx.strokeStyle = critico; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.stroke();
      } else {
        // pontos sobrepostos somam opacidade: onde clicam mais, fica mais forte
        const g = ctx.createRadialGradient(x, y, 0, x, y, 22);
        g.addColorStop(0, cor);
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.globalAlpha = 0.45;
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.arc(x, y, 22, 0, Math.PI * 2); ctx.fill();
        ctx.globalAlpha = 1;
      }
    }
  }, [doGrupo, larguraBase, altura]);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4 text-xs text-texto-2">
        <span className="inline-flex items-center gap-1.5"><span className="size-3 rounded-full bg-destaque/60" aria-hidden /> Clique ({doGrupo.length})</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-3 rounded-full border-2 border-cancelada" aria-hidden /> Clique sem resposta ({doGrupo.filter((k) => k.morto).length})</span>
        <span>Janelas de ~{larguraBase}px de largura{cliques.length > doGrupo.length && ` (${cliques.length - doGrupo.length} clique(s) em outras larguras ficaram de fora)`}</span>
      </div>
      <div ref={caixa} className="relative overflow-hidden rounded-lg border border-borda bg-fundo" style={{ height: altura * escala }}>
        <div className="absolute left-0 top-0 origin-top-left" style={{ width: larguraBase, height: altura, transform: `scale(${escala})` }}>
          {comId ? (
            <div className="flex h-full items-start justify-center p-10 text-sm text-texto-2">Tela com identificador ({rota}): os cliques aparecem sem a tela de fundo.</div>
          ) : (
            <iframe title={`Tela ${rota}`} src={rota} className="pointer-events-none h-full w-full border-0" tabIndex={-1}
              onLoad={(e) => { try { setAlturaDoc(e.currentTarget.contentDocument?.documentElement.scrollHeight ?? 900); } catch { /* sem acesso */ } }} />
          )}
          <canvas ref={tela} className="pointer-events-none absolute left-0 top-0" style={{ width: larguraBase, height: altura }} aria-hidden />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gravações (rrweb, com todo texto mascarado)
// ---------------------------------------------------------------------------

function AbaGravacoes({ dias }: { dias: number }) {
  const q = useQuery({ queryKey: ["monitoramento", "gravacoes", dias], queryFn: () => api<GravacaoItem[]>(`/api/admin/monitoramento/gravacoes?dias=${dias}`) });
  const [aberta, setAberta] = useState<GravacaoItem | null>(null);
  if (q.isLoading) return <Esqueleto className="h-64 w-full" />;
  if (q.isError) return <EstadoErro mensagem={(q.error as Error).message} tentarDeNovo={() => q.refetch()} />;
  return (
    <div className="space-y-4">
      <Aviso tom="info">As gravações mostram o layout, os cliques e a rolagem. Todo texto aparece como asteriscos e os campos ficam mascarados no próprio navegador do cliente. Ficam 30 dias no servidor.</Aviso>
      {aberta && <Player g={aberta} fechar={() => setAberta(null)} />}
      {!q.data!.length ? <EstadoVazio icone={Film} titulo="Nenhuma gravação no período">As sessões dos clientes aparecem aqui assim que eles usarem a plataforma.</EstadoVazio> : (
        <Painel>
          <Tabela cabecalho={["Quando", "Quem", "Duração", "Telas", ""]}
            linhas={q.data!.map((g) => [
              formatarDataHora(g.iniciado_em), <div><p>{g.usuario}</p><p className="text-xs text-texto-2">{g.escritorio}</p></div>, duracao(g.duracao_s),
              <span className="font-mono text-xs text-texto-2">{g.paginas.slice(0, 5).join(" → ")}{g.paginas.length > 5 && " …"}</span>,
              <Button tamanho="pequeno" onClick={() => setAberta(g)}><CirclePlay /> Assistir</Button>,
            ])} />
        </Painel>
      )}
    </div>
  );
}

type ReplayerT = import("rrweb").Replayer;

function Player({ g, fechar }: { g: GravacaoItem; fechar: () => void }) {
  const dados = useQuery({ queryKey: ["monitoramento", "gravacao", g.id], queryFn: () => api<{ eventos: unknown[] }>(`/api/admin/monitoramento/gravacoes/${g.id}`), staleTime: Infinity });
  const caixa = useRef<HTMLDivElement>(null);
  const palco = useRef<HTMLDivElement>(null);
  const rep = useRef<ReplayerT | null>(null);
  const [tocando, setTocando] = useState(false);
  const [total, setTotal] = useState(0);
  const [atual, setAtual] = useState(0);
  const [velocidade, setVelocidade] = useState(1);
  const [dim, setDim] = useState({ w: 1280, h: 720 });
  const [largura, setLargura] = useState(800);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const el = caixa.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setLargura(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const evs = dados.data?.eventos;
    if (!evs || !palco.current) return;
    if (evs.length < 2) { setErro("Gravação curta demais para reproduzir."); return; }
    let ativo = true;
    void (async () => {
      try {
        const { Replayer } = await import("rrweb");
        await import("rrweb/dist/style.css");
        if (!ativo || !palco.current) return;
        palco.current.innerHTML = "";
        const r = new Replayer(evs as never, { root: palco.current, skipInactive: true, showWarning: false, mouseTail: false });
        r.on("resize", (d) => { const x = d as { width: number; height: number }; setDim({ w: x.width, h: x.height }); });
        r.on("finish", () => setTocando(false));
        rep.current = r;
        setTotal(r.getMetaData().totalTime);
        const w = Number(r.iframe.getAttribute("width")) || 1280, h = Number(r.iframe.getAttribute("height")) || 720;
        setDim({ w, h });
        r.play(0);
        setTocando(true);
      } catch {
        setErro("Não foi possível reproduzir esta gravação.");
      }
    })();
    return () => { ativo = false; rep.current?.pause(); rep.current = null; };
  }, [dados.data]);

  useEffect(() => {
    if (!tocando) return;
    const t = window.setInterval(() => setAtual(rep.current?.getCurrentTime() ?? 0), 250);
    return () => clearInterval(t);
  }, [tocando]);

  const escala = Math.min(1, largura / dim.w);
  const alternar = () => {
    const r = rep.current;
    if (!r) return;
    if (tocando) { r.pause(); setTocando(false); } else { r.play(atual >= total ? 0 : atual); setTocando(true); }
  };
  const ir = (ms: number) => { const r = rep.current; if (!r) return; setAtual(ms); if (tocando) r.play(ms); else r.pause(ms); };
  const mm = (ms: number) => duracao(Math.round(ms / 1000));

  return (
    <Painel titulo={`Sessão de ${g.usuario} · ${formatarDataHora(g.iniciado_em)}`} descricao={g.escritorio}>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button tamanho="pequeno" variante="primario" onClick={alternar} disabled={!rep.current}>{tocando ? <><Pause /> Pausar</> : <><Play /> Tocar</>}</Button>
        <input type="range" min={0} max={total || 1} value={Math.min(atual, total)} onChange={(e) => ir(Number(e.target.value))}
          aria-label="Posição da gravação" className="min-w-40 flex-1 accent-[var(--destaque)]" />
        <span className="font-mono text-xs tabular-nums text-texto-2">{mm(atual)} / {mm(total)}</span>
        <Select aria-label="Velocidade" value={velocidade} className="w-24"
          onChange={(e) => { const v = Number(e.target.value); setVelocidade(v); rep.current?.setConfig({ speed: v }); }}>
          {[1, 2, 4, 8].map((v) => <option key={v} value={v}>{v}x</option>)}
        </Select>
        <Button tamanho="icone" variante="fantasma" aria-label="Fechar gravação" onClick={fechar}><X /></Button>
      </div>
      <div ref={caixa} className="relative mt-3 overflow-hidden rounded-lg border border-borda bg-white" style={{ height: dim.h * escala }}>
        {(dados.isLoading) && <div className="absolute inset-0 flex items-center justify-center"><Loader2 className="size-6 animate-spin text-texto-2" aria-label="Carregando gravação" /></div>}
        {(dados.isError || erro) && <div className="p-4"><EstadoErro mensagem={erro ?? (dados.error as Error).message} /></div>}
        <div ref={palco} className="absolute left-0 top-0 origin-top-left" style={{ width: dim.w, height: dim.h, transform: `scale(${escala})` }} />
      </div>
    </Painel>
  );
}
