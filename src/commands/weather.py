"""
SyriaBot - Weather Command
==========================

Get current weather for any city with fuzzy matching.

Author: حَـــــنَّـــــا
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
from difflib import SequenceMatcher
import aiohttp

from src.core.config import config
from src.core.logger import log
from src.core.colors import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING, COLOR_GOLD
from src.utils.footer import set_footer


def weather_cooldown(interaction: discord.Interaction) -> app_commands.Cooldown | None:
    """Dynamic cooldown - None for mods/owners, 5 min for everyone else."""
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

def fuzzy_match(query: str, choices: List[str], limit: int = 25) -> List[str]:
    """Fuzzy match query against choices."""
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
    """Convert Celsius to Fahrenheit."""
    return (celsius * 9/5) + 32


def get_wind_direction(degrees: int) -> str:
    """Convert wind degrees to compass direction."""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    index = round(degrees / 22.5) % 16
    return directions[index]


# =============================================================================
# Weather View (Toggle Button)
# =============================================================================

class WeatherView(discord.ui.View):
    """View with toggle button for temperature unit."""

    def __init__(self, weather_data: dict, city: str, user_id: int):
        super().__init__(timeout=300)
        self.weather_data = weather_data
        self.city = city
        self.user_id = user_id
        self.is_celsius = True

    async def on_timeout(self):
        """Disable button on timeout."""
        for item in self.children:
            item.disabled = True
        log.tree("Weather View Expired", [
            ("City", self.city),
            ("User ID", str(self.user_id)),
        ], emoji="⏳")

    def build_embed(self) -> discord.Embed:
        """Build a beautiful weather embed."""
        data = self.weather_data
        main = data["main"]
        weather = data["weather"][0]
        wind = data["wind"]

        # Get icon based on weather condition
        icon_code = weather.get("icon", "01d")
        icon = WEATHER_ICONS.get(icon_code, "🌡️")

        # Temperature calculations
        temp_c = main["temp"]
        feels_c = main["feels_like"]
        temp_min_c = main["temp_min"]
        temp_max_c = main["temp_max"]

        if self.is_celsius:
            temp_display = f"{temp_c:.0f}°C"
            feels_display = f"{feels_c:.0f}°C"
            high_low = f"{temp_max_c:.0f}° / {temp_min_c:.0f}°"
            unit_label = "Celsius"
        else:
            temp_display = f"{celsius_to_fahrenheit(temp_c):.0f}°F"
            feels_display = f"{celsius_to_fahrenheit(feels_c):.0f}°F"
            high_low = f"{celsius_to_fahrenheit(temp_max_c):.0f}° / {celsius_to_fahrenheit(temp_min_c):.0f}°"
            unit_label = "Fahrenheit"

        # Build the main description with large temperature display
        description_parts = [
            f"## {icon} {temp_display}",
            f"**{weather['description'].title()}**",
            f"Feels like **{feels_display}** · High/Low: **{high_low}**",
        ]

        embed = discord.Embed(
            title=f"Weather in {self.city}",
            description="\n".join(description_parts),
            color=COLOR_WEATHER
        )

        # Set weather icon as thumbnail
        if icon_code:
            embed.set_thumbnail(url=f"https://openweathermap.org/img/wn/{icon_code}@4x.png")

        # Wind info
        wind_speed = wind["speed"]
        wind_dir = get_wind_direction(wind.get("deg", 0))
        wind_gust = wind.get("gust", None)
        wind_value = f"**{wind_speed} m/s** {wind_dir}"
        if wind_gust:
            wind_value += f"\nGusts: {wind_gust} m/s"

        # Atmospheric conditions
        humidity = main["humidity"]
        pressure = main["pressure"]
        visibility = data.get("visibility", 0) / 1000
        clouds = data.get("clouds", {}).get("all", 0)

        # Row 1: Wind, Humidity, Clouds
        embed.add_field(
            name="💨 Wind",
            value=wind_value,
            inline=True
        )
        embed.add_field(
            name="💧 Humidity",
            value=f"**{humidity}%**",
            inline=True
        )
        embed.add_field(
            name="☁️ Clouds",
            value=f"**{clouds}%**",
            inline=True
        )

        # Row 2: Pressure, Visibility, Sunrise/Sunset
        embed.add_field(
            name="📊 Pressure",
            value=f"**{pressure}** hPa",
            inline=True
        )
        embed.add_field(
            name="👁️ Visibility",
            value=f"**{visibility:.1f}** km",
            inline=True
        )

        # Sunrise/Sunset
        if "sys" in data:
            sunrise = data["sys"].get("sunrise")
            sunset = data["sys"].get("sunset")
            if sunrise and sunset:
                embed.add_field(
                    name="🌅 Sun",
                    value=f"↑ <t:{sunrise}:t>\n↓ <t:{sunset}:t>",
                    inline=True
                )

        # Standard footer
        set_footer(embed)

        return embed

    @discord.ui.button(label="°C / °F", style=discord.ButtonStyle.secondary, emoji="<:transfer:1455710226429902858>")
    async def toggle_unit(self, interaction: discord.Interaction, button: discord.ui.Button):
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

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = config.OPENWEATHER_API_KEY

    async def fetch_weather(self, city: str) -> Optional[dict]:
        """Fetch weather data from OpenWeatherMap API."""
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
    async def weather(self, interaction: discord.Interaction, city: str):
        """Get current weather for a city."""
        await interaction.response.defer()

        if not self.api_key:
            embed = discord.Embed(
                description="⚠️ Weather API is not configured.",
                color=0xf04747
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
                color=0xf04747
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
    async def city_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for city names with fuzzy matching."""
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
            except discord.HTTPException:
                pass

            log.tree("Weather Cooldown", [
                ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
                ("User ID", str(interaction.user.id)),
                ("Remaining", time_str),
            ], emoji="⏳")
            return

        log.tree("Weather Command Error", [
            ("User", f"{interaction.user.name} ({interaction.user.display_name})"),
            ("User ID", str(interaction.user.id)),
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
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(WeatherCog(bot))
    log.success("Loaded weather command")
