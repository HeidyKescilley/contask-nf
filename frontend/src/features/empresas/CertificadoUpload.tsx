import { useMutation } from "@tanstack/react-query";
import { Eye, EyeOff, FileKey2, Loader2, ShieldCheck, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { SeloCertificado } from "@/components/selos";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input } from "@/components/ui/campos";
import { apiForm, type Certificado } from "@/lib/api";
import { formatarData, formatarDoc, limparCnpj } from "@/lib/formato";

export interface CertificadoEscolhido {
  arquivo: File;
  senha: string;
  info: Certificado;
}

/** Escolhe .pfx + senha e valida no servidor (sem gravar). */
export function CertificadoUpload({ cnpjEmpresa, valor, onChange }: {
  cnpjEmpresa?: string;
  valor: CertificadoEscolhido | null;
  onChange: (v: CertificadoEscolhido | null) => void;
}) {
  const [arquivo, setArquivo] = useState<File | null>(valor?.arquivo ?? null);
  const [senha, setSenha] = useState(valor?.senha ?? "");
  const [ver, setVer] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);

  const validar = useMutation({
    mutationFn: () => apiForm<Certificado>("/api/certificados/validar", { arquivo, senha }),
    onSuccess: (info) => onChange({ arquivo: arquivo!, senha, info }),
    onError: () => onChange(null),
  });

  const trocar = () => {
    onChange(null);
    validar.reset();
  };

  const info = valor?.info;
  const outraRaiz = info && cnpjEmpresa && info.tipo === "e-CNPJ" &&
    limparCnpj(info.titular_doc).slice(0, 8) !== limparCnpj(cnpjEmpresa).slice(0, 8);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-[1fr_220px_auto] items-end gap-3">
        <Campo rotulo="Arquivo do certificado (.pfx ou .p12)">
          {(p) => (
            <>
              <input
                ref={entrada}
                type="file"
                accept=".pfx,.p12,application/x-pkcs12"
                className="sr-only"
                {...p}
                onChange={(e) => {
                  setArquivo(e.target.files?.[0] ?? null);
                  trocar();
                }}
              />
              <button
                type="button"
                onClick={() => entrada.current?.click()}
                className="flex h-9 w-full items-center gap-2 rounded-xl border border-dashed border-borda-forte bg-fundo px-3 text-left text-sm hover:border-destaque"
              >
                {arquivo ? <FileKey2 className="size-4 text-destaque" aria-hidden /> : <Upload className="size-4 text-texto-2" aria-hidden />}
                <span className={arquivo ? "truncate" : "text-texto-2"}>{arquivo ? arquivo.name : "Escolher arquivo…"}</span>
              </button>
            </>
          )}
        </Campo>
        <Campo rotulo="Senha do certificado">
          {(p) => (
            <div className="relative">
              <Input
                {...p}
                type={ver ? "text" : "password"}
                autoComplete="off"
                value={senha}
                onChange={(e) => {
                  setSenha(e.target.value);
                  if (valor) trocar();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && arquivo && senha) {
                    e.preventDefault();
                    validar.mutate();
                  }
                }}
                className="pr-9"
              />
              <button
                type="button"
                onClick={() => setVer((v) => !v)}
                className="absolute right-1.5 top-1.5 rounded-md p-1 text-texto-2 hover:text-texto"
                aria-label={ver ? "Ocultar senha" : "Mostrar senha"}
              >
                {ver ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          )}
        </Campo>
        <Button type="button" onClick={() => validar.mutate()} disabled={!arquivo || !senha || validar.isPending || !!valor}>
          {validar.isPending ? <Loader2 className="animate-spin" /> : <ShieldCheck />}
          {valor ? "Validado" : "Validar"}
        </Button>
      </div>

      {validar.isError && <Aviso tom="erro">{(validar.error as Error).message}</Aviso>}

      {info && (
        <div className="rounded-xl border border-borda bg-fundo p-3.5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-medium">{info.titular_nome}</div>
              <div className="mt-0.5 font-mono text-[13px] text-texto-2">
                {info.tipo} · {formatarDoc(info.titular_doc)}
              </div>
              <div className="mt-1 text-xs text-texto-2">
                Emitido por {info.emissor || "—"}
                {info.responsavel && <> · responsável {info.responsavel}</>} · válido até {formatarData(info.validade)}
              </div>
            </div>
            <SeloCertificado cert={info} />
          </div>
          {info.situacao === "vencido" && <div className="mt-3"><Aviso tom="erro">Este certificado está vencido e não pode ser usado.</Aviso></div>}
          {outraRaiz && (
            <div className="mt-3">
              <Aviso>
                O certificado é de outra raiz de CNPJ. A busca só funciona se a empresa tiver outorgado procuração a
                esse titular.
              </Aviso>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
