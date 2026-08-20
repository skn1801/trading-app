import streamlit as st

from core import database as db
from core import session
from core import broker_factory
from brokers import instruments as inst
from brokers.angel_one import AngelOneAuthError

st.set_page_config(page_title="Market Watch", page_icon="📍", layout="wide")
session.require_login()

user = session.current_user()
enc_key = st.session_state["enc_key"]

st.title("📍 Market Watch")
st.caption("Live index prices, fetched through one of your connected Angel One accounts.")

angel_accounts = db.list_broker_accounts(user["id"], broker="angel_one")
if not angel_accounts:
    st.info("This needs at least one connected Angel One account (market data isn't available through Kite here).")
    st.page_link("pages/1_Manage_Accounts.py", label="Add an Angel One account", icon="🔗")
    st.stop()

account_names = {a["id"]: a["nickname"] for a in angel_accounts}
selected_id = st.selectbox(
    "Use account", options=list(account_names.keys()), format_func=lambda i: account_names[i]
)
selected_account = next(a for a in angel_accounts if a["id"] == selected_id)

refresh = st.button("🔄 Refresh prices", type="primary")

if "market_watch_cache" not in st.session_state or refresh:
    try:
        client = broker_factory.build_client(selected_account, enc_key)
        client.connect()

        # Pull the instrument master (cached ~daily) just to resolve current
        # index tokens - Angel occasionally changes these, so we don't hardcode them.
        instrument_df = inst.download_instrument_master()
        targets = inst.get_index_quote_targets(instrument_df)

        exchange_tokens = {}
        for _, (exchange, _symbol, token) in targets.items():
            exchange_tokens.setdefault(exchange, []).append(token)

        quotes = client.get_quotes(exchange_tokens, mode="FULL")
        quotes_by_token = {q["token"]: q for q in quotes}

        st.session_state["market_watch_cache"] = {
            label: quotes_by_token.get(token)
            for label, (_ex, _sym, token) in targets.items()
        }
        st.session_state["market_watch_error"] = None
    except (AngelOneAuthError, ImportError) as exc:
        st.session_state["market_watch_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        st.session_state["market_watch_error"] = f"Unexpected error: {exc}"

if st.session_state.get("market_watch_error"):
    st.error(st.session_state["market_watch_error"])

cache = st.session_state.get("market_watch_cache") or {}
cols = st.columns(3)
for col, label in zip(cols, ["NIFTY 50", "NIFTY BANK", "SENSEX"]):
    quote = cache.get(label)
    with col:
        if quote is None:
            st.metric(label, "—")
            st.caption("No data yet - click Refresh.")
        else:
            st.metric(
                label,
                f"{quote['ltp']:,.2f}",
                delta=f"{quote['net_change']:+,.2f} ({quote['percent_change']:+.2f}%)",
            )

st.divider()
st.page_link("pages/4_Option_Chain.py", label="Open option chain / futures explorer", icon="🧮")
