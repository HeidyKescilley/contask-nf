import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Estrutura } from "@/layout/Estrutura";
import { AssistenteContabilidade } from "@/features/empresas/AssistenteContabilidade";
import { DetalheEmpresa } from "@/features/empresas/DetalheEmpresa";
import { ListaEmpresas } from "@/features/empresas/ListaEmpresas";
import { NovaEmpresa } from "@/features/empresas/NovaEmpresa";
import { ImportarEmpresas } from "@/features/empresas/ImportarEmpresas";
import { PaginaNotas } from "@/features/notas/PaginaNotas";
import { Dashboard } from "@/features/dashboard/Dashboard";
import { Exportacoes } from "@/features/exportacoes/Exportacoes";
import { EmpresaEmissor } from "@/features/emissor/EmpresaEmissor";
import { EmpresasEmissoras } from "@/features/emissor/EmpresasEmissoras";
import { Tomadores } from "@/features/emissor/Tomadores";
import { EmitirNota } from "@/features/emissor/EmitirNota";
import { NotasEmitidas } from "@/features/emissor/NotasEmitidas";
import { EditarRecorrente, Recorrentes } from "@/features/emissor/Recorrentes";
import { Administracao } from "@/features/admin/Administracao";
import { Acessos } from "@/features/admin/Acessos";
import { Leads } from "@/features/admin/Leads";
import { Monitoramento } from "@/features/admin/Monitoramento";
import { Administradores } from "@/features/admin/Administradores";
import { Notificacoes } from "@/layout/Notificacoes";
import { Cadastrar, Entrar, TrocarSenha } from "@/features/acesso/Acesso";
import { Protegido } from "@/lib/sessao";
import { ProtegidoAdmin } from "@/lib/sessaoAdmin";
import { EntrarAdmin, EstruturaAdmin, TrocarSenhaAdmin } from "@/layout/EstruturaAdmin";
import { TemaProvider } from "@/lib/tema";
import {
  Configuracoes, NaoEncontrada,
} from "@/pages/paginas";
import "./index.css";

import { Inicio, MinhaEmpresa, SoContador } from "@/features/empresas/ContaEmpresa";
const consultas = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

const rotas = createBrowserRouter([
  { path: "entrar", element: <Entrar /> },
  { path: "cadastrar", element: <Cadastrar /> },
  { path: "trocar-senha", element: <TrocarSenha /> },
  // Administração: ambiente separado do sistema, com login, sessão e menu próprios
  { path: "admin/entrar", element: <EntrarAdmin /> },
  { path: "admin/senha", element: <ProtegidoAdmin><TrocarSenhaAdmin /></ProtegidoAdmin> },
  {
    path: "admin",
    element: <ProtegidoAdmin><EstruturaAdmin /></ProtegidoAdmin>,
    children: [
      { index: true, element: <Administracao /> },
      { path: "leads", element: <Leads /> },
      { path: "acessos", element: <Acessos /> },
      { path: "monitoramento", element: <Monitoramento /> },
      { path: "administradores", element: <Administradores /> },
      { path: "*", element: <NaoEncontrada /> },
    ],
  },
  {
    element: <Protegido><Estrutura /></Protegido>,
    children: [
      { index: true, element: <Inicio /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "tomados", element: <PaginaNotas key="tomada" papel="tomada" /> },
      { path: "prestados", element: <PaginaNotas key="prestada" papel="prestada" /> },
      { path: "exportacoes", element: <Exportacoes /> },
      { path: "emissor", element: <NotasEmitidas /> },
      { path: "emissor/emitir", element: <EmitirNota /> },
      { path: "emissor/recorrentes", element: <Recorrentes /> },
      { path: "emissor/recorrentes/nova", element: <EditarRecorrente /> },
      { path: "emissor/recorrentes/:id", element: <EditarRecorrente /> },
      { path: "emissor/empresas", element: <EmpresasEmissoras /> },
      { path: "emissor/empresas/:id", element: <EmpresaEmissor /> },
      { path: "emissor/tomadores", element: <Tomadores /> },
      { path: "empresas", element: <SoContador><ListaEmpresas /></SoContador> },
      { path: "empresas/nova", element: <SoContador><NovaEmpresa /></SoContador> },
      { path: "empresas/importar", element: <SoContador><ImportarEmpresas /></SoContador> },
      { path: "empresas/:id", element: <DetalheEmpresa /> },
      { path: "contabilidade", element: <AssistenteContabilidade /> },
      { path: "minha-empresa", element: <MinhaEmpresa /> },
      { path: "configuracoes", element: <Configuracoes /> },
      { path: "*", element: <NaoEncontrada /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TemaProvider>
      <QueryClientProvider client={consultas}>
        <TooltipProvider delayDuration={300}>
          <RouterProvider router={rotas} />
          <Notificacoes />
        </TooltipProvider>
      </QueryClientProvider>
    </TemaProvider>
  </StrictMode>,
);
