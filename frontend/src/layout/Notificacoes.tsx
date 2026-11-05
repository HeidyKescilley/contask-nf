import { Toaster } from "sonner";
import { useTema } from "@/lib/tema";

export function Notificacoes() {
  const { escuro } = useTema();
  return (
    <Toaster
      theme={escuro ? "dark" : "light"}
      position="bottom-right"
      richColors
      closeButton
      duration={6000}
      toastOptions={{ style: { fontFamily: "var(--font-sans)", borderRadius: "10px" } }}
    />
  );
}
