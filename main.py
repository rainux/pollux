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
from urllib.parse import urlparse, parse_qs
from markdownify import markdownify as md
from bs4 import BeautifulSoup

HAR_FILE = 'myactivity.google.com.har'
OUTPUT_JSON_FILE = 'recovered_gemini.json'
OUTPUT_DIR = 'recovered_sessions'

def strip_json_prefix(text):
    """Strips the common Google JSON prefix `)]}'` and length indicator from a string."""
    if text.startswith(")]}'"):
        text = text[4:]

    text = text.strip()
    match = re.search(r'^[0-9]+\s*([["{])', text)
    if match:
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
    """Scans a record list for a likely timestamp (microseconds)."""
    for item in record_list:
        if isinstance(item, int):
            if item > 1_600_000_000_000_000:
                return datetime.fromtimestamp(item / 1_000_000)
            elif item > 1_600_000_000_000:
                return datetime.fromtimestamp(item / 1_000)
    return None

def extract_prompt(record_list):
    """Scans a record list for the user prompt."""
    for item in record_list:
        if isinstance(item, list) and len(item) >= 3:
            if item[2] == "Prompted" and isinstance(item[0], str):
                return item[0]
    return None

def extract_response(record_list):
    """
    Extracts the Model Response from the record.
    Heuristic: The response is usually deeply nested in a list at a high index (e.g., 34).
    It is typically HTML content.
    """
    # Iterate backwards as response is usually towards the end
    for item in reversed(record_list):
        if isinstance(item, list):
            # The response structure seems to be: [ [ [null, "HTML", ...] ] ]
            # Let's traverse down
            try:
                if len(item) > 0 and isinstance(item[0], list):
                    nested1 = item[0]
                    if len(nested1) > 0 and isinstance(nested1[0], list):
                        nested2 = nested1[0]
                        # Check for HTML content in the second element (index 1)
                        if len(nested2) > 1 and isinstance(nested2[1], str) and "<" in nested2[1]:
                             return nested2[1]
            except (IndexError, TypeError):
                pass
    return None

def process_inner_payload(payload_json, recovered_records, metadata):
    """Traverses the inner decoded JSON payload to find chat records."""
    if not isinstance(payload_json, list):
        return

    # Check if THIS item is a record
    prompt = extract_prompt(payload_json)
    if prompt:
        timestamp = extract_timestamp(payload_json)
        response_html = extract_response(payload_json)

        if timestamp:
            record = {
                "date": timestamp.isoformat(),
                "prompt": prompt.strip(),
                "response": md(response_html).strip() if response_html else None,
                "metadata": metadata
            }
            # Capture IDs (just strings, no decoding needed for recovery)
            if len(payload_json) > 5: record['id_a'] = str(payload_json[5])
            if len(payload_json) > 6: record['id_b'] = str(payload_json[6])

            # Efficient deduplication check
            is_duplicate = False
            for r in recovered_records:
                if r['date'] == record['date'] and r['prompt'] == record['prompt']:
                    is_duplicate = True
                    break

            if not is_duplicate:
                recovered_records.append(record)

        # Don't recurse into the record itself if we found it (optimization)
        return

    # Otherwise recurse
    for item in payload_json:
        process_inner_payload(item, recovered_records, metadata)

def scan_for_nested_data(data, recovered_records, metadata):
    """Recursively scans JSON data for strings that look like nested JSON arrays."""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                if item.strip().startswith('[[') and item.strip().endswith(']'):
                    try:
                        inner_json = json.loads(item)
                        process_inner_payload(inner_json, recovered_records, metadata)
                    except (json.JSONDecodeError, TypeError):
                        pass
            else:
                scan_for_nested_data(item, recovered_records, metadata)
    elif isinstance(data, dict):
        for value in data.values():
            scan_for_nested_data(value, recovered_records, metadata)

def extract_json_from_html(html_content, recovered_records, metadata):
    """Extracts JSON data embedded in AF_initDataCallback script tags."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup.find_all('script'):
            if script.string and "AF_initDataCallback" in script.string:
                # Use regex to find the start of the data array
                # Pattern: data: [...]
                match = re.search(r'data\s*:\s*(\[.*)', script.string, re.DOTALL)
                if match:
                    json_candidate = match.group(1)
                    try:
                        decoder = json.JSONDecoder()
                        obj, _ = decoder.raw_decode(json_candidate)
                        # CRITICAL FIX: The data in HTML is ALREADY a JSON object (list),
                        # not a stringified JSON like in batchexecute.
                        # So we must call process_inner_payload directly, not scan_for_nested_data.
                        process_inner_payload(obj, recovered_records, metadata)
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass

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

    stats = {
        "html_entry_count": 0,
        "html_records": 0,
        "json_entry_count": 0,
        "json_records": 0,
        "json_valid_requests": 0
    }

    for i, entry in enumerate(entries):
        request = entry.get('request', {})
        url = request.get('url', '')
        content = entry.get('response', {}).get('content', {})
        mime_type = content.get('mimeType', '')
        text_content = decode_har_entry_content(content)

        if not text_content:
            continue

        # Extract Session ID from URL
        session_id = None
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        if 'f.sid' in query_params:
            session_id = query_params['f.sid'][0]

        metadata = {
            "entry_index": i,
            "session_id": session_id
        }

        start_count = len(recovered_records)

        # Handle JSON Responses (batchexecute)
        if 'application/json' in mime_type or 'text/javascript' in mime_type:
            stripped_text = strip_json_prefix(text_content)
            if stripped_text:
                stats["json_entry_count"] += 1
                decoder = json.JSONDecoder()
                pos = 0
                while pos < len(stripped_text):
                    try:
                        while pos < len(stripped_text) and stripped_text[pos].isspace():
                            pos += 1
                        if pos >= len(stripped_text): break
                        json_data, index = decoder.raw_decode(stripped_text, pos)
                        pos = index
                        scan_for_nested_data(json_data, recovered_records, metadata)
                    except json.JSONDecodeError:
                        break
                
                count = len(recovered_records) - start_count
                stats["json_records"] += count
                if count > 0:
                    stats["json_valid_requests"] += 1
        
        # Handle HTML Responses (Initial Page Load)
        elif 'text/html' in mime_type:
            stats["html_entry_count"] += 1
            extract_json_from_html(text_content, recovered_records, metadata)
            count = len(recovered_records) - start_count
            stats["html_records"] += count

        if (i + 1) % 20 == 0:
            print(f"Processed {i + 1}/{len(entries)} entries. Found {len(recovered_records)} records so far.")

    # Sort records by date
    recovered_records.sort(key=lambda x: x['date'])

    print("-" * 40)
    print("DATA INTEGRITY VERIFICATION")
    print("-" * 40)
    print(f"HTML Requests: {stats['html_entry_count']} | Records Extracted: {stats['html_records']}")
    print(f"JSON Requests: {stats['json_entry_count']} | Valid (with data): {stats['json_valid_requests']} | Records Extracted: {stats['json_records']}")
    print(f"Total Raw Records: {len(recovered_records)}")
    
    if stats['json_valid_requests'] > 0:
        avg_per_page = stats['json_records'] / stats['json_valid_requests']
        print(f"Average Records per JSON Page: {avg_per_page:.2f}")
    
    if stats['html_records'] == 0:
        print("WARNING: HTML Entry yielded 0 records. Check parsing logic.")
    
    print("-" * 40)

    return recovered_records

def analyze_sessions(records):
    # Time Clustering
    records.sort(key=lambda x: x['date'])

    sessions = []
    current_session = []
    last_ts = 0
    TIME_THRESHOLD_SEC = 2 * 60 * 60 # 2 hours

    for r in records:
        ts = datetime.fromisoformat(r['date']).timestamp()
        if last_ts == 0 or (ts - last_ts) > TIME_THRESHOLD_SEC:
            if current_session: sessions.append(current_session)
            current_session = [r]
        else:
            current_session.append(r)
        last_ts = ts
    if current_session: sessions.append(current_session)

    return sessions

def save_to_json(sessions, output_file):
    """Saves grouped sessions to a JSON file."""
    output_data = []
    for i, session in enumerate(sessions):
        if not session: continue
        session_data = {
            "session_id": f"guessed_session_{i+1}",
            "start_time": session[0]['date'],
            "message_count": len(session),
            "messages": session
        }
        output_data.append(session_data)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
    print(f"Recovered data saved to '{output_file}'")

def save_sessions_to_files(sessions, output_dir):
    """Saves each session to a separate Markdown file."""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print(f"Saving {len(sessions)} sessions to directory '{output_dir}/'...")

    for i, session in enumerate(sessions):
        if not session: continue

        # Get start time for filename
        start_dt = datetime.fromisoformat(session[0]['date'])
        filename = f"Session_{start_dt.strftime('%Y%m%d_%H%M')}.md"
        file_path = os.path.join(output_dir, filename)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# Session {i+1}\n")
            f.write(f"**Date:** {start_dt.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Messages:** {len(session)}\n\n")

            for record in session:
                date_obj = datetime.fromisoformat(record['date'])
                # Use complete time format as requested
                f.write(f"## [{date_obj.strftime('%Y-%m-%d %H:%M:%S')}]\n\n")

                # User Prompt
                clean_prompt = record['prompt'].replace('\r', '')
                quoted_prompt = "\n".join([f"> {line}" for line in clean_prompt.split('\n')])
                f.write(f"**User**:\n{quoted_prompt}\n\n")

                # Gemini Response
                if record.get('response'):
                    clean_response = record['response'].replace('\r', '')
                    f.write(f"**Gemini**:\n{clean_response}\n\n")

                f.write("---\n\n")

    print("All sessions saved.")

def main():
    recovered_data = parse_har_file(HAR_FILE)
    if recovered_data:
        sessions = analyze_sessions(recovered_data)
        print(f"Grouped into {len(sessions)} sessions based on 2h gaps.")
        save_to_json(sessions, OUTPUT_JSON_FILE)
        save_sessions_to_files(sessions, OUTPUT_DIR)
    else:
        print("No Gemini chat records found.")

if __name__ == '__main__':
    main()
