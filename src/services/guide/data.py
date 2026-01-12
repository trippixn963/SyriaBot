"""
SyriaBot - Guide Data
=====================

Content for the server guide panel sections.

Author: John Hamwi
Server: discord.gg/syria
"""

# =============================================================================
# Rules Data
# =============================================================================

RULES_DATA = [
    {
        "title": "1. Terrorism & Extremism",
        "content": (
            "Zero tolerance for ISIS, Al-Qaeda, or any extremist groups. "
            "No praise, support, propaganda, or jokes about terrorism. "
            "Includes usernames, avatars, banners, media. **Instant ban.**"
        ),
    },
    {
        "title": "2. Hate Speech",
        "content": (
            "No racial, religious, or ethnic slurs. "
            "No dehumanizing language toward any group. "
            "All backgrounds are respected here."
        ),
    },
    {
        "title": "3. Respect & Conduct",
        "content": (
            "No harassment, bullying, threats, or personal attacks. "
            "No insults based on religion, ethnicity, region, or family. "
            "Stay civil even when disagreeing."
        ),
    },
    {
        "title": "4. NSFW Content",
        "content": (
            "No pornography, sexual media, or explicit content. "
            "No sexual jokes or comments toward minors. "
            "Unwanted sexual DMs result in **instant ban.**"
        ),
    },
    {
        "title": "5. Privacy & Security",
        "content": (
            "No doxxing or leaking personal information. "
            "No sharing DMs or screenshots without consent. "
            "No phishing links, malware, or fake giveaways."
        ),
    },
    {
        "title": "6. Advertising & Self-Promotion",
        "content": (
            "No promoting servers, communities, or content through DMs. "
            "No self-promotion (YouTube, TikTok, social media, etc.). "
            "Contact inbox for partnerships. Private recruiting = ban."
        ),
    },
    {
        "title": "7. Impersonation",
        "content": (
            "No impersonating staff, members, or public figures. "
            "No alt accounts to evade bans or restrictions. "
            "Includes copying names, avatars, or profiles."
        ),
    },
    {
        "title": "8. Politics & Sensitive Topics",
        "content": (
            "Political discussions only in <#1391070464406978701>. "
            "No targeted harassment or agenda-pushing. "
            "Staff may end discussions that escalate."
        ),
    },
    {
        "title": "9. Profiles & Nicknames",
        "content": (
            "No offensive usernames or avatars. "
            "No terror symbols, hate symbols, or sexual content. "
            "Staff may change names that break rules."
        ),
    },
    {
        "title": "10. AI-Generated Media",
        "content": (
            "No AI-generated content of server members. "
            "No deepfakes or manipulated identity content. "
            "Violation results in **instant ban.**"
        ),
    },
    {
        "title": "11. Spam & Channels",
        "content": (
            "No spam, text walls, or repetitive pinging. "
            "Use the correct channel for each topic. "
            "No pinging staff without a valid reason."
        ),
    },
    {
        "title": "12. Voice Channels",
        "content": (
            "No ear rape, soundboards, excessive noise, or offensive language. "
            "No NSFW or offensive streams/screen shares. "
            "No recording without consent or channel hopping to disrupt."
        ),
    },
    {
        "title": "13. Bot Usage",
        "content": (
            "No spamming bot commands. "
            "No exploiting bugs or glitches. "
            "Report exploits to staff instead of abusing them."
        ),
    },
    {
        "title": "14. Mini-Modding",
        "content": (
            "Don't act as staff if you're not staff. "
            "Report issues privately in <#1406750411779604561>. "
            "Let moderators handle enforcement."
        ),
    },
    {
        "title": "15. Language",
        "content": (
            "Arabic and English are both welcome. "
            "Keep conversations readable for others. "
            "No spamming in other languages to exclude people."
        ),
    },
]


# =============================================================================
# Roles Data
# =============================================================================

ROLES_DATA = {
    "auto": {
        "title": "Auto Roles",
        "items": [
            "**Citizens** - Given automatically when you join",
            "**Level Roles** - Assigned as you level up through activity",
        ],
    },
    "self_assign": {
        "title": "Self-Assign Roles",
        "items": [
            "Go to <#1459644341361447181> to pick your own roles",
            "Available: Colors, pronouns, ping notifications",
        ],
    },
    "purchasable": {
        "title": "Purchasable Roles",
        "items": [
            "Earn coins through chatting and games",
            "Purchase cosmetic roles in <#1459658497879707883>",
        ],
    },
    "special": {
        "title": "Special Roles",
        "items": [
            "**Booster** - 2x XP multiplier, unlimited downloads",
            "**Staff** - Admin assigned only",
        ],
    },
    "level_perks": {
        "title": "Level Permissions",
        "items": [
            "**Level 1** - Connect to voice channels",
            "**Level 5** - Attach files & embed links",
            "**Level 10** - Use external emojis",
            "**Level 20** - Use external stickers",
            "**Level 30** - Change nickname",
        ],
    },
}


# =============================================================================
# Commands Data
# =============================================================================

COMMANDS_DATA = {
    "fun": {
        "title": "Fun Commands",
        "description": "Use in <#1459144517449158719>",
        "commands": [
            "`ship @user @user` - Compatibility percentage",
            "`howgay` `simp` `howsmart` `bodyfat` - Meter cards",
        ],
    },
    "actions": {
        "title": "Action Commands",
        "description": "Anime GIF reactions",
        "commands": [
            "`hug` `kiss` `slap` `pat` `poke` - Target actions",
            "`cry` `dance` `laugh` `sleep` - Self actions",
            "40+ actions available!",
        ],
    },
    "utility": {
        "title": "Utility Commands",
        "description": "Useful tools",
        "commands": [
            "`/rank` - View your XP and level",
            "`/get avatar` - Get user avatars/banners",
            "`/weather` - Check weather anywhere",
            "`/translate` - Translate text",
            "`/download` - Download social media videos",
            "`/convert` - Convert videos to GIF",
            "`/image` - Search for images",
        ],
    },
    "social": {
        "title": "Social Commands",
        "description": "Community features",
        "commands": [
            "`/confess` - Anonymous confessions",
            "`/suggest` - Submit server suggestions",
            "`/afk` - Set AFK status",
            "`/birthday` - Set your birthday",
        ],
    },
}
