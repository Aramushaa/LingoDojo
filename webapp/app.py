from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
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
def api_stats(user_id: int = Query(..., description="Telegram user id")):
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
    // MVP: you can hardcode a user_id for testing.
    // Later: we'll read Telegram user id from Telegram.WebApp.initDataUnsafe.
    const TEST_USER_ID = 94367831; // <-- replace with your Telegram numeric user id to test quickly

    function getUserId() {
      try {
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe) {
          const u = window.Telegram.WebApp.initDataUnsafe.user;
          if (u && u.id) return u.id;
        }
      } catch (e) {}
      return TEST_USER_ID;
    }

    async function loadStats() {
      const userId = getUserId();
      document.getElementById("userLine").textContent = `user_id=${userId}`;

      if (!userId || userId === 0) {
        document.getElementById("dueToday").textContent = "🔁 Due today: (set TEST_USER_ID)";
        return;
      }

      const res = await fetch(`/api/stats?user_id=${userId}`);
      const data = await res.json();

      document.getElementById("dueToday").textContent = `🔁 Due today: ${data.due_today}`;
      document.getElementById("newCount").textContent = `⚪ New: ${data.counts.new ?? 0}`;
      document.getElementById("learningCount").textContent = `🟡 Learning: ${data.counts.learning ?? 0}`;
      document.getElementById("matureCount").textContent = `🟢 Mature: ${data.counts.mature ?? 0}`;
    }

    loadStats();
  </script>
</body>
</html>
"""
    return HTMLResponse(html)

