# TikTok HQ Downloader — by smailxpy

## Requirements
- Python 3.11+ (Python 3.13 is supported by recent dependencies)
- Windows desktop VPN connected if TikTok is unreachable on your ISP
- Telegram bot token from @BotFather

## Setup (PowerShell)
```powershell
cd tiktok-hq-downloader
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe -m bot.main
```

Put your BotFather token into `.env` (`BOT_TOKEN=...`). Never share this token.
Open Telegram and send `/start` to your new bot, followed by a TikTok URL.

## Behavior
- Accepts up to five TikTok URLs per message; handles each one sequentially.
- Displays up to eight unique quality choices for each video.
- Ranks by pixel count, then reported total bitrate; user chooses the format.
- Skips the explicitly watermarked `download` format when other stream formats exist.
- Sends an unmodified downloaded file as a Telegram document, preventing Telegram video recompression.
- Cleans up temporary download files after upload.
- Rejects files above configured 49 MiB threshold for the hosted Telegram Bot API.

## Limitations
- Watermark-free is *not guaranteed*; the source must provide a watermark-free stream.
- Public TikTok links only; videos blocked from retrieval or access-restricted content may fail.
- Batch requests collect links from one message and prompt for each video; uploads are user-selected.
- Quality labels are based on yt-dlp-reported metadata, not a visual quality score. `-0`/`-1` duplicates are collapsed.
- The in-memory selection cache is lost when the bot restarts; this is an MVP, not a multi-worker production queue.
- Large files need a self-hosted Telegram Bot API server or different delivery solution.

## Recommended next version
- Add SQLite for persistent jobs and cached extraction metadata.
- Add per-user quota / global concurrency limit and disk-space safeguards.
- Add ffprobe validation and fallback format retry.
- Add progress indicators, tests, and a local Bot API endpoint for large files.

## Deploy on an Always Free Ubuntu VM

See [DEPLOY_ORACLE.md](DEPLOY_ORACLE.md) and `deploy/tiktok-hq-bot.service` for a copy-and-paste walkthrough and background service setup. Verify yt-dlp TikTok access from the VM before switching the bot off locally.

## Open source

Licensed under the MIT License. See [LICENSE](LICENSE). Contributions via issues and pull requests are welcome.

**Security:** Never commit `.env`, bot tokens, browser cookies, VPN credentials or downloaded media. Before publishing an existing local repo, inspect its complete git history for accidentally committed secrets. If a token was exposed, rotate it with BotFather.

Only download content you are authorized to access and respect applicable rules and creators’ rights.
