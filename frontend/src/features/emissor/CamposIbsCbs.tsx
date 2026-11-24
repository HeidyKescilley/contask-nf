import { Loader2 } from "lucide-react";
import { Aviso, Campo, Select } from "@/components/ui/campos";
import { useOpcoesIbsCbs, type OpcaoCClassTrib, type OpcaoCIndOp } from "@/lib/emissor";
import { cn } from "@/lib/utils";

const curto = (t: string, n = 80) => (t.length > n ? `${t.slice(0, n - 1)}…` : t);
const textoIndOp = (c: OpcaoCIndOp) => `${c.codigo} · ${curto(`${c.tipo}: ${c.caracteristica}`)}`;
const textoClass = (c: OpcaoCClassTrib) => `${c.codigo} · ${curto(c.nome)}`;

/** cIndOp e cClassTrib (grupo IBS/CBS) escolhidos nas listas oficiais da NFS-e, com os sugeridos para o
 *  serviço (Anexo VIII) primeiro. `padrao*`: o que vale quando o campo fica em branco (os códigos do serviço). */
export function CamposIbsCbs({ ctribnac, cnbs, cindop, cclasstrib, aoMudar, obrigatorio, padraoCindop, padraoCclasstrib, className }: {
  ctribnac?: string | null; cnbs?: string | null;
  cindop: string; cclasstrib: string;
  aoMudar: (campos: { cindop?: string; cclasstrib?: string }) => void;
  obrigatorio?: boolean;
  padraoCindop?: string | null; padraoCclasstrib?: string | null;
  className?: string;
}) {
  const q = useOpcoesIbsCbs(ctribnac, cnbs);
  if (q.isError) {
    return <Aviso tom="erro">Não foi possível carregar as listas de cIndOp e cClassTrib: {(q.error as Error).message}{" "}
      <button type="button" className="underline" onClick={() => q.refetch()}>Tentar de novo</button></Aviso>;
  }
  const ind = q.data?.cindop ?? [];
  const cls = q.data?.cclasstrib ?? [];
  const indAtual = ind.find((c) => c.codigo === (cindop || padraoCindop));
  const clsAtual = cls.find((c) => c.codigo === (cclasstrib || padraoCclasstrib));
  const sugInd = ind.filter((c) => c.sugerido);
  const sugCls = cls.filter((c) => c.sugerido);
  // Map (não objeto): chaves como "200" passariam na frente de "000" num objeto
  const porCst = new Map<string, OpcaoCClassTrib[]>();
  for (const c of cls.filter((x) => !x.sugerido).sort((a, b) => a.codigo.localeCompare(b.codigo)))
    porCst.set(c.cst, [...(porCst.get(c.cst) ?? []), c]);
  const carregando = q.isLoading && <option value="">Carregando a tabela…</option>;
  const branco = (padrao: string | null | undefined, rot: string) =>
    <option value="">{padrao ? `Do serviço (${padrao})` : obrigatorio ? `Escolha o ${rot}…` : "Não informar"}</option>;
  const fora = (v: string, lista: { codigo: string }[]) => v && q.data && !lista.some((c) => c.codigo === v)
    ? <option value={v}>{v} · fora da tabela da NFS-e</option> : null;

  return (
    <div className={cn("grid gap-3 sm:grid-cols-2", className)}>
      <Campo rotulo="cIndOp: indicador da operação" obrigatorio={obrigatorio}
        ajuda={indAtual ? <>Local de incidência do IBS/CBS: <strong className="font-medium text-texto">{indAtual.incidencia}</strong>
          {indAtual.exige_endereco_tomador && " (exige o endereço completo do tomador)"}.</>
          : "Tabela oficial da NFS-e (Anexo VII). Os sugeridos vêm da correlação com o serviço (Anexo VIII)."}>
        {(p) => (
          <div className="relative">
            <Select {...p} value={cindop} disabled={q.isLoading} onChange={(e) => aoMudar({ cindop: e.target.value })}>
              {carregando || branco(padraoCindop, "cIndOp")}
              {fora(cindop, ind)}
              {sugInd.length > 0 && <optgroup label="Sugeridos para este serviço">{sugInd.map((c) => <option key={c.codigo} value={c.codigo}>{textoIndOp(c)}</option>)}</optgroup>}
              <optgroup label={sugInd.length ? "Demais indicadores da NFS-e" : "Indicadores da NFS-e"}>
                {ind.filter((c) => !c.sugerido).map((c) => <option key={c.codigo} value={c.codigo}>{textoIndOp(c)}</option>)}
              </optgroup>
            </Select>
            {q.isLoading && <Loader2 className="absolute right-8 top-2.5 size-4 animate-spin text-texto-2" aria-hidden />}
          </div>
        )}
      </Campo>
      <Campo rotulo="cClassTrib: classificação tributária" obrigatorio={obrigatorio}
        ajuda={clsAtual ? <>CST {clsAtual.cst} · {clsAtual.nome_cst}
          {(clsAtual.red_ibs > 0 || clsAtual.red_cbs > 0) && ` · redução de ${clsAtual.red_ibs}% (IBS) e ${clsAtual.red_cbs}% (CBS)`}
          {clsAtual.lei && ` · ${clsAtual.lei}`}.</>
          : "Códigos vigentes para a NFS-e (tabela oficial do IBS/CBS). O CST são os 3 primeiros dígitos."}>
        {(p) => (
          <Select {...p} value={cclasstrib} disabled={q.isLoading} onChange={(e) => aoMudar({ cclasstrib: e.target.value })}>
            {carregando || branco(padraoCclasstrib, "cClassTrib")}
            {fora(cclasstrib, cls)}
            {sugCls.length > 0 && <optgroup label="Sugeridos para este serviço">{sugCls.map((c) => <option key={c.codigo} value={c.codigo}>{textoClass(c)}</option>)}</optgroup>}
            {[...porCst].map(([cst, lista]) => (
              <optgroup key={cst} label={`CST ${cst} · ${lista[0].nome_cst}`}>
                {lista.map((c) => <option key={c.codigo} value={c.codigo}>{textoClass(c)}</option>)}
              </optgroup>
            ))}
          </Select>
        )}
      </Campo>
    </div>
  );
}
