import requests
import json
import sys

# Get the search term from command-line argument
if len(sys.argv) < 2:
    print(json.dumps({"error": "Usage: python3 main.py <keyword>"}))
    sys.exit(1)

search_term = sys.argv[1]

# Get the lyrics from the URL
url = "https://raw.githubusercontent.com/leejaew/SearchKeywordOccurrences/main/lyrics.txt"
response = requests.get(url)
lyrics = response.text

# Find the number of occurrences of the search term in the lyrics
num_occurrences = lyrics.count(search_term)

# Generate the response payload in JSON format
payload = {
    "search_term": search_term,
    "num_occurrences": num_occurrences
}
response_json = json.dumps(payload)

# Print the response payload
print(response_json)
