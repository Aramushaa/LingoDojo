from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from bot.config import BOT_TOKEN
from webapp.telegram_auth import verify_telegram_webapp_init_data
from pathlib import Path

from bot.db import init_db, import_packs_from_folder, get_due_count, get_status_counts  


app = FastAPI()
init_db()
import_packs_from_folder()


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
      <body style="font-family: sans-serif">
        <h1>WebApp is alive ✅</h1>
        <p>If you see this, ngrok should work too.</p>
      </body>
    </html>
    """

@app.get("/api/stats")
def api_stats(x_telegram_init_data: str = Header(default="")):
    parsed = verify_telegram_webapp_init_data(x_telegram_init_data, BOT_TOKEN)
    if not parsed:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    import json
    user = json.loads(parsed["user"])
    user_id = int(user["id"])

    due_today = get_due_count(user_id)
    counts = get_status_counts(user_id)

    return {
        "user_id": user_id,
        "due_today": due_today,
        "counts": counts
    }


@app.get("/stats", response_class=HTMLResponse)
def stats_page():
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>LingoDojo Stats</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body { font-family: system-ui, sans-serif; padding: 16px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 12px; margin: 12px 0; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; }
    .pill { padding: 8px 10px; border: 1px solid #ddd; border-radius: 999px; }
    .muted { color: #666; font-size: 14px; }
    button { padding: 10px 12px; border-radius: 10px; border: 1px solid #ddd; background: #fff; cursor: pointer; }
  </style>
</head>
<body>
  <h2>📊 Stats</h2>
  <div class="muted">This page loads stats from the backend API.</div>

  <div class="card">
    <div class="muted">User</div>
    <div id="userLine">Loading…</div>
  </div>

  <div class="card">
    <div class="muted">SRS</div>
    <div class="row">
      <div class="pill" id="dueToday">🔁 Due today: …</div>
      <div class="pill" id="newCount">⚪ New: …</div>
      <div class="pill" id="learningCount">🟡 Learning: …</div>
      <div class="pill" id="matureCount">🟢 Mature: …</div>
    </div>
  </div>

  <button onclick="loadStats()">🔄 Refresh</button>

  <script>
    function getInitData() {
      try {
        if (window.Telegram && window.Telegram.WebApp) {
          // Expand the WebApp for better UX
          window.Telegram.WebApp.ready();
          window.Telegram.WebApp.expand();

          return window.Telegram.WebApp.initData || "";
        }
      } catch (e) {}
      return "";
    }

    async function apiGet(path) {
      const initData = getInitData();
      const res = await fetch(path, {
        headers: {
          "X-Telegram-Init-Data": initData
        }
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`API error ${res.status}: ${text}`);
      }
      return await res.json();
    }

    async function loadStats() {
      try {
        const me = await apiGet("/api/me");
        document.getElementById("userLine").textContent =
          `@${me.username || "-"} | ${me.first_name || ""} | id=${me.user_id}`;

        const data = await apiGet("/api/stats");

        document.getElementById("dueToday").textContent = `🔁 Due today: ${data.due_today}`;
        document.getElementById("newCount").textContent = `⚪ New: ${data.counts.new ?? 0}`;
        document.getElementById("learningCount").textContent = `🟡 Learning: ${data.counts.learning ?? 0}`;
        document.getElementById("matureCount").textContent = `🟢 Mature: ${data.counts.mature ?? 0}`;
      } catch (err) {
        document.getElementById("userLine").textContent = "Not inside Telegram WebApp (or auth failed).";
        document.getElementById("dueToday").textContent = "🔁 Due today: -";
        console.error(err);
      }
    }

    loadStats();
  </script>

</body>
</html>
"""
    return HTMLResponse(html)

@app.get("/api/me")
def api_me(x_telegram_init_data: str = Header(default="")):
    """
    Client sends Telegram initData in header.
    Backend verifies signature and returns user identity.
    """
    parsed = verify_telegram_webapp_init_data(x_telegram_init_data, BOT_TOKEN)
    if not parsed:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    # Telegram gives user as JSON string in 'user'
    # It's a JSON string inside querystring, so parse it safely:
    import json
    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Missing user in initData")

    user = json.loads(user_raw)
    return {
        "user_id": user.get("id"),
        "first_name": user.get("first_name"),
        "username": user.get("username"),
        "language_code": user.get("language_code"),
    }
