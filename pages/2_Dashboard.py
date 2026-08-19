import pandas as pd
import streamlit as st

from core import database as db
from core import session
from core import broker_factory
from brokers.angel_one import AngelOneAuthError
from brokers.kite import KiteAuthError

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
session.require_login()

user = session.current_user()
enc_key = st.session_state["enc_key"]

st.title("📊 Positions, P&L and Funds")

accounts = db.list_broker_accounts(user["id"])

if not accounts:
    st.info("No broker accounts yet.")
    st.page_link("pages/1_Manage_Accounts.py", label="Add a broker account", icon="🔗")
    st.stop()

refresh = st.button("🔄 Refresh", type="primary")

all_positions = []
all_funds = []
errors = []

with st.spinner("Connecting to broker accounts..."):
    for acc in accounts:
        broker_label = "Angel One" if acc["broker"] == "angel_one" else "Zerodha Kite"
        try:
            client = broker_factory.build_client(acc, enc_key)

            if acc["broker"] == "kite":
                # Reuse an existing access_token if it still works; otherwise ask for re-login.
                if not client.verify_existing_token():
                    errors.append(
                        f"**{broker_label} — {acc['nickname']}**: no valid session for today. "
                        f"Go to *Manage broker accounts* and click 'Re-login (Kite)'."
                    )
                    continue
            else:
                client.connect()

            all_positions.extend(client.fetch_positions())
            all_funds.append(client.fetch_funds())

        except (AngelOneAuthError, KiteAuthError) as exc:
            errors.append(f"**{broker_label} — {acc['nickname']}**: {exc}")
        except ImportError as exc:
            errors.append(f"**{broker_label} — {acc['nickname']}**: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"**{broker_label} — {acc['nickname']}**: unexpected error - {exc}")

if errors:
    with st.expander(f"⚠️ {len(errors)} account(s) could not be reached", expanded=True):
        for err in errors:
            st.warning(err)

# --- Funds summary ---
st.subheader("Funds")
total_available = sum(f["available"] for f in all_funds)
total_used = sum(f["used"] for f in all_funds)
total_funds = sum(f["total"] for f in all_funds)

c1, c2, c3 = st.columns(3)
c1.metric("Total funds", f"₹{total_funds:,.2f}")
c2.metric("Used margin", f"₹{total_used:,.2f}")
c3.metric("Available", f"₹{total_available:,.2f}")

if all_funds:
    st.dataframe(pd.DataFrame(all_funds), use_container_width=True, hide_index=True)

st.divider()

# --- Positions & PnL ---
st.subheader("Positions")
if not all_positions:
    st.info("No open positions across your connected accounts.")
else:
    df = pd.DataFrame(all_positions)
    total_pnl = df["pnl"].sum()
    st.metric("Total P&L across all accounts", f"₹{total_pnl:,.2f}")

    def _highlight_pnl(val):
        color = "green" if val > 0 else ("red" if val < 0 else "gray")
        return f"color: {color}"

    styled = df.style.applymap(_highlight_pnl, subset=["pnl"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.caption("Grouped by account:")
    for account_name, group in df.groupby("account"):
        with st.expander(f"{group.iloc[0]['broker']} — {account_name} ({len(group)} position(s))"):
            st.dataframe(group.drop(columns=["account"]), use_container_width=True, hide_index=True)
