import { formatChange } from "../lib/format";

export function ChangeValue({ fraction }: { fraction: number }) {
  const { text, direction } = formatChange(fraction);
  const cls = direction === "up" ? "gain" : direction === "down" ? "loss" : undefined;
  return <span className={cls}>{text}</span>;
}
