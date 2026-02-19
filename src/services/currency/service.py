"""
SyriaBot - Currency Service
===========================

Integration with JawdatBot's casino currency API.
Allows SyriaBot to reward users with casino coins.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from typing import Optional, Tuple

import aiohttp

from src.core.config import config
from src.core.logger import logger


class CurrencyService:
    """
    Service for granting JawdatBot casino currency.

    DESIGN:
        Integrates with JawdatBot's economy system via REST API.
        Allows SyriaBot to reward users with casino coins for activities.
        Supports granting to wallet or bank with balance queries.
    """

    def __init__(self) -> None:
        """
        Initialize the currency service.

        Sets up state tracking. Actual API connection happens in setup().
        Requires JAWDAT_API_KEY environment variable to be enabled.
        """
        self._enabled: bool = False
        self._session: Optional[aiohttp.ClientSession] = None

    async def setup(self) -> None:
        """Initialize the currency service."""
        if not config.JAWDAT_API_KEY:
            logger.tree("Currency Service", [
                ("Status", "Disabled"),
                ("Reason", "Missing JAWDAT_API_KEY"),
            ], emoji="ℹ️")
            return

        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        )
        self._enabled = True

        logger.tree("Currency Service Ready", [
            ("API URL", config.JAWDAT_API_URL),
            ("Status", "Enabled"),
        ], emoji="💰")

    def is_enabled(self) -> bool:
        """Check if service is enabled."""
        return self._enabled

    async def grant(
        self,
        user_id: int,
        amount: int,
        reason: str = "",
        target: str = "wallet"
    ) -> Tuple[bool, str]:
        """
        Grant casino currency to a user.

        Args:
            user_id: Discord user ID
            amount: Amount to grant (1-10,000,000)
            reason: Reason for the grant (for logging)
            target: "wallet" or "bank"

        Returns:
            Tuple of (success, message)
        """
        if not self._enabled or not self._session:
            logger.tree("Currency Grant Skipped", [
                ("ID", str(user_id)),
                ("Reason", "Service not enabled"),
            ], emoji="ℹ️")
            return False, "Currency service not enabled"

        if amount < 1 or amount > 10_000_000:
            logger.tree("Currency Grant Validation Failed", [
                ("ID", str(user_id)),
                ("Amount", str(amount)),
                ("Reason", "Must be 1-10,000,000"),
            ], emoji="⚠️")
            return False, "Amount must be between 1 and 10,000,000"

        if target not in ("wallet", "bank"):
            logger.tree("Currency Grant Validation Failed", [
                ("ID", str(user_id)),
                ("Target", str(target)),
                ("Reason", "Must be 'wallet' or 'bank'"),
            ], emoji="⚠️")
            return False, "Target must be 'wallet' or 'bank'"

        try:
            async with self._session.post(
                f"{config.JAWDAT_API_URL}/api/jawdat/currency/grant",
                json={
                    "user_id": user_id,
                    "amount": amount,
                    "reason": reason or "SyriaBot reward",
                    "target": target,
                },
                headers={"X-API-Key": config.JAWDAT_API_KEY},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.tree("Currency Granted", [
                        ("ID", str(user_id)),
                        ("Target", target.title()),
                        ("Amount", f"+{amount:,}"),
                        ("New Balance", f"{data.get('new_balance', 0):,}"),
                        ("Reason", reason[:50] if reason else "SyriaBot reward"),
                    ], emoji="💰" if target == "wallet" else "🏦")
                    return True, f"Granted {amount:,} coins to {target}!"
                elif resp.status == 401:
                    logger.tree("Currency Grant Failed", [
                        ("ID", str(user_id)),
                        ("Reason", "Invalid API key"),
                    ], emoji="🔒")
                    return False, "API authentication failed"
                else:
                    error = await resp.text()
                    logger.tree("Currency Grant Failed", [
                        ("ID", str(user_id)),
                        ("Status", str(resp.status)),
                        ("Error", error[:50]),
                    ], emoji="❌")
                    return False, "Failed to grant currency"

        except aiohttp.ClientError as e:
            logger.tree("Currency Grant Error", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False, "Connection error"
        except Exception as e:
            logger.tree("Currency Grant Error", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return False, "Unexpected error"

    async def get_balance(self, user_id: int) -> Optional[int]:
        """
        Get a user's casino balance.

        Args:
            user_id: Discord user ID

        Returns:
            Balance or None if failed
        """
        if not self._enabled or not self._session:
            logger.tree("Currency Balance Check Skipped", [
                ("ID", str(user_id)),
                ("Reason", "Service not enabled"),
            ], emoji="ℹ️")
            return None

        try:
            async with self._session.get(
                f"{config.JAWDAT_API_URL}/api/jawdat/user/{user_id}",
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance = data.get("wallet", 0) + data.get("bank", 0)
                    logger.tree("Currency Balance Fetched", [
                        ("ID", str(user_id)),
                        ("Wallet", f"{data.get('wallet', 0):,}"),
                        ("Bank", f"{data.get('bank', 0):,}"),
                        ("Total", f"{balance:,}"),
                    ], emoji="💰")
                    return balance
                elif resp.status == 404:
                    logger.tree("Currency Balance Not Found", [
                        ("ID", str(user_id)),
                        ("Reason", "User has no economy data"),
                    ], emoji="ℹ️")
                    return None
                else:
                    logger.tree("Currency Balance Fetch Failed", [
                        ("ID", str(user_id)),
                        ("Status", str(resp.status)),
                    ], emoji="⚠️")
                    return None
        except aiohttp.ClientError as e:
            logger.tree("Currency Balance Error", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return None
        except Exception as e:
            logger.tree("Currency Balance Error", [
                ("ID", str(user_id)),
                ("Error", str(e)[:50]),
            ], emoji="❌")
            return None

    async def stop(self) -> None:
        """Stop the currency service."""
        if self._session:
            await self._session.close()
            self._session = None
        self._enabled = False
        logger.tree("Currency Service Stopped", [], emoji="🛑")
