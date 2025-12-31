# SyriaBot - Claude Code Instructions

## Project Overview
Discord bot with TempVoice system and media convert feature.

## VPS Deployment Rules (CRITICAL)

**NEVER do these:**
- `nohup python main.py &` - creates orphaned processes
- `rm -f /tmp/syria_bot.lock` - defeats single-instance lock
- `pkill` followed by manual start - use systemctl instead

**ALWAYS do these:**
- Use `systemctl restart syria-bot.service` to restart
- Use `systemctl stop syria-bot.service` to stop
- Use `systemctl status syria-bot.service` to check status

## VPS Connection
- Host: `root@188.245.32.205`
- SSH Key: `~/.ssh/hetzner_vps`
- Bot path: `/root/SyriaBot`

## Other Bots on Same VPS
- OthmanBot: port 8080, `systemctl othmanbot.service`
- AzabBot: port 8081, `systemctl azabbot.service`
- JawdatBot: port 8082, `systemctl jawdatbot.service`
- TahaBot: port 8083, `systemctl tahabot.service`
- TrippixnBot: port 8086, `systemctl trippixnbot.service`

## Key Files
- Config: `src/core/config.py`
- Logger: `src/core/logger.py`
- Main entry: `main.py`
- TempVoice: `src/services/tempvoice.py`
- Convert: `src/services/convert_service.py`

## Features
- **TempVoice**: Create/manage temporary voice channels with control panel
- **Convert**: Add text bars to images/videos (NotSoBot-style dynamic sizing)
  - Images: png, jpg, jpeg, gif, webp, jfif, bmp, tiff, tif
  - Videos: mp4, mov, webm, avi, mkv, m4v, flv, wmv, 3gp

## Uploading Code Changes
1. Edit files locally
2. `scp -i ~/.ssh/hetzner_vps <file> root@188.245.32.205:/root/SyriaBot/<path>`
3. `ssh -i ~/.ssh/hetzner_vps root@188.245.32.205 "systemctl restart syria-bot.service"`

## After Deployment
- Verify: `systemctl status syria-bot.service`

## GitHub
- Repo: https://github.com/trippixn963/SyriaBot.git
- Push notifications: `.github/workflows/discord-notify.yml`
