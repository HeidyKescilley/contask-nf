export function limparCnpj(v: string) {
  return (v || "").replace(/[^0-9A-Za-z]/g, "").toUpperCase();
}

/** Máscara progressiva XX.XXX.XXX/XXXX-XX (aceita CNPJ alfanumérico). */
export function mascararCnpj(v: string) {
  const c = limparCnpj(v).slice(0, 14);
  let s = c.slice(0, 2);
  if (c.length > 2) s += "." + c.slice(2, 5);
  if (c.length > 5) s += "." + c.slice(5, 8);
  if (c.length > 8) s += "/" + c.slice(8, 12);
  if (c.length > 12) s += "-" + c.slice(12, 14);
  return s;
}

export function formatarDoc(doc: string) {
  const c = limparCnpj(doc);
  if (c.length === 11) return `${c.slice(0, 3)}.${c.slice(3, 6)}.${c.slice(6, 9)}-${c.slice(9)}`;
  if (c.length === 14) return mascararCnpj(c);
  return doc;
}

function dv(base: string, pesos: number[]) {
  const soma = [...base].reduce((s, ch, i) => s + (ch.charCodeAt(0) - 48) * pesos[i], 0);
  const r = soma % 11;
  return r < 2 ? 0 : 11 - r;
}

export function cnpjValido(v: string) {
  const c = limparCnpj(v);
  if (!/^[0-9A-Z]{12}[0-9]{2}$/.test(c) || new Set(c).size === 1) return false;
  return dv(c.slice(0, 12), [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) === Number(c[12]) &&
    dv(c.slice(0, 13), [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) === Number(c[13]);
}

export function formatarData(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}

export function formatarDataHora(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export const UFS = [
  "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
  "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
];
