# Texas roofing lead list

A small command-line tool that builds a delivery file of roofing contractors in Texas. It finds businesses with the [Apify Google Maps Scraper](https://apify.com/compass/crawler-google-places), looks up a public business email with [Hunter domain search](https://hunter.io/api-documentation/v2#domain-search), checks that email, and writes a 100-row CSV plus a QA report.

The practice command uses bundled fictional companies and does not call the internet, so you can learn the tool before spending anything.

This tool does not crawl websites itself. It does not collect home addresses, personal phone numbers, social profiles, government IDs, or financial data. Map listings supply the business name, business phone, website, and city. Hunter supplies a business email and, when the listing includes one, a public professional name.

## Setup

You need Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Leave `.env` empty until you run against the live APIs. Do not commit `.env`, and do not paste it into a bug report.

| Variable | Used for |
| --- | --- |
| `APIFY_TOKEN` | Apify → Settings → API tokens. Discover only. |
| `HUNTER_API_KEY` | Hunter → API. Enrich and verify only. |

`roofleads.toml` holds the city list, search words, and the spend caps. The dollar figures in that file are planning rates. They do not change what Apify or Hunter charge you. Edit them so the QA report matches your plan.

## Practice run

From this folder:

```bash
make test
make dry-run
```

The same practice run without Make:

```bash
python -m roofleads run --dry-run --target-rows 100
```

`--fixtures` is the same switch as `--dry-run`.

You should see `Wrote 100 rows to out/leads.csv` and `QA report: out/qa_report.txt`. Open the CSV in a spreadsheet. Every row is a fictional `.example` company. The QA text file should say `Delivered 100 of 100 requested rows.` Progress prints in plain sentences. The JSON log is `out/roofleads.log`.

Run the same command again. The second report should show `New Hunter credits: 0` and `New Apify estimate: $0.000000`. The cache already holds the sample lookups, so they are not counted again.

## Live run

1. Put `APIFY_TOKEN` and `HUNTER_API_KEY` in `.env`.
2. Read the caps in `roofleads.toml`. The defaults stop at 500 Hunter credits and $5 of estimated Apify spend, whichever comes first.
3. Run:

```bash
make run
```

Or, with a tighter cap for a first look:

```bash
python -m roofleads run --target-rows 100 --max-credits 40 --max-apify-usd 1
```

A short file is expected when the cap is tight. The QA report names the cap that stopped the run. Raise the cap only if you accept the extra spend, then run the same command again. Companies already in the cache are not billed again.

## Commands

Most people only need `run`. The other commands are the same stages, one at a time, and they share `out/` and the cache.

| Command | What it does |
| --- | --- |
| `discover` | Asks Apify for roofing companies. Writes `out/discovered.jsonl`. |
| `enrich` | Asks Hunter for one business email and a public owner name. Writes `out/enriched.jsonl`. |
| `verify` | Runs free checks, then Hunter's verifier. Writes `out/verified.jsonl`. |
| `clean` | Fixes phones and websites, drops bad rows, removes duplicates. Writes `out/cleaned.jsonl`. |
| `export` | Writes `out/leads.csv`, `out/qa_report.json`, and `out/qa_report.txt`. |
| `run` | Runs those five stages until it has the requested number of rows or a cap stops it. |

`run` also writes the stage files, so you can see what happened before the CSV.

## CSV columns

`out/leads.csv` is UTF-8, with a header row and no byte-order mark. The columns are exactly:

| Column | Meaning |
| --- | --- |
| `company_name` | Business name from the map listing. |
| `owner_name` | Public professional name from Hunter, when one is listed. Blank when Hunter has no name. |
| `email` | One business email on the company domain. |
| `website` | `https://` plus the site host, without a path. |
| `phone` | Business phone in US E.164 (`+15125550100`). Blank when the listing phone is not a US number. |
| `city` | City from the listing, or the city that was searched. |
| `email_status` | Always `valid` in this file. Other statuses are left out. |
| `source` | `apify:<actor id>+hunter:domain-search`. |
| `collected_at` | UTC time the delivery batch was assembled, `YYYY-MM-DDTHH:MM:SSZ`. |

`valid` means the free checks passed and Hunter's verifier returned `valid` (deliverable). `risky` (accept-all or webmail), `invalid`, and `unknown` are counted in the QA report and are not written to the CSV. That is how the file stays at or above the 90% deliverable target: rows that are not confirmed deliverable are not delivered. In the practice file the rate is 100%.

## How to read the QA report

Open `out/qa_report.txt` first. The JSON file next to it has the same numbers for a spreadsheet or a script.

- **Delivered N of M** is the file you have, compared with `--target-rows`.
- **New Hunter credits** and **New Apify estimate** are what this run added. They are planning numbers from `roofleads.toml`, not the invoice.
- **Cache total** is every run that used this cache folder. The caps apply to that total.
- **Hunter credits skipped** is work that was free because the domain or email was already saved.
- **Estimate per delivered row** is `this run's Apify estimate + (new Hunter credits × hunter_usd_per_credit)`, divided by delivered rows. The JSON field `formulas` spells that out, and `rate_card` shows the prices used.
- **Stages** count what each step kept, skipped, or dropped. Duplicate emails, duplicate website domains (a second location of the same company), and duplicate phones are listed under `clean`.

Per-row cost for a margin check is the JSON field `cost_per_delivered_row_usd`. Divide your real invoice by `delivered_rows` when you want the invoice number instead of the estimate.

## Operator runbook

1. One-time setup is the **Setup** section above. You do not need to do it again.
2. Practice: `make dry-run`. Confirm `out/leads.csv` has 100 data rows and `out/qa_report.txt` says the deliverable target is met.
3. For a real list, fill in `.env`, then `make run`.
4. If the CSV is shorter than you asked, open `out/qa_report.txt`. The **Attention** section says whether the credit cap, the Apify cap, or the city list stopped the run.
5. To continue, raise the cap in the command or in `roofleads.toml` and run the same command again. Do not delete the cache unless you are willing to pay for those companies again.
6. To start a separate budget, pass a new folder: `--cache-dir .cache/roofleads/batch-2`.
7. If a command fails, copy the last lines from the terminal and attach `out/qa_report.txt` and `out/roofleads.log` if they exist. Do not send `.env`, the API token, or the Hunter key. Pass `--verbose` and run the command again if the log does not show the failed call.
8. The usual recovery is to run the same command again. You do not have to run the five stages by hand.

## What a paid run does

Discover sends one Apify run per city. The request asks for the search terms in `roofleads.toml`, limited to the configured number of places. These switches are always sent off, because they collect personal data or add fees this tool does not use: contact scraping, leads enrichment, email verification inside Apify, social profiles, reviews, reviewer data, images, and questions.

The default actor is `compass/crawler-google-places`. Two filters are on by default (`withWebsite` and skip closed places). On the free Apify tier those filters add to the per-place price. The QA rate card includes them.

Enrich calls Hunter domain search once per company domain. It keeps a business address on that domain, preferring a role inbox such as `info@` when `prefer_role_emails` is true. It stores a person's name only when Hunter lists a first name, a last name, and an owner-level title. It does not store LinkedIn, X, or the phone number Hunter may return.

Verify runs four free checks before it spends a verification credit: the address is shaped like an email, the domain is not on the disposable list, the domain has MX records, and whether the inbox is a role account. Role accounts are still verified by default, because a small contractor often publishes only `info@`. Set `reject_role_accounts = true` to mark them risky without a Hunter call. The optional `--smtp-probe` flag is off. It opens port 25 and sends `RCPT`. Many providers treat that as abuse, the port is often blocked, and the result is a poor signal. Leave it off.

Clean turns US phones into E.164, reduces a website to its origin, drops rows with no company name or no email, and drops a later row that repeats an email, a company domain, or a phone. Directory hosts (Facebook, Yelp, and similar) and website-builder hosts are not sent to Hunter.

Calls that receive HTTP 429 or 5xx are retried with backoff. The client does not follow redirects, so a key cannot be sent to a different host. Keys are read from the environment and are removed from error text.

## Known limitations

- The practice companies are fictional and use the `.example` domain. A live run depends on Google Maps coverage and on Hunter having a public address for that domain. The tool cannot promise 100 live rows inside a small credit cap. It will stop and write the rows it already checked.
- Delivered rows are only those Hunter marked deliverable after the free checks. That is the 90% bar. Accept-all domains, webmail, and unknown results are left out even when the address might work.
- Cost figures are estimates from `roofleads.toml`. Apify can bill events this tool does not see. Hunter's credit price depends on your plan. Some plans include verification at no extra credit: set `hunter_credits_per_verification` to `0` if that is your plan, and the guard will stop charging the cap for those calls. Confirm both invoices.
- The Apify cap is checked before a city search using the maximum places requested. A run that Apify accepts and then fails still counts a reserved estimate against the cap so a retry cannot walk past the limit unnoticed. A crash in the moment after a successful response and before the cache is saved can cause that one lookup to be paid again.
- The default city list is twelve Texas cities. Businesses outside those searches are missing. Listings whose state is not Texas are dropped.
- A second location that shares a domain is treated as the same company and removed. Two different businesses that only have a Facebook or Wix URL are skipped, because searching that host would not find the contractor's own mail.
- Owner names exist only when Hunter publishes one. The map phone is the business number from the listing, not a number from Hunter.
- The disposable-domain file is a starter list. Add domains with `disposable_domains_file`.
- MX records show that a domain accepts mail. They do not prove a mailbox exists. SMTP probing is off because it is unreliable and can get the machine blocked.
- This tool does not send email. You are responsible for CAN-SPAM, TCPA, and any other rule that applies to how you use the list.
- The cache is local JSON. Do not put it on a shared drive if the business names and emails are confidential to you.

## Tests

```bash
make test
```

The tests use mock HTTP. They do not need API keys and they do not call Apify or Hunter. `make test` followed by `make dry-run` is the check that the practice instructions above work.
