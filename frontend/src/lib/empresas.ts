import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type Empresa } from "./api";
import { gravarLocal, lerLocal } from "./utils";

const CHAVE = "contask-empresa";

export function useEmpresas() {
  return useQuery({ queryKey: ["empresas"], queryFn: () => api<Empresa[]>("/api/empresas") });
}

export function useContabilidade() {
  return useQuery({ queryKey: ["contabilidade"], queryFn: () => api<Empresa | null>("/api/contabilidade") });
}

/** Invalida tudo que depende do cadastro de empresas. */
export function useAtualizarEmpresas() {
  const qc = useQueryClient();
  return useCallback(() => {
    qc.invalidateQueries({ queryKey: ["empresas"] });
    qc.invalidateQueries({ queryKey: ["empresa"] });
    qc.invalidateQueries({ queryKey: ["contabilidade"] });
    qc.invalidateQueries({ queryKey: ["saude"] });
  }, [qc]);
}

/**
 * Empresa selecionada: fica na URL (?empresa=<id>) e é lembrada no navegador.
 * Trocar de empresa mantém a página atual.
 */
export function useEmpresaSelecionada() {
  const [params, setParams] = useSearchParams();
  const { data: empresas, isLoading, isFetching } = useEmpresas();
  const daUrl = Number(params.get("empresa")) || null;

  const selecionar = useCallback(
    (id: number | null) => {
      setParams(
        (p) => {
          const n = new URLSearchParams(p);
          if (id) n.set("empresa", String(id));
          else n.delete("empresa");
          return n;
        },
        { replace: true },
      );
      if (id) gravarLocal(CHAVE, String(id));
    },
    [setParams],
  );

  // Sem empresa na URL: usa a última escolhida ou a primeira ativa que não seja a contabilidade
  useEffect(() => {
    if (!empresas || empresas.length === 0) return;
    const existe = (id: number | null) => id !== null && empresas.some((e) => e.id === id);
    if (existe(daUrl)) {
      gravarLocal(CHAVE, String(daUrl));
      return;
    }
    // A empresa da URL pode ter acabado de ser criada: espera a lista recarregar antes de trocar
    if (daUrl !== null && isFetching) return;
    const lembrada = Number(lerLocal(CHAVE)) || null;
    const padrao = existe(lembrada)
      ? lembrada
      : (empresas.find((e) => e.ativa && !e.is_contabilidade) ?? empresas[0]).id;
    selecionar(padrao);
  }, [empresas, daUrl, isFetching, selecionar]);

  const empresa = empresas?.find((e) => e.id === daUrl) ?? null;
  return { empresa, empresas: empresas ?? [], carregando: isLoading, selecionar };
}

export function nomeExibicao(e: Pick<Empresa, "apelido" | "nome_fantasia" | "razao_social">) {
  return e.apelido || e.nome_fantasia || e.razao_social;
}
