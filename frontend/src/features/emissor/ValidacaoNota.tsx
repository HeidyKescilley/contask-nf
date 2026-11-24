import { AlertTriangle, CheckCircle2, Loader2, MinusCircle, ShieldCheck, ShieldQuestion, ShieldX, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import { Selo } from "@/components/selos";
import { Aviso } from "@/components/ui/campos";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import type { CorpoEmissao, Rascunho } from "@/lib/emissor";
import { formatarDataHora } from "@/lib/formato";
import { cn } from "@/lib/utils";

export interface ItemValidacao { id: string; titulo: string; situacao: "ok" | "alerta" | "erro" | "pulado"; detalhe: string }
export interface ResultadoValidacao {
  pronta: boolean; erros: number; alertas: number; ambiente: number | null; canal: string | null; itens: ItemValidacao[];
}

/** Confere a nota sem transmitir. Com rascunho_id, o resultado fica guardado no rascunho. */
export const validarNota = (corpo: CorpoEmissao & { empresa_id: number; rascunho_id?: number | null }) =>
  api<ResultadoValidacao>("/api/emissor/notas/validar", { method: "POST", body: JSON.stringify(corpo) });

const ICONE = {
  ok: [CheckCircle2, "text-autorizada"], alerta: [AlertTriangle, "text-rejeitada"], erro: [XCircle, "text-cancelada"],
  pulado: [MinusCircle, "text-texto-2"],
} as const;
const ROTULO = { ok: "Certo", alerta: "Atenção", erro: "Erro", pulado: "Não se aplica" };

export function veredito(r: { pronta: boolean; alertas: number }) {
  if (!r.pronta) return { tom: "erro" as const, icone: ShieldX, texto: "Não está pronta" };
  if (r.alertas) return { tom: "alerta" as const, icone: ShieldQuestion, texto: "Pronta, com alertas" };
  return { tom: "ok" as const, icone: ShieldCheck, texto: "Pronta para transmitir" };
}

/** Selo da última validação do rascunho (some quando o rascunho é alterado). */
export function SeloValidacao({ v }: { v: Rascunho["validacao"] }) {
  if (!v) return null;
  const x = veredito(v);
  return <span title={`Validada em ${formatarDataHora(v.em)}`}><Selo tom={x.tom} icone={x.icone}>{x.texto}</Selo></span>;
}

export function ValidacaoDialog({ aberto, aoFechar, carregando, erro, resultado, salvaEmRascunho, acoes }: {
  aberto: boolean; aoFechar: () => void; carregando: boolean; erro: string | null; resultado: ResultadoValidacao | null;
  salvaEmRascunho?: boolean; acoes?: ReactNode;
}) {
  const v = resultado ? veredito(resultado) : null;
  return (
    <Dialog open={aberto} onOpenChange={(x) => !x && !carregando && aoFechar()}>
      <DialogContent titulo="Validação da nota"
        descricao="Conferimos tudo o que dá para conferir antes do envio. Nada foi transmitido e nenhum número foi usado.">
        {carregando && (
          <p className="flex items-center gap-2 py-6 text-sm text-texto-2" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden /> Conferindo regras, certificado e parâmetros do município…
          </p>
        )}
        {!carregando && erro && <Aviso tom="erro">{erro}</Aviso>}
        {!carregando && resultado && v && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Selo tom={v.tom} icone={v.icone}>{v.texto}</Selo>
              <span className="text-sm text-texto-2">
                {resultado.erros ? `${resultado.erros} erro(s)` : "Sem erros"}{resultado.alertas ? ` · ${resultado.alertas} alerta(s)` : ""}
              </span>
            </div>
            <ul className="divide-y divide-borda rounded-xl border border-borda">
              {resultado.itens.map((i) => {
                const [Icone, cor] = ICONE[i.situacao];
                return (
                  <li key={i.id} className="flex gap-3 px-3 py-2.5">
                    <Icone className={cn("mt-0.5 size-4 shrink-0", cor)} aria-label={ROTULO[i.situacao]} />
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{i.titulo}</p>
                      <p className="text-sm text-texto-2">{i.detalhe}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="text-xs text-texto-2">
              {resultado.pronta
                ? "A autorização final é da Sefin, que ainda confere cadastros que só ela vê (inscrição municipal, procurações, duplicidade). "
                : "Corrija os erros e valide de novo. "}
              {salvaEmRascunho ? "A nota foi salva como rascunho com este resultado." : ""}
            </p>
          </div>
        )}
        <div className="mt-5 flex flex-wrap justify-end gap-2">{acoes}</div>
      </DialogContent>
    </Dialog>
  );
}
