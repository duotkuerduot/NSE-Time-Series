# Runbook: create the environment from nothing (Phase 0)

About 45 minutes. Needs a Cloudflare account (R2 may ask for a payment method; usage stays in
the free tier), admin rights on the GitHub repository, and a healthchecks.io account.

## 1. Buckets (Cloudflare R2)

1. In the Cloudflare dashboard, open R2 and create an API token with **Admin Read & Write**.
2. Run the bootstrap, which creates `nsefc-data`, `nsefc-public` and `nsefc-scratch`, sets CORS
   on the public bucket and a 14-day expiry on scratch:

   ```bash
   export R2_ACCOUNT_ID=... R2_ADMIN_KEY_ID=... R2_ADMIN_SECRET=...
   uv run python deploy/cloudflare/bootstrap.py --dry-run   # check
   uv run python deploy/cloudflare/bootstrap.py
   ```

3. Delete the admin token afterwards.

## 2. Scoped tokens (ENGINEERING.md 26)

| Token | Permission | Buckets | Stored as |
| --- | --- | --- | --- |
| Pipeline | Object Read & Write | nsefc-data, nsefc-public | GitHub environment `production` |
| Dry run | Object Read (data), Object Read & Write (scratch) | nsefc-data, nsefc-scratch | GitHub environment `dryrun` |
| Developers | Object Read | nsefc-data | Each developer's local `.env` |
| Pages deploy | Cloudflare Pages: Edit | (account) | GitHub environment `production` |

Rotate every 90 days and whenever the team changes.

## 3. GitHub environments and secrets

```bash
gh api -X PUT repos/duotkuerduot/NSE-Time-Series/environments/production
gh api -X PUT repos/duotkuerduot/NSE-Time-Series/environments/dryrun
for name in NSEFC_R2_ACCOUNT_ID NSEFC_R2_ACCESS_KEY_ID NSEFC_R2_SECRET_ACCESS_KEY NSEFC_HEALTHCHECK_URL; do
  gh secret set "$name" --env production
done
```

Do not add required reviewers to `production`: scheduled runs (the spike, later the daily
pipeline) would wait for approval. Promotion review happens on pull requests instead (28.4).
In the repository settings, set the Actions spending limit to $0 and turn on secret scanning
with push protection.

## 4. Public API hostname and caching (review FE-2)

1. Connect a custom domain such as `api.<domain>` to `nsefc-public` (R2 bucket settings).
   The r2.dev development URL is rate-limited and not for production traffic.
2. Add a Cache Rule for that hostname: eligible for cache, respect origin `Cache-Control`.
   Cloudflare does not cache JSON by default, so without this rule every request reaches R2.
3. Check with `curl -sI https://api.<domain>/v1/status.json` twice: the second response should
   show `CF-Cache-Status: HIT`.

## 5. Dead-man's switch (healthchecks.io; review MF-5)

Create two checks with time zone Africa/Nairobi:

| Check | Pinged by | Schedule | Grace |
| --- | --- | --- | --- |
| scheduler-alive | every scheduled run, including holiday skips | weekdays, evening | 2 hours |
| session-committed | a run that commits the session (or confirms a holiday) | 07:30, Tuesday to Saturday | 30 minutes |

The second check replaces the 22:30 alert, which would page on holidays and before the designed
06:37 retry.

## 6. Start the source spike

After step 3, run the `source-spike` workflow once by hand (mode `probe`), then once with mode
`backcheck`, from `2026-01-01` to today. Scheduled runs take over from there.
