import requests
from flask import Flask, render_template, request

app = Flask(__name__)

DEFAULT_LYRICS_URL = "https://raw.githubusercontent.com/leejaew/SearchKeywordOccurrences/main/lyrics.txt"

def fetch_text(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text, None
    except requests.RequestException as e:
        return None, str(e)

@app.route("/", methods=["GET"])
def index():
    query = request.args.get("q", "").strip()
    url = request.args.get("url", "").strip() or DEFAULT_LYRICS_URL
    result = None
    error = None

    if query:
        text, fetch_error = fetch_text(url)
        if fetch_error:
            error = f"Could not fetch text from URL. ({fetch_error})"
        else:
            count = text.lower().count(query.lower())
            lines = [line.strip() for line in text.splitlines() if query.lower() in line.lower() and line.strip()]
            result = {
                "query": query,
                "count": count,
                "lines": lines[:10]
            }

    return render_template("index.html", result=result, error=error, query=query, url=url, default_url=DEFAULT_LYRICS_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
