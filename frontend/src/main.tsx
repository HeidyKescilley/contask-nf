import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
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
import { Notificacoes } from "@/layout/Notificacoes";
import { Entrar, TrocarSenha } from "@/features/acesso/Acesso";
import { Protegido } from "@/lib/sessao";
import { TemaProvider } from "@/lib/tema";
import {
  Configuracoes, NaoEncontrada,
} from "@/pages/paginas";
import "./index.css";

const consultas = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

const rotas = createBrowserRouter([
  { path: "entrar", element: <Entrar /> },
  { path: "trocar-senha", element: <TrocarSenha /> },
  {
    element: <Protegido><Estrutura /></Protegido>,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "tomados", element: <PaginaNotas key="tomada" papel="tomada" /> },
      { path: "prestados", element: <PaginaNotas key="prestada" papel="prestada" /> },
      { path: "exportacoes", element: <Exportacoes /> },
      { path: "empresas", element: <ListaEmpresas /> },
      { path: "empresas/nova", element: <NovaEmpresa /> },
      { path: "empresas/importar", element: <ImportarEmpresas /> },
      { path: "empresas/:id", element: <DetalheEmpresa /> },
      { path: "contabilidade", element: <AssistenteContabilidade /> },
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
