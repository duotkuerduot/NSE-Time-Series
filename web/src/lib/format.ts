// All number and date formatting lives here (ENGINEERING.md 23.4). Session dates are plain
// local dates ("2026-10-07") and are formatted in UTC so no time zone can shift them a day.

const MINUS = "−";
const kes2 = new Intl.NumberFormat("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int = new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 });

export const NO_CHANGE_BAND = 0.001; // ±0.1%: "≈ no change" (24.5)

export function formatPrice(value: number): string {
  return kes2.format(value);
}

export function formatKes(value: number): string {
  return `KES ${kes2.format(value)}`;
}

export function formatCompactKes(value: number): string {
  if (value >= 1e9) return `KES ${(value / 1e9).toFixed(1)}bn`;
  if (value >= 1e6) return `KES ${Math.round(value / 1e6)}m`;
  if (value >= 1e3) return `KES ${Math.round(value / 1e3)}k`;
  return `KES ${int.format(value)}`;
}

export function formatInt(value: number): string {
  return int.format(value);
}

/** 0.0124 -> "+1.24%", -0.0073 -> "−0.73%" (true minus sign), 0 -> "0.00%". */
export function formatPct(fraction: number, digits = 2): string {
  const text = Math.abs(fraction * 100).toFixed(digits);
  if (Number(text) === 0) return `${(0).toFixed(digits)}%`;
  return `${fraction > 0 ? "+" : MINUS}${text}%`;
}

/** Colour is never the only cue: a change always carries an arrow and a sign (24.8). */
export function formatChange(fraction: number): { text: string; direction: "up" | "down" | "flat" } {
  const text = formatPct(fraction);
  if (text.startsWith("+")) return { text: `▲ ${text}`, direction: "up" };
  if (text.startsWith(MINUS)) return { text: `▼ ${text}`, direction: "down" };
  return { text, direction: "flat" };
}

export function forecastChangeText(predictedReturn: number): string {
  return Math.abs(predictedReturn) < NO_CHANGE_BAND
    ? "≈ no change expected"
    : `${formatPct(predictedReturn)} from last close`;
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-07" -> "Wed 7 Oct 2026". Built by hand so every browser prints the same words. */
export function formatSessionDate(iso: string, withYear = true): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) throw new Error(`not a session date: ${iso}`);
  const weekday = WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
  return `${weekday} ${d} ${MONTHS[m - 1]}${withYear ? ` ${y}` : ""}`;
}

/** +0.87 or −0.35: an absolute price change, always signed. */
export function formatSignedPrice(value: number): string {
  const text = formatPrice(Math.abs(value));
  if (Number(text) === 0) return formatPrice(0);
  return `${value > 0 ? "+" : MINUS}${text}`;
}

/** An ISO timestamp shown in Nairobi time: "7 Oct 2026, 18:47 EAT". */
export function formatEat(isoTimestamp: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    hourCycle: "h23", timeZone: "Africa/Nairobi",
  }).formatToParts(new Date(isoTimestamp));
  const pick = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${pick("day")} ${pick("month")} ${pick("year")}, ${pick("hour")}:${pick("minute")} EAT`;
}
