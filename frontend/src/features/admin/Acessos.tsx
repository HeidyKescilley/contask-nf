import { useQuery } from "@tanstack/react-query";
import { BarChart3, ExternalLink, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { Select } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { useSessaoAdmin } from "@/lib/sessaoAdmin";

interface Linha { visitas: number; pessoas: number; leads: number; taxa: number | null }
interface Resumo {
  inicio: string;
  fim: string;
  totais: Linha & { black_friday: number };
  por_dia: { dia: string; visitas: number; pessoas: number; leads: number }[];
  canais: (Linha & { canal: string; black_friday: number })[];
  paginas: (Linha & { pagina: string })[];
  dispositivos: { celular: number; computador: number };
}

const dataBR = (iso: string) => iso.slice(0, 10).split("-").reverse().join("/");
const diaCurto = (iso: string) => iso.slice(8, 10) + "/" + iso.slice(5, 7);
const n = (v: number) => v.toLocaleString("pt-BR");
const pct = (v: number | null) => (v === null ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`);
const NOME_CANAL: Record<string, string> = { direto: "Direto" };
const NOME_PAGINA: Record<string, string> = { "/": "Página inicial", "/emissor/": "Emissor", "/30-dias-gratis/": "30 dias grátis", "/black-friday/": "Black Friday" };

export function Acessos() {
  const sessao = useSessaoAdmin();
  const admin = !!sessao.data?.usuario;
  const [dias, setDias] = useState(30);
  const q = useQuery({ queryKey: ["admin", "acessos", dias], queryFn: () => api<Resumo>(`/api/admin/acessos?dias=${dias}`), enabled: admin });

  if (sessao.isLoading) return <Esqueleto className="h-64 w-full" />;
  if (!admin) return <EstadoVazio icone={ShieldCheck} titulo="Área restrita">Só o administrador do sistema acessa esta página.</EstadoVazio>;
  const r = q.data;

  return (
    <>
      <Cabecalho titulo="Acessos do site" descricao="Visitas em contasknf.com.br, de onde vieram e quantas viraram lead. Contagem própria, sem cookie: pessoas são contadas por dia."
        acoes={
          <Select value={dias} onChange={(e) => setDias(Number(e.target.value))} aria-label="Período" className="w-44">
            <option value={7}>Últimos 7 dias</option>
            <option value={30}>Últimos 30 dias</option>
            <option value={90}>Últimos 90 dias</option>
          </Select>
        } />
      {q.isLoading && <Esqueleto className="h-80 w-full" />}
      {q.isError && <EstadoErro mensagem={(q.error as Error).message} tentarDeNovo={() => q.refetch()} />}
      {r && r.totais.visitas === 0 && r.totais.leads === 0 && (
        <EstadoVazio icone={BarChart3} titulo="Nenhuma visita no período">As visitas ao site aparecem aqui assim que alguém abrir as páginas.</EstadoVazio>
      )}
      {r && (r.totais.visitas > 0 || r.totais.leads > 0) && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Indicador rotulo="Pessoas" valor={n(r.totais.pessoas)} detalhe={`${n(r.totais.visitas)} páginas vistas`} />
            <Indicador rotulo="Leads" valor={n(r.totais.leads)} detalhe={r.totais.black_friday ? `${n(r.totais.black_friday)} da Black Friday` : "pelos formulários"} />
            <Indicador rotulo="Conversão" valor={pct(r.totais.taxa)} detalhe="leads ÷ pessoas" />
            <Indicador rotulo="Pelo celular" valor={pct(r.dispositivos.celular + r.dispositivos.computador ? Math.round(1000 * r.dispositivos.celular / (r.dispositivos.celular + r.dispositivos.computador)) / 10 : null)}
              detalhe={`${n(r.dispositivos.computador)} pelo computador`} />
          </div>
          <GraficoDias dias={r.por_dia} periodo={`${dataBR(r.inicio)} a ${dataBR(r.fim)}`} />
          <div className="grid gap-4 2xl:grid-cols-2">
            <Tabela titulo="Canais" colunaNome="Canal" linhas={r.canais.map((c) => ({ chave: c.canal, nome: NOME_CANAL[c.canal] ?? c.canal, ...c }))}
              rodape="Canal = utm_source do link (use um link diferente por canal) ou o site de onde a pessoa veio. Direto = digitou o endereço ou abriu um link sem origem." />
            <Tabela titulo="Páginas" colunaNome="Página" linhas={r.paginas.map((p) => ({ chave: p.pagina, nome: NOME_PAGINA[p.pagina] ?? p.pagina, ...p }))} />
          </div>
          <a href="https://analytics.google.com/" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-texto-2 hover:text-texto hover:underline">
            Abrir o Google Analytics <ExternalLink className="size-3.5" aria-hidden />
          </a>
        </div>
      )}
    </>
  );
}

function Indicador({ rotulo, valor, detalhe }: { rotulo: string; valor: string; detalhe: string }) {
  return (
    <div className="rounded-xl border border-borda bg-superficie px-4 py-3">
      <div className="text-xs text-texto-2">{rotulo}</div>
      <div className="font-mono text-2xl font-semibold tabular-nums">{valor}</div>
      <div className="text-xs text-texto-2">{detalhe}</div>
    </div>
  );
}

function GraficoDias({ dias, periodo }: { dias: Resumo["por_dia"]; periodo: string }) {
  const [foco, setFoco] = useState<number | null>(null);
  const max = Math.max(1, ...dias.map((d) => d.pessoas));
  const passo = Math.ceil(dias.length / 8);
  const atual = foco !== null ? dias[foco] : null;
  return (
    <section className="rounded-xl border border-borda bg-superficie p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Pessoas por dia</h2>
        <span className="text-xs text-texto-2" aria-live="polite">
          {atual ? `${dataBR(atual.dia)}: ${n(atual.pessoas)} pessoas · ${n(atual.visitas)} páginas · ${n(atual.leads)} leads` : periodo}
        </span>
      </div>
      <div className="relative h-44" onMouseLeave={() => setFoco(null)}>
        {[0.5, 1].map((f) => (
          <div key={f} className="pointer-events-none absolute inset-x-0 border-t border-dashed border-borda" style={{ bottom: `${f * 100}%` }}>
            <span className="absolute -top-2.5 left-0 bg-superficie pr-1 font-mono text-[10px] text-texto-2">{n(Math.round(max * f))}</span>
          </div>
        ))}
        <div className="absolute inset-0 flex items-end gap-[2px] pl-8">
          {dias.map((d, i) => (
            <button key={d.dia} type="button" className="group relative flex h-full flex-1 items-end outline-none"
              onMouseEnter={() => setFoco(i)} onFocus={() => setFoco(i)} onBlur={() => setFoco(null)}
              aria-label={`${dataBR(d.dia)}: ${d.pessoas} pessoas, ${d.leads} leads`}>
              <span className={`w-full rounded-t-[4px] transition-colors ${foco === i ? "bg-destaque" : "bg-destaque/70"} ${d.pessoas === 0 ? "h-px bg-borda" : ""}`}
                style={d.pessoas ? { height: `${(d.pessoas / max) * 100}%` } : undefined} />
              {d.leads > 0 && <span className="absolute -top-0 left-1/2 size-1.5 -translate-x-1/2 rounded-full bg-texto" style={{ bottom: `calc(${(d.pessoas / max) * 100}% + 4px)`, top: "auto" }} aria-hidden />}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1 flex gap-[2px] pl-8 font-mono text-[10px] text-texto-2">
        {dias.map((d, i) => <span key={d.dia} className="flex-1 text-center">{i % passo === 0 ? diaCurto(d.dia) : ""}</span>)}
      </div>
      <p className="mt-2 text-xs text-texto-2"><span className="mr-1 inline-block size-1.5 rounded-full bg-texto align-middle" aria-hidden /> dia com lead</p>
    </section>
  );
}

function Tabela({ titulo, colunaNome, linhas, rodape }: {
  titulo: string; colunaNome: string; rodape?: string;
  linhas: (Linha & { chave: string; nome: string })[];
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-borda bg-superficie">
      <h2 className="border-b border-borda px-4 py-3 text-sm font-semibold">{titulo}</h2>
      {linhas.length === 0 ? <p className="px-4 py-6 text-sm text-texto-2">Nada no período.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-texto-2">
              <tr><th className="px-4 py-2 text-left font-medium">{colunaNome}</th><th className="px-3 py-2 text-right font-medium">Pessoas</th>
                <th className="px-3 py-2 text-right font-medium">Páginas</th><th className="px-3 py-2 text-right font-medium">Leads</th>
                <th className="px-4 py-2 text-right font-medium">Conversão</th></tr>
            </thead>
            <tbody>
              {linhas.map((l) => (
                <tr key={l.chave} className="border-t border-borda">
                  <td className="max-w-56 truncate px-4 py-2" title={l.chave}>{l.nome}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{n(l.pessoas)}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums text-texto-2">{n(l.visitas)}</td>
                  <td className="px-3 py-2 text-right font-mono tabular-nums">{n(l.leads)}</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">{pct(l.taxa)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rodape && <p className="border-t border-borda px-4 py-2 text-xs text-texto-2">{rodape}</p>}
    </section>
  );
}
