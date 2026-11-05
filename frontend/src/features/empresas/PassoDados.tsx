import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Aviso, Campo, Input, Select } from "@/components/ui/campos";
import { api, type ConsultaCnpj } from "@/lib/api";
import { cnpjValido, limparCnpj, mascararCnpj, UFS } from "@/lib/formato";

const esquema = z.object({
  cnpj: z.string().refine(cnpjValido, "CNPJ inválido: confira os dígitos."),
  razao_social: z.string().trim().min(1, "Informe a razão social."),
  nome_fantasia: z.string().optional(),
  apelido: z.string().max(100).optional(),
  uf: z.string().optional(),
  municipio: z.string().optional(),
  situacao_cadastral: z.string().optional(),
  dados_brasilapi: z.string().optional(),
});
export type DadosEmpresa = z.infer<typeof esquema>;

export const DADOS_VAZIOS: DadosEmpresa = {
  cnpj: "", razao_social: "", nome_fantasia: "", apelido: "", uf: "", municipio: "", situacao_cadastral: "", dados_brasilapi: "",
};

export function PassoDados({ inicial, aoContinuar, cnpjBloqueado, rotuloContinuar = "Continuar" }: {
  inicial: DadosEmpresa;
  aoContinuar: (d: DadosEmpresa) => void;
  cnpjBloqueado?: boolean;
  rotuloContinuar?: string;
}) {
  const form = useForm<DadosEmpresa>({ resolver: zodResolver(esquema), defaultValues: inicial, mode: "onTouched" });
  const { register, handleSubmit, watch, setValue, formState: { errors } } = form;
  const regCnpj = register("cnpj");
  const cnpj = limparCnpj(watch("cnpj"));
  const valido = cnpjValido(cnpj);
  const preenchidoPara = useRef<string | null>(inicial.dados_brasilapi ? limparCnpj(inicial.cnpj) : null);

  const consulta = useQuery({
    queryKey: ["cnpj", cnpj],
    queryFn: () => api<ConsultaCnpj>(`/api/cnpj/${cnpj}`),
    enabled: valido,
    staleTime: 10 * 60_000,
    retry: false,
  });
  const r = consulta.data;

  // Preenche com a BrasilAPI uma vez por CNPJ (depois disso, o que o usuário digitar vale)
  useEffect(() => {
    if (!r?.encontrado || preenchidoPara.current === r.cnpj) return;
    preenchidoPara.current = r.cnpj;
    const op = { shouldValidate: true, shouldDirty: true };
    setValue("razao_social", r.razao_social ?? "", op);
    setValue("nome_fantasia", r.nome_fantasia ?? "", op);
    setValue("uf", r.uf ?? "", op);
    setValue("municipio", r.municipio ?? "", op);
    setValue("situacao_cadastral", r.situacao_cadastral ?? "", op);
    setValue("dados_brasilapi", JSON.stringify(r.bruto ?? null));
  }, [r, setValue]);

  const jaCadastrada = r?.ja_cadastrada && !cnpjBloqueado;

  return (
    <form onSubmit={handleSubmit((d) => aoContinuar({ ...d, cnpj: limparCnpj(d.cnpj) }))} className="space-y-5" noValidate>
      <div className="grid grid-cols-[260px_1fr] items-start gap-4">
        <Campo rotulo="CNPJ" obrigatorio erro={errors.cnpj?.message} ajuda="Aceita o CNPJ alfanumérico.">
          {(p) => (
            <Input
              {...p}
              {...regCnpj}
              onChange={(e) => {
                e.target.value = mascararCnpj(e.target.value);
                regCnpj.onChange(e);
              }}
              autoFocus={!cnpjBloqueado}
              disabled={cnpjBloqueado}
              placeholder="00.000.000/0000-00"
              className="font-mono"
              inputMode="text"
              autoComplete="off"
            />
          )}
        </Campo>
        <div className="pt-6" aria-live="polite">
          {valido && consulta.isFetching && (
            <span className="inline-flex items-center gap-2 text-sm text-texto-2">
              <Loader2 className="size-4 animate-spin" aria-hidden /> Consultando a BrasilAPI…
            </span>
          )}
          {r?.encontrado && !consulta.isFetching && (
            <span className="inline-flex items-center gap-2 text-sm text-autorizada">
              <CheckCircle2 className="size-4" aria-hidden /> Dados preenchidos pela BrasilAPI. Confira e ajuste se precisar.
            </span>
          )}
        </div>
      </div>

      {jaCadastrada && (
        <Aviso tom="erro">
          Este CNPJ já está cadastrado.{" "}
          <Link to={`/empresas/${r!.ja_cadastrada}`} className="font-medium text-destaque underline">Abrir empresa</Link>
        </Aviso>
      )}
      {r && !r.encontrado && r.erro && <Aviso tom="info">{r.erro}</Aviso>}
      {consulta.isError && <Aviso tom="info">Não foi possível consultar a BrasilAPI. Preencha os dados manualmente.</Aviso>}
      {r?.aviso && <Aviso>{r.aviso} Confira antes de continuar.</Aviso>}

      <div className="grid grid-cols-2 gap-4">
        <Campo rotulo="Razão social" obrigatorio erro={errors.razao_social?.message} className="col-span-2">
          {(p) => <Input {...p} {...register("razao_social")} />}
        </Campo>
        <Campo rotulo="Nome fantasia">{(p) => <Input {...p} {...register("nome_fantasia")} />}</Campo>
        <Campo rotulo="Apelido" ajuda="Como a empresa aparece no seletor.">
          {(p) => <Input {...p} {...register("apelido")} placeholder="Opcional" />}
        </Campo>
        <div className="grid grid-cols-[110px_1fr] gap-4">
          <Campo rotulo="UF">
            {(p) => (
              <Select {...p} {...register("uf")}>
                <option value="">—</option>
                {UFS.map((u) => <option key={u}>{u}</option>)}
              </Select>
            )}
          </Campo>
          <Campo rotulo="Município">{(p) => <Input {...p} {...register("municipio")} />}</Campo>
        </div>
        <Campo rotulo="Situação cadastral" ajuda="Vem da Receita, pela BrasilAPI.">
          {(p) => <Input {...p} {...register("situacao_cadastral")} placeholder="Ex.: ATIVA" />}
        </Campo>
      </div>

      <div className="flex justify-end">
        <Button type="submit" variante="primario" disabled={!!jaCadastrada}>{rotuloContinuar}</Button>
      </div>
    </form>
  );
}
