import uuid
import base64
import os
import streamlit as st
import jwt
from datetime import datetime, timedelta, timezone
from requests_oauthlib import OAuth2Session

st.set_page_config(
    page_title="Demand Dashboards",
    page_icon="📊",
    layout="wide",
)

# ── Config ─────────────────────────────────────────────────────────────────────
SERVER       = st.secrets["tableau"]["server"]
SITE         = st.secrets["tableau"]["site"]
USERNAME     = st.secrets["tableau"]["username"]
CA_CLIENT_ID = st.secrets["tableau"]["ca_client_id"]
CA_SECRET_ID = st.secrets["tableau"]["ca_secret_id"]
CA_SECRET_VAL= st.secrets["tableau"]["ca_secret_val"]

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
G_CLIENT_ID     = st.secrets["google"]["client_id"]
G_CLIENT_SECRET = st.secrets["google"]["client_secret"]
G_REDIRECT_URI  = st.secrets["google"]["redirect_uri"]
G_ALLOWED_DOMAIN= st.secrets["google"]["allowed_domain"]
G_AUTH_URL      = "https://accounts.google.com/o/oauth2/auth"
G_TOKEN_URL     = "https://accounts.google.com/o/oauth2/token"
G_USERINFO_URL  = "https://www.googleapis.com/oauth2/v3/userinfo"

DASHBOARDS = [
    {
        "name": "Ad Exchange Analysis",
        "url": f"{SERVER}/t/{SITE}/views/Demand-AdExchangeAnalysis/AdExchangeDemandSTBFM",
        "description": "TBD",
    },
    {
        "name": "Ad Exchange Investment per Brand",
        "url": f"{SERVER}/t/{SITE}/views/Demand-AdExchangeInvestmentPerBrandAdomain/AdExchangeSTBFM",
        "description": "TBD",
    },
    {
        "name": "Ad Exchange — DSP & SSP Deepdive",
        "url": f"{SERVER}/t/{SITE}/views/Demand-AdExchangeDSP-SSPDeepdive/OMPRevenue",
        "description": "TBD",
        "show_tabs": True,
    },
    {
        "name": "Managed - Investment per Brand",
        "url": f"{SERVER}/t/{SITE}/views/Managed-InvestmentperBrand/Managed-InvestmentPerBrand",
        "description": "TBD",
    },
]

# ── Google OAuth ───────────────────────────────────────────────────────────────
def make_oauth_session(state=None):
    return OAuth2Session(
        G_CLIENT_ID,
        scope=["openid", "email", "profile"],
        redirect_uri=G_REDIRECT_URI,
        state=state,
    )


def show_login() -> None:
    params = st.query_params

    if "code" in params:
        try:
            google = make_oauth_session(state=params.get("state"))
            google.fetch_token(
                G_TOKEN_URL,
                client_secret=G_CLIENT_SECRET,
                code=params["code"],
            )
            userinfo = google.get(G_USERINFO_URL).json()
            email = userinfo.get("email", "")
            if email.endswith(f"@{G_ALLOWED_DOMAIN}"):
                st.session_state["authenticated"] = True
                st.session_state["user_email"] = email
                st.query_params.clear()
                st.rerun()
            else:
                st.query_params.clear()
                st.error(f"Access restricted to @{G_ALLOWED_DOMAIN} accounts.")
        except Exception as e:
            st.query_params.clear()
            st.error(f"Authentication error: {e}")
        return

    google = make_oauth_session()
    auth_url, state = google.authorization_url(
        G_AUTH_URL,
        access_type="online",
        prompt="select_account",
    )
    st.session_state["oauth_state"] = state

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 📊 Demand Dashboards")
        st.markdown("Sign in with your Seedtag Google account to continue.")
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <a href="{auth_url}" target="_top" style="text-decoration:none;">
              <div style="
                display:flex; align-items:center; gap:12px;
                background:white; border:1px solid #dadce0; border-radius:6px;
                padding:12px 24px; cursor:pointer; width:fit-content;
                font-family:'Google Sans',sans-serif; font-size:15px;
                color:#3c4043; font-weight:500;
                box-shadow:0 1px 3px rgba(0,0,0,0.1);
              ">
                <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" width="20"/>
                Sign in with Google
              </div>
            </a>
            """,
            unsafe_allow_html=True,
        )


# ── Auth gate ──────────────────────────────────────────────────────────────────
if not st.session_state.get("authenticated"):
    show_login()
    st.stop()


# ── JWT generator ──────────────────────────────────────────────────────────────
def generate_jwt() -> str:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": CA_CLIENT_ID,
            "exp": now + timedelta(minutes=5),
            "jti": str(uuid.uuid4()),
            "aud": "tableau",
            "sub": USERNAME,
            "scp": ["tableau:views:embed"],
        },
        CA_SECRET_VAL,
        algorithm="HS256",
        headers={
            "kid": CA_SECRET_ID,
            "iss": CA_CLIENT_ID,
        },
    )
    return token


# ── Embed component ────────────────────────────────────────────────────────────
def render_tableau(url: str, height: int = 900, show_tabs: bool = False) -> None:
    token = generate_jwt()
    js_api = f"{SERVER}/javascripts/api/tableau.embedding.3.latest.min.js"
    tabs_attr = "" if show_tabs else "hide-tabs"
    html = f"""<!DOCTYPE html>
<html>
<head>
  <script type="module">
    import {{ TableauViz }} from "{js_api}";

    window.addEventListener("DOMContentLoaded", () => {{
      const viz = document.getElementById("tableauViz");
      const status = document.getElementById("status");

      viz.addEventListener("firstinteractive", () => {{
        status.style.display = "none";
      }});

      viz.addEventListener("vizloaderror", (e) => {{
        status.innerHTML = "<b style='color:red'>Error loading dashboard:</b><br><pre>" +
          JSON.stringify(e.detail, null, 2) + "</pre>";
      }});
    }});
  </script>
  <style>
    body {{ margin: 0; padding: 0; overflow: hidden; font-family: sans-serif; }}
    tableau-viz {{ width: 100%; height: {height}px; }}
    #status {{ padding: 12px; color: #555; }}
  </style>
</head>
<body>
  <div id="status">⏳ Loading dashboard…</div>
  <tableau-viz
    id="tableauViz"
    src="{url}"
    token="{token}"
    toolbar="bottom"
    {tabs_attr}>
  </tableau-viz>
</body>
</html>"""
    st.components.v1.html(html, height=height + 10, scrolling=False)


# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 Demand Dashboards")
    st.caption(f"👤 {st.session_state.get('user_email', '')}")
    if st.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.markdown("---")
    pages = ["🏠 Home"] + [f"📈 {d['name']}" for d in DASHBOARDS]
    selection = st.radio("Navigate to", pages, label_visibility="collapsed")


# ── Home / README page ────────────────────────────────────────────────────────
if selection == "🏠 Home":
    st.title("Demand Dashboards — Overview")
    st.markdown(
        """
Welcome to the **Demand Dashboards** hub. This app provides quick access to the
Ad Exchange Tableau dashboards used by the Demand team at Seedtag.

Use the **sidebar** to navigate directly to any dashboard.

---
"""
    )

    for i, d in enumerate(DASHBOARDS, start=1):
        with st.container(border=True):
            col_num, col_info = st.columns([1, 11])
            with col_num:
                st.markdown(f"### {i}")
            with col_info:
                st.markdown(f"### {d['name']}")
                st.markdown(
                    d["description"] if d["description"] != "TBD"
                    else "_Description coming soon._"
                )
                if d["url"]:
                    st.markdown(f"[Open in Tableau ↗]({d['url']})")
                else:
                    st.caption("URL not configured yet.")

    st.markdown("---")
    st.caption("Built with Streamlit · Demand team · Seedtag")


# ── Dashboard pages ───────────────────────────────────────────────────────────
else:
    dashboard = next(d for d in DASHBOARDS if f"📈 {d['name']}" == selection)
    st.title(dashboard["name"])

    if dashboard["description"] != "TBD":
        st.markdown(dashboard["description"])
        st.markdown("---")

    if not dashboard["url"]:
        st.warning("No URL configured for this dashboard yet.")
    else:
        render_tableau(dashboard["url"], show_tabs=dashboard.get("show_tabs", False))
