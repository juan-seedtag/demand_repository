import uuid
import os
import jwt
import toml
from datetime import datetime, timedelta, timezone
from functools import wraps

# Allow OAuth over HTTP for local development
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from flask import session, redirect, request
from requests_oauthlib import OAuth2Session

import dash
from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc

# ── Load secrets (secrets.toml for local, env vars for production) ─────────────
def _load_secrets():
    toml_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    if os.path.exists(toml_path):
        return toml.load(toml_path)
    return {}

_secrets = _load_secrets()

def _get(section, key, env_var):
    try:
        return _secrets[section][key]
    except KeyError:
        return os.environ.get(env_var, "")

TABLEAU_SERVER  = _get("tableau", "server",        "TABLEAU_SERVER")
TABLEAU_SITE    = _get("tableau", "site",           "TABLEAU_SITE")
TABLEAU_USER    = _get("tableau", "username",       "TABLEAU_USERNAME")
CA_CLIENT_ID    = _get("tableau", "ca_client_id",   "CA_CLIENT_ID")
CA_SECRET_ID    = _get("tableau", "ca_secret_id",   "CA_SECRET_ID")
CA_SECRET_VAL   = _get("tableau", "ca_secret_val",  "CA_SECRET_VAL")
G_CLIENT_ID     = _get("google",  "client_id",      "GOOGLE_CLIENT_ID")
G_CLIENT_SECRET = _get("google",  "client_secret",  "GOOGLE_CLIENT_SECRET")
G_REDIRECT_URI  = _get("google",  "redirect_uri",   "GOOGLE_REDIRECT_URI")
ALLOWED_DOMAIN  = _get("google",  "allowed_domain", "ALLOWED_DOMAIN") or "seedtag.com"
FLASK_SECRET    = _get("google",  "cookie_secret",  "FLASK_SECRET") or "demand-dashboards-secret"

# ── Dashboards ─────────────────────────────────────────────────────────────────
DASHBOARDS = [
    {
        "name":      "Ad Exchange Analysis",
        "url":       f"{TABLEAU_SERVER}/t/{TABLEAU_SITE}/views/Demand-AdExchangeAnalysis/AdExchangeDemandSTBFM",
        "description": "TBD",
        "show_tabs": False,
    },
    {
        "name":      "Ad Exchange Investment per Brand",
        "url":       f"{TABLEAU_SERVER}/t/{TABLEAU_SITE}/views/Demand-AdExchangeInvestmentPerBrandAdomain/AdExchangeSTBFM",
        "description": "TBD",
        "show_tabs": False,
    },
    {
        "name":      "Ad Exchange — DSP & SSP Deepdive",
        "url":       f"{TABLEAU_SERVER}/t/{TABLEAU_SITE}/views/Demand-AdExchangeDSP-SSPDeepdive/OMPRevenue",
        "description": "TBD",
        "show_tabs": True,
    },
    {
        "name":      "Managed - Investment per Brand",
        "url":       f"{TABLEAU_SERVER}/t/{TABLEAU_SITE}/views/Managed-InvestmentperBrand/Managed-InvestmentPerBrand",
        "description": "TBD",
        "show_tabs": False,
    },
]

# ── Tableau JWT ────────────────────────────────────────────────────────────────
def generate_jwt() -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": CA_CLIENT_ID,
            "exp": now + timedelta(minutes=5),
            "jti": str(uuid.uuid4()),
            "aud": "tableau",
            "sub": TABLEAU_USER,
            "scp": ["tableau:views:embed"],
        },
        CA_SECRET_VAL,
        algorithm="HS256",
        headers={"kid": CA_SECRET_ID, "iss": CA_CLIENT_ID},
    )

# ── Dash app ───────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="Demand Dashboards",
)
server = app.server
server.secret_key = FLASK_SECRET
server.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
)

# ── Google OAuth ───────────────────────────────────────────────────────────────
G_AUTH_URL     = "https://accounts.google.com/o/oauth2/auth"
G_TOKEN_URL    = "https://accounts.google.com/o/oauth2/token"
G_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

def make_google_session(state=None):
    return OAuth2Session(
        G_CLIENT_ID,
        scope=["openid", "email", "profile"],
        redirect_uri=G_REDIRECT_URI,
        state=state,
    )

# ── Flask OAuth routes ─────────────────────────────────────────────────────────
@server.route("/login")
def login():
    google_session = make_google_session()
    auth_url, state = google_session.authorization_url(
        G_AUTH_URL,
        access_type="online",
        prompt="select_account",
    )
    session["oauth_state"] = state
    return redirect(auth_url)

@server.route("/callback")
def callback():
    google_session = make_google_session(state=session.get("oauth_state"))
    google_session.fetch_token(
        G_TOKEN_URL,
        client_secret=G_CLIENT_SECRET,
        authorization_response=request.url,
    )
    userinfo = google_session.get(G_USERINFO_URL).json()
    email    = userinfo.get("email", "")
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        return f"<h3>Access denied.</h3><p>Only @{ALLOWED_DOMAIN} accounts are allowed.</p>", 403
    session["user_email"] = email
    session["user_name"]  = userinfo.get("name", email)
    return redirect("/")

@server.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ── Auth guard ─────────────────────────────────────────────────────────────────
UNPROTECTED = {"/login", "/callback"}

@server.before_request
def require_login():
    if request.path in UNPROTECTED or request.path.startswith("/_dash"):
        return
    if "user_email" not in session:
        return redirect("/login")

# ── Tableau embed page (served as Flask route) ─────────────────────────────────
@server.route("/embed/<int:idx>")
def embed(idx):
    if idx < 0 or idx >= len(DASHBOARDS):
        return "Not found", 404
    d         = DASHBOARDS[idx]
    token     = generate_jwt()
    js_api    = f"{TABLEAU_SERVER}/javascripts/api/tableau.embedding.3.latest.min.js"
    tabs_attr = "" if d["show_tabs"] else "hide-tabs"
    return f"""<!DOCTYPE html>
<html>
<head>
  <script type="module">
    import {{ TableauViz }} from "{js_api}";
    window.addEventListener("DOMContentLoaded", () => {{
      const viz    = document.getElementById("viz");
      const status = document.getElementById("status");
      viz.addEventListener("firstinteractive", () => {{ status.style.display = "none"; }});
      viz.addEventListener("vizloaderror",     (e) => {{
        status.innerHTML = "<b style='color:red'>Error:</b><pre>" + JSON.stringify(e.detail, null, 2) + "</pre>";
      }});
    }});
  </script>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ overflow:hidden; }}
    tableau-viz {{ width:100vw; height:100vh; display:block; }}
    #status {{ padding:12px; color:#555; font-family:sans-serif; }}
  </style>
</head>
<body>
  <div id="status">⏳ Loading dashboard…</div>
  <tableau-viz id="viz" src="{d['url']}" token="{token}" toolbar="bottom" {tabs_attr}></tableau-viz>
</body>
</html>"""

# ── Layout helpers ─────────────────────────────────────────────────────────────
def sidebar():
    nav_items = [
        dbc.NavLink("🏠 Home", href="/", active="exact", className="text-dark"),
    ] + [
        dbc.NavLink(f"📈 {d['name']}", href=f"/dashboard/{i}", active="exact", className="text-dark")
        for i, d in enumerate(DASHBOARDS)
    ]
    return html.Div([
        html.H5("📊 Demand Dashboards", className="fw-bold mb-3"),
        html.Hr(),
        dbc.Nav(nav_items, vertical=True, pills=True),
        html.Hr(),
        html.Small(id="user-email", className="text-muted"),
        html.Br(),
        dbc.Button("Log out", href="/logout", color="outline-secondary", size="sm", className="mt-2"),
    ], style={
        "position": "fixed", "top": 0, "left": 0, "bottom": 0,
        "width": "260px", "padding": "20px", "backgroundColor": "#f8f9fa",
        "overflowY": "auto", "zIndex": 100,
    })

def home_page():
    cards = []
    for i, d in enumerate(DASHBOARDS, start=1):
        cards.append(
            dbc.Card(dbc.CardBody([
                dbc.Row([
                    dbc.Col(html.H2(str(i), className="text-muted"), width=1),
                    dbc.Col([
                        html.H5(d["name"], className="fw-bold mb-1"),
                        html.P(
                            d["description"] if d["description"] != "TBD"
                            else html.Em("Description coming soon."),
                            className="text-muted mb-2",
                        ),
                        dbc.Button("Open in Tableau ↗", href=d["url"], target="_blank",
                                   color="link", size="sm", className="p-0"),
                    ]),
                ], align="center"),
            ]), className="mb-3 shadow-sm")
        )
    return html.Div([
        html.H2("Demand Dashboards — Overview", className="mb-2"),
        html.P(
            "Welcome to the Demand Dashboards hub. Use the sidebar to navigate to any dashboard.",
            className="text-muted mb-4",
        ),
        html.Hr(),
        *cards,
        html.Hr(),
        html.Small("Built with Dash · Demand team · Seedtag", className="text-muted"),
    ])

def dashboard_page(idx):
    d = DASHBOARDS[idx]
    return html.Div([
        html.H3(d["name"], className="mb-3"),
        html.Iframe(
            src=f"/embed/{idx}",
            style={"width": "100%", "height": "90vh", "border": "none"},
        ),
    ])

# ── App layout ─────────────────────────────────────────────────────────────────
app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    sidebar(),
    html.Div(id="page-content", style={"marginLeft": "270px", "padding": "30px"}),
])

# ── Routing callback ───────────────────────────────────────────────────────────
@app.callback(
    Output("page-content", "children"),
    Output("user-email", "children"),
    Input("url", "pathname"),
)
def render_page(pathname):
    email = session.get("user_email", "")
    if pathname == "/" or pathname is None:
        return home_page(), f"👤 {email}"
    if pathname.startswith("/dashboard/"):
        try:
            idx = int(pathname.split("/")[-1])
            if 0 <= idx < len(DASHBOARDS):
                return dashboard_page(idx), f"👤 {email}"
        except ValueError:
            pass
    return html.H3("Page not found."), f"👤 {email}"

# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=8050)
