# Role

You are a Senior Data Recovery Engineer specializing in forensic analysis of HAR (HTTP Archive) files and Google internal API protocols.

# Context

I have experienced data loss on the Gemini App and need to recover my chat history (User Prompts) from a `.har` file exported from `myactivity.google.com/product/gemini`.
The file is roughly 16MB.

# Task

Write a robust Python script to parse the `myactivity.google.com.har` file and extract all available chat records related to Gemini.

# Environment & Tooling

- I use **uv** to manage Python dependencies and virtual environments.
- You are free to use robust external libraries (specifically `beautifulsoup4` for HTML cleaning) if it improves the quality of the extraction.
- **Crucial**: At the very top of the script, include a comment block with the exact `uv` commands to initialize the project and add necessary dependencies (e.g., `uv init`, `uv add beautifulsoup4`).

# Technical Constraints & Heuristics

1.  **Input**: The script should read a file named `myactivity.google.com.har` in the current directory.
2.  **Target Data**: We are looking for:
    - User's prompt text (The most important part).
    - Timestamp (when the prompt was sent).
    - (Optional) Any associated metadata identifying it as a Gemini interaction.
3.  **Data Structure Challenges (Crucial)**:
    - The data in My Activity is dynamically loaded. It might reside in:
      - `entries -> response -> content -> text` of JSON endpoints.
      - `entries -> response -> content -> text` of HTML documents (embedded in JavaScript variables or DOM elements).
    - Google's JSON responses often start with "garbage" characters like `)]}'` to prevent XSSI. The script must strip these before parsing JSON.
    - The actual data is likely deeply nested in unnamed arrays (Protobuf-style JSON), e.g., `[null, ["User Prompt", ...]]`.
4.  **Parsing Strategy**:
    - Instead of hardcoding a brittle path (which changes often), use a **search/scan approach**:
      - Iterate through all HTTP response bodies in the HAR file.
      - Decode content if it is base64 encoded.
      - Search for text patterns or data structures that look like user activity.
    - Identify Gemini-specific records. In My Activity, the "header" usually contains "Gemini" and the "title" or "description" contains the prompt.
    - Look for the keyword "Gemini" inside the JSON to filter relevant events.

# Output Format

The script should save the recovered data into two files:

1.  `recovered_gemini.json`: A clean JSON array of objects: `[{"date": "...", "prompt": "..."}]`.
2.  `recovered_gemini.md`: A readable Markdown file where each entry is formatted as:

    ```markdown
    ### [YYYY-MM-DD HH:MM]

    > [User Prompt Content]
    ```

# Code Requirements

- Use standard libraries (`json`, `base64`, `re`, `datetime`).
- Include error handling (try/except) so the script doesn't crash on one bad entry.
- Add print statements to show progress (e.g., "Found 5 potential records...").
- **Double Check**: Ensure specific logic to handle the ")]}'" prefix often found in Google XHR responses.

# Technical Findings & Protocol Analysis

Through forensic analysis of the HAR data, the following protocol details have been established:

## 1. Google Batchexecute Protocol
The core data resides in `application/json` responses, wrapped in a specific format:
-   **XSSI Prefix**: Responses start with `)]}'` (plus optional whitespace/newlines) to prevent Cross-Site Scripting Inclusion.
-   **Length Indicator**: This prefix is often followed by a number (length of the payload) and a newline.
-   **Streaming JSON**: The actual body often contains multiple concatenated JSON objects. The parser must handle `Extra data` errors by reading one object at a time (`decoder.raw_decode`).
-   **Nested Serialization**: The payload is typically a JSON list `[["wrb.fr", "rpcid", "STRING"]]`, where the third element is a **stringified** JSON array containing the actual business data. This requires a double-parse approach.

## 2. Protobuf-over-JSON Structure
The internal data structure is a JSON mapping of Google Protobuf messages. It is schemaless (no keys, only indices).
-   **Record Structure**: A large array representing a single event.
    -   **Index 4**: Timestamp (Microseconds since epoch).
    -   **Index 5 & 6**: Base64-like strings (e.g., `AODP...`). Analysis confirms these are **Protobuf messages** containing a constant User/App ID and a variable Message ID. They do **not** contain a Conversation ID.
    -   **Index 9**: The User Prompt structure: `["Prompt Text", true, "Prompted"]`. The string `"Prompted"` is a reliable signature.
    -   **Index 34**: The Model Response structure. Contains nested lists eventually holding an HTML string of the response.

## 3. Session & ID Analysis
-   **Conversation ID**: **Absent**. Detailed analysis of the metadata (URL parameters, Protobuf IDs) revealed no stable identifier that groups messages into conversations across different time points. `f.sid` in the URL is a Browser Session ID that remains constant over days.
-   **Grouping Strategy**: Since explicit IDs are missing, **Time-based Clustering** is the only viable method to restore logical sessions. A gap of **2 hours** between messages is a proven heuristic to delimit distinct conversation sessions.

## 4. Recovery Logic
1.  **Iterate** all HAR entries.
2.  **Decode** `batchexecute` JSON streams.
3.  **Recursive Scan** for the `["Prompt", true, "Prompted"]` signature.
4.  **Extract** Prompt, Timestamp, and Response (HTML converted to Markdown).
5.  **Cluster** records into sessions based on time gaps (e.g., >2 hours).
6.  **Output** structured files per session.