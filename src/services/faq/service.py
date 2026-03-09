"""
SyriaBot - FAQ Service
======================

FAQ data, analytics, and translations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import json
from pathlib import Path
from typing import Optional

from src.core.config import config
from src.core.logger import logger
from src.services.database import db


# =============================================================================
# FAQ Data Builder
# =============================================================================

def _replace_placeholders(text: str) -> str:
    """Replace config placeholders in FAQ text."""
    replacements = {
        "{config.BOOSTER_ROLE_ID}": str(config.BOOSTER_ROLE_ID),
        "{config.AUTO_ROLE_ID}": str(config.AUTO_ROLE_ID),
        "{config.CMDS_CHANNEL_ID}": str(config.CMDS_CHANNEL_ID),
        "{config.ROLE_SHOP_CHANNEL_ID}": str(config.ROLE_SHOP_CHANNEL_ID),
        "{config.VC_CREATOR_CHANNEL_ID}": str(config.VC_CREATOR_CHANNEL_ID),
        "{config.TICKET_CHANNEL_ID}": str(config.TICKET_CHANNEL_ID),
        "{config.CONFESSIONS_CHANNEL_ID}": str(config.CONFESSIONS_CHANNEL_ID),
        "{config.FLAGS_GAME_CHANNEL_ID}": str(config.FLAGS_GAME_CHANNEL_ID),
        "{config.COUNTING_CHANNEL_ID}": str(config.COUNTING_CHANNEL_ID),
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text


def get_faq_description(topic: str, lang: str = "en") -> str | None:
    """Get FAQ description with config values replaced."""
    faq = _FAQ_DATA_RAW.get(topic)
    if not faq:
        return None
    desc = faq.get("description", {}).get(lang)
    if desc:
        return _replace_placeholders(desc)
    return None


def get_faq_title(topic: str, lang: str = "en") -> str | None:
    """Get FAQ title."""
    faq = _FAQ_DATA_RAW.get(topic)
    if not faq:
        return None
    return faq.get("title", {}).get(lang)


def get_faq_topics() -> list[str]:
    """Get all FAQ topic keys."""
    return list(_FAQ_DATA_RAW.keys())


# Raw FAQ data with placeholders (use get_faq_* functions to access)
_FAQ_DATA_RAW = {
    "xp": {
        "title": {
            "en": "📊 How XP & Leveling Works",
            "ar": "📊 كيف يعمل نظام الـ XP والمستويات",
        },
        "description": {
            "en": """**Earning XP:**
• **Messages:** 8-12 XP per message (60 second cooldown)
• **Voice:** 3 XP per minute (must have 2+ people, not deafened)
• **Boosters:** <@&{config.BOOSTER_ROLE_ID}> get 2x XP multiplier

**Level Rewards:**
• Level 1 → Connect to voice channels
• Level 5 → Attach files & embed links
• Level 10 → Use external emojis
• Level 20 → Use external stickers
• Level 30 → Change nickname

Check your rank with `/rank`""",
            "ar": """**كسب XP:**
• **الرسائل:** 8-12 XP لكل رسالة (كولداون 60 ثانية)
• **الصوت:** 3 XP لكل دقيقة (يجب أن يكون هناك 2+ أشخاص)
• **البوسترز:** <@&{config.BOOSTER_ROLE_ID}> يحصلون على 2x XP

**مكافآت المستويات:**
• مستوى 1 ← الاتصال بالقنوات الصوتية
• مستوى 5 ← إرفاق ملفات وروابط
• مستوى 10 ← استخدام إيموجي خارجي
• مستوى 20 ← استخدام ستيكرز خارجية
• مستوى 30 ← تغيير الاسم المستعار

تحقق من رتبتك بـ `/rank`""",
        },
    },
    "roles": {
        "title": {
            "en": "🎭 How to Get Roles",
            "ar": "🎭 كيف تحصل على الرولات",
        },
        "description": {
            "en": """**Auto Roles:**
• You get <@&{config.AUTO_ROLE_ID}> automatically when you join
• Level roles are given automatically as you level up

**Self-Assign Roles:**
• Go to <id:customize> to pick your roles
• Choose colors, pronouns, notifications, etc.

**Purchasable Roles (Economy):**
• Earn coins by chatting, playing games, and being active
• Check your balance in <#{config.CMDS_CHANNEL_ID}>
• Buy custom roles in <#{config.ROLE_SHOP_CHANNEL_ID}>

**Special Roles:**
• <@&{config.BOOSTER_ROLE_ID}> roles → boost the server
• Staff roles → given by admins only""",
            "ar": """**الرولات التلقائية:**
• تحصل على <@&{config.AUTO_ROLE_ID}> تلقائياً عند الانضمام
• رولات المستوى تُعطى تلقائياً مع ارتفاع مستواك

**الرولات الذاتية:**
• اذهب إلى <id:customize> لاختيار رولاتك
• اختر الألوان والضمائر والإشعارات

**الرولات القابلة للشراء:**
• اكسب عملات بالدردشة واللعب والنشاط
• تحقق من رصيدك في <#{config.CMDS_CHANNEL_ID}>
• اشترِ رولات في <#{config.ROLE_SHOP_CHANNEL_ID}>

**الرولات الخاصة:**
• رولات <@&{config.BOOSTER_ROLE_ID}> ← بوست السيرفر
• رولات الستاف ← تُعطى من الأدمن فقط""",
        },
    },
    "tempvoice": {
        "title": {
            "en": "🎤 TempVoice (Custom Voice Channels)",
            "ar": "🎤 قنوات صوتية مؤقتة",
        },
        "description": {
            "en": """**How to Create:**
1. Join <#{config.VC_CREATOR_CHANNEL_ID}>
2. You'll be moved to your own private channel
3. Use the control panel to manage it

**What You Can Do:**
• Rename your channel
• Set user limit
• Lock/unlock the channel
• Kick/ban users from your channel
• Transfer ownership

Your channel is deleted when everyone leaves.""",
            "ar": """**كيفية الإنشاء:**
1. انضم إلى <#{config.VC_CREATOR_CHANNEL_ID}>
2. سيتم نقلك إلى قناتك الخاصة
3. استخدم لوحة التحكم لإدارتها

**ما يمكنك فعله:**
• إعادة تسمية قناتك
• تحديد عدد المستخدمين
• قفل/فتح القناة
• طرد/حظر مستخدمين من قناتك
• نقل الملكية

تُحذف قناتك عندما يغادر الجميع.""",
        },
    },
    "report": {
        "title": {
            "en": "📥 How to Report Someone",
            "ar": "📥 كيف تبلّغ عن شخص",
        },
        "description": {
            "en": """**To report a rule violation:**
1. Go to <#{config.TICKET_CHANNEL_ID}>
2. Create a ticket with details
3. Include screenshots/evidence if possible

**Do NOT:**
• Ping staff in public channels
• Report in general chat
• Mini-mod or confront the person yourself

Staff will handle it privately.""",
            "ar": """**للإبلاغ عن مخالفة:**
1. اذهب إلى <#{config.TICKET_CHANNEL_ID}>
2. أنشئ تذكرة مع التفاصيل
3. أرفق صور/أدلة إن أمكن

**لا تفعل:**
• منشن الستاف في القنوات العامة
• الإبلاغ في الشات العام
• التصرف كمود أو مواجهة الشخص بنفسك

الستاف سيتعاملون معها بشكل خاص.""",
        },
    },
    "confess": {
        "title": {
            "en": "🤫 Anonymous Confessions",
            "ar": "🤫 اعترافات مجهولة",
        },
        "description": {
            "en": """**How to Confess:**
1. Use `/confess` command anywhere
2. Type your confession (text only)
3. It will be posted in <#{config.CONFESSIONS_CHANNEL_ID}>

**Rules:**
• No hate speech or harassment
• No doxxing or personal info
• No NSFW content

Confessions can be traced by staff if rules are broken.""",
            "ar": """**كيف تعترف:**
1. استخدم أمر `/confess` في أي مكان
2. اكتب اعترافك (نص فقط)
3. سيُنشر في <#{config.CONFESSIONS_CHANNEL_ID}>

**القواعد:**
• لا كلام كراهية أو تحرش
• لا نشر معلومات شخصية
• لا محتوى +18

يمكن للستاف تتبع الاعترافات إذا خُرقت القواعد.""",
        },
    },
    "language": {
        "title": {
            "en": "🌍 Language Rules",
            "ar": "🌍 قواعد اللغة",
        },
        "description": {
            "en": """**Both Arabic and English are welcome!**

• You can chat in either language
• Keep conversations readable for others
• Don't spam in other languages to exclude people

**Arabic Channels:**
Some channels may be Arabic-focused - check channel descriptions.

نرحب بالعربية والإنجليزية في هذا السيرفر 🇸🇾""",
            "ar": """**العربية والإنجليزية مرحب بهما!**

• يمكنك الدردشة بأي لغة
• اجعل المحادثات مفهومة للآخرين
• لا تسبم بلغات أخرى لاستبعاد الناس

**القنوات العربية:**
بعض القنوات قد تكون عربية - تحقق من وصف القناة.

Welcome to chat in Arabic or English 🇸🇾""",
        },
    },
    "staff": {
        "title": {
            "en": "👮 How to Become Staff",
            "ar": "👮 كيف تصبح ستاف",
        },
        "description": {
            "en": """**We don't accept staff applications.**

Staff members are hand-picked based on:
• Activity and engagement
• Helpfulness to other members
• Following the rules consistently
• Being a positive presence

**Don't ask to be staff** - it won't help your chances.
Just be a good community member and you might get noticed.""",
            "ar": """**نحن لا نقبل طلبات الستاف.**

يتم اختيار الستاف بناءً على:
• النشاط والمشاركة
• مساعدة الأعضاء الآخرين
• اتباع القواعد باستمرار
• أن تكون حضوراً إيجابياً

**لا تطلب أن تكون ستاف** - لن يساعد فرصك.
كن عضواً جيداً في المجتمع وقد يتم ملاحظتك.""",
        },
    },
    "invite": {
        "title": {
            "en": "🔗 Server Invite",
            "ar": "🔗 رابط السيرفر",
        },
        "description": {
            "en": """**Permanent Invite Link:**
https://discord.gg/syria

Feel free to share this with friends!

**Note:** Advertising other servers in DMs is against the rules.""",
            "ar": """**رابط الدعوة الدائم:**
https://discord.gg/syria

شاركه مع أصدقائك!

**ملاحظة:** الإعلان عن سيرفرات أخرى في الخاص ممنوع.""",
        },
    },
    "download": {
        "title": {
            "en": "📥 Download Command",
            "ar": "📥 أمر التحميل",
        },
        "description": {
            "en": """**How to Download Videos:**
Use `/download` with a video URL

**Supported Sites:**
• YouTube, TikTok, Instagram, Twitter/X
• Reddit, Facebook, and many more

**Limits:**
• 5 downloads per week
• Max file size depends on boost level

Reply to a message with a link and say `download` to download it.""",
            "ar": """**كيف تحمّل فيديوهات:**
استخدم `/download` مع رابط الفيديو

**المواقع المدعومة:**
• يوتيوب، تيك توك، انستقرام، تويتر/X
• ريديت، فيسبوك، وغيرها

**الحدود:**
• 5 تحميلات في الأسبوع
• حجم الملف يعتمد على مستوى البوست

رد على رسالة فيها رابط واكتب `download` لتحميله.""",
        },
    },
    "convert": {
        "title": {
            "en": "🔄 Convert to GIF",
            "ar": "🔄 تحويل إلى GIF",
        },
        "description": {
            "en": """**How to Convert Videos to GIF:**
1. Reply to a message with a video/image
2. Type `convert` or `gif`
3. Use the editor to adjust (crop, speed, etc.)
4. Save the GIF

**Tip:** Works with videos, images, and stickers!""",
            "ar": """**كيف تحول فيديو إلى GIF:**
1. رد على رسالة فيها فيديو/صورة
2. اكتب `convert` أو `gif`
3. استخدم المحرر للتعديل (قص، سرعة، إلخ)
4. احفظ الـ GIF

**نصيحة:** يعمل مع الفيديوهات والصور والستيكرز!""",
        },
    },
    "economy": {
        "title": {
            "en": "💰 Economy System",
            "ar": "💰 نظام الاقتصاد",
        },
        "description": {
            "en": """**How to Earn Coins:**
• Chat in the server (passive income)
• Play casino games (roulette, blackjack, slots)
• Win minigames and events
• Daily rewards with `/daily`

**Check Balance:**
• Use commands in <#{config.CMDS_CHANNEL_ID}>

**Spending:**
• Buy roles in <#{config.ROLE_SHOP_CHANNEL_ID}>
• Gamble in the casino""",
            "ar": """**كيف تكسب عملات:**
• الدردشة في السيرفر (دخل سلبي)
• العب ألعاب الكازينو (روليت، بلاك جاك، سلوتس)
• فز في الألعاب المصغرة والفعاليات
• مكافآت يومية بـ `/daily`

**تحقق من رصيدك:**
• استخدم الأوامر في <#{config.CMDS_CHANNEL_ID}>

**الإنفاق:**
• اشترِ رولات في <#{config.ROLE_SHOP_CHANNEL_ID}>
• قامر في الكازينو""",
        },
    },
    "casino": {
        "title": {
            "en": "🎰 Casino Games",
            "ar": "🎰 ألعاب الكازينو",
        },
        "description": {
            "en": """**Available Games:**
• 🎡 **Roulette** - Bet on numbers, colors, or ranges
• 🃏 **Blackjack** - Classic 21 card game
• 🎰 **Slots** - Spin to win

**How to Play:**
1. Go to the Casino forum
2. Find the game you want to play
3. Use the bot commands in that post

**Warning:** Only bet what you're willing to lose!""",
            "ar": """**الألعاب المتوفرة:**
• 🎡 **روليت** - راهن على أرقام أو ألوان
• 🃏 **بلاك جاك** - لعبة 21 الكلاسيكية
• 🎰 **سلوتس** - دور واربح

**كيف تلعب:**
1. اذهب إلى منتدى الكازينو
2. اختر اللعبة التي تريدها
3. استخدم أوامر البوت في ذلك البوست

**تحذير:** راهن فقط بما أنت مستعد لخسارته!""",
        },
    },
    "games": {
        "title": {
            "en": "🎮 Minigames & Activities",
            "ar": "🎮 ألعاب مصغرة ونشاطات",
        },
        "description": {
            "en": """**Available Games:**
• 🎰 Casino (roulette, blackjack, slots)
• 🚩 Flag guessing game
• 🔢 Counting channel
• More coming soon!

**Flag Game:**
Guess countries from their flags in <#{config.FLAGS_GAME_CHANNEL_ID}>

**Counting:**
Count together in <#{config.COUNTING_CHANNEL_ID}> - don't break the chain!

Win coins by participating in games!""",
            "ar": """**الألعاب المتوفرة:**
• 🎰 كازينو (روليت، بلاك جاك، سلوتس)
• 🚩 لعبة تخمين الأعلام
• 🔢 قناة العد
• المزيد قريباً!

**لعبة الأعلام:**
خمّن الدول من أعلامها في <#{config.FLAGS_GAME_CHANNEL_ID}>

**العد:**
عدّوا معاً في <#{config.COUNTING_CHANNEL_ID}> - لا تكسروا السلسلة!

اربح عملات بالمشاركة في الألعاب!""",
        },
    },
    "partnership": {
        "title": {
            "en": "🤝 Partnership Requests",
            "ar": "🤝 طلبات الشراكة",
        },
        "description": {
            "en": """**Want to partner with us?**

1. Go to <#{config.TICKET_CHANNEL_ID}>
2. Open a **Partnership** ticket
3. Include your server's invite link and member count
4. Wait for a staff member to review

**Requirements:**
• Your server must have a reasonable member count
• No NSFW or rule-breaking content
• Must be an active, established community

**Do NOT:**
• DM staff or admins directly
• Advertise in public channels
• Spam partnership requests""",
            "ar": """**تريد الشراكة معنا؟**

1. اذهب إلى <#{config.TICKET_CHANNEL_ID}>
2. افتح تذكرة **شراكة**
3. أرفق رابط سيرفرك وعدد الأعضاء
4. انتظر مراجعة أحد الستاف

**المتطلبات:**
• سيرفرك يجب أن يكون لديه عدد معقول من الأعضاء
• لا محتوى +18 أو مخالف للقواعد
• يجب أن يكون مجتمعاً نشطاً ومُؤسساً

**لا تفعل:**
• مراسلة الستاف أو الأدمن مباشرة
• الإعلان في القنوات العامة
• سبام طلبات الشراكة""",
        },
    },
}


def _build_faq_data() -> dict:
    """Build FAQ_DATA with config values replaced in all strings."""
    result = {}
    for topic, data in _FAQ_DATA_RAW.items():
        result[topic] = {
            "title": data["title"].copy(),
            "description": {
                lang: _replace_placeholders(desc)
                for lang, desc in data["description"].items()
            },
        }
    return result


# Build FAQ_DATA at module load time (backward compatible export)
FAQ_DATA = _build_faq_data()


# =============================================================================
# Analytics
# =============================================================================

class FAQAnalytics:
    """
    Tracks FAQ usage statistics.

    DESIGN:
        Persists analytics to SQLite via the database mixin system.
        Records triggers, helpful/unhelpful feedback, ticket clicks,
        and language switches per topic.
    """

    _JSON_FILE = Path(__file__).parent.parent.parent.parent / "data" / "faq_analytics.json"

    def __init__(self) -> None:
        self._migrate_json()

    def _migrate_json(self) -> None:
        """One-time migration from JSON file to SQLite."""
        if not self._JSON_FILE.exists():
            return

        try:
            with open(self._JSON_FILE, "r") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                self._JSON_FILE.rename(self._JSON_FILE.with_suffix(".json.migrated"))
                return

            for metric in ("triggers", "helpful", "unhelpful", "language_switches"):
                for topic, count in data.get(metric, {}).items():
                    for _ in range(count):
                        db.faq_increment(topic, metric)

            ticket_clicks = data.get("ticket_clicks", 0)
            for _ in range(ticket_clicks):
                db.faq_increment("_global", "ticket_clicks")

            self._JSON_FILE.rename(self._JSON_FILE.with_suffix(".json.migrated"))

            logger.tree("FAQ Analytics Migrated", [
                ("From", "JSON"),
                ("To", "SQLite"),
            ], emoji="🔄")

        except Exception as e:
            logger.error_tree("FAQ Analytics JSON Migration Failed", e, [
                ("File", str(self._JSON_FILE)),
            ])

    def record_trigger(self, topic: str) -> None:
        """Record a FAQ being triggered."""
        db.faq_increment(topic, "triggers")

    def record_helpful(self, topic: str) -> None:
        """Record a helpful vote."""
        db.faq_increment(topic, "helpful")

    def record_unhelpful(self, topic: str) -> None:
        """Record an unhelpful vote."""
        db.faq_increment(topic, "unhelpful")

    def record_ticket_click(self) -> None:
        """Record a ticket button click."""
        db.faq_increment("_global", "ticket_clicks")

    def record_language_switch(self, topic: str) -> None:
        """Record a language switch to Arabic."""
        db.faq_increment(topic, "language_switches")

    def get_stats(self) -> dict:
        """Get all stats."""
        raw = db.faq_get_all_stats()
        triggers = raw.get("triggers", {})
        helpful = raw.get("helpful", {})
        unhelpful = raw.get("unhelpful", {})
        ticket_clicks = raw.get("ticket_clicks", {}).get("_global", 0)
        language_switches = raw.get("language_switches", {})

        return {
            "triggers": triggers,
            "helpful": helpful,
            "unhelpful": unhelpful,
            "ticket_clicks": ticket_clicks,
            "language_switches": language_switches,
            "total_triggers": sum(triggers.values()),
            "total_helpful": sum(helpful.values()),
            "total_unhelpful": sum(unhelpful.values()),
        }

    def get_top_faqs(self, limit: int = 5) -> list[tuple[str, int]]:
        """Get most triggered FAQs."""
        return db.faq_get_top("triggers", limit)


# Global instance
faq_analytics = FAQAnalytics()
