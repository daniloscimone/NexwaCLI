# NexwaCLI

A customer dashboard and boost panel for [Nexwa](https://nexwa.store), built for the terminal.

Connect the API key from your Nexwa account, browse services, place orders with your wallet credit, and check their status. You can use the interactive panel or run individual commands from your own scripts.

NexwaCLI connects to **`https://nexwa.store/api/v2`**. Every customer uses their own key. The service catalog, prices, wallet balance, and order charges come from Nexwa.

## What you can do

- See your available Nexwa credit.
- Search the service catalog by name, platform, category, or description.
- Read service details, quantity limits, pricing units, and refill availability.
- Review and submit orders using wallet credit.
- Check one order or up to 100 order IDs in a single request.
- Keep local purchase receipts and resume requests after a connection failure.
- Request a refill when Nexwa accepts it for the order.
- Change the panel language and colors from Settings.
- Get JSON output for your own integrations.

The panel uses Nexwa's purple and supports English, Italian, French, German, Spanish, and Russian—the same languages as the website. English is the initial language. Service names, descriptions, and API error messages are displayed as Nexwa returns them. Command names, command help, and JSON field names stay in English.

## Run it

You need **Python 3.11 or newer** to run from source. The application has no third-party runtime dependencies.

```sh
git clone https://github.com/daniloscimone/NexwaCLI.git
cd NexwaCLI
python3 nexwa.py
```

On Windows:

```powershell
git clone https://github.com/daniloscimone/NexwaCLI.git
cd NexwaCLI
py -3 nexwa.py
```

Running without arguments opens the dashboard in an interactive terminal. Running without arguments in a pipe prints help instead.

### Install the `nexwa` command

From the project directory on macOS or Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
nexwa
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install .
nexwa
```

You can also use `python -m nexwacli` or `python nexwa.py` wherever the examples below use `nexwa`. Replace `python` with `python3` or `py -3` if that is how Python is installed on your computer.

### Standalone executables

The repository includes a **Build executables** GitHub Actions workflow. It builds separate packages for Windows x64, Linux x64, and macOS on Intel and Apple Silicon. Packaged executables include Python, so users do not need to install it.

The workflow runs for application changes on `main` and can also be started manually from the Actions tab. It runs when a GitHub Release is published and attaches the packages to that release after the builds pass. Download packages from [Releases](https://github.com/daniloscimone/NexwaCLI/releases) when available. Source installation works independently of the release builds.

Extract the package and run `nexwa` (`nexwa.exe` on Windows) in a terminal. On macOS or Linux, you may need `chmod +x nexwa` if your extraction tool did not preserve executable permissions. The executables are unsigned; platform security checks may apply. Build from source if you prefer to inspect and compile your own copy.

## Connect your account

1. Sign in at [nexwa.store](https://nexwa.store).
2. Verify your email address.
3. Open **Wallet and API**, generate a customer API key, and copy it. The website shows the full key only once.
4. Add wallet credit on the website before placing orders.
5. In the panel, choose **Connect account**, or run:

```sh
nexwa auth login
nexwa balance
```

The login prompt hides the key as you type. NexwaCLI checks it with a balance request before saving it. The saved key is **not encrypted**. On macOS and Linux, newly written configuration files are restricted to their owner; on Windows, access follows the user's directory permissions.

For scripts or temporary sessions, set `NEXWA_API_KEY` through your shell or secret manager. An environment key takes priority over a saved key. The CLI intentionally has no `--api-key` argument, keeping the secret out of command arguments.

To enter a key without including its value in shell history, on Bash:

```sh
read -rsp 'Nexwa API key: ' NEXWA_API_KEY
export NEXWA_API_KEY
printf '\n'
nexwa balance --json
```

On PowerShell:

```powershell
$env:NEXWA_API_KEY = Read-Host 'Nexwa API key' -MaskInput
nexwa balance --json
```

`-MaskInput` needs PowerShell 7.1 or newer. On older PowerShell versions, use the panel's hidden login prompt instead.

Check your local configuration or remove the saved key:

```sh
nexwa auth status
nexwa auth logout
```

Logout removes the local saved key. It does not revoke the key on Nexwa or unset an environment variable. Revoke keys from the website when necessary.

## The dashboard

The dashboard puts wallet credit and **New order** first. **Services** opens a searchable, paged catalog. Select a service ID to read its full details, then start an order from that screen.

Before submitting an order, the panel shows the service, target link, quantity, and pricing note. It asks you to type a confirmation. A successful purchase returns the Nexwa order ID and charge.

**My orders** contains receipts saved by this installation for the active API key. From there, you can check delivery status, retry an unconfirmed purchase using its original request key, or request a refill. The local receipt state is separate from the live delivery status.

**Wallet** opens the account page for credit top-ups and key management. Funding and email verification take place on the website.

### Language and colors

Open **Settings → Language** to choose English, Italiano, Français, Deutsch, Español, or Русский. The change applies immediately and is saved for the next launch.

The same settings are available without opening the panel:

```sh
nexwa settings
nexwa settings --language it
nexwa settings --color off
```

Colors can be automatic, enabled, or disabled. `NO_COLOR`, `TERM=dumb`, redirected output, and unsupported Windows consoles disable ANSI colors. The panel uses ordinary numbered choices and line input; it does not require a mouse or special keyboard bindings.

## Commands

| Command | Purpose |
| --- | --- |
| `nexwa` or `nexwa menu` | Open the customer dashboard |
| `nexwa auth login` | Validate and save a customer API key |
| `nexwa auth status` | Show the local key source, without printing the key |
| `nexwa auth logout` | Delete the saved key |
| `nexwa balance` | Fetch current wallet credit |
| `nexwa services` | Browse the cached catalog |
| `nexwa services <ID>` | Read one service's details |
| `nexwa orders create` | Review and submit an order |
| `nexwa orders status <IDs>` | Fetch live order status |
| `nexwa orders list` | Show this computer's receipts for the active key |
| `nexwa orders retry <request-key>` | Resume an order with the original payload and key |
| `nexwa orders refill <ID>` | Request a refill |
| `nexwa account --open` | Open the Nexwa account page |
| `nexwa settings` | Read or update language and color preferences |

Use `--help` on a command for all its options.

### Browse services

```sh
nexwa services --platform instagram --search followers
nexwa services --category views --limit 20
nexwa services --refresh
nexwa services 123
nexwa services --all --json > services.json
```

`123` is an example ID. Use an ID from your current Nexwa catalog.

The catalog cache lasts 12 hours and is isolated by API key. `--refresh` fetches a new copy. Results are limited to 50 by default, including JSON output; use `--all` to return every match.

### Preview and place an order

```sh
nexwa orders create \
  --service 123 \
  --link 'https://www.instagram.com/example/' \
  --quantity 100 \
  --dry-run
```

`--dry-run` checks the service and quantity against the catalog and prints a preview. It does not submit an order, spend credit, or save a purchase request. Nexwa performs the final target and account validation when you submit.

To submit, remove `--dry-run` and confirm the prompt. In a script, `--yes` is required:

```sh
nexwa orders create \
  --service 123 \
  --link 'https://www.instagram.com/example/' \
  --quantity 100 \
  --request-key shop-order-1042 \
  --yes --json
```

**That command makes a real purchase when the parameters, account, and wallet balance are valid.** Choose a fresh request key for each intended purchase and keep it stable for retries of that purchase.

The catalog's `rate` is a reference price per 1,000 units. It is not an exact quote for every quantity or pricing unit. Nexwa calculates the final charge, including applicable minimums and promotions. The CLI does not apply its own markup or calculate an alternative sale price.

### Interrupted requests

Before sending a purchase, NexwaCLI saves the payload and a request key locally. It sends that key as the API's `idempotency_key`. If you do not provide a key, the CLI generates one and prints it before sending the order.

A timeout can leave the outcome unknown. Do not start a fresh purchase to recover it. Find the original request and retry it:

```sh
nexwa orders list --pending
nexwa orders retry shop-order-1042 --yes --json
```

The retry uses the saved service, link, quantity, and original key. Once a successful response is saved locally, repeating that request returns the saved receipt without submitting another purchase. Reusing a request key with a different payload is rejected locally.

Nexwa's idempotency scope is the customer API key. Recover a purchase using the **same API key**. Changing or revoking it does not transfer the original request's protection to another key. Application errors are also left in the unconfirmed list until resolved; that list means “no saved success response,” not “definitely uncharged.”

The client never automatically retries purchases or refill requests. It also keeps a local lock while handling a purchase key. After a hard crash, a `.lock` file may remain; the error prints its exact location. Remove it only after making sure no NexwaCLI process is using that request, then retry with the original key.

### Status and refill

```sh
nexwa orders status 1042
nexwa orders status 1042 1043 1044 --json
nexwa orders status 1042,1043 --json
nexwa orders refill 1042
```

The API accepts up to 100 distinct order IDs per status request. It returns statuses such as `Pending`, `In progress`, `Processing`, `Partial`, `Completed`, and `Canceled`. The interactive panel translates these labels. `start_count` and `remains` currently come back as `null`; they are unknown values, not zero.

A refill is available only when Nexwa accepts the request for that order. The public API does not currently expose order cancellation, refill-status lookup, account-wide order listing, wallet top-ups, or API key creation. A capability flag in the service catalog does not add an API endpoint.

## JSON, errors, and rate limits

`--json` writes command results to standard output. Errors go to standard error; in JSON mode, runtime errors contain an `error` field and API errors also include `http_status` and `retry_after`. Purchase request-key notices go to standard error so they do not break JSON output.

```sh
nexwa balance --json
nexwa --timeout 45 orders status 1042 --json
```

The timeout defaults to 30 seconds and can be set between 1 and 300. API error messages are preserved, including application errors returned with HTTP 200. HTTP 429 reports the `Retry-After` header rather than retrying a purchase.

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | Command completed |
| `1` | API, configuration, validation, or confirmation error |
| `2` | Invalid command syntax reported by the argument parser |
| `130` | Interrupted input or Ctrl+C |

For batch status responses, inspect each order's result: a missing order can have its own `error` field inside an otherwise successful response. Argument syntax errors use the standard command-line help format, including when `--json` is selected.

## Local files

The default data directory is:

| System | Directory |
| --- | --- |
| macOS / Linux | `$XDG_CONFIG_HOME/nexwa`, or `~/.config/nexwa` |
| Windows | `%APPDATA%\NexwaCLI` |

Set `NEXWA_CONFIG_DIR` to choose a different directory, for example for a separate installation or a portable setup.

```text
nexwa/
├── config.json             # saved API key, if you use login
├── settings.json           # panel language and colors
└── accounts/
    └── <key fingerprint>/
        ├── services.json   # catalog cache
        └── orders/
            └── <request hash>.json
```

Receipts contain target URLs, quantities, timestamps, request keys, and API responses. Keep the data directory private and back it up if you rely on the local receipts. It is separate from the project directory by default. No credentials or customer order files belong in Git commits or issue reports.

## Development and forks

```sh
python -m unittest discover -v
python -m compileall -q nexwacli tests
```

The tests use mock API responses. They cover request encoding, application errors, HTTP 429, malformed responses, interrupted purchases, idempotency, local file failures, account isolation, translation completeness, and panel flows. They do not need a customer key or create real orders.

The **Tests** workflow runs on Windows, macOS, and Linux with Python 3.11 and 3.14. The build workflow tests each standalone executable on its own runner before packaging it.

Project layout:

```text
nexwacli/
├── api.py       # HTTPS transport and the Nexwa public API contract
├── cli.py       # command parsing, purchase workflow, output
├── panel.py     # customer dashboard and guided flows
├── i18n.py      # the six panel languages
└── storage.py   # local keys, settings, catalog cache, order journal
```

To change the interface, start with `panel.py`. Terminal color tokens are defined there. Add or edit translated panel strings in `i18n.py`; each message must have one entry per supported language. `PRODUCT.md` and `DESIGN.md` record the scope and interface decisions.

For editable development:

```sh
python -m pip install -e .
```

To build an executable for your current operating system:

```sh
python -m pip install -r requirements-build.txt
python -m PyInstaller --clean --noconfirm --onefile --name nexwa nexwa.py
```

The result is in `dist/`. Build on each target OS; PyInstaller does not produce Windows, macOS, and Linux executables from one build. The repository's workflow defines the supported binary targets. Other systems that support Python 3.11+ can run the source version, but are not claimed as tested binary targets.

## Contributing

Fork the repository, make a focused change, run the tests, and open a pull request. Include the command or panel flow affected and what you checked. For API changes, use the Nexwa public contract and add a test for the changed behavior. Do not include live keys, private customer data, or real purchase receipts in examples.

## License

[MIT](LICENSE). You can use, modify, distribute, and sell your own version under the license terms. Keep the copyright and license notice with copies. API access, wallet credit, and Nexwa services are managed separately through your Nexwa account.
