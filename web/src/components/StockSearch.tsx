import { useId, useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import { useNavigate } from "react-router";
import { useStocks } from "../api/hooks";
import { COPY } from "../lib/copy";
import { formatPrice } from "../lib/format";
import { search } from "../lib/search";

/** Combobox following the ARIA pattern: arrows move, Enter opens, Escape clears (24.3).
 * On the homepage the label doubles as the page's h1 (24.2: search is the primary action). */
export function StockSearch({
  autoFocus = false,
  asHeading = false,
}: {
  autoFocus?: boolean;
  asHeading?: boolean;
}) {
  const stocks = useStocks();
  const navigate = useNavigate();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const results = useMemo(() => search(stocks.data?.items ?? [], query), [stocks.data, query]);
  const open = query.trim().length > 0;

  const go = (ticker: string) => {
    setQuery("");
    navigate(`/stocks/${ticker}`);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && results[active]) {
      go(results[active].ticker);
    } else if (event.key === "Escape") {
      setQuery("");
    }
  };

  return (
    <div className="search">
      {asHeading ? (
        <h1>
          <label htmlFor={`${listId}-input`}>{COPY.searchLabel}</label>
        </h1>
      ) : (
        <label htmlFor={`${listId}-input`}>{COPY.searchLabel}</label>
      )}
      <input
        id={`${listId}-input`}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && results[active] ? `${listId}-${results[active].ticker}` : undefined}
        placeholder={COPY.searchPlaceholder}
        autoComplete="off"
        autoFocus={autoFocus}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActive(0);
        }}
        onKeyDown={onKeyDown}
      />
      {open && (
        <ul id={listId} role="listbox" aria-label={COPY.searchLabel}>
          {results.length === 0 ? (
            <li role="option" aria-selected={false} aria-disabled="true">
              {COPY.noMatches(query)}
            </li>
          ) : (
            results.map((item, index) => (
              <li
                key={item.ticker}
                id={`${listId}-${item.ticker}`}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => {
                  event.preventDefault();
                  go(item.ticker);
                }}
              >
                <strong>{item.ticker}</strong>
                <span>{item.name}</span>
                {item.last && <span className="meta">{formatPrice(item.last.close)}</span>}
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
