import streamlit as st

from core import database as db
from core import security
from core import session
from core import broker_factory
from brokers.angel_one import AngelOneAuthError
from brokers.kite import KiteAuthError

st.set_page_config(page_title="Manage Accounts", page_icon="🔗", layout="wide")
session.require_login()

user = session.current_user()
enc_key = st.session_state["enc_key"]

st.title("🔗 Manage broker accounts")

accounts = db.list_broker_accounts(user["id"])

st.subheader("Your connected accounts")
if not accounts:
    st.info("No broker accounts added yet. Add one below.")
else:
    for acc in accounts:
        broker_label = "Angel One" if acc["broker"] == "angel_one" else "Zerodha Kite"
        with st.expander(f"{broker_label} — {acc['nickname']}"):
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                if st.button("Test connection", key=f"test_{acc['id']}"):
                    try:
                        client = broker_factory.build_client(acc, enc_key)
                        client.connect()
                        st.success("Connected successfully.")
                    except (AngelOneAuthError, KiteAuthError, ValueError, ImportError) as exc:
                        st.error(str(exc))
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Unexpected error: {exc}")
            with c2:
                if acc["broker"] == "kite":
                    if st.button("Re-login (Kite)", key=f"relogin_{acc['id']}"):
                        st.session_state[f"kite_relogin_{acc['id']}"] = True
            with c3:
                if st.button("Delete", key=f"delete_{acc['id']}", type="secondary"):
                    db.delete_broker_account(acc["id"])
                    st.rerun()

            if acc["broker"] == "kite" and st.session_state.get(f"kite_relogin_{acc['id']}"):
                payload = security.decrypt_dict(enc_key, acc["encrypted_payload"])
                client = broker_factory.build_client(acc, enc_key)
                login_url = client.get_login_url()
                st.markdown(f"**Step 1.** [Open the Zerodha login page]({login_url}) and log in.")
                st.markdown(
                    "**Step 2.** After logging in, your browser will redirect to a URL "
                    "containing `request_token=...`. Paste that full URL (or just the token) below."
                )
                pasted = st.text_input("Redirected URL or request_token", key=f"kite_token_input_{acc['id']}")
                if st.button("Complete login", key=f"kite_complete_{acc['id']}"):
                    try:
                        access_token = client.generate_session(pasted)
                        import datetime

                        new_payload = broker_factory.payload_for_kite(
                            payload["api_key"],
                            payload["api_secret"],
                            access_token=access_token,
                            token_date=datetime.date.today().isoformat(),
                        )
                        encrypted = security.encrypt_dict(enc_key, new_payload)
                        db.update_broker_account_payload(acc["id"], encrypted)
                        st.session_state[f"kite_relogin_{acc['id']}"] = False
                        st.success("Kite login complete. Access token saved for today.")
                        st.rerun()
                    except KiteAuthError as exc:
                        st.error(str(exc))

st.divider()
st.subheader("Add a new broker account")

broker_choice = st.radio("Broker", ["Angel One", "Zerodha Kite"], horizontal=True)

if broker_choice == "Angel One":
    st.caption(
        "Angel One supports fully automated login, so this dashboard can connect on its own "
        "each time using your client ID, password/MPIN, and TOTP secret."
    )
    with st.form("add_angel_one_form"):
        nickname = st.text_input("Nickname for this account (e.g. 'My Angel One - main')")
        api_key = st.text_input("API key")
        client_id = st.text_input("Client ID")
        password = st.text_input("Password / MPIN", type="password")
        totp_secret = st.text_input(
            "TOTP secret",
            type="password",
            help="The base32 secret behind the QR code at smartapi.angelbroking.com/enable-totp "
            "(not a 6-digit code - the secret itself).",
        )
        submitted = st.form_submit_button("Add Angel One account", type="primary")
    if submitted:
        if not all([nickname.strip(), api_key.strip(), client_id.strip(), password, totp_secret.strip()]):
            st.error("All fields are required.")
        else:
            payload = broker_factory.payload_for_angel_one(api_key, client_id, password, totp_secret)
            encrypted = security.encrypt_dict(enc_key, payload)
            db.add_broker_account(user["id"], "angel_one", nickname.strip(), encrypted)
            st.success(f"Added Angel One account '{nickname.strip()}'.")
            st.rerun()

else:
    st.caption(
        "Zerodha's official API requires a one-time browser login per day (no automated "
        "password/TOTP login is supported by Zerodha for security reasons). Add your API "
        "key and secret first, then complete the login step below or from the account list above."
    )
    with st.form("add_kite_form"):
        nickname = st.text_input("Nickname for this account (e.g. 'My Zerodha - main')")
        api_key = st.text_input("API key")
        api_secret = st.text_input("API secret", type="password")
        submitted = st.form_submit_button("Add Zerodha Kite account", type="primary")
    if submitted:
        if not all([nickname.strip(), api_key.strip(), api_secret.strip()]):
            st.error("All fields are required.")
        else:
            payload = broker_factory.payload_for_kite(api_key, api_secret)
            encrypted = security.encrypt_dict(enc_key, payload)
            account_id = db.add_broker_account(user["id"], "kite", nickname.strip(), encrypted)
            st.session_state[f"kite_relogin_{account_id}"] = True
            st.success(f"Added Zerodha Kite account '{nickname.strip()}'. Complete login below.")
            st.rerun()
