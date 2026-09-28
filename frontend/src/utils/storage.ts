// localStorage может бросить исключение (приватный режим, запрет куки в WebView),
// поэтому каждое обращение — в try/catch, а приложение работает и без хранилища.

export function load<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function save(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* без хранилища просто не запоминаем */
  }
}
