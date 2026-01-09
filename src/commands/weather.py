"""
SyriaBot - Weather Command
==========================

Get current weather for any city with fuzzy matching.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

import discord
from discord import app_commands
from discord.ext import commands
from difflib import SequenceMatcher
import aiohttp

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_GOLD, COLOR_ERROR, EMOJI_TRANSFER
from src.core.constants import VIEW_TIMEOUT_DEFAULT
from src.utils.footer import set_footer


def weather_cooldown(interaction: discord.Interaction) -> app_commands.Cooldown | None:
    """
    Dynamic cooldown - None for mods/owners, 5 min for everyone else.

    Args:
        interaction: The Discord interaction

    Returns:
        Cooldown object or None if user is exempt
    """
    if interaction.user.id == config.OWNER_ID:
        return None

    if isinstance(interaction.user, discord.Member):
        if config.MOD_ROLE_ID:
            mod_role = interaction.user.get_role(config.MOD_ROLE_ID)
            if mod_role:
                return None

    return app_commands.Cooldown(1, 300.0)

# Main embed color (alias for backwards compatibility)
COLOR_WEATHER = COLOR_GOLD


# =============================================================================
# Popular Cities for Autocomplete
# =============================================================================

CITIES = [
    # Middle East
    "Damascus, Syria", "Aleppo, Syria", "Homs, Syria", "Latakia, Syria",
    "Dubai, UAE", "Abu Dhabi, UAE", "Riyadh, Saudi Arabia", "Jeddah, Saudi Arabia",
    "Mecca, Saudi Arabia", "Medina, Saudi Arabia", "Amman, Jordan", "Beirut, Lebanon",
    "Baghdad, Iraq", "Erbil, Iraq", "Kuwait City, Kuwait", "Doha, Qatar",
    "Manama, Bahrain", "Muscat, Oman", "Sanaa, Yemen", "Tehran, Iran",
    "Jerusalem, Israel", "Tel Aviv, Israel", "Gaza, Palestine", "Ramallah, Palestine",

    # North America
    "New York, USA", "Los Angeles, USA", "Chicago, USA", "Houston, USA",
    "Phoenix, USA", "San Francisco, USA", "Seattle, USA", "Miami, USA",
    "Boston, USA", "Denver, USA", "Las Vegas, USA", "Atlanta, USA",
    "Toronto, Canada", "Vancouver, Canada", "Montreal, Canada", "Calgary, Canada",
    "Mexico City, Mexico", "Guadalajara, Mexico", "Cancun, Mexico",

    # Europe
    "London, UK", "Manchester, UK", "Birmingham, UK", "Edinburgh, UK",
    "Paris, France", "Lyon, France", "Marseille, France",
    "Berlin, Germany", "Munich, Germany", "Frankfurt, Germany", "Hamburg, Germany",
    "Rome, Italy", "Milan, Italy", "Venice, Italy", "Florence, Italy",
    "Madrid, Spain", "Barcelona, Spain", "Seville, Spain",
    "Amsterdam, Netherlands", "Brussels, Belgium", "Vienna, Austria",
    "Zurich, Switzerland", "Geneva, Switzerland", "Stockholm, Sweden",
    "Oslo, Norway", "Copenhagen, Denmark", "Helsinki, Finland",
    "Dublin, Ireland", "Lisbon, Portugal", "Athens, Greece",
    "Warsaw, Poland", "Prague, Czech Republic", "Budapest, Hungary",
    "Moscow, Russia", "Saint Petersburg, Russia", "Kyiv, Ukraine",

    # Asia
    "Tokyo, Japan", "Osaka, Japan", "Kyoto, Japan",
    "Beijing, China", "Shanghai, China", "Hong Kong, China", "Shenzhen, China",
    "Seoul, South Korea", "Busan, South Korea",
    "Bangkok, Thailand", "Phuket, Thailand",
    "Singapore, Singapore", "Kuala Lumpur, Malaysia",
    "Jakarta, Indonesia", "Bali, Indonesia",
    "Manila, Philippines", "Hanoi, Vietnam", "Ho Chi Minh City, Vietnam",
    "Mumbai, India", "Delhi, India", "Bangalore, India", "Chennai, India",
    "Karachi, Pakistan", "Lahore, Pakistan", "Islamabad, Pakistan",
    "Dhaka, Bangladesh", "Colombo, Sri Lanka", "Kathmandu, Nepal",

    # Africa
    "Cairo, Egypt", "Alexandria, Egypt", "Casablanca, Morocco", "Marrakech, Morocco",
    "Tunis, Tunisia", "Algiers, Algeria", "Lagos, Nigeria", "Nairobi, Kenya",
    "Cape Town, South Africa", "Johannesburg, South Africa", "Addis Ababa, Ethiopia",

    # Oceania
    "Sydney, Australia", "Melbourne, Australia", "Brisbane, Australia", "Perth, Australia",
    "Auckland, New Zealand", "Wellington, New Zealand",

    # South America
    "Sao Paulo, Brazil", "Rio de Janeiro, Brazil", "Buenos Aires, Argentina",
    "Lima, Peru", "Bogota, Colombia", "Santiago, Chile", "Caracas, Venezuela",
]


# =============================================================================
# Weather Condition Icons & Colors
# =============================================================================

WEATHER_ICONS = {
    "01d": "☀️",  # clear sky day
    "01n": "🌙",  # clear sky night
    "02d": "⛅",  # few clouds day
    "02n": "☁️",  # few clouds night
    "03d": "☁️",  # scattered clouds
    "03n": "☁️",
    "04d": "☁️",  # broken clouds
    "04n": "☁️",
    "09d": "🌧️",  # shower rain
    "09n": "🌧️",
    "10d": "🌦️",  # rain day
    "10n": "🌧️",  # rain night
    "11d": "⛈️",  # thunderstorm
    "11n": "⛈️",
    "13d": "❄️",  # snow
    "13n": "❄️",
    "50d": "🌫️",  # mist
    "50n": "🌫️",
}



# =============================================================================
# Helper Functions
# =============================================================================

def fuzzy_match(query: str, choices: list[str], limit: int = 25) -> list[str]:
    """
    Fuzzy match query against choices.

    Args:
        query: Search string
        choices: List of choices to match against
        limit: Maximum number of results

    Returns:
        List of matched choices sorted by relevance
    """
    if not query:
        return choices[:limit]

    query_lower = query.lower()
    scored = []

    for choice in choices:
        choice_lower = choice.lower()

        # Exact prefix match gets highest score
        if choice_lower.startswith(query_lower):
            scored.append((choice, 1.0))
        # Contains query
        elif query_lower in choice_lower:
            scored.append((choice, 0.8))
        # Fuzzy match
        else:
            ratio = SequenceMatcher(None, query_lower, choice_lower).ratio()
            if ratio > 0.4:
                scored.append((choice, ratio))

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return [choice for choice, _ in scored[:limit]]


def celsius_to_fahrenheit(celsius: float) -> float:
    """
    Convert Celsius to Fahrenheit.

    Args:
        celsius: Temperature in Celsius

    Returns:
        Temperature in Fahrenheit
    """
    return (celsius * 9/5) + 32


# =============================================================================
# Weather View (Toggle Button)
# =============================================================================

class WeatherView(discord.ui.View):
    """View with toggle button for temperature unit."""

    def __init__(self, weather_data: dict, city: str, user_id: int) -> None:
        """
        Initialize the weather view.

        Args:
            weather_data: Weather API response data
            city: City name for display
            user_id: ID of user who invoked command
        """
        super().__init__(timeout=VIEW_TIMEOUT_DEFAULT)
        self.weather_data = weather_data
        self.city = city
        self.user_id = user_id
        self.is_celsius = True

    async def on_timeout(self) -> None:
        """Disable button on timeout."""
        for item in self.children:
            item.disabled = True
        log.tree("Weather View Expired", [
            ("City", self.city),
            ("ID", str(self.user_id)),
        ], emoji="⏳")

    def build_embed(self) -> discord.Embed:
        """
        Build a clean weather embed.

        Returns:
            Discord embed with weather information
        """
        data = self.weather_data
        main = data["main"]
        weather = data["weather"][0]

        # Get icon based on weather condition
        icon_code = weather.get("icon", "01d")
        icon = WEATHER_ICONS.get(icon_code, "🌡️")

        # Temperature calculations
        temp_c = main["temp"]
        feels_c = main["feels_like"]
        temp_min_c = main["temp_min"]
        temp_max_c = main["temp_max"]
        humidity = main["humidity"]

        if self.is_celsius:
            temp_display = f"{temp_c:.0f}°C"
            feels_display = f"{feels_c:.0f}°C"
            high_low = f"{temp_max_c:.0f}° / {temp_min_c:.0f}°"
        else:
            temp_display = f"{celsius_to_fahrenheit(temp_c):.0f}°F"
            feels_display = f"{celsius_to_fahrenheit(feels_c):.0f}°F"
            high_low = f"{celsius_to_fahrenheit(temp_max_c):.0f}° / {celsius_to_fahrenheit(temp_min_c):.0f}°"

        # Clean, minimal description
        description = (
            f"## {icon} {temp_display}\n"
            f"**{weather['description'].title()}**\n\n"
            f"Feels like **{feels_display}** · H/L **{high_low}** · 💧 **{humidity}%**"
        )

        embed = discord.Embed(
            title=self.city,
            description=description,
            color=COLOR_WEATHER
        )

        # Set weather icon as thumbnail
        if icon_code:
            embed.set_thumbnail(url=f"https://openweathermap.org/img/wn/{icon_code}@4x.png")

        set_footer(embed)

        return embed

    @discord.ui.button(label="°C / °F", style=discord.ButtonStyle.secondary, emoji=EMOJI_TRANSFER)
    async def toggle_unit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Toggle between Celsius and Fahrenheit."""
        # Only allow the original user to toggle
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Only the person who used the command can toggle units.", ephemeral=True)
            log.tree("Weather Toggle Rejected", [
                ("City", self.city),
                ("Attempted By", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("Attempted By ID", str(interaction.user.id)),
                ("Owner ID", str(self.user_id)),
                ("Reason", "Not command owner"),
            ], emoji="⚠️")
            return

        self.is_celsius = not self.is_celsius
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

        log.tree("Weather Unit Toggled", [
            ("City", self.city),
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Unit", "Celsius" if self.is_celsius else "Fahrenheit"),
        ], emoji="🔄")


# =============================================================================
# Cog
# =============================================================================

class WeatherCog(commands.Cog):
    """Weather command with fuzzy city search."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the weather cog with API key."""
        self.bot = bot
        self.api_key = config.OPENWEATHER_API_KEY

    async def fetch_weather(self, city: str) -> dict | None:
        """
        Fetch weather data from OpenWeatherMap API.

        Args:
            city: City name to search for

        Returns:
            Weather data dict or None if not found
        """
        if not self.api_key:
            return None

        url = "https://api.openweathermap.org/data/2.5/weather"

        # Try different query formats
        queries_to_try = [
            city,  # Full string "Damascus, Syria"
            city.split(",")[0].strip(),  # Just city name "Damascus"
        ]

        try:
            async with aiohttp.ClientSession() as session:
                for query in queries_to_try:
                    params = {
                        "q": query,
                        "appid": self.api_key,
                        "units": "metric",
                    }
                    async with session.get(url, params=params, timeout=10) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 401:
                            log.tree("Weather API Error", [
                                ("City", city),
                                ("Status", str(resp.status)),
                                ("Reason", "Invalid API key"),
                            ], emoji="❌")
                            return None

                log.tree("Weather City Not Found", [
                    ("Query", city),
                ], emoji="⚠️")
                return None

        except Exception as e:
            log.tree("Weather Fetch Error", [
                ("City", city),
                ("Error", str(e)[:100]),
            ], emoji="❌")
            return None

    @app_commands.command(name="weather", description="Get current weather for any city")
    @app_commands.describe(city="City name (type to search)")
    @app_commands.checks.dynamic_cooldown(weather_cooldown)
    async def weather(self, interaction: discord.Interaction, city: str) -> None:
        """Get current weather for a city."""
        await interaction.response.defer()

        if not self.api_key:
            embed = discord.Embed(
                description="⚠️ Weather API is not configured.",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            log.tree("Weather Command Failed", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Reason", "API key not configured"),
            ], emoji="❌")
            return

        log.tree("Weather Command", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("City", city),
        ], emoji="🌤️")

        # Fetch weather data
        data = await self.fetch_weather(city)

        if not data:
            embed = discord.Embed(
                title="City Not Found",
                description=f"Could not find weather for **{city}**.\n\n"
                           f"Try:\n"
                           f"• Just the city name without country\n"
                           f"• A nearby major city\n"
                           f"• Check spelling",
                color=COLOR_ERROR
            )
            set_footer(embed)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # Get actual city name from response
        actual_city = data.get("name", city)
        if "sys" in data and "country" in data["sys"]:
            actual_city = f"{actual_city}, {data['sys']['country']}"

        # Build view and embed
        view = WeatherView(data, actual_city, interaction.user.id)
        embed = view.build_embed()

        await interaction.followup.send(embed=embed, view=view)

        log.tree("Weather Complete", [
            ("City", actual_city),
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Temp", f"{data['main']['temp']:.1f}°C"),
            ("Condition", data["weather"][0]["description"]),
        ], emoji="✅")

    @weather.autocomplete("city")
    async def city_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """
        Autocomplete for city names with fuzzy matching.

        Args:
            interaction: The Discord interaction
            current: Current input string

        Returns:
            List of autocomplete choices
        """
        matches = fuzzy_match(current, CITIES, limit=25)
        return [app_commands.Choice(name=city, value=city) for city in matches]

    @weather.error
    async def weather_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """Handle weather command errors."""
        if isinstance(error, app_commands.CommandOnCooldown):
            minutes = int(error.retry_after // 60)
            seconds = int(error.retry_after % 60)
            if minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"

            try:
                await interaction.response.send_message(
                    f"⏳ Slow down! You can use `/weather` again in **{time_str}**",
                    ephemeral=True,
                )
            except discord.HTTPException as e:
                log.tree("Weather Cooldown Response Failed", [
                    ("User", f"{interaction.user.name}"),
                    ("Error", str(e)[:50]),
                ], emoji="⚠️")

            log.tree("Weather Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("ID", str(interaction.user.id)),
                ("Remaining", time_str),
            ], emoji="⏳")
            return

        log.tree("Weather Command Error", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("ID", str(interaction.user.id)),
            ("Error", str(error)[:100]),
        ], emoji="❌")

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ An error occurred",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "❌ An error occurred",
                    ephemeral=True,
                )
        except discord.HTTPException as e:
            log.tree("Weather Error Response Failed", [
                ("User", f"{interaction.user.name}"),
                ("Error", str(e)[:50]),
            ], emoji="⚠️")


async def setup(bot: commands.Bot) -> None:
    """Load the weather cog."""
    await bot.add_cog(WeatherCog(bot))
    log.tree("Command Loaded", [("Name", "weather")], emoji="✅")
