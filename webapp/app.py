from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from bot.config import BOT_TOKEN
from webapp.telegram_auth import verify_telegram_webapp_init_data
from pathlib import Path
import json
from bot.db import init_db, import_packs_from_folder, get_due_count, get_status_counts  


app = FastAPI()

print("BOT_TOKEN loaded, length:", len(BOT_TOKEN or ""))


@app.on_event("startup")
def startup():
    init_db()
    import_packs_from_folder()


def get_verified_user(x_telegram_init_data: str) -> dict:
    parsed = verify_telegram_webapp_init_data(x_telegram_init_data, BOT_TOKEN)
    if not parsed:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Missing user in initData")

    try:
        user = json.loads(user_raw)
    except Exception:
        raise HTTPException(status_code=401, detail="Bad user JSON in initData")

    if not user.get("id"):
        raise HTTPException(status_code=401, detail="Missing user.id in initData")

    return user


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


    user = get_verified_user(x_telegram_init_data)
    user_id = int(user["id"])

    due_today = get_due_count(user_id)
    counts = get_status_counts(user_id)

    return {"user_id": user_id, "due_today": due_today, "counts": counts}


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
    :root{
      --bg: #0b0f19;
      --card: rgba(255,255,255,0.06);
      --card2: rgba(255,255,255,0.08);
      --text: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.65);
      --border: rgba(255,255,255,0.12);
      --shadow: 0 18px 60px rgba(0,0,0,0.35);
      --radius: 18px;

      --good: #4ade80;
      --warn: #fbbf24;
      --info: #60a5fa;
      --danger:#fb7185;
    }

    /* Telegram theme support (falls back if not present) */
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background: var(--tg-theme-bg-color, var(--bg));
      color: var(--tg-theme-text-color, var(--text));
    }

    .wrap{
      padding: 18px 16px 28px;
      max-width: 520px;
      margin: 0 auto;
    }

    .topbar{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap: 10px;
      margin-bottom: 12px;
    }

    .title{
      display:flex;
      flex-direction:column;
      gap:2px;
    }

    .title h1{
      font-size: 18px;
      margin:0;
      letter-spacing: .2px;
    }

    .title .sub{
      font-size: 13px;
      color: var(--tg-theme-hint-color, var(--muted));
    }

    .pill{
      font-size: 12px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: rgba(255,255,255,0.04);
      color: var(--tg-theme-hint-color, var(--muted));
    }

    .grid{
      display:grid;
      gap: 12px;
    }

    .card{
      border: 1px solid var(--tg-theme-hint-color, var(--border));
      border-color: rgba(255,255,255,0.10);
      background: var(--tg-theme-secondary-bg-color, var(--card));
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow:hidden;
      position: relative;
    }

    .cardInner{
      padding: 14px;
    }

    .hero{
      padding: 16px 14px;
      background: radial-gradient(1200px 300px at 20% 0%, rgba(96,165,250,0.35), transparent 60%),
                  radial-gradient(900px 280px at 90% 20%, rgba(74,222,128,0.28), transparent 60%),
                  rgba(255,255,255,0.05);
    }

    .heroRow{
      display:flex;
      align-items:flex-end;
      justify-content:space-between;
      gap: 10px;
    }

    .bigNum{
      font-size: 44px;
      line-height: 1;
      font-weight: 800;
      letter-spacing: -1px;
    }

    .heroLabel{
      font-size: 13px;
      color: var(--tg-theme-hint-color, var(--muted));
      margin-top: 4px;
    }

    .badge{
      display:inline-flex;
      align-items:center;
      gap:8px;
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(0,0,0,0.12);
      color: var(--tg-theme-text-color, var(--text));
      font-size: 13px;
      white-space: nowrap;
    }

    .spark{
      width:10px;height:10px;border-radius:999px;
      background: var(--info);
      box-shadow: 0 0 18px rgba(96,165,250,0.9);
      animation: pulse 1.2s infinite ease-in-out;
    }

    @keyframes pulse{
      0%,100%{ transform: scale(0.9); opacity: 0.75; }
      50%{ transform: scale(1.25); opacity: 1; }
    }

    .rows{
      display:grid;
      gap: 10px;
      padding: 14px;
    }

    .row{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap: 10px;
    }

    .label{
      font-size: 13px;
      color: var(--tg-theme-hint-color, var(--muted));
      display:flex;
      align-items:center;
      gap:8px;
    }

    .val{
      font-weight: 700;
      font-size: 14px;
    }

    .bar{
      height: 10px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.05);
      overflow:hidden;
      position: relative;
      margin-top: 8px;
    }

    .bar > div{
      height: 100%;
      width: 0%;
      border-radius: 999px;
      background: linear-gradient(90deg, rgba(96,165,250,0.9), rgba(74,222,128,0.9));
      transition: width 700ms cubic-bezier(.2,.8,.2,1);
    }

    .btnRow{
      display:flex;
      gap: 10px;
      padding: 12px 14px 14px;
    }

    button{
      flex:1;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(255,255,255,0.06);
      color: var(--tg-theme-text-color, var(--text));
      padding: 12px 12px;
      border-radius: 14px;
      cursor:pointer;
      font-weight: 700;
      letter-spacing: .2px;
      transition: transform 120ms ease, background 120ms ease;
    }
    button:active{ transform: scale(0.98); }
    button:hover{ background: rgba(255,255,255,0.09); }

    .error{
      border-color: rgba(251,113,133,0.35);
      background: rgba(251,113,133,0.12);
      color: rgba(255,255,255,0.92);
    }
    .error .muted { color: rgba(255,255,255,0.72); }

    .muted{ color: var(--tg-theme-hint-color, var(--muted)); font-size: 12.5px; }

    /* Skeleton loading */
    .skel{
      background: linear-gradient(90deg, rgba(255,255,255,0.06), rgba(255,255,255,0.14), rgba(255,255,255,0.06));
      background-size: 200% 100%;
      animation: shimmer 1.2s infinite linear;
      border-radius: 10px;
    }
    @keyframes shimmer{
      0%{ background-position: 200% 0; }
      100%{ background-position: -200% 0; }
    }
    .skelLine{ height: 14px; width: 160px; }
    .skelBig{ height: 44px; width: 80px; border-radius: 14px; }

    #diag{ opacity: .7; font-size: 12px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="title">
        <h1>📊 Stats</h1>
        <div class="sub" id="userLine">Loading identity…</div>
      </div>
      <div class="pill" id="diag">…</div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="hero">
          <div class="heroRow">
            <div>
              <div class="bigNum" id="dueNum"><span class="skel skelBig"></span></div>
              <div class="heroLabel">Due Today</div>
            </div>
            <div class="badge"><span class="spark"></span><span id="mood">Loading…</span></div>
          </div>

          <div class="bar" aria-label="Progress bar">
            <div id="progressFill"></div>
          </div>
          <div class="muted" style="margin-top:8px;" id="progressText">Calculating progress…</div>
        </div>

        <div class="rows">
          <div class="row">
            <div class="label">⚪ New</div>
            <div class="val" id="newCount"><span class="skel skelLine"></span></div>
          </div>
          <div class="row">
            <div class="label">🟡 Learning</div>
            <div class="val" id="learningCount"><span class="skel skelLine"></span></div>
          </div>
          <div class="row">
            <div class="label">🟢 Mature</div>
            <div class="val" id="matureCount"><span class="skel skelLine"></span></div>
          </div>
        </div>

        <div class="btnRow">
          <button onclick="refresh()">🔄 Refresh</button>
          <button onclick="hint()">🛠 Fix Auth</button>
        </div>
      </div>

      <div class="card error" id="errorCard" style="display:none;">
        <div class="cardInner">
          <div style="font-weight:800;">Auth / Loading issue</div>
          <div class="muted" id="errorText" style="margin-top:6px;"></div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function setError(show, text){
      const card = document.getElementById("errorCard");
      const t = document.getElementById("errorText");
      card.style.display = show ? "block" : "none";
      t.textContent = text || "";
    }

    function diagSet(msg){
      const diag = document.getElementById("diag");
      diag.textContent = msg;
    }

    function getInitData(){
      const hasTG = !!(window.Telegram && window.Telegram.WebApp);
      const initData = hasTG ? (window.Telegram.WebApp.initData || "") : "";
      console.log("initDataLen:", initData.length);
      diagSet(`TG=${hasTG} | initDataLen=${initData.length}`);
      return initData;
    }

    async function apiGet(path){
      const initData = getInitData();
      const res = await fetch(path, {
        headers: { "X-Telegram-Init-Data": initData }
      });
      if(!res.ok){
        const txt = await res.text();
        throw new Error(`API ${res.status}: ${txt}`);
      }
      return await res.json();
    }

    function moodText(due){
      if (due === 0) return "Chill — you're clear ✅";
      if (due <= 5) return "Light work — keep it moving";
      if (due <= 15) return "Solid session incoming";
      return "Boss fight today 💀";
    }

    function setProgress(newC, learningC, matureC){
      const total = Math.max(1, newC + learningC + matureC);
      const maturePct = Math.round((matureC / total) * 100);
      const fill = document.getElementById("progressFill");
      fill.style.width = maturePct + "%";
      document.getElementById("progressText").textContent =
        `Mature progress: ${maturePct}% of tracked items`;
    }

    async function load(){
      setError(false, "");
      try{
        // Telegram UX polish
        if (window.Telegram && window.Telegram.WebApp){
          window.Telegram.WebApp.ready();
          window.Telegram.WebApp.expand();
        }

        const me = await apiGet("/api/me");
        document.getElementById("userLine").textContent =
          `@${me.username || "-"} • ${me.first_name || ""} • id=${me.user_id}`;

        const data = await apiGet("/api/stats");

        const due = data.due_today ?? 0;
        const c = data.counts || {new:0, learning:0, mature:0};

        document.getElementById("dueNum").textContent = due;
        document.getElementById("mood").textContent = moodText(due);

        document.getElementById("newCount").textContent = c.new ?? 0;
        document.getElementById("learningCount").textContent = c.learning ?? 0;
        document.getElementById("matureCount").textContent = c.mature ?? 0;

        setProgress(c.new ?? 0, c.learning ?? 0, c.mature ?? 0);

      }catch(err){
        document.getElementById("userLine").textContent = "Not inside Telegram WebApp (or auth failed).";
        document.getElementById("dueNum").textContent = "—";
        document.getElementById("mood").textContent = "Auth needed";
        document.getElementById("progressText").textContent = "Open this page via the bot WebApp button.";

        setError(true,
          "1) Open via Telegram WebApp button (not browser). " +
          "2) Set domain in BotFather (/setdomain) to your ngrok domain. " +
          "3) Ensure the bot button uses WebAppInfo. " +
          "Details: " + String(err)
        );
        console.error(err);
      }
    }

    function refresh(){ load(); }

    function hint(){
      alert(
        "Fix checklist:\\n" +
        "• Open the page from Telegram via the WebApp button\\n" +
        "• In BotFather set your domain to: <your-ngrok-domain>\\n" +
        "• Button must use WebAppInfo(url=...)\\n" +
        "• ngrok must be https"
      );
    }

    load();
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

    user = get_verified_user(x_telegram_init_data)
    return {
        "user_id": int(user["id"]),
        "first_name": user.get("first_name"),
        "username": user.get("username"),
        "language_code": user.get("language_code"),
    }

@app.get("/api/debug-init")
def debug_init(x_telegram_init_data: str = Header(default="")):
    return {
        "has_header": bool(x_telegram_init_data),
        "header_len": len(x_telegram_init_data or ""),
        "header_preview": (x_telegram_init_data[:80] + "...") if x_telegram_init_data else "",
        "contains_hash": ("hash=" in (x_telegram_init_data or "")),
    }

@app.get("/debug", response_class=HTMLResponse)
def debug_page():
    html = """
    <!doctype html>
    <html>
    <body style="font-family:system-ui;padding:16px;">
      <h3>Telegram WebApp Debug</h3>
      <pre id="out">Loading...</pre>
      <script>
        const hasTG = !!(window.Telegram && window.Telegram.WebApp);
        const initData = hasTG ? (window.Telegram.WebApp.initData || "") : "";
        const user = hasTG ? (window.Telegram.WebApp.initDataUnsafe?.user || null) : null;

        document.getElementById("out").textContent = JSON.stringify({
          hasTG,
          initDataLen: initData.length,
          hasUnsafeUser: !!user,
          unsafeUser: user
        }, null, 2);
      </script>
    </body>
    </html>
    """
    return HTMLResponse(html)
