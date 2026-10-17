"""Stage 6, serve (§15.5): a standard-library HTTP server on 127.0.0.1."""

from nsefc.serve.server import NoResultsError, Server, make_server, open_browser

__all__ = ["NoResultsError", "Server", "make_server", "open_browser"]
