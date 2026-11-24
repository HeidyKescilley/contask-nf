import { useQuery } from "@tanstack/react-query";
import { Campo, Input, Select } from "@/components/ui/campos";
import { api } from "@/lib/api";
import { lerValor, escreverValor, type Tomador } from "@/lib/emissor";

interface Codigo { codigo: string; nome: string }

/** Países (ISO 2, sem o Brasil) e moedas mais usadas (tabela do Banco Central). */
export function useCodigosExterior() {
  return useQuery({
    queryKey: ["emissor", "codigos-exterior"],
    queryFn: () => api<{ paises: Codigo[]; moedas: Codigo[] }>("/api/emissor/codigos/exterior"),
    staleTime: Infinity,
  });
}

export const ehExterior = (t: Partial<Tomador> | null | undefined) => !!t?.pais && t.pais !== "BR";

/** Campos do tomador no exterior: país, NIF (ou o motivo de não ter) e endereço no exterior. */
export function CamposTomadorExterior({ t, mudar }: { t: Tomador; mudar: (campos: Partial<Tomador>) => void }) {
  const q = useCodigosExterior();
  const semNif = !t.nif && !!t.nao_nif;
  const txt = (k: keyof Tomador) => (ev: React.ChangeEvent<HTMLInputElement>) => mudar({ [k]: ev.target.value });
  return (
    <>
      <Campo rotulo="País" obrigatorio className="col-span-6 sm:col-span-3">
        {(p) => (
          <Select {...p} value={t.pais ?? ""} disabled={q.isLoading} onChange={(ev) => mudar({ pais: ev.target.value })}>
            <option value="">{q.isLoading ? "Carregando os países…" : q.isError ? "Não foi possível carregar" : "Escolha o país…"}</option>
            {q.data?.paises.map((x) => <option key={x.codigo} value={x.codigo}>{x.nome}</option>)}
          </Select>
        )}
      </Campo>
      <Campo rotulo="NIF (identificação fiscal no país)" obrigatorio={!semNif} className="col-span-6 sm:col-span-3"
        ajuda="Equivalente ao CNPJ/CPF no país do tomador (ex.: EIN nos EUA, VAT na Europa).">
        {(p) => (
          <div className="space-y-2">
            <Input {...p} value={t.nif ?? ""} maxLength={40} disabled={semNif} onChange={(ev) => mudar({ nif: ev.target.value, nao_nif: "" })} />
            <label className="flex items-center gap-2 text-sm text-texto-2">
              <input type="checkbox" className="size-4 accent-destaque" checked={semNif}
                onChange={(ev) => mudar(ev.target.checked ? { nif: "", nao_nif: "1" } : { nao_nif: "" })} />
              O tomador não tem NIF
            </label>
            {semNif && (
              <Select aria-label="Motivo de não ter NIF" value={t.nao_nif ?? "1"} onChange={(ev) => mudar({ nao_nif: ev.target.value })}>
                <option value="1">Dispensado do NIF</option>
                <option value="2">O país não exige NIF</option>
              </Select>
            )}
          </div>
        )}
      </Campo>
      <Campo rotulo="Nome ou razão social" obrigatorio className="col-span-6">
        {(p) => <Input {...p} value={t.nome} maxLength={300} onChange={txt("nome")} />}
      </Campo>
      <Campo rotulo="Código postal" obrigatorio className="col-span-3 sm:col-span-2">
        {(p) => <Input {...p} value={t.cod_postal ?? ""} maxLength={11} onChange={txt("cod_postal")} placeholder="ZIP, postcode…" />}
      </Campo>
      <Campo rotulo="Cidade" obrigatorio className="col-span-3 sm:col-span-2">
        {(p) => <Input {...p} value={t.cidade ?? ""} maxLength={60} onChange={txt("cidade")} />}
      </Campo>
      <Campo rotulo="Estado, província ou região" obrigatorio className="col-span-6 sm:col-span-2">
        {(p) => <Input {...p} value={t.estado_provincia ?? ""} maxLength={60} onChange={txt("estado_provincia")} />}
      </Campo>
      <Campo rotulo="Logradouro" obrigatorio className="col-span-6 sm:col-span-4">
        {(p) => <Input {...p} value={t.logradouro ?? ""} maxLength={255} onChange={txt("logradouro")} />}
      </Campo>
      <Campo rotulo="Número" obrigatorio className="col-span-6 sm:col-span-2">
        {(p) => <Input {...p} value={t.numero ?? ""} maxLength={60} onChange={txt("numero")} />}
      </Campo>
      <Campo rotulo="Complemento" className="col-span-6 sm:col-span-3">
        {(p) => <Input {...p} value={t.complemento ?? ""} maxLength={156} onChange={txt("complemento")} placeholder="Opcional" />}
      </Campo>
      <Campo rotulo="Bairro ou distrito" obrigatorio className="col-span-6 sm:col-span-3">
        {(p) => <Input {...p} value={t.bairro ?? ""} maxLength={60} onChange={txt("bairro")} />}
      </Campo>
    </>
  );
}

/** Problemas do tomador no exterior para a lista "Confira antes de enviar". */
export function problemasExterior(t: Tomador): string[] {
  const p: string[] = [];
  if (!t.pais) p.push("Escolha o país do tomador no exterior.");
  if (!t.nif?.trim() && !t.nao_nif) p.push("Informe o NIF do tomador ou marque que ele não tem.");
  if (!t.nome.trim()) p.push("Informe o nome do tomador.");
  if (![t.cod_postal, t.cidade, t.estado_provincia, t.logradouro, t.numero, t.bairro].every((x) => x?.trim()))
    p.push("Complete o endereço do tomador no exterior (código postal, cidade, estado, logradouro, número e bairro).");
  return p;
}

// --- Comércio exterior (grupo comExt) -----------------------------------------------------------

export interface ComexForm {
  moeda: string; outraMoeda: string; valorMoeda: string; exportacao: boolean;
  modo: string; vinculo: string; mecPrestador: string; mecTomador: string; movTempBens: string; mdic: boolean;
}

export interface ComexCorpo {
  moeda: string; valor_moeda: string; exportacao: boolean; modo: string; vinculo: string;
  mec_prestador: string; mec_tomador: string; mov_temp_bens: string; mdic: string;
}

/** ISSNet do DF não tem "0 = sem vínculo": o padrão lá é 9 (desconhecido). */
export const comexVazio = (issnet = false): ComexForm => ({
  moeda: "220", outraMoeda: "", valorMoeda: "", exportacao: true, modo: "1", vinculo: issnet ? "9" : "0",
  mecPrestador: "01", mecTomador: "01", movTempBens: "1", mdic: false,
});

const MOEDAS_LISTA = new Set(["220", "978", "540", "470", "425", "706"]);

export function comexDe(c: (Omit<Partial<ComexCorpo>, "valor_moeda"> & { valor_moeda?: string | number }) | null | undefined, issnet = false): ComexForm {
  if (!c) return comexVazio(issnet);
  const moeda = c.moeda ?? "220";
  const valor = lerValor(String(c.valor_moeda ?? ""));
  return {
    moeda: MOEDAS_LISTA.has(moeda) ? moeda : "outra", outraMoeda: MOEDAS_LISTA.has(moeda) ? "" : moeda,
    valorMoeda: isNaN(valor) || !valor ? "" : escreverValor(valor), exportacao: c.exportacao ?? true,
    modo: c.modo ?? "1", vinculo: c.vinculo ?? (issnet ? "9" : "0"), mecPrestador: c.mec_prestador ?? "01",
    mecTomador: c.mec_tomador ?? "01", movTempBens: c.mov_temp_bens ?? "1", mdic: c.mdic === "1",
  };
}

export function comexCorpo(c: ComexForm): ComexCorpo {
  const v = lerValor(c.valorMoeda);
  return {
    moeda: c.moeda === "outra" ? c.outraMoeda : c.moeda, valor_moeda: isNaN(v) ? "" : v.toFixed(2), exportacao: c.exportacao,
    modo: c.modo, vinculo: c.vinculo, mec_prestador: c.mecPrestador, mec_tomador: c.mecTomador,
    mov_temp_bens: c.movTempBens, mdic: c.mdic ? "1" : "0",
  };
}

export function problemasComex(c: ComexForm): string[] {
  const p: string[] = [];
  const v = lerValor(c.valorMoeda);
  if (!(v > 0)) p.push("Informe o valor do serviço na moeda estrangeira.");
  if (c.moeda === "outra" && !/^\d{3}$/.test(c.outraMoeda)) p.push("Informe o código da moeda (3 dígitos da tabela do Banco Central).");
  return p;
}

const MODOS = [["1", "Transfronteiriço (prestado do Brasil para o exterior)"], ["2", "Consumo no Brasil (o tomador veio ao Brasil)"],
  ["3", "Presença comercial no exterior"], ["4", "Movimento temporário de pessoas físicas"]];
const VINCULOS = [["0", "Sem vínculo"], ["1", "Controlada"], ["2", "Controladora"], ["3", "Coligada"], ["4", "Matriz"],
  ["5", "Filial ou sucursal"], ["6", "Outro vínculo"], ["9", "Desconhecido"]];
const MEC_PRESTADOR = [["01", "Nenhum"], ["02", "ACC: adiantamento sobre contrato de câmbio"], ["03", "ACE: adiantamento sobre cambiais entregues"],
  ["04", "BNDES-Exim pós-embarque"], ["05", "BNDES-Exim pré-embarque"], ["06", "FGE: fundo de garantia à exportação"],
  ["07", "PROEX: equalização"], ["08", "PROEX: financiamento"]];
const MEC_TOMADOR = [["01", "Nenhum"], ["02", "Adm. pública e repr. internacional"], ["03", "Aluguéis e arrend. mercantil de máquinas, equip., embarc. e aeronaves"],
  ["04", "Arrend. mercantil de aeronave para transporte aéreo público"], ["05", "Comissão a agentes externos na exportação"],
  ["06", "Armazenagem, movimentação e transporte de carga no exterior"], ["07", "Eventos FIFA (subsidiária)"], ["08", "Eventos FIFA"],
  ["09", "Fretes, arrendamentos de embarcações ou aeronaves e outros"], ["10", "Material aeronáutico"], ["11", "Promoção de bens no exterior"],
  ["12", "Promoção de destinos turísticos brasileiros"], ["13", "Promoção do Brasil no exterior"], ["14", "Promoção de serviços no exterior"],
  ["15", "RECINE"], ["16", "RECOPA"], ["17", "Registro e manutenção de marcas, patentes e cultivares"], ["18", "REICOMP"], ["19", "REIDI"],
  ["20", "REPENEC"], ["21", "REPES"], ["22", "RETAERO"], ["23", "RETID"], ["24", "Royalties, assistência técnica, científica e assemelhados"],
  ["25", "Serviços de avaliação da conformidade vinculados aos acordos da OMC"], ["26", "ZPE"]];
const MOV_BENS = [["1", "Não"], ["2", "Vinculada a declaração de importação"], ["3", "Vinculada a declaração de exportação"]];

/** Grupo comExt da nota: moeda e valor na moeda, exportação e, recolhidos, os demais códigos do leiaute. */
export function CamposComercioExterior({ c, mudar, issnet }: { c: ComexForm; mudar: (x: Partial<ComexForm>) => void; issnet?: boolean }) {
  const q = useCodigosExterior();
  const sel = (k: keyof ComexForm, opcoes: string[][], rotulo: string) => (
    <Campo rotulo={rotulo} className="col-span-6 sm:col-span-3">
      {(p) => (
        <Select {...p} value={String(c[k])} onChange={(ev) => mudar({ [k]: ev.target.value })}>
          {opcoes.filter(([v]) => !(issnet && k === "vinculo" && v === "0")).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
        </Select>
      )}
    </Campo>
  );
  return (
    <div className="col-span-6 rounded-xl border border-borda p-3">
      <p className="mb-3 text-sm font-medium">Comércio exterior</p>
      <div className="grid grid-cols-6 gap-3">
        <Campo rotulo="Moeda" obrigatorio className="col-span-6 sm:col-span-3">
          {(p) => (
            <div className="flex gap-2">
              <Select {...p} value={c.moeda} onChange={(ev) => mudar({ moeda: ev.target.value })}>
                {q.data?.moedas.map((m) => <option key={m.codigo} value={m.codigo}>{m.nome} ({m.codigo})</option>)}
                {!q.data && <option value="220">Dólar dos Estados Unidos (220)</option>}
                <option value="outra">Outra moeda…</option>
              </Select>
              {c.moeda === "outra" && (
                <Input aria-label="Código da moeda no Banco Central" value={c.outraMoeda} inputMode="numeric" maxLength={3}
                  className="w-24 font-mono" placeholder="000" onChange={(ev) => mudar({ outraMoeda: ev.target.value.replace(/\D/g, "") })} />
              )}
            </div>
          )}
        </Campo>
        <Campo rotulo="Valor do serviço na moeda" obrigatorio className="col-span-6 sm:col-span-3" ajuda="O valor em reais vai no campo de valor da nota.">
          {(p) => <Input {...p} value={c.valorMoeda} inputMode="decimal" placeholder="0,00" className="text-right font-mono"
            onChange={(ev) => mudar({ valorMoeda: ev.target.value })}
            onBlur={() => { const v = lerValor(c.valorMoeda); if (!isNaN(v) && v) mudar({ valorMoeda: escreverValor(v) }); }} />}
        </Campo>
        <label className="col-span-6 flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-0.5 size-4 accent-destaque" checked={c.exportacao} onChange={(ev) => mudar({ exportacao: ev.target.checked })} />
          <span>
            Exportação de serviço (sem ISS)
            <span className="block text-xs text-texto-2">
              Marque quando o resultado do serviço acontece no exterior. Serviço feito no Brasil com resultado aqui não é exportação,
              mesmo com tomador estrangeiro: desmarque e a nota sai como operação tributável.
            </span>
          </span>
        </label>
        <details className="col-span-6 rounded-lg bg-superficie-2 px-3 py-2 text-sm">
          <summary className="cursor-pointer text-texto-2">Mais dados de comércio exterior (já preenchidos com o mais comum)</summary>
          <div className="mt-3 grid grid-cols-6 gap-3">
            {sel("modo", MODOS, "Modo de prestação")}
            {sel("vinculo", VINCULOS, "Vínculo entre prestador e tomador")}
            {sel("mecPrestador", MEC_PRESTADOR, "Apoio ao comércio exterior (prestador)")}
            {sel("mecTomador", MEC_TOMADOR, "Apoio ao comércio exterior (tomador)")}
            {sel("movTempBens", MOV_BENS, "Movimentação temporária de bens")}
            <label className="col-span-6 flex items-center gap-2 self-end text-sm sm:col-span-3">
              <input type="checkbox" className="size-4 accent-destaque" checked={c.mdic} onChange={(ev) => mudar({ mdic: ev.target.checked })} />
              Compartilhar com o MDIC (Secretaria de Comércio Exterior)
            </label>
          </div>
        </details>
      </div>
    </div>
  );
}
