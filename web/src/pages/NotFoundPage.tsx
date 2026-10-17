import { Link } from "react-router";
import { COPY } from "../lib/copy";

export function NotFoundPage() {
  return (
    <section>
      <h1>{COPY.pageNotFound}</h1>
      <p>
        <Link to="/" className="btn btn-secondary">
          Go to the homepage
        </Link>
      </p>
    </section>
  );
}
