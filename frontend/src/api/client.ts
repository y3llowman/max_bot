// Клиент API. С пустым VITE_API_URL работает на моках (src/api/mock.ts),
// иначе ходит в бэкенд. Авторизация — по схеме бэкенда: initData из MAX Bridge
// один раз меняется на JWT (POST /user/auth, подпись initData проверяет сервер),
// дальше запросы идут с заголовком Authorization: Bearer <токен>.
// Токен держим только в памяти: при каждом запуске MAX отдаёт свежий initData,
// так что хранить токен между запусками незачем. Контракт эндпоинтов — в README.
import { config, isMock } from "../utils/config";
import { load, save } from "../utils/storage";
import { initData } from "../max/bridge";
import { ApiError, type Api } from "./contract";
import { mockApi, seedMockCache } from "./mock";
import type { Company, DashboardData } from "./types";

export { ApiError } from "./contract";

let token: string | null = null;
let pendingAuth: Promise<string> | null = null;

async function send(method: string, path: string, body?: unknown, bearer?: string): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  try {
    return await fetch(config.apiUrl.replace(/\/$/, "") + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("network", "Нет соединения");
  }
}

/** initData → JWT. Параллельные запросы при запуске ждут одну авторизацию, а не запускают свою. */
function authenticate(): Promise<string> {
  pendingAuth ??= (async () => {
    const data = initData();
    if (!data) throw new ApiError("unauthorized", "Приложение открыто не из MAX");
    const res = await send("POST", "/user/auth", { initData: data });
    if (res.status === 401 || res.status === 400) throw new ApiError("unauthorized", "MAX не подтвердил вход");
    if (!res.ok) throw new ApiError("server", `Ошибка сервера ${res.status}`);
    const json = (await res.json()) as { access_token: string };
    token = json.access_token;
    return token;
  })().finally(() => {
    pendingAuth = null;
  });
  return pendingAuth;
}

async function request<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const used = token ?? (await authenticate());
  const res = await send(method, path, body, used);
  // Токен отозван или сервер перезапущен с другим ключом — входим заново, один раз.
  // Сбрасываем только тот токен, с которым ушёл запрос: если параллельный запрос
  // уже получил новый, повторный вход не нужен.
  if (res.status === 401 && retry) {
    if (token === used) token = null;
    return request<T>(method, path, body, false);
  }
  if (res.status === 401) throw new ApiError("unauthorized", "Сессия не подтверждена");
  if (res.status === 404) throw new ApiError("not_found", "Не найдено");
  if (!res.ok) throw new ApiError("server", `Ошибка сервера ${res.status}`);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const httpApi: Api = {
  session: () =>
    request<Company>("GET", "/session").catch((e: unknown) => {
      if (e instanceof ApiError && e.code === "not_found") return null;
      throw e;
    }),
  connect: (inn) => request("POST", "/session", { inn }),
  dashboard: () => request("GET", "/dashboard"),
  task: (id) => request("GET", `/tasks/${encodeURIComponent(id)}`),
  calendar: (from, to) => request("GET", `/calendar?from=${from}&to=${to}`),
  company: () => request("GET", "/company"),
  refreshCompany: () => request("POST", "/company/refresh"),
  notifications: () => request("GET", "/settings/notifications"),
  saveNotifications: (s) => request("PUT", "/settings/notifications", s),
  markSubmitted: (id) => request("POST", `/tasks/${encodeURIComponent(id)}/submitted`),
  undoSubmitted: (id) => request("DELETE", `/tasks/${encodeURIComponent(id)}/submitted`),
  generateDocument: (id) => request("POST", `/tasks/${encodeURIComponent(id)}/document`),
};

const impl: Api = isMock ? mockApi : httpApi;

const CACHE_KEY = "dashboard-cache";

/** Последний успешный дашборд — для «Показать сохранённые», когда ФНС не отвечает. */
export function cachedDashboard(): DashboardData | null {
  const cached = load<DashboardData>(CACHE_KEY);
  // в демо ?state=error сохранённой версии ещё нет — подкладываем её, чтобы показать S3 целиком
  if (!cached && isMock && config.forcedState === "error") return seedMockCache();
  return cached;
}

export const api: Api = {
  ...impl,
  dashboard: async () => {
    const data = await impl.dashboard();
    save(CACHE_KEY, { ...data, savedAt: data.savedAt ?? new Date().toISOString() });
    return data;
  },
};
