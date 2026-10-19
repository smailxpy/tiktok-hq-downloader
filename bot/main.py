"""Telegram TikTok high-quality video downloader (Windows-friendly long polling)."""
import asyncio
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv
from yt_dlp import YoutubeDL

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "")
MAX_LINKS = max(1, min(int(os.getenv("MAX_LINKS_PER_MESSAGE", "5")), 10))
MAX_FILE_BYTES = max(1, int(os.getenv("MAX_FILE_MB", "49"))) * 1024 * 1024
ROOT = Path(os.getenv("DOWNLOAD_DIR", "downloads"))
ROOT.mkdir(parents=True, exist_ok=True)
URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
router = Router()

@dataclass
class Choice:
    url: str
    format_id: str
    label: str
    filesize: int | None

# Choices are scoped to a user and message; no URL/format IDs in callback payloads.
choices: dict[tuple[int, int], list[Choice]] = {}
user_locks: dict[int, asyncio.Lock] = {}

def valid_tiktok_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (host == "tiktok.com" or host.endswith(".tiktok.com"))
    except ValueError:
        return False

def urls_from_text(text: str) -> list[str]:
    result = []
    for match in URL_PATTERN.findall(text):
        url = match.rstrip(".,;!?)\"'")
        if valid_tiktok_url(url) and url not in result:
            result.append(url)
    return result[:MAX_LINKS]

def extract_formats(url: str) -> tuple[str, list[Choice]]:
    options = {"quiet": True, "no_warnings": True, "skip_download": True,
               "noplaylist": True, "socket_timeout": 30,
               "extractor_args": {}, "impersonate": None}
    # Equivalent to the user's successful --impersonate chrome; yt-dlp accepts string
    # impersonation targets through parse_options only, so use a request handler target
    # via CLI-compatible parse_options to avoid relying on undocumented internals.
    from yt_dlp import parse_options
    parsed = parse_options(["--impersonate", "chrome"])
    options.update(parsed.ydl_opts)
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("TikTok did not return video information")
    if info.get("_type") == "playlist":
        raise RuntimeError("Only individual TikTok videos are supported")
    title = str(info.get("title") or "TikTok video")[:100]
    raw = []
    for fmt in info.get("formats") or []:
        if fmt.get("vcodec") in (None, "none") or fmt.get("format_id") in (None, "audio"):
            continue
        fid = str(fmt["format_id"])
        # Avoid the explicitly watermarked download variant; do not claim others
        # are guaranteed watermark-free.
        if fid == "download" or "watermarked" in str(fmt.get("format_note", "")).lower():
            continue
        width, height = fmt.get("width") or 0, fmt.get("height") or 0
        if not width or not height:
            continue
        bitrate = fmt.get("tbr") or 0
        codec = str(fmt.get("vcodec", "unknown"))
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        # Deduplicate mirrored '-0'/'-1' URLs with equivalent quality attributes.
        signature = (width, height, round(bitrate), codec)
        raw.append((signature, width, height, bitrate, codec, size, fid))
    raw.sort(key=lambda x: (x[1] * x[2], x[3], x[4]), reverse=True)
    found = set()
    choices_out = []
    for signature, width, height, bitrate, codec, size, fid in raw:
        if signature in found:
            continue
        found.add(signature)
        label = f"{width}×{height} · {codec} · {round(bitrate)} kbps"
        choices_out.append(Choice(url, fid, label, size))
    return title, choices_out[:8]

def download_choice(choice: Choice, target_dir: Path) -> Path:
    from yt_dlp import parse_options
    opts = parse_options(["--impersonate", "chrome"]).ydl_opts
    opts.update({"quiet": True, "no_warnings": True, "noplaylist": True,
                 "format": choice.format_id, "outtmpl": str(target_dir / "video.%(ext)s"),
                 "socket_timeout": 30, "overwrites": True})
    with YoutubeDL(opts) as ydl:
        ydl.download([choice.url])
    files = [p for p in target_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
    if not files:
        raise RuntimeError("Download finished without an output file")
    return max(files, key=lambda p: p.stat().st_size)

def get_lock(user_id: int) -> asyncio.Lock:
    return user_locks.setdefault(user_id, asyncio.Lock())

@router.message(CommandStart())
async def start(message: Message):
    await message.answer("🎬 TikTok HQ Downloader\n\nSend one or more TikTok links (up to "
                         f"{MAX_LINKS} at a time). I'll show real quality options, then "
                         "send your selected format as a file to preserve its quality.")

@router.message(F.text)
async def on_links(message: Message):
    if not message.from_user:
        return
    urls = urls_from_text(message.text or "")
    if not urls:
        await message.answer("Send a public TikTok video URL starting with https://")
        return
    if get_lock(message.from_user.id).locked():
        await message.answer("One of your downloads is still processing. Please try again shortly.")
        return
    for url in urls:
        status = await message.answer("🔎 Reading available video streams…")
        try:
            title, formats = await asyncio.to_thread(extract_formats, url)
            if not formats:
                await status.edit_text("No downloadable video streams were found for this link.")
                continue
            uid = message.from_user.id
            choices[(uid, status.message_id)] = formats
            buttons = []
            for idx, item in enumerate(formats):
                suffix = f" · {item.filesize/1048576:.1f} MiB" if item.filesize else ""
                buttons.append([InlineKeyboardButton(text=("🏆 " if idx == 0 else "") + item.label + suffix,
                                                     callback_data=f"dl:{status.message_id}:{idx}")])
            await status.edit_text(f"🎬 {title}\n\nSelect an available format (best resolution/bitrate first). "
                                   "Watermark-free is not guaranteed for every TikTok.",
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        except Exception as exc:
            logging.exception("Extraction failed")
            await status.edit_text(f"Could not read this TikTok. {type(exc).__name__}: {str(exc)[:200]}")

@router.callback_query(F.data.startswith("dl:"))
async def on_download(query: CallbackQuery):
    if not query.from_user or not query.message:
        await query.answer("Invalid request", show_alert=True)
        return
    try:
        _, msg_id_str, idx_str = (query.data or "").split(":")
        msg_id, idx = int(msg_id_str), int(idx_str)
        available = choices.get((query.from_user.id, msg_id), [])
        choice = available[idx]
        if msg_id != query.message.message_id:
            raise ValueError("Mismatched message")
    except (ValueError, IndexError, KeyError):
        await query.answer("This selection expired. Send the TikTok link again.", show_alert=True)
        return
    lock = get_lock(query.from_user.id)
    if lock.locked():
        await query.answer("You already have a download in progress.", show_alert=True)
        return
    await query.answer("Downloading selected quality…")
    async with lock:
        await query.message.answer("⬇️ Downloading: " + choice.label)
        # A separate temporary directory per download avoids collisions and cleans up files.
        workdir = Path(tempfile.mkdtemp(prefix="tiktok_", dir=ROOT))
        try:
            filepath = await asyncio.to_thread(download_choice, choice, workdir)
            size = filepath.stat().st_size
            if size > MAX_FILE_BYTES:
                await query.message.answer(f"File is {size/1048576:.1f} MiB, above the configured "
                                           f"{MAX_FILE_BYTES/1048576:.0f} MiB Telegram upload threshold. "
                                           "Use a smaller format or a local Bot API server.")
            else:
                await query.message.answer_document(FSInputFile(filepath, filename=filepath.name),
                                                    caption=f"✅ {choice.label}\n"
                                                            f"📦 {size/1048576:.2f} MiB\n"
                                                            "Original downloaded stream (no re-encoding).")
        except Exception as exc:
            logging.exception("Download failed")
            await query.message.answer(f"Download failed: {type(exc).__name__}: {str(exc)[:180]}")
        finally:
            await asyncio.to_thread(shutil.rmtree, workdir, True)

async def main():
    if not TOKEN or TOKEN == "PUT_YOUR_BOTFATHER_TOKEN_HERE":
        raise RuntimeError("Set BOT_TOKEN in .env (copy .env.example first)")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
