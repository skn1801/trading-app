import datetime

import pandas as pd
import streamlit as st

from core import database as db
from core import session
from core import broker_factory
from brokers import instruments as inst
from brokers.angel_one import AngelOneAuthError

st.set_page_config(page_title="Option Chain & Futures", page_icon="🧮", layout="wide")
session.require_login()

user = session.current_user()
enc_key = st.session_state["enc_key"]

st.title("🧮 Option Chain & Futures Explorer")
st.caption(
    "Covers NIFTY, BANKNIFTY, SENSEX and every other index/stock with F&O contracts, "
    "sourced from Angel One's instrument list and live quotes."
)

angel_accounts = db.list_broker_accounts(user["id"], broker="angel_one")
if not angel_accounts:
    st.info("This needs at least one connected Angel One account.")
    st.page_link("pages/1_Manage_Accounts.py", label="Add an Angel One account", icon="🔗")
    st.stop()

account_names = {a["id"]: a["nickname"] for a in angel_accounts}
selected_id = st.selectbox(
    "Use account", options=list(account_names.keys()), format_func=lambda i: account_names[i]
)
selected_account = next(a for a in angel_accounts if a["id"] == selected_id)

# --- Instrument master (cached ~daily on disk) ---
col_a, col_b = st.columns([3, 1])
with col_b:
    force_refresh = st.button("Refresh instrument list")
try:
    with st.spinner("Loading instrument list..."):
        instrument_df = inst.download_instrument_master(force_refresh=force_refresh)
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load the instrument list: {exc}")
    st.stop()

last_updated = inst.cache_last_updated()
with col_a:
    st.caption(f"Instrument list last refreshed: {last_updated or 'unknown'} (UTC)")

index_underlyings = inst.list_index_underlyings(instrument_df)
stock_underlyings = inst.list_fno_stock_underlyings(instrument_df)
all_underlyings = index_underlyings + stock_underlyings

if not all_underlyings:
    st.warning("No F&O underlyings found in the instrument list. Try refreshing it above.")
    st.stop()

underlying = st.selectbox(
    "Underlying",
    options=all_underlyings,
    help="Indices are listed first, followed by every F&O stock alphabetically.",
)

try:
    client = broker_factory.build_client(selected_account, enc_key)
    client.connect()
except (AngelOneAuthError, ImportError) as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.error(f"Unexpected error connecting to Angel One: {exc}")
    st.stop()


def _fetch_spot_price(underlying_name: str):
    """Best-effort current price for ATM highlighting: index spot, or stock cash price."""
    if underlying_name in index_underlyings:
        targets = inst.get_index_quote_targets(instrument_df)
        label_map = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "SENSEX": "SENSEX"}
        label = label_map.get(underlying_name)
        if not label or label not in targets:
            return None
        exchange, _symbol, token = targets[label]
    else:
        target = inst.get_equity_spot_target(instrument_df, underlying_name)
        if not target:
            return None
        exchange, _symbol, token = target

    quotes = client.get_quotes({exchange: [token]}, mode="LTP")
    return quotes[0]["ltp"] if quotes else None


tab_options, tab_futures = st.tabs(["Option Chain", "Futures"])

with tab_options:
    expiries = inst.get_option_expiries(instrument_df, underlying)
    if not expiries:
        st.info(f"No option contracts found for {underlying}.")
    else:
        expiry = st.selectbox(
            "Expiry", options=expiries, format_func=lambda d: d.strftime("%d %b %Y"), key="opt_expiry"
        )
        strike_window = st.slider(
            "Strikes to show around the current price (0 = show all)",
            min_value=0,
            max_value=40,
            value=10,
            key="strike_window",
        )
        load = st.button("Load option chain", type="primary")

        if load:
            with st.spinner("Fetching option chain quotes..."):
                chain_rows = inst.get_option_chain_rows(instrument_df, underlying, expiry)
                spot_price = _fetch_spot_price(underlying)

                if strike_window > 0 and spot_price and not chain_rows.empty:
                    chain_rows = chain_rows.assign(_dist=(chain_rows["strike"] - spot_price).abs())
                    chain_rows = chain_rows.nsmallest(strike_window * 2 + 1, "_dist").sort_values("strike")

                exchange_tokens = {}
                for _, row in chain_rows.iterrows():
                    if pd.notna(row["ce_token"]):
                        exchange_tokens.setdefault(row["exchange"], []).append(row["ce_token"])
                    if pd.notna(row["pe_token"]):
                        exchange_tokens.setdefault(row["exchange"], []).append(row["pe_token"])

                quotes = client.get_quotes(exchange_tokens, mode="FULL") if exchange_tokens else []
                quotes_by_token = {q["token"]: q for q in quotes}

                display_rows = []
                for _, row in chain_rows.iterrows():
                    ce_quote = quotes_by_token.get(row["ce_token"]) if pd.notna(row["ce_token"]) else None
                    pe_quote = quotes_by_token.get(row["pe_token"]) if pd.notna(row["pe_token"]) else None
                    display_rows.append(
                        {
                            "CE OI": ce_quote["open_interest"] if ce_quote else None,
                            "CE Volume": ce_quote["volume"] if ce_quote else None,
                            "CE Chg%": ce_quote["percent_change"] if ce_quote else None,
                            "CE LTP": ce_quote["ltp"] if ce_quote else None,
                            "Strike": row["strike"],
                            "PE LTP": pe_quote["ltp"] if pe_quote else None,
                            "PE Chg%": pe_quote["percent_change"] if pe_quote else None,
                            "PE Volume": pe_quote["volume"] if pe_quote else None,
                            "PE OI": pe_quote["open_interest"] if pe_quote else None,
                        }
                    )

                if spot_price:
                    st.metric(f"{underlying} spot / underlying price", f"{spot_price:,.2f}")

                if not display_rows:
                    st.info("No quotes returned for this expiry.")
                else:
                    result_df = pd.DataFrame(display_rows)
                    if spot_price:
                        atm_idx = (result_df["Strike"] - spot_price).abs().idxmin()

                        def _highlight_atm(row):
                            return ["background-color: #fff3cd" if row.name == atm_idx else "" for _ in row]

                        st.dataframe(
                            result_df.style.apply(_highlight_atm, axis=1),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.dataframe(result_df, use_container_width=True, hide_index=True)

with tab_futures:
    fut_rows = inst.get_futures_rows(instrument_df, underlying)
    if fut_rows.empty:
        st.info(f"No futures contracts found for {underlying}.")
    else:
        load_futs = st.button("Load futures quotes", type="primary")
        if load_futs:
            with st.spinner("Fetching futures quotes..."):
                exchange_tokens = {}
                for _, row in fut_rows.iterrows():
                    exchange_tokens.setdefault(row["exch_seg"], []).append(row["token"])
                quotes = client.get_quotes(exchange_tokens, mode="FULL")
                quotes_by_token = {q["token"]: q for q in quotes}

                display_rows = []
                for _, row in fut_rows.iterrows():
                    q = quotes_by_token.get(row["token"])
                    display_rows.append(
                        {
                            "Symbol": row["symbol"],
                            "Expiry": row["expiry_date"].strftime("%d %b %Y") if row["expiry_date"] else "—",
                            "Lot size": row["lotsize"],
                            "LTP": q["ltp"] if q else None,
                            "Chg%": q["percent_change"] if q else None,
                            "Volume": q["volume"] if q else None,
                            "OI": q["open_interest"] if q else None,
                        }
                    )
                st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
