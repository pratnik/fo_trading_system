"""
Complete Configuration File for F&O Trading System
- Database and security settings
- Trading system parameters
- Risk management configuration
- Strategy settings
- Broker configurations
- Event calendar settings
- Notification settings
- System limits and monitoring
"""

import os
from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import time
from pydantic import BaseSettings, Field
import logging

logger = logging.getLogger("config")

class StrategyType(str, Enum):
    """Available strategy types in the system"""
    IRON_CONDOR = "IRON_CONDOR"
    BUTTERFLY_SPREAD = "BUTTERFLY_SPREAD"  
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    HEDGED_STRANGLE = "HEDGED_STRANGLE"
    DIRECTIONAL_FUTURES = "DIRECTIONAL_FUTURES"
    JADE_LIZARD = "JADE_LIZARD"
    RATIO_SPREADS = "RATIO_SPREADS"
    BROKEN_WING_BUTTERFLY = "BROKEN_WING_BUTTERFLY"

class BrokerType(str, Enum):
    """Supported broker types"""
    ZERODHA = "ZERODHA"
    FYERS = "FYERS"
    ANGELONE = "ANGELONE"
    UPSTOX = "UPSTOX"
    IIFL = "IIFL"

class MarketDataProvider(str, Enum):
    """Market data providers"""
    ZERODHA_KITE = "ZERODHA_KITE"
    FYERS_API = "FYERS_API"
    NSE_DIRECT = "NSE_DIRECT"
    YAHOO_FINANCE = "YAHOO_FINANCE"

class Settings(BaseSettings):
    """Main application settings"""
    
    # ==================== CORE APPLICATION SETTINGS ====================
    
    # Environment
    DEBUG: bool = Field(default=False, env="DEBUG")
    TESTING: bool = Field(default=False, env="TESTING")
    ENVIRONMENT: str = Field(default="production", env="ENVIRONMENT")
    
    # Security
    SECRET_KEY: str = Field(..., env="SECRET_KEY")
    ENCRYPTION_KEY: str = Field(..., env="ENCRYPTION_KEY")
    
    # Server Configuration
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8501, env="PORT")
    
    # ==================== DATABASE CONFIGURATION ====================
    
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_POOL_SIZE: int = Field(default=10, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")
    DATABASE_POOL_RECYCLE: int = Field(default=300, env="DATABASE_POOL_RECYCLE")
    DATABASE_ECHO: bool = Field(default=False, env="DATABASE_ECHO")
    
    # ==================== REDIS CONFIGURATION ====================
    
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    REDIS_DECODE_RESPONSES: bool = Field(default=True, env="REDIS_DECODE_RESPONSES")
    REDIS_SOCKET_TIMEOUT: int = Field(default=30, env="REDIS_SOCKET_TIMEOUT")
    
    # ==================== TRADING SYSTEM CONFIGURATION ====================
    
    # Capital and Position Limits
    DEFAULT_CAPITAL: float = Field(default=200000.0, env="DEFAULT_CAPITAL")
    MAX_LOTS_PER_STRATEGY: int = Field(default=10, env="MAX_LOTS_PER_STRATEGY")
    MAX_STRATEGIES_ACTIVE: int = Field(default=5, env="MAX_STRATEGIES_ACTIVE")
    MAX_DAILY_LOSS_PCT: float = Field(default=0.05, env="MAX_DAILY_LOSS_PCT")  # 5%
    
    # Risk Management Thresholds
    DANGER_ZONE_WARNING: float = Field(default=1.0, env="DANGER_ZONE_WARNING")    # 1.0%
    DANGER_ZONE_RISK: float = Field(default=1.25, env="DANGER_ZONE_RISK")        # 1.25%
    DANGER_ZONE_EXIT: float = Field(default=1.5, env="DANGER_ZONE_EXIT")         # 1.5%
    
    # VIX Thresholds
    VIX_THRESHOLD: float = Field(default=25.0, env="VIX_THRESHOLD")
    MIN_VIX_FOR_ENTRY: float = Field(default=12.0, env="MIN_VIX_FOR_ENTRY")
    MAX_VIX_FOR_ENTRY: float = Field(default=45.0, env="MAX_VIX_FOR_ENTRY")
    
    # Time Controls
    ENTRY_CUTOFF_TIME: str = Field(default="11:00", env="ENTRY_CUTOFF_TIME")
    MANDATORY_EXIT_TIME: str = Field(default="15:10", env="MANDATORY_EXIT_TIME")
    MARKET_OPEN_TIME: str = Field(default="09:15", env="MARKET_OPEN_TIME")
    MARKET_CLOSE_TIME: str = Field(default="15:30", env="MARKET_CLOSE_TIME")
    
    # ==================== INSTRUMENT CONFIGURATION ====================
    
    # Allowed instruments (high liquidity only)
    ALLOWED_INSTRUMENTS: List[str] = Field(
        default=["NIFTY", "BANKNIFTY"], 
        env="ALLOWED_INSTRUMENTS"
    )
    
    # Blocked instruments (low liquidity)
    BLOCKED_INSTRUMENTS: List[str] = Field(
        default=["FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"], 
        env="BLOCKED_INSTRUMENTS"
    )
    
    # Instrument specifications
    NIFTY_LOT_SIZE: int = Field(default=50, env="NIFTY_LOT_SIZE")
    BANKNIFTY_LOT_SIZE: int = Field(default=15, env="BANKNIFTY_LOT_SIZE")
    
    # ==================== STRATEGY-SPECIFIC CONFIGURATIONS ====================
    
    # Iron Condor Settings
    IRON_CONDOR_MIN_VIX: float = Field(default=12.0, env="IRON_CONDOR_MIN_VIX")
    IRON_CONDOR_MAX_VIX: float = Field(default=25.0, env="IRON_CONDOR_MAX_VIX")
    IRON_CONDOR_WIN_RATE: float = Field(default=85.0, env="IRON_CONDOR_WIN_RATE")
    IRON_CONDOR_SL_PER_LOT: float = Field(default=1500.0, env="IRON_CONDOR_SL_PER_LOT")
    IRON_CONDOR_TP_PER_LOT: float = Field(default=3000.0, env="IRON_CONDOR_TP_PER_LOT")
    
    # Butterfly Spread Settings
    BUTTERFLY_MIN_VIX: float = Field(default=12.0, env="BUTTERFLY_MIN_VIX")
    BUTTERFLY_MAX_VIX: float = Field(default=22.0, env="BUTTERFLY_MAX_VIX")
    BUTTERFLY_WIN_RATE: float = Field(default=80.0, env="BUTTERFLY_WIN_RATE")
    BUTTERFLY_SL_PER_LOT: float = Field(default=1200.0, env="BUTTERFLY_SL_PER_LOT")
    BUTTERFLY_TP_PER_LOT: float = Field(default=2500.0, env="BUTTERFLY_TP_PER_LOT")
    
    # Calendar Spread Settings
    CALENDAR_MIN_VIX: float = Field(default=12.0, env="CALENDAR_MIN_VIX")
    CALENDAR_MAX_VIX: float = Field(default=28.0, env="CALENDAR_MAX_VIX")
    CALENDAR_WIN_RATE: float = Field(default=80.0, env="CALENDAR_WIN_RATE")
    CALENDAR_SL_PER_LOT: float = Field(default=1500.0, env="CALENDAR_SL_PER_LOT")
    CALENDAR_TP_PER_LOT: float = Field(default=3000.0, env="CALENDAR_TP_PER_LOT")
    
    # Hedged Strangle Settings
    HEDGED_STRANGLE_MIN_VIX: float = Field(default=20.0, env="HEDGED_STRANGLE_MIN_VIX")
    HEDGED_STRANGLE_MAX_VIX: float = Field(default=45.0, env="HEDGED_STRANGLE_MAX_VIX")
    HEDGED_STRANGLE_WIN_RATE: float = Field(default=75.0, env="HEDGED_STRANGLE_WIN_RATE")
    HEDGED_STRANGLE_SL_PER_LOT: float = Field(default=2500.0, env="HEDGED_STRANGLE_SL_PER_LOT")
    HEDGED_STRANGLE_TP_PER_LOT: float = Field(default=5000.0, env="HEDGED_STRANGLE_TP_PER_LOT")
    
    # Directional Futures Settings
    DIRECTIONAL_FUTURES_MIN_VIX: float = Field(default=15.0, env="DIRECTIONAL_FUTURES_MIN_VIX")
    DIRECTIONAL_FUTURES_MAX_VIX: float = Field(default=40.0, env="DIRECTIONAL_FUTURES_MAX_VIX")
    DIRECTIONAL_FUTURES_WIN_RATE: float = Field(default=65.0, env="DIRECTIONAL_FUTURES_WIN_RATE")
    DIRECTIONAL_FUTURES_SL_PER_LOT: float = Field(default=3000.0, env="DIRECTIONAL_FUTURES_SL_PER_LOT")
    DIRECTIONAL_FUTURES_TP_PER_LOT: float = Field(default=6000.0, env="DIRECTIONAL_FUTURES_TP_PER_LOT")
    
    # Jade Lizard Settings
    JADE_LIZARD_MIN_VIX: float = Field(default=22.0, env="JADE_LIZARD_MIN_VIX")
    JADE_LIZARD_MAX_VIX: float = Field(default=40.0, env="JADE_LIZARD_MAX_VIX")
    JADE_LIZARD_WIN_RATE: float = Field(default=78.0, env="JADE_LIZARD_WIN_RATE")
    JADE_LIZARD_SL_PER_LOT: float = Field(default=2500.0, env="JADE_LIZARD_SL_PER_LOT")
    JADE_LIZARD_TP_PER_LOT: float = Field(default=4500.0, env="JADE_LIZARD_TP_PER_LOT")
    
    # Ratio Spreads Settings
    RATIO_SPREADS_MIN_VIX: float = Field(default=18.0, env="RATIO_SPREADS_MIN_VIX")
    RATIO_SPREADS_MAX_VIX: float = Field(default=35.0, env="RATIO_SPREADS_MAX_VIX")
    RATIO_SPREADS_WIN_RATE: float = Field(default=70.0, env="RATIO_SPREADS_WIN_RATE")
    RATIO_SPREADS_SL_PER_LOT: float = Field(default=2200.0, env="RATIO_SPREADS_SL_PER_LOT")
    RATIO_SPREADS_TP_PER_LOT: float = Field(default=4500.0, env="RATIO_SPREADS_TP_PER_LOT")
    
    # Broken Wing Butterfly Settings
    BROKEN_WING_MIN_VIX: float = Field(default=18.0, env="BROKEN_WING_MIN_VIX")
    BROKEN_WING_MAX_VIX: float = Field(default=32.0, env="BROKEN_WING_MAX_VIX")
    BROKEN_WING_WIN_RATE: float = Field(default=75.0, env="BROKEN_WING_WIN_RATE")
    BROKEN_WING_SL_PER_LOT: float = Field(default=2000.0, env="BROKEN_WING_SL_PER_LOT")
    BROKEN_WING_TP_PER_LOT: float = Field(default=4500.0, env="BROKEN_WING_TP_PER_LOT")
    
    # ==================== BROKER CONFIGURATION ====================
    
    # Default broker
    DEFAULT_BROKER: BrokerType = Field(default=BrokerType.ZERODHA, env="DEFAULT_BROKER")
    
    # Zerodha Configuration
    ZERODHA_API_KEY: Optional[str] = Field(default=None, env="ZERODHA_API_KEY")
    ZERODHA_API_SECRET: Optional[str] = Field(default=None, env="ZERODHA_API_SECRET")
    ZERODHA_REQUEST_TOKEN: Optional[str] = Field(default=None, env="ZERODHA_REQUEST_TOKEN")
    ZERODHA_ACCESS_TOKEN: Optional[str] = Field(default=None, env="ZERODHA_ACCESS_TOKEN")
    
    # Fyers Configuration
    FYERS_API_ID: Optional[str] = Field(default=None, env="FYERS_API_ID")
    FYERS_API_SECRET: Optional[str] = Field(default=None, env="FYERS_API_SECRET")
    FYERS_ACCESS_TOKEN: Optional[str] = Field(default=None, env="FYERS_ACCESS_TOKEN")
    
    # AngelOne Configuration
    ANGELONE_API_KEY: Optional[str] = Field(default=None, env="ANGELONE_API_KEY")
    ANGELONE_CLIENT_ID: Optional[str] = Field(default=None, env="ANGELONE_CLIENT_ID")
    ANGELONE_PASSWORD: Optional[str] = Field(default=None, env="ANGELONE_PASSWORD")
    ANGELONE_TOTP_KEY: Optional[str] = Field(default=None, env="ANGELONE_TOTP_KEY")
    
    # Broker Connection Settings
    BROKER_TIMEOUT: int = Field(default=30, env="BROKER_TIMEOUT")
    BROKER_RETRY_ATTEMPTS: int = Field(default=3, env="BROKER_RETRY_ATTEMPTS")
    BROKER_RETRY_DELAY: int = Field(default=5, env="BROKER_RETRY_DELAY")
    
    # ==================== MARKET DATA CONFIGURATION ====================
    
    DEFAULT_DATA_PROVIDER: MarketDataProvider = Field(
        default=MarketDataProvider.ZERODHA_KITE, 
        env="DEFAULT_DATA_PROVIDER"
    )
    
    # Data refresh intervals (seconds)
    MARKET_DATA_REFRESH_INTERVAL: int = Field(default=60, env="MARKET_DATA_REFRESH_INTERVAL")
    VIX_DATA_REFRESH_INTERVAL: int = Field(default=300, env="VIX_DATA_REFRESH_INTERVAL")
    OPTION_CHAIN_REFRESH_INTERVAL: int = Field(default=30, env="OPTION_CHAIN_REFRESH_INTERVAL")
    
    # Data sources
    NSE_DATA_URL: str = Field(default="https://www.nseindia.com", env="NSE_DATA_URL")
    VIX_DATA_URL: str = Field(default="https://www.nseindia.com/api/equity-meta", env="VIX_DATA_URL")
    
    # ==================== NOTIFICATION CONFIGURATION ====================
    
    # WhatsApp (Gupshup API)
    GUPSHUP_API_KEY: Optional[str] = Field(default=None, env="GUPSHUP_API_KEY")
    GUPSHUP_APP_NAME: Optional[str] = Field(default=None, env="GUPSHUP_APP_NAME")
    ADMIN_PHONE_NUMBER: Optional[str] = Field(default=None, env="ADMIN_PHONE_NUMBER")
    
    # Email Configuration
    SMTP_SERVER: Optional[str] = Field(default=None, env="SMTP_SERVER")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USERNAME: Optional[str] = Field(default=None, env="SMTP_USERNAME")
    SMTP_PASSWORD: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    ADMIN_EMAIL: Optional[str] = Field(default=None, env="ADMIN_EMAIL")
    
    # Notification Settings
    SEND_ENTRY_NOTIFICATIONS: bool = Field(default=True, env="SEND_ENTRY_NOTIFICATIONS")
    SEND_EXIT_NOTIFICATIONS: bool = Field(default=True, env="SEND_EXIT_NOTIFICATIONS")
    SEND_RISK_ALERTS: bool = Field(default=True, env="SEND_RISK_ALERTS")
    SEND_DAILY_SUMMARY: bool = Field(default=True, env="SEND_DAILY_SUMMARY")
    
    # ==================== EVENT CALENDAR CONFIGURATION ====================
    
    # Calendar Settings
    CALENDAR_AUTO_REFRESH: bool = Field(default=True, env="CALENDAR_AUTO_REFRESH")
    CALENDAR_REFRESH_INTERVAL_HOURS: int = Field(default=24, env="CALENDAR_REFRESH_INTERVAL_HOURS")
    NSE_HOLIDAY_API_TIMEOUT: int = Field(default=10, env="NSE_HOLIDAY_API_TIMEOUT")
    CALENDAR_FALLBACK_MODE: bool = Field(default=True, env="CALENDAR_FALLBACK_MODE")
    
    # Holiday API endpoints (backup URLs)
    NSE_HOLIDAY_ENDPOINTS: List[str] = Field(
        default=[
            "https://static.nseindia.com/api/holiday-master",
            "https://www.nseindia.com/api/holiday-master", 
            "https://nseindia.com/api/holiday-master"
        ],
        env="NSE_HOLIDAY_ENDPOINTS"
    )
    
    # ==================== MONITORING AND LOGGING ====================
    
    # Logging Configuration
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE_PATH: str = Field(default="logs/fo_trading.log", env="LOG_FILE_PATH")
    LOG_MAX_BYTES: int = Field(default=10485760, env="LOG_MAX_BYTES")  # 10MB
    LOG_BACKUP_COUNT: int = Field(default=5, env="LOG_BACKUP_COUNT")
    
    # Monitoring Settings
    HEALTH_CHECK_INTERVAL: int = Field(default=60, env="HEALTH_CHECK_INTERVAL")  # seconds
    PERFORMANCE_MONITORING: bool = Field(default=True, env="PERFORMANCE_MONITORING")
    AUDIT_LOGGING: bool = Field(default=True, env="AUDIT_LOGGING")
    
    # ==================== CELERY CONFIGURATION ====================
    
    # Celery Broker
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/0", env="CELERY_RESULT_BACKEND")
    
    # Celery Settings
    CELERY_TIMEZONE: str = Field(default="Asia/Kolkata", env="CELERY_TIMEZONE")
    CELERY_ENABLE_UTC: bool = Field(default=False, env="CELERY_ENABLE_UTC")
    CELERY_TASK_SERIALIZER: str = Field(default="json", env="CELERY_TASK_SERIALIZER")
    CELERY_RESULT_SERIALIZER: str = Field(default="json", env="CELERY_RESULT_SERIALIZER")
    
    # ==================== PERFORMANCE TUNING ====================
    
    # Database Connection Pool
    DB_POOL_PRE_PING: bool = Field(default=True, env="DB_POOL_PRE_PING")
    DB_POOL_RECYCLE_TIME: int = Field(default=300, env="DB_POOL_RECYCLE_TIME")
    
    # Caching
    ENABLE_CACHING: bool = Field(default=True, env="ENABLE_CACHING")
    CACHE_TTL_SECONDS: int = Field(default=300, env="CACHE_TTL_SECONDS")
    
    # API Rate Limiting
    API_RATE_LIMIT_PER_MINUTE: int = Field(default=100, env="API_RATE_LIMIT_PER_MINUTE")
    BROKER_API_RATE_LIMIT: int = Field(default=50, env="BROKER_API_RATE_LIMIT")
    
    # ==================== DEVELOPMENT SETTINGS ====================
    
    # Development Mode
    ENABLE_DEBUG_MODE: bool = Field(default=False, env="ENABLE_DEBUG_MODE")
    MOCK_BROKER_RESPONSES: bool = Field(default=False, env="MOCK_BROKER_RESPONSES")
    SIMULATION_MODE: bool = Field(default=False, env="SIMULATION_MODE")
    
    # Testing
    TEST_DATABASE_URL: Optional[str] = Field(default=None, env="TEST_DATABASE_URL")
    TEST_REDIS_URL: Optional[str] = Field(default=None, env="TEST_REDIS_URL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

# Create global settings instance
settings = Settings()

# ==================== INSTRUMENT CONFIGURATIONS ====================

def get_instrument_config(symbol: str) -> Dict[str, Any]:
    """Get configuration for specific instrument"""
    instrument_configs = {
        "NIFTY": {
            "lot_size": settings.NIFTY_LOT_SIZE,
            "tick_price": 0.05,
            "strike_difference": 50,
            "liquid": True,
            "segment": "NFO",
            "expiry_day": "Thursday",
            "weekly_expiry": True,
            "monthly_expiry": True
        },
        "BANKNIFTY": {
            "lot_size": settings.BANKNIFTY_LOT_SIZE,
            "tick_price": 0.05,
            "strike_difference": 100,
            "liquid": True,
            "segment": "NFO",
            "expiry_day": "Thursday",
            "weekly_expiry": True,
            "monthly_expiry": True
        },
        "FINNIFTY": {
            "lot_size": 40,
            "tick_price": 0.05,
            "strike_difference": 50,
            "liquid": False,  # Blocked instrument
            "segment": "NFO",
            "expiry_day": "Tuesday",
            "weekly_expiry": True,
            "monthly_expiry": True
        },
        "MIDCPNIFTY": {
            "lot_size": 75,
            "tick_price": 0.05,
            "strike_difference": 25,
            "liquid": False,  # Blocked instrument
            "segment": "NFO",
            "expiry_day": "Monday",
            "weekly_expiry": True,
            "monthly_expiry": True
        }
    }
    
    return instrument_configs.get(symbol, {})

def validate_instrument_liquidity(symbol: str) -> bool:
    """Validate if instrument has sufficient liquidity for trading"""
    if symbol in settings.BLOCKED_INSTRUMENTS:
        logger.warning(f"Instrument {symbol} is blocked due to low liquidity")
        return False
    
    if symbol not in settings.ALLOWED_INSTRUMENTS:
        logger.warning(f"Instrument {symbol} not in allowed instruments list")
        return False
    
    config = get_instrument_config(symbol)
    return config.get("liquid", False)

def get_strategy_config(strategy_name: str) -> Dict[str, Any]:
    """Get configuration for specific strategy"""
    strategy_configs = {
        StrategyType.IRON_CONDOR: {
            "min_vix": settings.IRON_CONDOR_MIN_VIX,
            "max_vix": settings.IRON_CONDOR_MAX_VIX,
            "target_win_rate": settings.IRON_CONDOR_WIN_RATE,
            "sl_per_lot": settings.IRON_CONDOR_SL_PER_LOT,
            "tp_per_lot": settings.IRON_CONDOR_TP_PER_LOT,
            "legs": 4,
            "market_outlook": "NEUTRAL",
            "is_hedged": True
        },
        StrategyType.BUTTERFLY_SPREAD: {
            "min_vix": settings.BUTTERFLY_MIN_VIX,
            "max_vix": settings.BUTTERFLY_MAX_VIX,
            "target_win_rate": settings.BUTTERFLY_WIN_RATE,
            "sl_per_lot": settings.BUTTERFLY_SL_PER_LOT,
            "tp_per_lot": settings.BUTTERFLY_TP_PER_LOT,
            "legs": 4,
            "market_outlook": "NEUTRAL",
            "is_hedged": True
        },
        StrategyType.CALENDAR_SPREAD: {
            "min_vix": settings.CALENDAR_MIN_VIX,
            "max_vix": settings.CALENDAR_MAX_VIX,
            "target_win_rate": settings.CALENDAR_WIN_RATE,
            "sl_per_lot": settings.CALENDAR_SL_PER_LOT,
            "tp_per_lot": settings.CALENDAR_TP_PER_LOT,
            "legs": 4,
            "market_outlook": "NEUTRAL",
            "is_hedged": True
        },
        StrategyType.HEDGED_STRANGLE: {
            "min_vix": settings.HEDGED_STRANGLE_MIN_VIX,
            "max_vix": settings.HEDGED_STRANGLE_MAX_VIX,
            "target_win_rate": settings.HEDGED_STRANGLE_WIN_RATE,
            "sl_per_lot": settings.HEDGED_STRANGLE_SL_PER_LOT,
            "tp_per_lot": settings.HEDGED_STRANGLE_TP_PER_LOT,
            "legs": 4,
            "market_outlook": "NEUTRAL",
            "is_hedged": True
        },
        StrategyType.DIRECTIONAL_FUTURES: {
            "min_vix": settings.DIRECTIONAL_FUTURES_MIN_VIX,
            "max_vix": settings.DIRECTIONAL_FUTURES_MAX_VIX,
            "target_win_rate": settings.DIRECTIONAL_FUTURES_WIN_RATE,
            "sl_per_lot": settings.DIRECTIONAL_FUTURES_SL_PER_LOT,
            "tp_per_lot": settings.DIRECTIONAL_FUTURES_TP_PER_LOT,
            "legs": 2,
            "market_outlook": "DIRECTIONAL",
            "is_hedged": True
        },
        StrategyType.JADE_LIZARD: {
            "min_vix": settings.JADE_LIZARD_MIN_VIX,
            "max_vix": settings.JADE_LIZARD_MAX_VIX,
            "target_win_rate": settings.JADE_LIZARD_WIN_RATE,
            "sl_per_lot": settings.JADE_LIZARD_SL_PER_LOT,
            "tp_per_lot": settings.JADE_LIZARD_TP_PER_LOT,
            "legs": 3,
            "market_outlook": "NEUTRAL_BULLISH",
            "is_hedged": True
        },
        StrategyType.RATIO_SPREADS: {
            "min_vix": settings.RATIO_SPREADS_MIN_VIX,
            "max_vix": settings.RATIO_SPREADS_MAX_VIX,
            "target_win_rate": settings.RATIO_SPREADS_WIN_RATE,
            "sl_per_lot": settings.RATIO_SPREADS_SL_PER_LOT,
            "tp_per_lot": settings.RATIO_SPREADS_TP_PER_LOT,
            "legs": 3,
            "market_outlook": "DIRECTIONAL",
            "is_hedged": True
        },
        StrategyType.BROKEN_WING_BUTTERFLY: {
            "min_vix": settings.BROKEN_WING_MIN_VIX,
            "max_vix": settings.BROKEN_WING_MAX_VIX,
            "target_win_rate": settings.BROKEN_WING_WIN_RATE,
            "sl_per_lot": settings.BROKEN_WING_SL_PER_LOT,
            "tp_per_lot": settings.BROKEN_WING_TP_PER_LOT,
            "legs": 4,
            "market_outlook": "DIRECTIONAL",
            "is_hedged": True
        }
    }
    
    return strategy_configs.get(strategy_name, {})

# ==================== UTILITY FUNCTIONS ====================

def get_time_from_string(time_str: str) -> time:
    """Convert time string to time object"""
    try:
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    except ValueError:
        logger.error(f"Invalid time format: {time_str}")
        return time(9, 15)  # Default to market open

def get_danger_zone_limits() -> Dict[str, float]:
    """Get danger zone limits"""
    return {
        "warning": settings.DANGER_ZONE_WARNING,
        "risk": settings.DANGER_ZONE_RISK,
        "exit": settings.DANGER_ZONE_EXIT
    }

def get_trading_times() -> Dict[str, time]:
    """Get trading time configurations"""
    return {
        "market_open": get_time_from_string(settings.MARKET_OPEN_TIME),
        "market_close": get_time_from_string(settings.MARKET_CLOSE_TIME),
        "entry_cutoff": get_time_from_string(settings.ENTRY_CUTOFF_TIME),
        "mandatory_exit": get_time_from_string(settings.MANDATORY_EXIT_TIME)
    }

def is_production_environment() -> bool:
    """Check if running in production environment"""
    return settings.ENVIRONMENT.lower() == "production" and not settings.DEBUG

def get_broker_config(broker_type: str) -> Dict[str, Any]:
    """Get broker-specific configuration"""
    broker_configs = {
        BrokerType.ZERODHA: {
            "api_key": settings.ZERODHA_API_KEY,
            "api_secret": settings.ZERODHA_API_SECRET,
            "access_token": settings.ZERODHA_ACCESS_TOKEN,
            "base_url": "https://api.kite.trade",
            "login_url": "https://kite.zerodha.com/connect/login"
        },
        BrokerType.FYERS: {
            "api_id": settings.FYERS_API_ID,
            "api_secret": settings.FYERS_API_SECRET,
            "access_token": settings.FYERS_ACCESS_TOKEN,
            "base_url": "https://api.fyers.in/api/v2",
            "login_url": "https://api.fyers.in/api/v2/generate-authcode"
        },
        BrokerType.ANGELONE: {
            "api_key": settings.ANGELONE_API_KEY,
            "client_id": settings.ANGELONE_CLIENT_ID,
            "password": settings.ANGELONE_PASSWORD,
            "totp_key": settings.ANGELONE_TOTP_KEY,
            "base_url": "https://apiconnect.angelbroking.com",
            "login_url": "https://smartapi.angelbroking.com/publisher-login"
        }
    }
    
    return broker_configs.get(broker_type, {})

def validate_configuration() -> List[str]:
    """Validate configuration and return list of issues"""
    issues = []
    
    # Check required settings
    if not settings.SECRET_KEY:
        issues.append("SECRET_KEY is required")
    
    if not settings.ENCRYPTION_KEY:
        issues.append("ENCRYPTION_KEY is required")
    
    if not settings.DATABASE_URL:
        issues.append("DATABASE_URL is required")
    
    # Check capital limits
    if settings.DEFAULT_CAPITAL <= 0:
        issues.append("DEFAULT_CAPITAL must be positive")
    
    if settings.MAX_DAILY_LOSS_PCT <= 0 or settings.MAX_DAILY_LOSS_PCT >= 1:
        issues.append("MAX_DAILY_LOSS_PCT must be between 0 and 1")
    
    # Check danger zone limits
    if not (settings.DANGER_ZONE_WARNING < settings.DANGER_ZONE_RISK < settings.DANGER_ZONE_EXIT):
        issues.append("Danger zone limits must be in ascending order")
    
    # Check VIX thresholds
    if settings.MIN_VIX_FOR_ENTRY >= settings.MAX_VIX_FOR_ENTRY:
        issues.append("MIN_VIX_FOR_ENTRY must be less than MAX_VIX_FOR_ENTRY")
    
    # Check broker configuration if not in simulation mode
    if not settings.SIMULATION_MODE:
        broker_config = get_broker_config(settings.DEFAULT_BROKER)
        if not any(broker_config.values()):
            issues.append(f"Broker configuration incomplete for {settings.DEFAULT_BROKER}")
    
    return issues

# ==================== INITIALIZATION ====================

def initialize_configuration():
    """Initialize and validate configuration on startup"""
    logger.info("Initializing F&O trading system configuration...")
    
    # Validate configuration
    config_issues = validate_configuration()
    if config_issues:
        logger.error("Configuration validation failed:")
        for issue in config_issues:
            logger.error(f"  - {issue}")
        
        if is_production_environment():
            raise ValueError("Configuration validation failed in production environment")
    
    # Log key configuration
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Default Capital: ₹{settings.DEFAULT_CAPITAL:,.0f}")
    logger.info(f"Allowed Instruments: {settings.ALLOWED_INSTRUMENTS}")
    logger.info(f"Default Broker: {settings.DEFAULT_BROKER}")
    logger.info(f"Danger Zone Limits: {get_danger_zone_limits()}")
    
    logger.info("✅ Configuration initialized successfully")

# Auto-initialize on import
try:
    initialize_configuration()
except Exception as e:
    logger.error(f"Configuration initialization failed: {e}")
    if is_production_environment():
        raise

# Export main components
__all__ = [
    "settings",
    "StrategyType",
    "BrokerType", 
    "MarketDataProvider",
    "get_instrument_config",
    "validate_instrument_liquidity",
    "get_strategy_config",
    "get_danger_zone_limits",
    "get_trading_times",
    "get_broker_config",
    "is_production_environment",
    "validate_configuration",
    "initialize_configuration"
]
