"""
SyriaBot - FAQ Service
======================

FAQ data, analytics, and translations.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import json
import time
from pathlib import Path
from typing import Optional
from collections import defaultdict

from src.core.logger import logger


# =============================================================================
# FAQ Data
# =============================================================================

FAQ_DATA = {
    "xp": {
        "title": {
            "en": "📊 How XP & Leveling Works",
            "ar": "📊 كيف يعمل نظام الـ XP والمستويات",
        },
        "description": {
            "en": """**Earning XP:**
• **Messages:** 8-12 XP per message (60 second cooldown)
• **Voice:** 3 XP per minute (must have 2+ people, not deafened)
• **Boosters:** <@&1230147693490471023> get 2x XP multiplier

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
• **البوسترز:** <@&1230147693490471023> يحصلون على 2x XP

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
• You get <@&1236824194722041876> automatically when you join
• Level roles are given automatically as you level up

**Self-Assign Roles:**
• Go to <id:customize> to pick your roles
• Choose colors, pronouns, notifications, etc.

**Purchasable Roles (Economy):**
• Earn coins by chatting, playing games, and being active
• Check your balance in <#1459658497879707883>
• Buy custom roles in <#1459644341361447181>

**Special Roles:**
• <@&1230147693490471023> roles → boost the server
• Staff roles → given by admins only""",
            "ar": """**الرولات التلقائية:**
• تحصل على <@&1236824194722041876> تلقائياً عند الانضمام
• رولات المستوى تُعطى تلقائياً مع ارتفاع مستواك

**الرولات الذاتية:**
• اذهب إلى <id:customize> لاختيار رولاتك
• اختر الألوان والضمائر والإشعارات

**الرولات القابلة للشراء:**
• اكسب عملات بالدردشة واللعب والنشاط
• تحقق من رصيدك في <#1459658497879707883>
• اشترِ رولات في <#1459644341361447181>

**الرولات الخاصة:**
• رولات <@&1230147693490471023> ← بوست السيرفر
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
1. Join <#1455684848977969399>
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
1. انضم إلى <#1455684848977969399>
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
1. Go to <#1406750411779604561>
2. Create a ticket with details
3. Include screenshots/evidence if possible

**Do NOT:**
• Ping staff in public channels
• Report in general chat
• Mini-mod or confront the person yourself

Staff will handle it privately.""",
            "ar": """**للإبلاغ عن مخالفة:**
1. اذهب إلى <#1406750411779604561>
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
3. It will be posted in <#1459123706189058110>

**Rules:**
• No hate speech or harassment
• No doxxing or personal info
• No NSFW content

Confessions can be traced by staff if rules are broken.""",
            "ar": """**كيف تعترف:**
1. استخدم أمر `/confess` في أي مكان
2. اكتب اعترافك (نص فقط)
3. سيُنشر في <#1459123706189058110>

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
• Use commands in <#1459658497879707883>

**Spending:**
• Buy roles in <#1459644341361447181>
• Gamble in the casino""",
            "ar": """**كيف تكسب عملات:**
• الدردشة في السيرفر (دخل سلبي)
• العب ألعاب الكازينو (روليت، بلاك جاك، سلوتس)
• فز في الألعاب المصغرة والفعاليات
• مكافآت يومية بـ `/daily`

**تحقق من رصيدك:**
• استخدم الأوامر في <#1459658497879707883>

**الإنفاق:**
• اشترِ رولات في <#1459644341361447181>
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
Guess countries from their flags in <#1402445407312941158>

**Counting:**
Count together in <#1457434957772488714> - don't break the chain!

Win coins by participating in games!""",
            "ar": """**الألعاب المتوفرة:**
• 🎰 كازينو (روليت، بلاك جاك، سلوتس)
• 🚩 لعبة تخمين الأعلام
• 🔢 قناة العد
• المزيد قريباً!

**لعبة الأعلام:**
خمّن الدول من أعلامها في <#1402445407312941158>

**العد:**
عدّوا معاً في <#1457434957772488714> - لا تكسروا السلسلة!

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

1. Go to <#1406750411779604561>
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

1. اذهب إلى <#1406750411779604561>
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


# =============================================================================
# Analytics
# =============================================================================

class FAQAnalytics:
    """
    Tracks FAQ usage statistics.

    DESIGN:
        Persists analytics to JSON file for tracking FAQ engagement.
        Records triggers, helpful/unhelpful feedback, ticket clicks,
        and language switches per topic.
    """

    DATA_FILE = Path(__file__).parent.parent.parent.parent / "data" / "faq_analytics.json"

    def __init__(self) -> None:
        self._stats: dict = {
            "triggers": defaultdict(int),  # topic -> count
            "helpful": defaultdict(int),   # topic -> helpful count
            "unhelpful": defaultdict(int), # topic -> unhelpful count
            "ticket_clicks": 0,
            "language_switches": defaultdict(int),  # topic -> ar switch count
        }
        self._load()

    def _load(self) -> None:
        """Load stats from file."""
        try:
            if self.DATA_FILE.exists():
                with open(self.DATA_FILE, "r") as f:
                    data = json.load(f)
                    self._stats["triggers"] = defaultdict(int, data.get("triggers", {}))
                    self._stats["helpful"] = defaultdict(int, data.get("helpful", {}))
                    self._stats["unhelpful"] = defaultdict(int, data.get("unhelpful", {}))
                    self._stats["ticket_clicks"] = data.get("ticket_clicks", 0)
                    self._stats["language_switches"] = defaultdict(int, data.get("language_switches", {}))
        except Exception as e:
            logger.tree("FAQ Analytics Load Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    def _save(self) -> None:
        """Save stats to file."""
        try:
            self.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.DATA_FILE, "w") as f:
                json.dump({
                    "triggers": dict(self._stats["triggers"]),
                    "helpful": dict(self._stats["helpful"]),
                    "unhelpful": dict(self._stats["unhelpful"]),
                    "ticket_clicks": self._stats["ticket_clicks"],
                    "language_switches": dict(self._stats["language_switches"]),
                }, f, indent=2)
        except Exception as e:
            logger.tree("FAQ Analytics Save Failed", [
                ("Error", str(e)[:50]),
            ], emoji="⚠️")

    def record_trigger(self, topic: str) -> None:
        """Record a FAQ being triggered."""
        self._stats["triggers"][topic] += 1
        self._save()

    def record_helpful(self, topic: str) -> None:
        """Record a helpful vote."""
        self._stats["helpful"][topic] += 1
        self._save()

    def record_unhelpful(self, topic: str) -> None:
        """Record an unhelpful vote."""
        self._stats["unhelpful"][topic] += 1
        self._save()

    def record_ticket_click(self) -> None:
        """Record a ticket button click."""
        self._stats["ticket_clicks"] += 1
        self._save()

    def record_language_switch(self, topic: str) -> None:
        """Record a language switch to Arabic."""
        self._stats["language_switches"][topic] += 1
        self._save()

    def get_stats(self) -> dict:
        """Get all stats."""
        return {
            "triggers": dict(self._stats["triggers"]),
            "helpful": dict(self._stats["helpful"]),
            "unhelpful": dict(self._stats["unhelpful"]),
            "ticket_clicks": self._stats["ticket_clicks"],
            "language_switches": dict(self._stats["language_switches"]),
            "total_triggers": sum(self._stats["triggers"].values()),
            "total_helpful": sum(self._stats["helpful"].values()),
            "total_unhelpful": sum(self._stats["unhelpful"].values()),
        }

    def get_top_faqs(self, limit: int = 5) -> list[tuple[str, int]]:
        """Get most triggered FAQs."""
        sorted_faqs = sorted(
            self._stats["triggers"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_faqs[:limit]


# Global instance
faq_analytics = FAQAnalytics()
