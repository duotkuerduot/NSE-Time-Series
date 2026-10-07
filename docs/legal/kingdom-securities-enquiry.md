# Draft enquiry to Kingdom Securities

Send to the research desk (address on kingdomsecurities.co.ke). A draft for the team to
adapt; it is not legal advice. ADR-003 proposes the Daily Market Wrap as a validator, not as a
displayed source, so the request is narrow.

---

**Subject:** Permission to use the Daily Market Wrap for data validation

Dear Kingdom Securities research team,

We are building a small research website that shows end-of-day prices for NSE-listed
equities and a statistical forecast of each liquid stock's next closing price. We intend to
license the prices we display from the Nairobi Securities Exchange.

We would like to use your Daily Market Wrap, which you publish on your website, only as an
independent check on the exchange data we receive: our software would read each evening's
wrap, compare its closing prices with ours, and flag any disagreement for review. We would
not republish the wrap or any figures from it, and we would store copies privately, only to
re-run those checks.

Could you tell us whether you are happy with this use, whether any conditions or fees
apply, and how you would like us to attribute Kingdom Securities if we describe our checks
publicly?

Kind regards,

[Name, organisation, contact details]

---

## Notes

- Fetching follows ENGINEERING.md 8.5: an identifying User-Agent with a contact address,
  robots.txt honoured, at most one request per second, and no re-fetching of archived files.
- If permission is refused, drop the validator role and rely on the exchange feed plus the
  data-quality checks; record the decision in ADR-003.
