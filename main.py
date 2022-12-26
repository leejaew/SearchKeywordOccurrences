import requests
import json

# Get the lyrics from the URL
url = "https://raw.githubusercontent.com/leejaew/SearchKeywordOccurrences/main/lyrics.txt"
response = requests.get(url)
lyrics = response.text

# Get the user's search term
search_term = input("Enter a word or phrase to search for in the lyrics: ")

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
