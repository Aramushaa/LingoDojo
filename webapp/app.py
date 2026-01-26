from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

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
