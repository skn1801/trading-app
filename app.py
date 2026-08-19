import streamlit as st

from core import database as db
from core import security
from core import session

st.set_page_config(page_title="Trading Dashboard", page_icon="📈", layout="wide")

db.init_db()


def render_login_gate():
    st.title("📈 Trading Dashboard")
    st.caption(
        "A local, offline dashboard for your own Angel One and Zerodha Kite accounts. "
        "Nothing here is uploaded anywhere - everything lives in a file on this computer."
    )

    has_users = db.any_user_exists()
    tab_labels = ["Log In"] if has_users else ["Create Account"]
    if has_users:
        tab_labels.append("Create Another Account")
    tabs = st.tabs(tab_labels)

    # --- Login tab ---
    if has_users:
        with tabs[0]:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Log in", type="primary")
            if submitted:
                user = db.get_user_by_username(username.strip())
                if not user or not security.verify_password(password, user["password_hash"]):
                    st.error("Incorrect username or password.")
                else:
                    enc_key = security.derive_encryption_key(password, user["kdf_salt"])
                    session.login(user["id"], user["username"], enc_key)
                    st.rerun()

    # --- Create account tab ---
    create_tab = tabs[-1]
    with create_tab:
        st.write(
            "This password protects the app **and** encrypts every broker credential you add. "
            "There is no password reset - if you forget it, you'll need to delete the local "
            "database and re-add your broker accounts. Store it somewhere safe."
        )
        with st.form("create_account_form"):
            new_username = st.text_input("Choose a username")
            new_password = st.text_input("Choose a password", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            if not new_username.strip() or not new_password:
                st.error("Username and password are required.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            elif len(new_password) < 8:
                st.error("Use at least 8 characters for your password.")
            elif db.get_user_by_username(new_username.strip()):
                st.error("That username is already taken.")
            else:
                password_hash = security.hash_password(new_password)
                kdf_salt = security.generate_kdf_salt()
                user_id = db.create_user(new_username.strip(), password_hash, kdf_salt)
                enc_key = security.derive_encryption_key(new_password, kdf_salt)
                session.login(user_id, new_username.strip(), enc_key)
                st.success("Account created.")
                st.rerun()


def render_logged_in_home():
    user = session.current_user()
    st.title("📈 Trading Dashboard")
    st.success(f"Logged in as **{user['username']}**")

    col1, col2 = st.columns(2)
    with col1:
        st.page_link("pages/1_Manage_Accounts.py", label="Manage broker accounts", icon="🔗")
    with col2:
        st.page_link("pages/2_Dashboard.py", label="View positions, P&L and funds", icon="📊")

    st.divider()
    if st.button("Log out"):
        session.logout()
        st.rerun()


if session.is_logged_in():
    render_logged_in_home()
else:
    render_login_gate()
