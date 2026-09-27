// Подключённая компания. Грузится один раз при запуске; экраны разделов
// ждут её, а без компании уводят на «Подключите компанию».
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, api } from "./api/client";
import type { Company } from "./api/types";

/** unauthorized — вход не подтверждён: приложение открыто не из MAX или initData не прошёл проверку. */
type Status = "loading" | "ready" | "none" | "error" | "unauthorized";

interface Session {
  status: Status;
  company: Company | null;
  setCompany: (company: Company) => void;
  reload: () => void;
}

const SessionContext = createContext<Session>({
  status: "loading",
  company: null,
  setCompany: () => {},
  reload: () => {},
});

export function useSession() {
  return useContext(SessionContext);
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [company, setCompanyState] = useState<Company | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    setStatus("loading");
    api.session().then(
      (c) => {
        if (!alive) return;
        setCompanyState(c);
        setStatus(c ? "ready" : "none");
      },
      (e: unknown) => {
        if (!alive) return;
        setStatus(e instanceof ApiError && e.code === "unauthorized" ? "unauthorized" : "error");
      },
    );
    return () => {
      alive = false;
    };
  }, [attempt]);

  const setCompany = useCallback((c: Company) => {
    setCompanyState(c);
    setStatus("ready");
  }, []);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  return <SessionContext.Provider value={{ status, company, setCompany, reload }}>{children}</SessionContext.Provider>;
}
