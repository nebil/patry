# Patry

> Money as a CLI.

Patry is a command-line utility crafted for monitoring financial assets across multiple accounts.
It can consolidate your data into an easy-to-read table,
enabling quick comparison of investment performance and
making financial oversight both efficient and straightforward.

## Getting started

### Prerequisites

Make sure that you have [Git](https://git-scm.com),
[Python](https://www.python.org) **3.10** (or higher),
and [Poetry](https://python-poetry.org) installed in your machine.

```sh
python --version
```

### Installation

1. Clone this repository and navigate into the project directory.

```sh
git clone https://github.com/nebil/patry.git && cd patry
```

2. Create a [virtual environment](https://docs.python.org/3/library/venv.html)
   to install the project dependencies.  
   **Note:** If you don’t have [Make](https://www.gnu.org/software/make) installed,
   you can manually run the commands defined in [that target](Makefile) instead.

```sh
make venv-with-dependencies
```

3. Copy the [**.env.example**](.env.example) file to **.env**, and update it with your specific values.
More details in [this section](#environment-secrets).

```sh
cp .env.example .env
```

4. Activate your virtual environment.

```sh
source .venv/bin/activate
```

5. You’re all set: start monitoring your assets with Patry.

## How to use

Once installed, run **patry --help** (or just **patry**) to get a list of available arguments and options:

```console
Patry: a command-line interface for monitoring [my] financial assets.

positional arguments:
  <bchile|fintual|renta4|extras|monio>  Select the account(s) to check.

options:
  --no-cache                            Fetch cashflows and store them.
  --with-usd [COLINDEX]                 Include an extra column for USD.
  --loaddata YYYY-MM-DD                 Load historical data from date.
  --savejson [FILENAME]                 Export portfolio to a JSON file.
  --headed                              Show browser UI during execution.
  --verbose, --info                     Set log level at <logging.INFO>.
  --debug                               Set log level at <logging.DEBUG>.
  --version                             Show Patry's version and exit.
  --help                                Display this help message and exit.

More info at <https://github.com/nebil/patry>
```

For instance, to get data from Banco de Chile and Fintual, you would type:

```sh
patry bchile fintual --info
```

### Supported accounts

Patry supports monitoring for several accounts, each with specific assets and fetching methods:

| Name              | Filename        | Type of available assets          | Data fetching method  |
|-------------------|-----------------|-----------------------------------|-----------------------|
| [Banco de Chile]  | **bchile.py**   | Balance, depósitos a plazo        | [Playwright]          |
| [Fintual]         | **fintual.py**  | Objetivos                         | Playwright + [HTTPX]  |
| [Renta 4]         | **renta4.py**   | Balance, fondos mutuos, acciones  | Playwright            |
| [AFP Modelo]      | **extras.py**   | Balance                           | Playwright            |

### Key options

- **--no-cache:** Recompute [CAGR](https://en.wikipedia.org/wiki/Compound_annual_growth_rate)
by fetching cashflows, bypassing cache stored in **.patry** files.
- **--with-usd:** Insert a column for asset value in USD,
using rates from [mindicador.cl](https://mindicador.cl/).
- **--loaddata:** Load historical data from a given date. **Only works with Fintual.**
- **--savejson:** Save today’s data into a file named **output.json**.

### Environment secrets

Before using Patry, configure the following environment variables using your **.env** file.

- **CHILE_ID_NUMBER** is your Chilean RUN/RUT.
- **BCHILE_PASSWORD** is the password for your Banco de Chile account.
- **RENTA4_PASSWORD** is the password for your Renta 4 account.
- **RENTA4_START_DATE** is the date you began using Renta 4.
- **FINTUAL_EMAIL** is the email address linked to your Fintual account.
- **FINTUAL_TOKEN** is a token generated by Fintual to access [their API](https://fintual.cl/api-docs/index.html).
- **FINTUAL_COOKIE** is a browser cookie to simulate a web session at Fintual.
- **MODELO_PASSWORD** is the password for your AFP Modelo account.
- **MONIO** is a list of comma-separated accounts to be fetched when calling **patry monio**.

**Security notice:**
These secrets allow Patry to authenticate and retrieve your financial information.
They are used solely to access your financial accounts directly from your machine,
and they will **never** be transmitted or stored on third-party servers.

## Development

### Dependencies

Patry is built on a handful of dependencies.
Here’s an overview of the most important ones.

- **[HTTPX]** is a next-gen HTTP client with sync and async APIs.
- **[Playwright]** is a framework for web testing and automation.
- **[PyXIRR]** is a Rust-powered collection of financial functions.
- **[Rich]** is a library for beautiful formatting in the terminal.

### Code health

To keep a (somewhat) healthy codebase, we use four different tools:
[Ruff](https://github.com/astral-sh/ruff),
[Black](https://github.com/psf/black),
[mypy](https://github.com/python/mypy) &
[doctests](https://docs.python.org/3/library/doctest.html).

You can run them all by typing…

```sh
make --jobs checks
```

## Disclaimer

Please make sure to **review the codebase** before including your credentials.
Although this script performs only read-only operations,
it is wise not to blindly trust code from unknown sources on GitHub.
Just so we’re clear…
the author assumes no responsibility for any financial issues that could arise from using **Patry**. 😇

## License

Copyright © 2024, Nebil Kawas García  
This project is subject to the terms of the [Mozilla Public License](
https://www.mozilla.org/MPL/2.0/).

[/]:# (Implicit links)

[Banco de Chile]:  https://bancochile.cl
[Fintual]:         https://fintual.cl
[Renta 4]:         https://www.renta4.cl
[AFP Modelo]:      https://www.afpmodelo.cl

[HTTPX]:           https://www.python-httpx.org
[Playwright]:      https://playwright.dev
[PyXIRR]:          https://anexen.github.io/pyxirr
[Rich]:            https://rich.readthedocs.io/en/stable
