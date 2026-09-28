// Проверка ИНН: длина (10 — организация, 12 — ИП) и контрольные цифры.
// Контрольные цифры ловят опечатку до запроса в ФНС — иначе пользователь
// ждал бы ответа реестра, чтобы узнать, что перепутал цифру.

export type InnCheck =
  | { ok: true; kind: "org" | "ip" }
  | { ok: false; reason: "empty" | "length" | "checksum"; length: number };

const W10 = [2, 4, 10, 3, 5, 9, 4, 6, 8];
const W11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8];
const W12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8];

function control(digits: number[], weights: number[]): number {
  const sum = weights.reduce((acc, w, i) => acc + w * digits[i], 0);
  return (sum % 11) % 10;
}

export function checkInn(value: string): InnCheck {
  const length = value.length;
  if (length === 0) return { ok: false, reason: "empty", length };
  if (!/^\d+$/.test(value) || (length !== 10 && length !== 12)) {
    return { ok: false, reason: "length", length };
  }
  const d = value.split("").map(Number);
  if (length === 10) {
    return control(d, W10) === d[9] ? { ok: true, kind: "org" } : { ok: false, reason: "checksum", length };
  }
  const ok = control(d, W11) === d[10] && control(d, W12) === d[11];
  return ok ? { ok: true, kind: "ip" } : { ok: false, reason: "checksum", length };
}

export function innError(check: InnCheck): string | null {
  if (check.ok || check.reason === "empty") return null;
  if (check.reason === "length") {
    return `Нужно 10 цифр для организации или 12 для ИП. Сейчас — ${check.length}`;
  }
  return "Похоже, в ИНН опечатка — проверьте цифры";
}

/** ИНН из QR-кода счёта или письма налоговой: поле PayeeINN, иначе первая
 *  отдельно стоящая группа из 10 или 12 цифр. */
export function innFromQr(text: string): string | null {
  const payee = /PayeeINN=(\d{10}|\d{12})(?!\d)/i.exec(text);
  if (payee) return payee[1];
  const loose = /(?<!\d)(\d{12}|\d{10})(?!\d)/.exec(text);
  return loose ? loose[1] : null;
}
