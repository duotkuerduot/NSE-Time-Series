import type { ReactNode } from "react";
import { COPY } from "../lib/copy";

interface Props {
  title: string;
  isPending: boolean;
  error: unknown;
  onRetry: () => void;
  children: ReactNode;
}

/** One section's loading and error states; a failure never blanks the rest of the page (24.6). */
export function Section({ title, isPending, error, onRetry, children }: Props) {
  return (
    <section aria-labelledby={slug(title)}>
      <h2 id={slug(title)}>{title}</h2>
      {error ? (
        <p role="alert">
          {COPY.sectionFailed(title)} <button onClick={onRetry}>{COPY.retry}</button>
        </p>
      ) : isPending ? (
        <p aria-busy="true" className="meta">…</p>
      ) : (
        children
      )}
    </section>
  );
}

const slug = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, "-");
