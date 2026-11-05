import {
  AlertTriangle, BadgeCheck, CircleDashed, Clock, KeyRound, Loader2, ShieldAlert, ShieldCheck, ShieldX, Users, type LucideIcon,
  Gauge,
} from "lucide-react";
import type { Certificado, Empresa, SituacaoBusca } from "@/lib/api";
import { formatarData } from "@/lib/formato";
import { cn } from "@/lib/utils";
import { Dica } from "./ui/tooltip";

type Tom = "ok" | "alerta" | "erro" | "neutro" | "destaque";
const TONS: Record<Tom, string> = {
  ok: "bg-autorizada-suave text-autorizada",
  alerta: "bg-rejeitada-suave text-rejeitada",
  erro: "bg-cancelada-suave text-cancelada",
  neutro: "bg-superficie-2 text-texto-2",
  destaque: "bg-destaque-suave text-destaque",
};

/** Sempre ícone + texto: nunca só cor. */
export function Selo({ tom, icone: Icone, children, className }: { tom: Tom; icone: LucideIcon; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-md px-2 text-xs font-medium", TONS[tom], className)}>
      <Icone className="size-3.5 shrink-0" aria-hidden />
      {children}
    </span>
  );
}

export function SeloCertificado({ cert }: { cert: Certificado | null }) {
  if (!cert) return <Selo tom="erro" icone={ShieldX}>Sem certificado</Selo>;
  const dica = `${cert.tipo} de ${cert.titular_nome}, válido até ${formatarData(cert.validade)}`;
  const [tom, icone, texto]: [Tom, LucideIcon, string] =
    cert.situacao === "vencido" ? ["erro", ShieldX, `Vencido em ${formatarData(cert.validade)}`]
    : cert.situacao === "ok" ? ["ok", ShieldCheck, `Até ${formatarData(cert.validade)}`]
    : ["alerta", ShieldAlert, `Vence em ${cert.dias_restantes} dia${cert.dias_restantes === 1 ? "" : "s"}`];
  return (
    <Dica texto={dica} lado="top">
      <span tabIndex={0} className="rounded-md"><Selo tom={tom} icone={icone}>{texto}</Selo></span>
    </Dica>
  );
}

export function SeloAcesso({ acesso }: { acesso: Empresa["acesso"] }) {
  const m: Record<Empresa["acesso"], [Tom, LucideIcon, string]> = {
    proprio: ["neutro", KeyRound, "Certificado próprio"],
    mesma_raiz: ["neutro", KeyRound, "Mesma raiz"],
    procuracao: ["destaque", Users, "Procuração"],
    sem_certificado: ["erro", ShieldX, "Sem certificado"],
  };
  const [tom, icone, texto] = m[acesso];
  return <Selo tom={tom} icone={icone}>{texto}</Selo>;
}

export function SeloBusca({ situacao, pendente }: { situacao: SituacaoBusca; pendente?: boolean }) {
  if (situacao === "buscando") return <Selo tom="destaque" icone={Loader2} className="[&_svg]:animate-spin">Buscando</Selo>;
  const m: Record<SituacaoBusca, [Tom, LucideIcon, string]> = {
    nunca_buscada: pendente ? ["neutro", Clock, "Busca agendada"] : ["neutro", CircleDashed, "Nunca buscada"],
    buscando: ["destaque", Loader2, "Buscando"],
    em_dia: ["ok", BadgeCheck, "Em dia"],
    sem_procuracao: ["alerta", AlertTriangle, "Procuração pendente"],
    erro_certificado: ["erro", ShieldX, "Erro de certificado"],
    erro: ["erro", AlertTriangle, "Erro na busca"],
    limite_mes: ["alerta", Gauge, "Limite do mês"],
  };
  const [tom, icone, texto] = m[situacao];
  return <Selo tom={tom} icone={icone}>{texto}</Selo>;
}
