export class ErroApi extends Error {
  constructor(public status: number, mensagem: string) {
    super(mensagem);
  }
}

async function tratar<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try {
      const d = await r.json();
      if (typeof d?.detail === "string") msg = d.detail;
    } catch {
      /* corpo sem JSON */
    }
    const rotaLogin = new URL(r.url, window.location.origin).pathname.startsWith("/api/auth/");
    if (!rotaLogin && (r.status === 401 || (r.status === 403 && msg.startsWith("Troque a senha"))))
      window.dispatchEvent(new Event("contask:sessao"));
    throw new ErroApi(r.status, msg);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

async function chamar(caminho: string, init: RequestInit) {
  try {
    return await fetch(caminho, init);
  } catch {
    throw new ErroApi(0, "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.");
  }
}

export async function api<T>(caminho: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init?.body && typeof init.body === "string") headers["Content-Type"] = "application/json";
  return tratar<T>(await chamar(caminho, { ...init, headers: { ...headers, ...(init?.headers as object) } }));
}

/** Envio multipart (certificado + campos). O navegador define o Content-Type com o boundary. */
export async function apiForm<T>(caminho: string, dados: Record<string, string | Blob | null | undefined>, method = "POST"): Promise<T> {
  const fd = new FormData();
  for (const [k, v] of Object.entries(dados)) if (v !== null && v !== undefined && v !== "") fd.append(k, v);
  return tratar<T>(await chamar(caminho, { method, body: fd, headers: { Accept: "application/json" } }));
}

export interface Saude {
  versao: string;
  banco: { ok: boolean; journal_mode: string };
  chave_mestra: boolean;
  empresas: number;
  tem_contabilidade: boolean;
}

export type SituacaoCert = "ok" | "vence_30" | "vence_15" | "vence_7" | "vencido";

export interface Certificado {
  id: number | null;
  titular_doc: string;
  titular_nome: string;
  tipo: "e-CNPJ" | "e-CPF";
  validade: string;
  dias_restantes: number;
  situacao: SituacaoCert;
  emissor: string | null;
  responsavel: string | null;
}

export type SituacaoBusca = "nunca_buscada" | "buscando" | "em_dia" | "sem_procuracao" | "erro_certificado" | "erro" | "limite_mes" | "limite_teste";

export interface Empresa {
  id: number;
  cnpj: string;
  razao_social: string;
  nome_fantasia: string | null;
  apelido: string | null;
  uf: string | null;
  municipio: string | null;
  situacao_cadastral: string | null;
  is_contabilidade: boolean;
  ativa: boolean;
  modo_certificado: "proprio" | "contabilidade";
  acesso: "proprio" | "mesma_raiz" | "procuracao" | "sem_certificado";
  certificado: Certificado | null;
  busca: {
    situacao: SituacaoBusca;
    ultima_busca_em: string | null;
    ultimo_erro: string | null;
    tipo_consulta: string | null;
    ultimo_nsu: number;
    job_pendente: boolean;
  };
  total_notas: number;
  pendencias: number;
  criado_em: string;
}

export interface EmpresaCriada {
  empresa: Empresa;
  avisos: string[];
}

export interface ConsultaCnpj {
  cnpj: string;
  encontrado: boolean;
  erro: string | null;
  nao_encontrado?: boolean;
  ja_cadastrada: number | null;
  razao_social?: string;
  nome_fantasia?: string | null;
  uf?: string | null;
  municipio?: string | null;
  situacao_cadastral?: string | null;
  aviso?: string | null;
  bruto?: unknown;
}
