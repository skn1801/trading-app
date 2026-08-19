"""
Small helpers around st.session_state so every page logs in/out the same way.

Nothing sensitive is ever persisted by Streamlit itself - the decrypted
encryption key (`enc_key`) lives only in this browser session's server-side
memory and disappears the moment the app process restarts or you log out.
"""

import streamlit as st


def is_logged_in() -> bool:
    return bool(st.session_state.get("user_id")) and st.session_state.get("enc_key") is not None


def current_user():
    if not is_logged_in():
        return None
    return {
        "id": st.session_state["user_id"],
        "username": st.session_state["username"],
    }


def login(user_id: int, username: str, enc_key: bytes):
    st.session_state["user_id"] = user_id
    st.session_state["username"] = username
    st.session_state["enc_key"] = enc_key


def logout():
    for key in ("user_id", "username", "enc_key", "broker_clients"):
        st.session_state.pop(key, None)


def require_login():
    """Call at the top of every page in pages/. Stops the page if not logged in."""
    if not is_logged_in():
        st.warning("Please log in from the main app page first.")
        st.page_link("app.py", label="Go to login", icon="🔐")
        st.stop()


def get_broker_clients_cache() -> dict:
    """A per-session cache of live, connected broker client objects, keyed by account id.

    This avoids re-logging-in to Angel One / re-checking Kite tokens on every
    single widget interaction/rerun within the same browser session.
    """
    if "broker_clients" not in st.session_state:
        st.session_state["broker_clients"] = {}
    return st.session_state["broker_clients"]
