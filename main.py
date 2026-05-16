import requests
import json
from flask import Flask, render_template, request

app = Flask(__name__)

LYRICS_URL = "https://raw.githubusercontent.com/leejaew/SearchKeywordOccurrences/main/lyrics.txt"

def fetch_lyrics():
    try:
        response = requests.get(LYRICS_URL, timeout=10)
        response.raise_for_status()
        return response.text, None
    except requests.RequestException as e:
        return None, str(e)

@app.route("/", methods=["GET"])
def index():
    query = request.args.get("q", "").strip()
    result = None
    error = None

    if query:
        lyrics, fetch_error = fetch_lyrics()
        if fetch_error:
            error = "Could not fetch lyrics. Please try again."
        else:
            count = lyrics.lower().count(query.lower())
            lines = [line.strip() for line in lyrics.splitlines() if query.lower() in line.lower() and line.strip()]
            result = {
                "query": query,
                "count": count,
                "lines": lines[:10]
            }

    return render_template("index.html", result=result, error=error, query=query)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
