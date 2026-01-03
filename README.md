# SyriaBot

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![Discord.py](https://img.shields.io/badge/Discord.py-2.7.0+-5865F2?style=flat-square&logo=discord&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991?style=flat-square&logo=openai&logoColor=white)
![License](https://img.shields.io/badge/License-Source%20Available-red?style=flat-square)

**Multi-Feature Discord Bot with XP System & TempVoice**

*Built for [discord.gg/syria](https://discord.gg/syria)*

[![Join Server](https://img.shields.io/badge/Join%20Server-discord.gg/syria-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/syria)
[![Dashboard](https://img.shields.io/badge/Leaderboard-trippixn.com/syria-1F5E2E?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTMgOWwzLTMgMyAzIi8+PHBhdGggZD0iTTYgNnYxMiIvPjxwYXRoIGQ9Ik0xNSAyMWwzLTMgMy0zIi8+PHBhdGggZD0iTTE4IDE4VjYiLz48L3N2Zz4=&logoColor=white)](https://trippixn.com/syria)

</div>

---

## Overview

SyriaBot is a feature-rich Discord bot providing XP leveling, temporary voice channels, media conversion, translation, and more. It powers the community features for the Syria Discord server.

**Live Leaderboard**: [trippixn.com/syria](https://trippixn.com/syria)

> **Note**: This bot was custom-built for **discord.gg/syria** and is provided as-is for educational purposes. **No support will be provided.**

---

## Features

| Feature | Description |
|---------|-------------|
| **XP System** | Level-based progression with message and voice XP |
| **Role Rewards** | Automatic role assignment at milestone levels |
| **Rank Cards** | Graphical rank cards with progress bars |
| **TempVoice** | Create and manage temporary voice channels |
| **Media Convert** | Add captions to images and videos |
| **Translation** | Google Translate + AI-powered translation (boosters) |
| **Weather** | Real-time weather with fuzzy city search |
| **AFK System** | Dyno-style AFK status with mention notifications |
| **Media Download** | Download media from social platforms |
| **Profile Sync** | Sync avatars and banners across the server |
| **Gallery Mode** | Auto-delete non-media messages in gallery channels |
| **Rich Presence** | Rotating status with live stats + hourly promo |
| **Booster Perks** | 2x XP, no cooldowns, AI translation for boosters |
| **Stats API** | REST API for leaderboard dashboard |

---

## XP System

### Leveling
- **Message XP**: 8-12 XP per message (60s cooldown)
- **Voice XP**: 3 XP per minute (requires 2+ humans, not deafened)
- **Anti-AFK**: No XP if muted for over 1 hour (prevents farming)
- **Booster Bonus**: 2x multiplier on all XP

### Role Rewards

| Level | Role | Permissions Unlocked |
|-------|------|---------------------|
| 1 | LVL 1 | Connect to voice channels |
| 5 | LVL 5 | Attach files, embed links |
| 10 | LVL 10 | Use external emojis |
| 20 | LVL 20 | Use external stickers |
| 30 | LVL 30 | Change nickname |
| 40-100 | LVL 40-100 | Prestige roles |

---

## TempVoice System

Create temporary voice channels with full control:

| Control | Description |
|---------|-------------|
| **Lock/Unlock** | Toggle channel access |
| **Set Limit** | Set user limit (0-99) |
| **Rename** | Change channel name |
| **Allow/Block** | Manage user access |
| **Kick** | Remove users from channel |
| **Claim** | Request ownership (requires approval) |
| **Transfer** | Give ownership to another user |
| **Delete** | Instantly delete your channel |

---

## Commands

| Command | Description |
|---------|-------------|
| `/rank [user]` | View XP rank card |
| `/translate <text> [to]` | Translate text to any language |
| `/convert [media] [url]` | Add caption to image/video |
| `/weather <city>` | Get current weather |
| `/get <option> [user]` | Get avatar, banner, or server assets |
| `/afk [reason]` | Set yourself as AFK |
| `/download <url>` | Download media from social platforms |

### Reply Commands
| Reply With | Action |
|------------|--------|
| `convert` | Add caption to replied image/video |
| `quote` | Generate quote image from message |
| `translate to <lang>` | Translate replied message |

---

## Tech Stack

- **Python 3.12+** - Async runtime
- **Discord.py 2.7+** - Discord API wrapper
- **OpenAI GPT-4o-mini** - AI translation
- **SQLite** - Persistent storage with WAL mode
- **aiohttp** - Async HTTP client
- **Pillow** - Image processing
- **FFmpeg** - Video processing

---

## Architecture

```
SyriaBot/
├── src/
│   ├── core/           # Config, logging, colors, constants
│   ├── services/
│   │   ├── tempvoice/  # TempVoice system (modular)
│   │   ├── xp/         # XP system (service, utils, card)
│   │   ├── afk/        # AFK system
│   │   ├── presence.py # Rich presence handler
│   │   ├── gallery.py  # Gallery mode service
│   │   └── ...         # Convert, quote, translate, download
│   ├── handlers/       # Event handlers (voice, message, members)
│   ├── commands/       # Slash commands
│   ├── views/          # Discord UI components
│   └── utils/          # Helpers, HTTP, footer
├── data/               # SQLite database
└── logs/               # Application logs
```

---

## Database Schema

| Table | Description |
|-------|-------------|
| `user_xp` | XP, level, messages, voice time per user |
| `tempvoice_channels` | Active temporary voice channels |
| `tempvoice_trusted` | Trusted users per channel |
| `tempvoice_blocked` | Blocked users per channel |
| `tempvoice_settings` | Channel-specific settings |
| `afk_users` | Active AFK statuses with reasons |

---

## Stats API

REST API for the leaderboard dashboard:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/syria/stats` | Overall stats + top 3 |
| `GET /api/syria/leaderboard` | Paginated leaderboard |
| `GET /api/syria/user/{id}` | Individual user data |

---

## License

**Source Available** - See [LICENSE](LICENSE) for details.

This code is provided for **educational and viewing purposes only**. You may not run, redistribute, or create derivative works from this code.

---

<div align="center">

**SyriaBot**

*Built with care for [discord.gg/syria](https://discord.gg/syria)*

</div>
