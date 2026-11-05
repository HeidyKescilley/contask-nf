import * as DM from "@radix-ui/react-dropdown-menu";
import { AlertTriangle, Building2, Check, ChevronsUpDown, Plus, Search, Settings2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Esqueleto } from "@/components/estados";
import type { Empresa } from "@/lib/api";
import { nomeExibicao, useEmpresaSelecionada } from "@/lib/empresas";
import { formatarDoc, limparCnpj } from "@/lib/formato";
import { cn } from "@/lib/utils";

const normalizar = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

/** Ponto de situação: certificado e busca (sempre com texto alternativo). */
function Situacao({ e }: { e: Empresa }) {
  const c = e.certificado?.situacao;
  const problema = !e.certificado || c === "vencido" || e.busca.situacao === "sem_procuracao" ||
    e.busca.situacao === "erro_certificado" || e.busca.situacao === "erro";
  const alerta = !problema && (c === "vence_7" || c === "vence_15" || c === "vence_30");
  const texto = !e.certificado ? "Sem certificado"
    : c === "vencido" ? "Certificado vencido"
    : e.busca.situacao === "sem_procuracao" ? "Procuração pendente"
    : e.busca.situacao.startsWith("erro") ? "Erro na busca"
    : alerta ? `Certificado vence em ${e.certificado.dias_restantes} dia(s)`
    : e.busca.situacao === "em_dia" ? "Em dia" : e.busca.job_pendente ? "Busca agendada" : "Nunca buscada";
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs", problema ? "text-cancelada" : alerta ? "text-rejeitada" : "text-texto-2")}>
      {(problema || alerta) && <AlertTriangle className="size-3" aria-hidden />}
      {texto}
    </span>
  );
}

export function SeletorEmpresa() {
  const { empresa, empresas, carregando, selecionar } = useEmpresaSelecionada();
  const [termo, setTermo] = useState("");
  const [aberto, setAberto] = useState(false);
  const busca = useRef<HTMLInputElement>(null);
  const navegar = useNavigate();

  // O Radix foca o menu ao abrir; depois disso, o foco vai para a busca (digitar já filtra)
  useEffect(() => {
    if (!aberto) return;
    const t = setTimeout(() => busca.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [aberto]);

  const filtradas = useMemo(() => {
    const t = normalizar(termo.trim());
    const doc = limparCnpj(termo);
    if (!t) return empresas;
    return empresas.filter((e) =>
      normalizar(`${e.razao_social} ${e.nome_fantasia ?? ""} ${e.apelido ?? ""}`).includes(t) || (doc && e.cnpj.includes(doc)));
  }, [empresas, termo]);

  if (carregando) return <Esqueleto className="h-10 w-80" />;

  if (empresas.length === 0) {
    return (
      <Link to="/contabilidade" className="flex h-10 w-80 min-w-0 shrink items-center gap-3 rounded-xl border border-dashed border-borda-forte px-3 hover:border-destaque">
        <Building2 className="size-4 shrink-0 text-texto-2" aria-hidden />
        <div className="min-w-0 leading-tight">
          <div className="truncate text-sm font-medium">Nenhuma empresa cadastrada</div>
          <div className="truncate text-xs text-texto-2">Cadastre a contabilidade para começar</div>
        </div>
      </Link>
    );
  }

  return (
    <DM.Root open={aberto} onOpenChange={(a) => { setAberto(a); if (!a) setTermo(""); }}>
      <DM.Trigger
        className="flex h-10 w-80 min-w-0 shrink items-center gap-3 rounded-xl border border-borda bg-superficie px-3 text-left transition-colors duration-150 hover:border-borda-forte data-[state=open]:border-destaque"
        aria-label={`Empresa selecionada: ${empresa ? nomeExibicao(empresa) : "nenhuma"}. Trocar empresa`}
        data-testid="seletor-empresa"
      >
        <div className="flex size-6 shrink-0 items-center justify-center rounded-md bg-destaque-suave text-destaque">
          <Building2 className="size-3.5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="truncate text-sm font-medium">{empresa ? nomeExibicao(empresa) : "Selecione uma empresa"}</div>
          {empresa && (
            <div className="flex items-center gap-2 truncate">
              <span className="font-mono text-xs text-texto-2">{formatarDoc(empresa.cnpj)}</span>
              <Situacao e={empresa} />
            </div>
          )}
        </div>
        <ChevronsUpDown className="size-4 shrink-0 text-texto-2" aria-hidden />
      </DM.Trigger>

      <DM.Portal>
        <DM.Content align="start" sideOffset={6}
          className="z-50 w-[400px] rounded-xl border border-borda bg-superficie p-1.5 text-texto shadow-[0_12px_32px_-12px_rgb(0_0_0/0.3)]">
          <div className="relative mb-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-texto-2" aria-hidden />
            <input
              ref={busca}
              value={termo}
              onChange={(e) => setTermo(e.target.value)}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === "ArrowDown") (e.currentTarget.closest("[role=menu]")?.querySelector("[role=menuitem]") as HTMLElement | null)?.focus();
                if (e.key === "Escape") setAberto(false);
                if (e.key === "Enter" && filtradas[0]) { selecionar(filtradas[0].id); setAberto(false); }
              }}
              placeholder="Buscar por nome ou CNPJ"
              aria-label="Buscar empresa"
              className="h-9 w-full rounded-lg bg-fundo pl-8 pr-2 text-sm outline-none placeholder:text-texto-2"
            />
          </div>
          <div className="max-h-80 overflow-auto">
            {filtradas.length === 0 && <div className="px-3 py-5 text-center text-sm text-texto-2">Nenhuma empresa encontrada.</div>}
            {filtradas.map((e) => (
              <DM.Item key={e.id} onSelect={() => selecionar(e.id)}
                className="flex cursor-default items-center gap-3 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-superficie-2">
                <div className="min-w-0 flex-1">
                  <div className={cn("truncate text-sm", e.id === empresa?.id && "font-medium")}>
                    {nomeExibicao(e)}
                    {e.is_contabilidade && <span className="ml-1.5 text-[11px] text-destaque">Contabilidade</span>}
                    {!e.ativa && <span className="ml-1.5 text-[11px] text-texto-2">inativa</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-texto-2">{formatarDoc(e.cnpj)}</span>
                    <Situacao e={e} />
                  </div>
                </div>
                {e.id === empresa?.id && <Check className="size-4 text-destaque" aria-hidden />}
              </DM.Item>
            ))}
          </div>
          <DM.Separator className="my-1.5 h-px bg-borda" />
          <DM.Item onSelect={() => navegar("/empresas/nova")} className="flex cursor-default items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-superficie-2">
            <Plus className="size-4 text-texto-2" aria-hidden /> Nova empresa
          </DM.Item>
          <DM.Item onSelect={() => navegar("/empresas")} className="flex cursor-default items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-superficie-2">
            <Settings2 className="size-4 text-texto-2" aria-hidden /> Gerenciar empresas
          </DM.Item>
        </DM.Content>
      </DM.Portal>
    </DM.Root>
  );
}
