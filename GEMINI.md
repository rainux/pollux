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

Please provide the complete, ready-to-run Python code.
