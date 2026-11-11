import { useState } from "react";
import { Outlet } from "react-router-dom";
import { CentralBuscas } from "@/features/buscas/CentralBuscas";
import { CentralProvider, useEventosTempoReal } from "@/lib/buscas";
import { Aviso } from "@/components/ui/campos";
import { useUso } from "@/lib/sessao";
import { gravarLocal, lerLocal } from "@/lib/utils";
import { BarraLateral } from "./BarraLateral";
import { Topo } from "./Topo";

const CHAVE = "contask-menu-recolhido";

/** Aviso do limite mensal de XMLs do plano (a partir de 80%). */
function AvisoUso() {
  const { data } = useUso();
  const n = (v: number) => v.toLocaleString("pt-BR");
  if (data?.teste)
    return (
      <div className="mb-5">
        <Aviso tom="info">
          {data.teste.concluido
            ? <><strong>Teste grátis:</strong> as {n(data.teste.max_xmls)} primeiras notas já foram buscadas. Confira cada uma e abra o PDF.
              O download dos XMLs, o histórico completo, todas as empresas e as emissões ficam liberados ao assinar o plano: fale com o suporte.</>
            : <><strong>Teste grátis:</strong> {n(data.usados)} de {n(data.teste.max_xmls)} notas buscadas, com {data.teste.max_empresas} empresa,
              e {data.teste.max_emissoes - data.teste.emissoes} emissão de nota disponível. Dá para ver cada nota e abrir o PDF.</>}
        </Aviso>
      </div>
    );
  if (!data || (data.situacao !== "aviso" && data.situacao !== "atingido")) return null;
  return (
    <div className="mb-5">
      <Aviso tom={data.situacao === "atingido" ? "erro" : "alerta"}>
        {data.situacao === "atingido"
          ? <>Limite do plano atingido: {n(data.usados)} de {n(data.limite ?? 0)} XMLs neste mês. As buscas de notas novas
            voltam no dia 1º. Para continuar agora, fale com o suporte e amplie o plano.</>
          : <>Você já usou {n(data.usados)} de {n(data.limite ?? 0)} XMLs do plano neste mês ({data.percentual?.toLocaleString("pt-BR")}%).</>}
      </Aviso>
    </div>
  );
}

export function Estrutura() {
  return (
    <CentralProvider>
      <EstruturaInterna />
      <CentralBuscas />
    </CentralProvider>
  );
}

function EstruturaInterna() {
  useEventosTempoReal();
  const [recolhida, setRecolhida] = useState(() => lerLocal(CHAVE) === "1");
  const alternar = () =>
    setRecolhida((r) => {
      gravarLocal(CHAVE, r ? "0" : "1");
      return !r;
    });

  return (
    <div className="flex min-h-screen">
      <BarraLateral recolhida={recolhida} alternar={alternar} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topo />
        <main className="mx-auto w-full max-w-[1280px] flex-1 px-6 py-6">
          <AvisoUso />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
