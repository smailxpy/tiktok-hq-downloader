# Deploy TikTok HQ Bot on Oracle Cloud Always Free (Ubuntu)

Keep the already-working `bot/main.py` unchanged to preserve the yt-dlp format selection and document upload behavior.

## Prerequisites

- An Oracle Cloud account accepted for Always Free resources; signup can require payment-card verification. **Always Free** eligibility does not mean all resources in the console are free.
- An **Always Free eligible** Ubuntu Compute instance, preferably `VM.Standard.A1.Flex` (Arm64), with SSH access and a public IP. Choose the home region carefully. Capacity may be unavailable.
- Your Telegram bot token, stored privately. The bot must not also be running on your Windows PC at the same time (the same polling token on two instances causes conflicts).
- Linux machine can reach TikTok and Telegram. A foreign VM is not automatically guaranteed access to TikTok.

## 1. Open PowerShell on Windows

Save/extract this project next to your existing bot folder, and connect with your Oracle-provided SSH private key:

```powershell
ssh -i "$env:USERPROFILE\.ssh\oracle_tiktok.key" ubuntu@YOUR_VM_PUBLIC_IP
```

If SSH complains about the key's file permissions, see Oracle's SSH instructions for Windows. Never share the private key.

## 2. Install system packages on Ubuntu

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg unzip curl ca-certificates
```

Test the server *before* deploying:

```bash
curl -I -L --connect-timeout 15 https://www.tiktok.com
```

A response from TikTok, even an HTTP error, indicates that HTTPS reached the server. A timeout/reset means the machine might not be suitable. We still need to test yt-dlp itself.

## 3. Copy project files from Windows

In a **second, local PowerShell window**, from the folder containing `tiktok_hq_bot`:

```powershell
scp -i "$env:USERPROFILE\.ssh\oracle_tiktok.key" -r .\tiktok_hq_bot ubuntu@YOUR_VM_PUBLIC_IP:~/
```

Do **not** upload an existing `.env` file containing a token into a public GitHub repository. If your Windows project contains `.env`, consider creating a clean copy excluding it before SCP.

## 4. Install the Python project on Ubuntu

Back in the SSH terminal:

```bash
cd ~/tiktok_hq_bot
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m yt_dlp --list-impersonate-targets
.venv/bin/python -m yt_dlp -F --impersonate chrome 'https://www.tiktok.com/@steniemp4/video/7654272624322874647'
```

If the last command reports video formats, the server can retrieve video metadata. If it times out or is rejected, solve that before starting the bot.

## 5. Configure the bot token privately

```bash
cp .env.example .env
nano .env
```

Replace `PUT_YOUR_BOTFATHER_TOKEN_HERE` with your actual Telegram bot token. Do not add quotes or spaces around the value. Then:

```bash
chmod 600 .env
mkdir -p downloads
.venv/bin/python -m bot.main
```

Test with `/start` and a TikTok link from Telegram. Ctrl+C stops this manual run before enabling the service.

## 6. Keep the bot running automatically (systemd)

```bash
sudo cp deploy/tiktok-hq-bot.service /etc/systemd/system/tiktok-hq-bot.service
sudo sed -i "s|__BOT_USER__|$USER|g; s|__BOT_HOME__|$HOME|g" /etc/systemd/system/tiktok-hq-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now tiktok-hq-bot
sudo systemctl status tiktok-hq-bot --no-pager
```

Watch logs:

```bash
sudo journalctl -u tiktok-hq-bot -n 100 --no-pager
sudo journalctl -u tiktok-hq-bot -f
```

Restart after updating:

```bash
sudo systemctl restart tiktok-hq-bot
```

Stop if needed:

```bash
sudo systemctl stop tiktok-hq-bot
```

## Quality and limits

- The app selects the same `yt-dlp` format IDs as it did locally and sends each downloaded file as a Telegram **document** to avoid re-encoding.
- No changes to `bot/main.py` are necessary for Ubuntu hosting.
- The hosted Telegram Bot API currently imposes a size limit on new file uploads (the application defaults to a 49 MiB cutoff). Videos bigger than that need a different delivery method or self-hosted Bot API setup.
- The VM has finite bandwidth and disk resources, and no free plan guarantees indefinite availability. Monitor Oracle billing and resource eligibility.
- Keep the token/private SSH key secret. Don't open extra inbound ports: **long polling only needs outbound HTTPS and SSH access**.

## Troubleshooting

- **`Conflict: terminated by other getUpdates request`**: Stop the bot on Windows, or stop any other running instance with the same bot token.
- **TikTok times out/403**: Compare `curl -I` and `yt-dlp -F` on the VM. An overseas IP alone is not a guarantee; try another allowed region/provider.
- **`ModuleNotFoundError`**: Confirm you used `.venv/bin/python` and installed requirements.
- **Uploads fail on large files**: Respect `MAX_FILE_MB=49` in `.env` or set up a separate local Bot API server.
- **No free instance availability**: Oracle may lack Always Free capacity in the chosen availability domain. Avoid accidentally provisioning paid resources.
