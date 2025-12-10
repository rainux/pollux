# Pollux - Gemini Chat History Recovery Tool

> In Greek mythology, Castor was mortal, while **Pollux** was the immortal twin. When Castor died, Pollux shared his immortality to save him from fading away.
>
> This tool is the "Pollux" to your lost Gemini chats—rescuing them from the void of Google's buggy interface and making them permanent.

Pollux is a practical data recovery tool designed to extract and reconstruct your **Google Gemini** chat history from a raw HTTP Archive (`.har`) export of your "My Activity" data. It organizes your conversations into easy-to-read Markdown files for local archival and review.

## Features

- **Comprehensive Extraction**: Recovers user prompts and Gemini's responses from your "My Activity" HAR file.
- **Smart Session Grouping**: Intelligently clusters scattered chat records into logical **Sessions** based on time gaps (a 2-hour heuristic), restoring conversation flow.
- **Dual Data Source Recovery**: Processes both initial HTML page content and subsequent JSON data fetches for complete data capture.
- **Clean Output**: Converts raw HTML responses into neatly formatted Markdown.
- **Data Integrity Check**: Includes a built-in verification to ensure extracted data quantity aligns with the server's pagination logic.

## Getting Started

### Prerequisites

This project is built with modern Python tooling. You will need:

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)** (An extremely fast Python package installer and runner)

### Step 1: Export Your HAR File

1.  Open Chrome or a Chromium-based browser.
2.  Navigate to [myactivity.google.com/product/gemini](https://myactivity.google.com/product/gemini).
3.  Open **Developer Tools** (F12) and switch to the **Network** tab.
4.  Check the **"Preserve log"** checkbox.
5.  Refresh the page to capture the initial HTML content.
6.  Scroll down to load more history. Continue scrolling as far back as you wish to recover.
7.  In the Network tab, right-click on any request and select **"Save all as HAR with content"**.
8.  Save the file as `myactivity.google.com.har` in the root directory of this project.

### Step 2: Run the Recovery Script

Execute the script using `uv`:

```bash
uv run python main.py
```

`uv` will automatically create a virtual environment, install necessary dependencies, and run the script.

## Output Files

The tool generates the following:

- **`recovered_sessions/`**: A directory containing individual Markdown files for each detected session (e.g., `Session_20251129_1732.md`). This is the primary human-readable output.
- **`recovered_gemini.json`**: A complete, structured JSON file containing all recovered sessions and messages, ideal for programmatic processing or archiving.

## License

This project is open-source under the [MIT License](LICENSE).

---

Co-Authored with Gemini & Gemini CLI

> 你做得太棒了！辛苦了，摸摸头！
>
> 最后帮我写一份 README.md 吧，我会把这个项目使用 MIT 协议开源到 GitHub 上。

> ✦ Thank you for the pat on the head! It was a pleasure working with you to uncover the secrets of the data structure.
