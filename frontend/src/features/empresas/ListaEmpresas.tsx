import { useQuery } from "@tanstack/react-query";
import { Building2, FileSpreadsheet, KeyRound, Plus, Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Cabecalho, EstadoErro, EstadoVazio, Esqueleto } from "@/components/estados";
import { SeloAcesso, SeloBusca, SeloCertificado } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Input } from "@/components/ui/campos";
import { api, type Empresa } from "@/lib/api";
import { nomeExibicao, useContabilidade } from "@/lib/empresas";
import { formatarDataHora, formatarDoc } from "@/lib/formato";
import { cn } from "@/lib/utils";

const FILTROS = [
  { id: "", rotulo: "Todas" },
  { id: "procuracao_pendente", rotulo: "Procuração pendente" },
  { id: "certificado", rotulo: "Certificado com alerta" },
  { id: "pendencias", rotulo: "Com pendências" },
  { id: "inativas", rotulo: "Inativas" },
];

export function ListaEmpresas() {
  const [params, setParams] = useSearchParams();
  const filtro = params.get("filtro") ?? "";
  const [q, setQ] = useState("");
  const navegar = useNavigate();
  const contab = useContabilidade();

  const lista = useQuery({
    queryKey: ["empresas", { filtro, q }],
    queryFn: () => api<Empresa[]>(`/api/empresas?${new URLSearchParams({ ...(filtro && { filtro }), ...(q.trim() && { q: q.trim() }) })}`),
    placeholderData: (ant) => ant,
  });

  const definirFiltro = (f: string) =>
    setParams((p) => {
      const n = new URLSearchParams(p);
      if (f) n.set("filtro", f);
      else n.delete("filtro");
      return n;
    }, { replace: true });

  if (contab.isSuccess && !contab.data) {
    return (
      <>
        <Cabecalho titulo="Empresas" descricao="Cadastro, certificados, procurações e situação das buscas." />
        <EstadoVazio icone={KeyRound} titulo="Comece pela contabilidade"
          acao={<Button variante="primario" asChild><Link to="/contabilidade"><KeyRound /> Cadastrar a contabilidade</Link></Button>}>
          A contabilidade é a empresa que recebeu as procurações dos clientes. O certificado dela é usado para buscar as
          notas de todas as empresas.
        </EstadoVazio>
      </>
    );
  }

  const contabCert = contab.data?.certificado;

  return (
    <>
      <Cabecalho
        titulo="Empresas"
        descricao="Cadastro, certificados, procurações e situação das buscas."
        acoes={<div className="flex gap-2"><Button asChild><Link to="/empresas/importar"><FileSpreadsheet /> Importar planilha</Link></Button><Button variante="primario" asChild><Link to="/empresas/nova"><Plus /> Nova empresa</Link></Button></div>}
      />

      {contabCert && contabCert.situacao !== "ok" && (
        <div className="mb-4">
          <Aviso tom={contabCert.situacao === "vencido" ? "erro" : "alerta"}>
            {contabCert.situacao === "vencido"
              ? "O certificado da contabilidade está vencido. As buscas por procuração estão bloqueadas."
              : `O certificado da contabilidade vence em ${contabCert.dias_restantes} dia(s). Sem renovação, as buscas por procuração param.`}{" "}
            <Link to="/contabilidade" className="font-medium text-destaque underline">Enviar certificado renovado</Link>
          </Aviso>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-80">
          <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-texto-2" aria-hidden />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nome, apelido ou CNPJ" className="pl-9" aria-label="Filtrar empresas" />
        </div>
        <div className="flex gap-1 rounded-xl border border-borda bg-superficie p-1" role="group" aria-label="Filtro rápido">
          {FILTROS.map((f) => (
            <button key={f.id} onClick={() => definirFiltro(f.id)} aria-pressed={filtro === f.id}
              className={cn("h-7 rounded-lg px-2.5 text-[13px]", filtro === f.id ? "bg-destaque-suave font-medium text-destaque" : "text-texto-2 hover:text-texto")}>
              {f.rotulo}
            </button>
          ))}
        </div>
      </div>

      {lista.isLoading && <Esqueleto className="h-64 w-full" />}
      {lista.isError && <EstadoErro mensagem={(lista.error as Error).message} tentarDeNovo={() => lista.refetch()} />}
      {lista.data && lista.data.length === 0 && (
        <EstadoVazio icone={Building2} titulo={filtro || q ? "Nenhuma empresa neste filtro" : "Nenhuma empresa cadastrada"}>
          {filtro === "procuracao_pendente" ? "Nenhuma empresa está sem procuração. As empresas aparecem aqui quando o ADN responde que não há procuração."
            : filtro || q ? "Tente outro filtro ou termo." : "Cadastre a primeira empresa pelo CNPJ."}
        </EstadoVazio>
      )}

      {lista.data && lista.data.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-borda bg-superficie">
          <table className="w-full text-sm">
            <thead className="border-b border-borda bg-fundo text-left text-xs text-texto-2">
              <tr>
                <th className="px-4 py-2.5 font-medium">Empresa</th>
                <th className="px-3 py-2.5 font-medium">Acesso</th>
                <th className="px-3 py-2.5 font-medium">Certificado</th>
                <th className="px-3 py-2.5 font-medium">Busca</th>
                <th className="px-3 py-2.5 font-medium">Última busca</th>
                <th className="px-3 py-2.5 text-right font-medium">Notas</th>
                <th className="px-4 py-2.5 text-right font-medium">Pendências</th>
              </tr>
            </thead>
            <tbody>
              {lista.data.map((e) => (
                <tr key={e.id} onClick={() => navegar(`/empresas/${e.id}?empresa=${e.id}`)}
                  className={cn("cursor-pointer border-b border-borda last:border-0 hover:bg-superficie-2/60", !e.ativa && "opacity-60")}>
                  <td className="px-4 py-2.5">
                    <Link to={`/empresas/${e.id}?empresa=${e.id}`} onClick={(ev) => ev.stopPropagation()} className="font-medium hover:text-destaque">
                      {nomeExibicao(e)}
                    </Link>
                    {e.is_contabilidade && <span className="ml-2 rounded bg-destaque-suave px-1.5 py-0.5 text-[11px] font-medium text-destaque">Contabilidade</span>}
                    {!e.ativa && <span className="ml-2 text-xs text-texto-2">(inativa)</span>}
                    <div className="font-mono text-xs text-texto-2">{formatarDoc(e.cnpj)}</div>
                  </td>
                  <td className="px-3 py-2.5"><SeloAcesso acesso={e.acesso} /></td>
                  <td className="px-3 py-2.5"><SeloCertificado cert={e.certificado} /></td>
                  <td className="px-3 py-2.5"><SeloBusca situacao={e.busca.situacao} pendente={e.busca.job_pendente} /></td>
                  <td className="px-3 py-2.5 text-texto-2">{formatarDataHora(e.busca.ultima_busca_em)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{e.total_notas.toLocaleString("pt-BR")}</td>
                  <td className={cn("px-4 py-2.5 text-right font-mono tabular-nums", e.pendencias > 0 ? "text-rejeitada" : "text-texto-2")}>
                    {e.pendencias}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
