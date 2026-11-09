import { ArrowDownToLine, ArrowUpFromLine, Building2, FileArchive, LayoutDashboard, ReceiptText, Settings, type LucideIcon } from "lucide-react";

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
