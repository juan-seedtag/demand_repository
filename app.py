import uuid
import streamlit as st
import jwt
from datetime import datetime, timedelta, timezone

st.set_page_config(
    page_title="Demand Dashboards",
    page_icon="📊",
    layout="wide",
)

# ── Tableau config ─────────────────────────────────────────────────────────────
SERVER       = st.secrets["tableau"]["server"]
SITE         = st.secrets["tableau"]["site"]
USERNAME     = st.secrets["tableau"]["username"]
CA_CLIENT_ID = st.secrets["tableau"]["ca_client_id"]
CA_SECRET_ID = st.secrets["tableau"]["ca_secret_id"]
CA_SECRET_VAL= st.secrets["tableau"]["ca_secret_val"]

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

# ── JWT generator ──────────────────────────────────────────────────────────────
def generate_jwt() -> str:
    # Use the logged-in user's email so Tableau applies their own permissions.
    # Falls back to the service account if viewer auth is not enabled.
    try:
        user_email = st.user.email if st.user.is_logged_in else USERNAME
    except Exception:
        user_email = USERNAME
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": CA_CLIENT_ID,
            "exp": now + timedelta(minutes=5),
            "jti": str(uuid.uuid4()),
            "aud": "tableau",
            "sub": user_email,
            "scp": ["tableau:views:embed"],
        },
        CA_SECRET_VAL,
        algorithm="HS256",
        headers={
            "kid": CA_SECRET_ID,
            "iss": CA_CLIENT_ID,
        },
    )


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
    st.markdown("---")
    pages = ["🏠 Home"] + [f"📈 {d['name']}" for d in DASHBOARDS]
    selection = st.radio("Navigate to", pages, label_visibility="collapsed")
    st.markdown("---")
    try:
        st.caption(f"🔍 st.user attrs: {[a for a in dir(st.user) if not a.startswith('_')]}")
    except Exception as e:
        st.caption(f"⚠️ Error: {e}")
    if st.button("Log out", use_container_width=True):
        st.logout()


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
