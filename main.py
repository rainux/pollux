# uv project setup:
# uv init
# uv add beautifulsoup4
# uv add markdownify

import json
import base64

from datetime import datetime
from bs4 import BeautifulSoup
import os

HAR_FILE = 'myactivity.google.com.har'
OUTPUT_JSON_FILE = 'recovered_gemini.json'
OUTPUT_MD_FILE = 'recovered_gemini.md'

def strip_json_prefix(text):
    """Strips the common Google JSON prefix `)]}'` from a string."""
    if text.startswith(")]}'"):
        return text[4:]
    return text

def decode_har_entry_content(content):
    """Decodes content from a HAR entry, handling base64 if specified."""
    if content.get('encoding') == 'base64' and content.get('text'):
        try:
            return base64.b64decode(content['text']).decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"Error decoding base64 content: {e}")
            return None
    return content.get('text')

def find_gemini_data_in_json(data):
    """
    Recursively searches for Gemini chat data within a JSON structure.
    Looks for patterns indicative of user prompts and timestamps.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "query_text" and isinstance(value, str):
                # Found a potential prompt
                return value
            if key == "query" and isinstance(value, str):
                return value
            result = find_gemini_data_in_json(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_gemini_data_in_json(item)
            if result:
                return result
    return None

def find_timestamp_in_json(data):
    """
    Recursively searches for a timestamp within a JSON structure.
    Assumes timestamp is an integer representing milliseconds or microseconds since epoch.
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ["timestamp", "time_usec", "query_timestamp"] and isinstance(value, (int, str)):
                try:
                    # Attempt to convert to int, handle potential string timestamps
                    ts = int(value)
                    # Heuristic: If it's a very large number, it's likely microseconds, convert to milliseconds
                    if ts > 999999999999: # More than 13 digits, likely microseconds
                        return datetime.fromtimestamp(ts / 1_000_000)
                    elif ts > 999999999: # More than 10 digits, likely milliseconds
                        return datetime.fromtimestamp(ts / 1_000)
                    else: # Assume seconds
                        return datetime.fromtimestamp(ts)
                except ValueError:
                    pass # Not a valid integer timestamp
            result = find_timestamp_in_json(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_timestamp_in_json(item)
            if result:
                return result
    return None

def parse_har_file(har_file_path):
    """Parses the HAR file to extract Gemini chat records."""
    recovered_records = []

    if not os.path.exists(har_file_path):
        print(f"Error: HAR file not found at '{har_file_path}'")
        return []

    with open(har_file_path, 'r', encoding='utf-8') as f:
        try:
            har_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error decoding HAR file '{har_file_path}': {e}")
            return []

    entries = har_data.get('log', {}).get('entries', [])
    print(f"Found {len(entries)} HAR entries. Processing...")

    for i, entry in enumerate(entries):
        request = entry.get('request', {})
        response = entry.get('response', {})
        content = response.get('content', {})

        url = request.get('url', '')
        mime_type = content.get('mimeType', '')
        text_content = decode_har_entry_content(content)

        if not text_content:
            continue

        prompt = None
        timestamp = None

        # Heuristic 1: Check request URL for Gemini indicators
        if "gemini" in url.lower() or "bard" in url.lower():
            # Try to find prompt and timestamp in request POST data
            post_data_text = request.get('postData', {}).get('text')
            if post_data_text:
                try:
                    post_data_json = json.loads(strip_json_prefix(post_data_text))
                    prompt = find_gemini_data_in_json(post_data_json)
                    timestamp = find_timestamp_in_json(post_data_json)
                except json.JSONDecodeError:
                    pass # Not JSON

        # Heuristic 2: Process JSON responses
        if mime_type == 'application/json' or 'json' in mime_type:
            try:
                json_data = json.loads(strip_json_prefix(text_content))

                # Look for "Gemini" keyword to filter relevant JSON blobs
                if "Gemini" in json.dumps(json_data): # Check if "Gemini" is anywhere in the JSON
                    current_prompt = find_gemini_data_in_json(json_data)
                    current_timestamp = find_timestamp_in_json(json_data)
                    if current_prompt and current_timestamp:
                        prompt = current_prompt
                        timestamp = current_timestamp
                        # If we found it, no need to search further in this entry
                        print(f"Found potential Gemini JSON record in entry {i+1}: '{prompt[:50]}...'" )

            except json.JSONDecodeError:
                pass # Not JSON, or malformed JSON

        # Heuristic 3: Process HTML responses (e.g., myactivity page itself)
        elif 'text/html' in mime_type:
            # Look for structured data within HTML, e.g., script tags with JSON-LD or embedded JS variables
            soup = BeautifulSoup(text_content, 'html.parser')
            for script in soup.find_all('script', type='application/json'):
                try:
                    script_json = json.loads(strip_json_prefix(script.string))
                    if "Gemini" in json.dumps(script_json):
                        current_prompt = find_gemini_data_in_json(script_json)
                        current_timestamp = find_timestamp_in_json(script_json)
                        if current_prompt and current_timestamp:
                            prompt = current_prompt
                            timestamp = current_timestamp
                            print(f"Found potential Gemini HTML script record in entry {i+1}: '{prompt[:50]}...'" )
                            break # Found in script, move to next entry
                except (json.JSONDecodeError, TypeError):
                    pass

            # Also search for specific elements that might contain activity details
            # This is highly dependent on My Activity page structure and might change
            # As a general search, we can look for div/span elements with relevant text
            # This is less reliable due to dynamic IDs/classes, so prioritize JSON/script tags
            if not prompt: # If not found yet, try searching more broadly in HTML
                for elem in soup.find_all(lambda tag: tag.name in ['div', 'span', 'p']):
                    if elem.string and ("Gemini" in elem.string or "Bard" in elem.string):
                        # This is very broad, need a better heuristic for prompts in HTML
                        # For now, if "Gemini" is in text, consider it for further inspection if other methods fail
                        pass

        if prompt and timestamp:
            # Basic deduplication based on prompt and date might be needed if multiple heuristics hit the same data
            record = {
                "date": timestamp.isoformat(),
                "prompt": prompt.strip()
            }
            if record not in recovered_records: # Simple deduplication
                recovered_records.append(record)
        
        if (i + 1) % 100 == 0:
            print(f"Processed {i + 1}/{len(entries)} entries. Found {len(recovered_records)} potential records.")

    print(f"Finished processing HAR entries. Total potential records found: {len(recovered_records)}")
    return recovered_records

def save_to_json(records, output_file):
    """Saves records to a JSON file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=4)
    print(f"Recovered data saved to '{output_file}'")

def save_to_markdown(records, output_file):
    """Saves records to a Markdown file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        for record in records:
            date_obj = datetime.fromisoformat(record['date'])
            f.write(f"### [{date_obj.strftime('%Y-%m-%d %H:%M')}]\n\n")
            # Basic markdown sanitation for prompts
            clean_prompt = record['prompt'].replace('\n', ' ').replace('\r', ' ')
            f.write(f"> {clean_prompt}\n\n")
    print(f"Recovered data saved to '{output_file}'")

def main():
    recovered_data = parse_har_file(HAR_FILE)
    if recovered_data:
        save_to_json(recovered_data, OUTPUT_JSON_FILE)
        save_to_markdown(recovered_data, OUTPUT_MD_FILE)
    else:
        print("No Gemini chat records found.")

if __name__ == '__main__':
    main()