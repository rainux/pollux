# uv project setup:
# uv init
# uv add beautifulsoup4
# uv add markdownify
# uv pip install ruff

import json
import base64
from datetime import datetime
import os
import re

HAR_FILE = 'myactivity.google.com.har'
OUTPUT_JSON_FILE = 'recovered_gemini.json'
OUTPUT_MD_FILE = 'recovered_gemini.md'

def strip_json_prefix(text):
    """Strips the common Google JSON prefix `)]}'` and length indicator from a string."""
    if text.startswith(")]}'"):
        text = text[4:]
    
    text = text.strip()
    
    # Check for and remove potential length prefix (digits followed by JSON start)
    # The length is usually followed by a newline, then the JSON content.
    # We look for the first '[' or '{' to ensure we capture the JSON start.
    match = re.search(r'^[0-9]+\s*([\[\{])', text)
    if match:
        # If we found a number followed by [ or {, start from the [ or {
        return text[match.start(1):]
        
    return text

def decode_har_entry_content(content):
    """Decodes content from a HAR entry, handling base64 if specified."""
    if content.get('encoding') == 'base64' and content.get('text'):
        try:
            return base64.b64decode(content['text']).decode('utf-8', errors='ignore')
        except Exception:
            return None
    return content.get('text')

def extract_timestamp(record_list):
    """
    Scans a record list for a likely timestamp (microseconds).
    Heuristic: Integer > 1,600,000,000,000,000 (Year 2020+ in microseconds).
    """
    for item in record_list:
        if isinstance(item, int):
            # Check for microseconds (16 digits)
            if item > 1_600_000_000_000_000:
                return datetime.fromtimestamp(item / 1_000_000)
            # Fallback check for milliseconds (13 digits) - less likely for Google internal but possible
            elif item > 1_600_000_000_000:
                return datetime.fromtimestamp(item / 1_000)
    return None

def extract_prompt(record_list):
    """
    Scans a record list for the user prompt.
    Heuristic: A sub-list [ "Prompt Text", true, "Prompted" ].
    """
    for item in record_list:
        if isinstance(item, list) and len(item) >= 3:
            # Check for the specific signature ["Text", boolean, "Prompted"]
            if item[2] == "Prompted" and isinstance(item[0], str):
                return item[0]
    return None

def process_inner_payload(payload_json, recovered_records):
    """
    Traverses the inner decoded JSON payload to find chat records.
    The payload is typically a list of lists.
    """
    if not isinstance(payload_json, list):
        return

    # The payload structure is complex. We iterate through everything looking for records.
    # A "record" usually is a list that contains a timestamp and a "Prompted" sub-list.
    
    # We can try to iterate recursively or just iterate the top-level items if they represent conversation nodes.
    # Based on debug output, the payload is a list of records.
    
    for item in payload_json:
        if isinstance(item, list):
            # This 'item' could be a chat record.
            prompt = extract_prompt(item)
            if prompt:
                timestamp = extract_timestamp(item)
                if timestamp:
                    record = {
                        "date": timestamp.isoformat(),
                        "prompt": prompt.strip()
                    }
                    # Simple deduplication
                    if record not in recovered_records:
                        recovered_records.append(record)
                else:
                    # Found prompt but no timestamp? Capture it anyway with a fallback or omit?
                    # Better to capture.
                    pass 

            # Recursion: The structure might be nested.
            process_inner_payload(item, recovered_records)

def scan_for_nested_data(data, recovered_records):
    """
    Recursively scans JSON data for strings that look like nested JSON arrays.
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                # Check if it looks like a JSON array start
                if item.startswith('[[') and item.endswith(']'):
                    try:
                        inner_json = json.loads(item)
                        process_inner_payload(inner_json, recovered_records)
                    except (json.JSONDecodeError, TypeError):
                        pass
            else:
                scan_for_nested_data(item, recovered_records)
    elif isinstance(data, dict):
        for value in data.values():
            scan_for_nested_data(value, recovered_records)

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
        content = entry.get('response', {}).get('content', {})
        mime_type = content.get('mimeType', '')
        text_content = decode_har_entry_content(content)

        if not text_content:
            continue

        # Heuristic: Only process JSON responses, specifically from batchexecute or similar
        # But scanning all JSONs is safer.
        if 'application/json' in mime_type or 'text/javascript' in mime_type: # sometimes it's text/javascript with )]}'
            stripped_text = strip_json_prefix(text_content)
            if not stripped_text:
                continue

            decoder = json.JSONDecoder()
            pos = 0
            while pos < len(stripped_text):
                try:
                    # Skip leading whitespace which raw_decode doesn't always handle if explicitly passed start index? 
                    # Actually raw_decode handles whitespace before the object, but we loops.
                    # We should manually skip whitespace to be safe or rely on raw_decode.
                    # raw_decode reads *one* object.
                    
                    # Manually skip whitespace to detect end of string
                    while pos < len(stripped_text) and stripped_text[pos].isspace():
                        pos += 1
                    
                    if pos >= len(stripped_text):
                        break

                    json_data, index = decoder.raw_decode(stripped_text, pos)
                    pos = index
                    
                    scan_for_nested_data(json_data, recovered_records)
                    
                except json.JSONDecodeError:
                    # If we fail to decode a chunk, we might as well stop for this entry
                    # print(f"JSON Decode Error in entry {i} at pos {pos}")
                    break

        
        if (i + 1) % 20 == 0:
            print(f"Processed {i + 1}/{len(entries)} entries. Found {len(recovered_records)} records so far.")

    # Sort records by date
    recovered_records.sort(key=lambda x: x['date'])
    
    print(f"Finished processing. Total unique records found: {len(recovered_records)}")
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
            clean_prompt = record['prompt'].replace('\r', '') # Keep newlines in prompts, they are valuable
            
            # Blockquote the prompt
            quoted_prompt = "\n".join([f"> {line}" for line in clean_prompt.split('\n')])
            f.write(f"{quoted_prompt}\n\n")
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
