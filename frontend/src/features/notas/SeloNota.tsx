import { Ban, CheckCircle2, Hourglass, Lock, XCircle } from "lucide-react";
import { Selo } from "@/components/selos";
import { Dica } from "@/components/ui/tooltip";
import type { Nota } from "@/lib/notas";

const DICA_REJEITADA =
  "Rejeição manifestada pelo prestador, tomador ou intermediário e não anulada. Não é cancelamento: a nota continua existindo, mas foi contestada.";

export function SeloNota({ n }: { n: Pick<Nota, "status" | "status_detalhe" | "em_analise_fiscal" | "bloqueada"> }) {
  const principal =
    n.status === "cancelada" ? <Selo tom="erro" icone={XCircle}>{n.status_detalhe?.includes("substitui") ? "Substituída" : "Cancelada"}</Selo>
    : n.status === "rejeitada" ? <Selo tom="alerta" icone={Ban}>Rejeitada</Selo>
    : <Selo tom="ok" icone={CheckCircle2}>Autorizada</Selo>;
  const dica = n.status === "rejeitada" ? `${n.status_detalhe ?? "Rejeitada"}. ${DICA_REJEITADA}` : n.status_detalhe;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {dica ? <Dica texto={dica} lado="left"><span tabIndex={0} className="rounded-md">{principal}</span></Dica> : principal}
      {n.em_analise_fiscal && (
        <Dica texto="Há uma solicitação de análise fiscal para cancelamento ainda sem decisão. A nota continua autorizada." lado="left">
          <span tabIndex={0} className="rounded-md"><Selo tom="neutro" icone={Hourglass}>Em análise</Selo></span>
        </Dica>
      )}
      {n.bloqueada && (
        <Dica texto="Bloqueada por ofício pelo município: eventos de cancelamento não são aceitos." lado="left">
          <span tabIndex={0} className="rounded-md"><Selo tom="neutro" icone={Lock}>Bloqueada</Selo></span>
        </Dica>
      )}
    </span>
  );
}
