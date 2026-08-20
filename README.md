# Trading Dashboard (Angel One + Zerodha Kite)

A local Streamlit app that connects to your own Angel One and Zerodha Kite
accounts and shows combined positions, P&L, and funds. Everything runs and
stores data on your own computer — nothing is sent to any third-party server
except the brokers' own APIs.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Requires Python 3.10+ (uses the `X | None` type-hint syntax).

On first run, you'll be asked to create a local username + password. That
password:
- protects the app itself (hashed with bcrypt, never stored in plaintext)
- is also used to derive the encryption key that protects every broker
  credential you add (PBKDF2 → Fernet/AES). The key only ever exists in
  memory while you're logged in — it is never written to disk.

**There is no password reset.** If you forget it, delete
`~/.trading_dashboard/app.db` and start over — you'll need to re-enter your
broker credentials.

## Adding Angel One accounts

Angel One's SmartAPI officially supports headless login, so once you add:
- API key
- Client ID
- Trading password / MPIN
- TOTP secret (the base32 secret behind the QR code at
  https://smartapi.angelbroking.com/enable-totp — not a 6-digit code)

...the app logs in and refreshes the session automatically, every time.

## Adding Zerodha Kite accounts

**Zerodha's official Kite Connect API does not support headless
password+TOTP login.** This is a deliberate security decision on Zerodha's
part — the only supported flow is:

1. You add your API key + API secret (from https://developers.kite.trade)
2. The app gives you a login link. You open it and log in with your normal
   Zerodha password + TOTP, in your own browser.
3. Zerodha redirects to your app's registered redirect URL with a
   `request_token` in the query string.
4. You paste that URL (or just the token) back into the app, which
   exchanges it for a day-valid `access_token`.

You'll need to repeat steps 2–4 once a day — Zerodha invalidates the
access_token every day around 6 AM IST. This is a Zerodha platform rule,
not a limitation of this app; there is no officially supported way around
the daily browser login.

(You may see other scripts online that simulate the Kite *website* login
with raw HTTP requests and your TOTP secret, avoiding the browser step.
That is not part of Zerodha's supported API, is fragile against
undocumented changes, and risks violating Zerodha's terms of service — this
app intentionally does not do that.)

To create a Kite Connect app / get an API key and secret, and to register a
redirect URL, see https://developers.kite.trade — note Kite Connect API
access carries its own subscription fee from Zerodha, separate from your
trading account.

## What the dashboard shows

- **Funds**: total funds, used margin, available margin — per account and
  combined.
- **Positions**: symbol, exchange, product, quantity, average price, LTP,
  and P&L, grouped by account, with a combined total P&L.
- **Market Watch**: live NIFTY 50, NIFTY BANK, and SENSEX prices.
- **Option Chain & Futures Explorer**: pick any index (NIFTY, BANKNIFTY,
  FINNIFTY, MIDCPNIFTY, SENSEX, BANKEX) or any individual F&O stock, then:
  - **Option Chain tab** — pick an expiry, see CE/PE OI, volume, % change,
    and LTP per strike, with the at-the-money strike highlighted. A slider
    lets you limit how many strikes around the current price to show (full
    NIFTY/BANKNIFTY chains can be 80–150+ rows).
  - **Futures tab** — every available expiry (current/next/far month) for
    that underlying, with LTP, % change, volume, and OI.

These three features all require a connected **Angel One** account (Zerodha
isn't used for market data here) and pull the list of tradable
strikes/expiries from Angel's daily instrument master file, which is cached
locally for about a day so it isn't re-downloaded on every click.

## Project layout

```
app.py                        # login / account creation
core/
  database.py                 # SQLite storage (~/.trading_dashboard/app.db)
  security.py                 # password hashing + encryption
  session.py                  # Streamlit session-state / login guard
  broker_factory.py           # builds broker clients from encrypted rows
brokers/
  angel_one.py                # SmartAPI wrapper (positions, funds, batched quotes)
  kite.py                     # Kite Connect wrapper
  instruments.py              # Angel instrument-master download/cache + option/futures lookups
pages/
  1_Manage_Accounts.py        # add / test / remove broker accounts
  2_Dashboard.py               # combined positions, P&L, funds
  3_Market_Watch.py            # NIFTY / BANKNIFTY / SENSEX live prices
  4_Option_Chain.py            # option chain + futures explorer, any underlying
```

## Notes & caveats

- Broker field names (e.g. exact keys in `rmsLimit()` / `margins()`
  responses) can change over time as Angel One / Zerodha update their APIs.
  If a number looks wrong, check the raw response against the current
  SmartAPI (https://smartapi.angelbroking.com/docs) or Kite Connect
  (https://kite.trade/docs/connect/v3/) docs and adjust the field mapping
  in `brokers/angel_one.py` / `brokers/kite.py`.
- **Instrument master / quote field names**: `brokers/instruments.py` and
  the quote normalizer in `brokers/angel_one.py` were built and tested
  against Angel's documented/publicly posted field names (`token`,
  `symbol`, `name`, `expiry`, `strike`, `instrumenttype`, `exch_seg` for the
  instrument master; `ltp`, `netChange`, `percentChange`, `opnInterest`,
  `tradeVolume` for quotes) using a synthetic fixture, since this
  environment couldn't reach Angel's servers to test against the live file.
  The code tries a couple of alternate key-name spellings defensively, but
  if a column looks empty/wrong after connecting a real account, check the
  raw JSON from `download_instrument_master()` / `get_quotes()` against
  what's actually being returned.
- **Rate limits**: Angel's quote endpoint accepts up to 50 tokens per
  request and is rate-limited to roughly 1 request/second; the option
  chain page paces batched requests accordingly, so loading a full
  NIFTY/BANKNIFTY chain (150+ strikes × 2) can take several seconds. Use
  the strike-window slider to keep it fast.
- **Index tokens**: NIFTY 50 / NIFTY BANK / SENSEX tokens are looked up
  dynamically from Angel's instrument master each time (instrument type
  `AMXIDX`) and only fall back to hardcoded values if that lookup fails,
  since Angel has changed these tokens before.
- This app only reads positions/funds — it doesn't place orders. Treat any
  extension toward order placement with extra care and test with small
  quantities first.
- This is single-desktop, single-machine software. If you move it to a
  shared or cloud machine, anyone with access to that machine while you're
  logged in has access to your decrypted broker sessions — treat it like
  you would a password manager.
