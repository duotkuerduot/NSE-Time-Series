import { Link, Outlet, useLocation } from "react-router";
import type { Status } from "../api";
import { useSite, useStatus } from "../api/hooks";
import { COPY } from "../lib/copy";
import { isStale } from "../lib/staleness";
import { StockSearch } from "./StockSearch";

/** "Data through Fri 31 Oct 2025 · Mendeley Data v1", or "· Sample data". */
export function dataLabel(status: Status): string {
  const through = COPY.dataThrough(status.latest_session);
  const imported = status.data_mode === "historical+imports" ? `, ${COPY.withImports}` : "";
  const source =
    status.data_mode === "sample"
      ? COPY.sampleData
      : status.dataset.source === "mendeley"
        ? COPY.mendeleyData(status.dataset.version)
        : COPY.localFiles;
  return `${through}${imported} · ${source}`;
}

export function AppShell() {
  const status = useStatus();
  const site = useSite();
  const { pathname } = useLocation();
  const data = status.data;
  const notices = data?.notices ?? [];
  const dataset = data?.dataset;

  return (
    <div className="shell">
      <header className="site">
        <Link to="/" className="wordmark">
          {COPY.wordmark}
        </Link>
        {data && <p className="meta">{dataLabel(data)}</p>}
      </header>
      {data?.data_mode === "sample" && (
        <p className="notice sample" role="note">
          {COPY.sampleNotice}
        </p>
      )}
      {status.isError && (
        <div className="banner" role="alert">
          {COPY.cannotReach} <button onClick={() => status.refetch()}>{COPY.retry}</button>
        </div>
      )}
      {data && isStale(data) && (
        <div className="banner" role="status">
          {COPY.staleBanner(data.latest_session, data.next_session)}
        </div>
      )}
      {notices
        .filter((notice) => notice.severity === "warning")
        .map((notice) => (
          <div className="banner" role="status" key={notice.code}>
            {notice.message}
          </div>
        ))}
      {pathname !== "/" && (
        <div className="page-search">
          <StockSearch />
        </div>
      )}
      <main>
        <Outlet />
      </main>
      <footer className="site">
        <p>{COPY.disclaimer}</p>
        {dataset?.citation && (
          <p>
            {COPY.dataCredit}{" "}
            {dataset.url ? <a href={dataset.url}>{dataset.citation}</a> : dataset.citation}
            {dataset.licence ? `. Licence: ${dataset.licence}.` : null}
          </p>
        )}
        {notices
          .filter((notice) => notice.severity === "info" && notice.code !== "SAMPLE_DATA")
          .map((notice) => (
            <p key={notice.code}>{notice.message}</p>
          ))}
        {site.data && (
          <p>
            {COPY.builtBy(site.data.owner_name)}
            {site.data.links.map((link) => (
              <span key={link.url}>
                {" · "}
                <a href={link.url}>{link.label}</a>
              </span>
            ))}
          </p>
        )}
        <p>
          <Link to="/about">How it works, results, limitations and data</Link>
        </p>
      </footer>
    </div>
  );
}
