"""
SyriaBot - API Error System
===========================

Centralized error codes and exception handling for consistent API responses.

Author: حَـــــنَّـــــا
Server: discord.gg/syria
"""

from enum import Enum
from typing import Any, Dict, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
)


# =============================================================================
# Error Codes
# =============================================================================

class ErrorCode(str, Enum):
    """
    Centralized error codes for the API.

    Format: CATEGORY_SPECIFIC_ERROR

    Categories:
    - AUTH: Authentication errors
    - USER: User-related errors
    - XP: XP system errors
    - VALIDATION: Input validation errors
    - RATE_LIMIT: Rate limiting errors
    - SERVER: Server-side errors
    """

    # Authentication errors (401, 403)
    AUTH_INVALID_KEY = "AUTH_INVALID_KEY"
    AUTH_MISSING_KEY = "AUTH_MISSING_KEY"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_INSUFFICIENT_PERMISSIONS"

    # User errors (404, 400)
    USER_NOT_FOUND = "USER_NOT_FOUND"
    USER_INVALID_ID = "USER_INVALID_ID"

    # XP errors (400)
    XP_INVALID_AMOUNT = "XP_INVALID_AMOUNT"
    XP_UPDATE_FAILED = "XP_UPDATE_FAILED"

    # Bot errors (503)
    BOT_NOT_INITIALIZED = "BOT_NOT_INITIALIZED"

    # Validation errors (400, 422)
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_INVALID_ID = "VALIDATION_INVALID_ID"
    VALIDATION_MISSING_FIELD = "VALIDATION_MISSING_FIELD"
    VALIDATION_INVALID_FORMAT = "VALIDATION_INVALID_FORMAT"

    # Rate limit errors (429)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Server errors (500)
    SERVER_ERROR = "SERVER_ERROR"
    SERVER_DATABASE_ERROR = "SERVER_DATABASE_ERROR"
    SERVER_DISCORD_ERROR = "SERVER_DISCORD_ERROR"

    # WebSocket errors
    WS_CONNECTION_FAILED = "WS_CONNECTION_FAILED"
    WS_INVALID_MESSAGE = "WS_INVALID_MESSAGE"


# =============================================================================
# Error Messages
# =============================================================================

ERROR_MESSAGES: Dict[ErrorCode, str] = {
    # Auth
    ErrorCode.AUTH_INVALID_KEY: "Invalid API key",
    ErrorCode.AUTH_MISSING_KEY: "API key is required",
    ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS: "Insufficient permissions for this action",

    # Users
    ErrorCode.USER_NOT_FOUND: "User not found",
    ErrorCode.USER_INVALID_ID: "Invalid user ID format",

    # XP
    ErrorCode.XP_INVALID_AMOUNT: "Invalid XP amount",
    ErrorCode.XP_UPDATE_FAILED: "Failed to update XP",

    # Bot
    ErrorCode.BOT_NOT_INITIALIZED: "Bot is not initialized",

    # Validation
    ErrorCode.VALIDATION_FAILED: "Request validation failed",
    ErrorCode.VALIDATION_INVALID_ID: "Invalid ID format",
    ErrorCode.VALIDATION_MISSING_FIELD: "Required field is missing",
    ErrorCode.VALIDATION_INVALID_FORMAT: "Invalid data format",

    # Rate limiting
    ErrorCode.RATE_LIMIT_EXCEEDED: "Too many requests, please slow down",

    # Server
    ErrorCode.SERVER_ERROR: "An internal server error occurred",
    ErrorCode.SERVER_DATABASE_ERROR: "A database error occurred",
    ErrorCode.SERVER_DISCORD_ERROR: "Failed to communicate with Discord",

    # WebSocket
    ErrorCode.WS_CONNECTION_FAILED: "WebSocket connection failed",
    ErrorCode.WS_INVALID_MESSAGE: "Invalid WebSocket message format",
}


# =============================================================================
# Default Status Codes
# =============================================================================

ERROR_STATUS_CODES: Dict[ErrorCode, int] = {
    # Auth - 401/403
    ErrorCode.AUTH_INVALID_KEY: HTTP_401_UNAUTHORIZED,
    ErrorCode.AUTH_MISSING_KEY: HTTP_401_UNAUTHORIZED,
    ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS: HTTP_403_FORBIDDEN,

    # Users - 404/400
    ErrorCode.USER_NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.USER_INVALID_ID: HTTP_400_BAD_REQUEST,

    # XP - 400
    ErrorCode.XP_INVALID_AMOUNT: HTTP_400_BAD_REQUEST,
    ErrorCode.XP_UPDATE_FAILED: HTTP_500_INTERNAL_SERVER_ERROR,

    # Bot - 503
    ErrorCode.BOT_NOT_INITIALIZED: 503,

    # Validation - 400/422
    ErrorCode.VALIDATION_FAILED: HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.VALIDATION_INVALID_ID: HTTP_400_BAD_REQUEST,
    ErrorCode.VALIDATION_MISSING_FIELD: HTTP_422_UNPROCESSABLE_ENTITY,
    ErrorCode.VALIDATION_INVALID_FORMAT: HTTP_400_BAD_REQUEST,

    # Rate limit - 429
    ErrorCode.RATE_LIMIT_EXCEEDED: HTTP_429_TOO_MANY_REQUESTS,

    # Server - 500
    ErrorCode.SERVER_ERROR: HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.SERVER_DATABASE_ERROR: HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.SERVER_DISCORD_ERROR: HTTP_500_INTERNAL_SERVER_ERROR,

    # WebSocket - 400
    ErrorCode.WS_CONNECTION_FAILED: HTTP_400_BAD_REQUEST,
    ErrorCode.WS_INVALID_MESSAGE: HTTP_400_BAD_REQUEST,
}


# =============================================================================
# API Error Exception
# =============================================================================

class APIError(HTTPException):
    """
    Custom API exception with error codes.

    Usage:
        raise APIError(ErrorCode.USER_NOT_FOUND)
        raise APIError(ErrorCode.VALIDATION_FAILED, details={"field": "user_id"})
        raise APIError(ErrorCode.AUTH_MISSING_KEY, headers={"WWW-Authenticate": "ApiKey"})
    """

    def __init__(
        self,
        code: ErrorCode,
        status_code: Optional[int] = None,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.error_code = code
        self.error_message = message or ERROR_MESSAGES.get(code, "An error occurred")
        self.error_details = details

        # Use default status code if not provided
        if status_code is None:
            status_code = ERROR_STATUS_CODES.get(code, HTTP_400_BAD_REQUEST)

        super().__init__(
            status_code=status_code,
            detail={
                "success": False,
                "error_code": code.value,
                "message": self.error_message,
                "details": details,
            },
            headers=headers,
        )


# =============================================================================
# Helper Functions
# =============================================================================

def error_response(
    code: ErrorCode,
    status_code: Optional[int] = None,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """
    Create a JSON error response without raising an exception.

    Useful for returning errors in exception handlers.
    """
    if status_code is None:
        status_code = ERROR_STATUS_CODES.get(code, HTTP_400_BAD_REQUEST)

    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error_code": code.value,
            "message": message or ERROR_MESSAGES.get(code, "An error occurred"),
            "details": details,
        },
    )


def not_found(resource: str = "User") -> APIError:
    """Shorthand for 404 errors."""
    return APIError(ErrorCode.USER_NOT_FOUND, message=f"{resource} not found")


def forbidden(message: Optional[str] = None) -> APIError:
    """Shorthand for 403 errors."""
    return APIError(
        ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
        message=message,
    )


def bad_request(
    code: ErrorCode = ErrorCode.VALIDATION_FAILED,
    details: Optional[Dict[str, Any]] = None,
) -> APIError:
    """Shorthand for 400 errors."""
    return APIError(code, details=details)


__all__ = [
    "ErrorCode",
    "ERROR_MESSAGES",
    "ERROR_STATUS_CODES",
    "APIError",
    "error_response",
    "not_found",
    "forbidden",
    "bad_request",
]
