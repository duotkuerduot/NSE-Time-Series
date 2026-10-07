import { Link, Outlet, useLocation } from "react-router";
import { useStatus } from "../api/hooks";
import { COPY } from "../lib/copy";
import { formatEat } from "../lib/format";
import { isStale } from "../lib/staleness";
import { StockSearch } from "./StockSearch";

export function AppShell() {
  const status = useStatus();
  const { pathname } = useLocation();
  const data = status.data;

  return (
    <div className="shell">
      <header className="site">
        <Link to="/" className="wordmark">
          {COPY.wordmark}
        </Link>
        {data && (
          <p className="meta">
            {COPY.dataTo(data.latest_session)}
            <br />
            {COPY.updated(formatEat(data.generated_at))}
          </p>
        )}
      </header>
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
      {data?.notices.map((notice) => (
        <div className="banner" role="status" key={notice.code}>
          {notice.message}
        </div>
      ))}
      {pathname !== "/" && (
        <div style={{ paddingTop: 16 }}>
          <StockSearch />
        </div>
      )}
      <main>
        <Outlet />
      </main>
      <footer className="site">
        <p>{COPY.disclaimer}</p>
        <p>{COPY.attribution}</p>
        <p>
          <Link to="/about">Methodology, limitations and data sources</Link>
        </p>
      </footer>
    </div>
  );
}
