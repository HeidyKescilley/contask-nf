import { Activity, ArrowDownToLine, Inbox, ArrowUpFromLine, Building2, FileArchive, LayoutDashboard, ReceiptText, Settings, ShieldCheck, type LucideIcon } from "lucide-react";

export interface ItemNav {
  rota: string;
  rotulo: string;
  icone: LucideIcon;
  descricao: string;
}

export const NAVEGACAO: ItemNav[] = [
  { rota: "/dashboard", rotulo: "Dashboard", icone: LayoutDashboard, descricao: "Visão mensal da empresa" },
  { rota: "/tomados", rotulo: "Serviços Tomados", icone: ArrowDownToLine, descricao: "Notas recebidas (entradas)" },
  { rota: "/prestados", rotulo: "Serviços Prestados", icone: ArrowUpFromLine, descricao: "Notas emitidas (saídas)" },
  { rota: "/exportacoes", rotulo: "Exportações", icone: FileArchive, descricao: "ZIP com XMLs e relatório" },
  { rota: "/emissor", rotulo: "Emissor NFS-e", icone: ReceiptText, descricao: "Empresas emissoras, serviços e tomadores" },
  { rota: "/empresas", rotulo: "Empresas", icone: Building2, descricao: "Cadastro, certificados e procurações" },
  { rota: "/configuracoes", rotulo: "Configurações", icone: Settings, descricao: "Sistema e preferências" },
];

/** Conta de empresa: o emissor primeiro e "Minha empresa" no lugar da lista de empresas. */
export const NAVEGACAO_EMPRESA: ItemNav[] = [
  { rota: "/emissor", rotulo: "Emissor NFS-e", icone: ReceiptText, descricao: "Emitir notas, serviços e tomadores" },
  { rota: "/dashboard", rotulo: "Dashboard", icone: LayoutDashboard, descricao: "Visão mensal da empresa" },
  { rota: "/prestados", rotulo: "Notas emitidas", icone: ArrowUpFromLine, descricao: "Serviços prestados (saídas)" },
  { rota: "/tomados", rotulo: "Notas recebidas", icone: ArrowDownToLine, descricao: "Serviços tomados (entradas)" },
  { rota: "/exportacoes", rotulo: "Exportações", icone: FileArchive, descricao: "ZIP com XMLs e relatório" },
  { rota: "/minha-empresa", rotulo: "Minha empresa", icone: Building2, descricao: "Dados e certificado digital" },
  { rota: "/configuracoes", rotulo: "Configurações", icone: Settings, descricao: "Sistema e preferências" },
];

/** Só para o administrador do sistema. */
export const NAV_ADMIN: ItemNav = { rota: "/admin", rotulo: "Administração", icone: ShieldCheck, descricao: "Escritórios e usuários do sistema" };
export const NAV_LEADS: ItemNav = { rota: "/admin/leads", rotulo: "Leads", icone: Inbox, descricao: "Pedidos de teste grátis do site" };
export const NAV_MONITORAMENTO: ItemNav = { rota: "/admin/monitoramento", rotulo: "Monitoramento", icone: Activity, descricao: "Uso da plataforma, gravações e suporte" };
