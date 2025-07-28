"""
Database Models for F&O Trading System - Complete Version
- Comprehensive user and broker management
- Strategy and trade tracking with encryption
- Risk management and audit logging
- Event calendar integration
- Performance tracking and analytics
- Compatible with all 8 hedged strategies (Iron Condor, Butterfly, etc.)
"""

import logging
from datetime import datetime, date, time
from typing import Dict, List, Any, Optional
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Time,
    Text, JSON, ForeignKey, Index, UniqueConstraint, CheckConstraint,
    Enum, Numeric, BigInteger
)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

from app.db.base import Base
from app.db.encryption import EncryptedString, EncryptedJSON

logger = logging.getLogger("models")

# Enums for better type safety
class UserType(str, PyEnum):
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    VIEWER = "VIEWER"

class BrokerType(str, PyEnum):
    ZERODHA = "ZERODHA"
    ANGELONE = "ANGELONE"
    FYERS = "FYERS"
    UPSTOX = "UPSTOX"
    IIFL = "IIFL"

class StrategyType(str, PyEnum):
    IRON_CONDOR = "IRON_CONDOR"
    BUTTERFLY_SPREAD = "BUTTERFLY_SPREAD"
    CALENDAR_SPREAD = "CALENDAR_SPREAD"
    HEDGED_STRANGLE = "HEDGED_STRANGLE"
    DIRECTIONAL_FUTURES = "DIRECTIONAL_FUTURES"
    JADE_LIZARD = "JADE_LIZARD"
    RATIO_SPREADS = "RATIO_SPREADS"
    BROKEN_WING_BUTTERFLY = "BROKEN_WING_BUTTERFLY"

class InstrumentType(str, PyEnum):
    NIFTY = "NIFTY"
    BANKNIFTY = "BANKNIFTY"
    FINNIFTY = "FINNIFTY"
    MIDCPNIFTY = "MIDCPNIFTY"

class TradeStatus(str, PyEnum):
    PENDING = "PENDING"
    PARTIAL_FILLED = "PARTIAL_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class PositionStatus(str, PyEnum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    ASSIGNED = "ASSIGNED"

class OrderSide(str, PyEnum):
    BUY = "BUY"
    SELL = "SELL"

class OptionType(str, PyEnum):
    CE = "CE"  # Call European
    PE = "PE"  # Put European

class RiskLevel(str, PyEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

# Core Models
class User(Base):
    """User accounts and authentication"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone_number = Column(String(15), nullable=True)
    full_name = Column(String(255), nullable=False)
    user_type = Column(Enum(UserType), nullable=False, default=UserType.TRADER)
    
    # Security
    password_hash = Column(EncryptedString, nullable=True)  # Encrypted password
    api_token = Column(EncryptedString, nullable=True)      # Encrypted API token
    last_login = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    is_locked = Column(Boolean, default=False)
    
    # Profile
    is_active = Column(Boolean, default=True, nullable=False)
    email_verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)
    
    # Trading Settings (encrypted for security)
    trading_settings = Column(EncryptedJSON, nullable=True)  # Risk limits, preferences
    notification_settings = Column(JSON, nullable=True)      # Non-sensitive notifications
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    last_activity = Column(DateTime, default=datetime.now)
    
    # Relationships
    broker_accounts = relationship("BrokerAccount", back_populates="user", cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="user")
    positions = relationship("Position", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    
    # Indexes
    __table_args__ = (
        Index('idx_user_email_active', 'email', 'is_active'),
        Index('idx_user_type_active', 'user_type', 'is_active'),
    )
    
    def __repr__(self):
        return f"<User(username='{self.username}', type='{self.user_type}')>"

class BrokerAccount(Base):
    """Broker account credentials and configuration"""
    __tablename__ = "broker_accounts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Broker Information
    broker_name = Column(Enum(BrokerType), nullable=False)
    account_id = Column(String(100), nullable=False)
    account_name = Column(String(255), nullable=True)
    
    # Encrypted Credentials
    api_credentials = Column(EncryptedJSON, nullable=False)  # API key, secret, etc.
    access_token = Column(EncryptedString, nullable=True)    # Session token
    refresh_token = Column(EncryptedString, nullable=True)   # Refresh token
    
    # Configuration
    is_active = Column(Boolean, default=False, nullable=False)
    is_paper_trading = Column(Boolean, default=True, nullable=False)
    max_daily_loss = Column(Numeric(12, 2), nullable=True)
    max_position_size = Column(Integer, nullable=True)
    
    # Connection Status
    last_connected = Column(DateTime, nullable=True)
    connection_status = Column(String(50), default="DISCONNECTED")
    last_error = Column(Text, nullable=True)
    
    # Trading Limits (encrypted)
    trading_limits = Column(EncryptedJSON, nullable=True)  # Capital, risk limits
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="broker_accounts")
    trades = relationship("Trade", back_populates="broker_account")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('user_id', 'broker_name', 'account_id', name='uq_user_broker_account'),
        Index('idx_broker_active', 'broker_name', 'is_active'),
    )
    
    def __repr__(self):
        return f"<BrokerAccount(broker='{self.broker_name}', account='{self.account_id}')>"

class Strategy(Base):
    """Strategy definitions and configurations"""
    __tablename__ = "strategies"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Strategy Identity
    name = Column(Enum(StrategyType), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Strategy Characteristics
    legs = Column(Integer, nullable=False)  # Number of legs
    is_hedged = Column(Boolean, default=True, nullable=False)
    market_outlook = Column(String(50), nullable=True)  # NEUTRAL, BULLISH, BEARISH, etc.
    
    # Risk Parameters
    min_vix = Column(Float, nullable=True)
    max_vix = Column(Float, nullable=True)
    target_win_rate = Column(Float, nullable=True)
    
    # Configuration (encrypted for strategy secrets)
    configuration = Column(EncryptedJSON, nullable=True)  # Strategy-specific params
    
    # Performance Tracking
    is_active = Column(Boolean, default=True, nullable=False)
    is_eliminated = Column(Boolean, default=False, nullable=False)
    elimination_reason = Column(Text, nullable=True)
    elimination_date = Column(DateTime, nullable=True)
    
    # Statistics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    total_pnl = Column(Numeric(15, 2), default=0)
    last_trade_date = Column(Date, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # Relationships
    positions = relationship("Position", back_populates="strategy")
    strategy_stats = relationship("StrategyStats", back_populates="strategy", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_strategy_active', 'is_active', 'is_eliminated'),
        Index('idx_strategy_performance', 'total_trades', 'winning_trades'),
    )
    
    def __repr__(self):
        return f"<Strategy(name='{self.name}', active={self.is_active})>"

class Position(Base):
    """Trading positions - combines multiple trades into a strategy position"""
    __tablename__ = "positions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Position Identity
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)
    
    # Position Details
    symbol = Column(Enum(InstrumentType), nullable=False)
    expiry_date = Column(Date, nullable=False)
    lot_count = Column(Integer, nullable=False, default=1)
    
    # Position Structure (encrypted for security)
    position_legs = Column(EncryptedJSON, nullable=False)  # Detailed leg information
    
    # Entry Information
    entry_time = Column(DateTime, default=datetime.now, nullable=False)
    entry_spot_price = Column(Numeric(10, 2), nullable=True)
    entry_vix = Column(Float, nullable=True)
    entry_premium_paid = Column(Numeric(12, 2), default=0)
    entry_premium_received = Column(Numeric(12, 2), default=0)
    net_entry_cost = Column(Numeric(12, 2), default=0)
    
    # Current Status
    status = Column(Enum(PositionStatus), default=PositionStatus.ACTIVE, nullable=False)
    current_mtm = Column(Numeric(12, 2), default=0)
    current_spot_price = Column(Numeric(10, 2), nullable=True)
    last_mtm_update = Column(DateTime, nullable=True)
    
    # Exit Information
    exit_time = Column(DateTime, nullable=True)
    exit_spot_price = Column(Numeric(10, 2), nullable=True)
    exit_reason = Column(String(100), nullable=True)
    final_pnl = Column(Numeric(12, 2), nullable=True)
    
    # Risk Management
    stop_loss = Column(Numeric(12, 2), nullable=True)
    take_profit = Column(Numeric(12, 2), nullable=True)
    max_loss_hit = Column(Numeric(12, 2), default=0)
    max_profit_hit = Column(Numeric(12, 2), default=0)
    
    # Tracking
    days_held = Column(Integer, default=0)
    risk_alerts_count = Column(Integer, default=0)
    
    # Metadata (encrypted for sensitive info)
    position_metadata = Column(EncryptedJSON, nullable=True)  # Additional position data
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="positions")
    strategy = relationship("Strategy", back_populates="positions")
    trades = relationship("Trade", back_populates="position")
    risk_events = relationship("RiskEvent", back_populates="position", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_position_active', 'status', 'symbol'),
        Index('idx_position_strategy', 'strategy_id', 'status'),
        Index('idx_position_expiry', 'expiry_date', 'status'),
        Index('idx_position_user_active', 'user_id', 'status'),
    )
    
    def __repr__(self):
        return f"<Position(symbol='{self.symbol}', strategy='{self.strategy.name}', status='{self.status}')>"

class Trade(Base):
    """Individual trade executions - legs of a position"""
    __tablename__ = "trades"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Trade Identity
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    position_id = Column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=True)
    broker_account_id = Column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False)
    
    # Order Details
    order_id = Column(String(100), nullable=True)  # Broker order ID
    exchange_order_id = Column(String(100), nullable=True)  # Exchange order ID
    
    # Instrument Details
    symbol = Column(String(50), nullable=False)  # Full symbol (e.g., NIFTY25JUL22000CE)
    underlying = Column(Enum(InstrumentType), nullable=False)
    option_type = Column(Enum(OptionType), nullable=True)  # CE/PE for options
    strike_price = Column(Numeric(10, 2), nullable=True)
    expiry_date = Column(Date, nullable=False)
    
    # Trade Execution
    side = Column(Enum(OrderSide), nullable=False)  # BUY/SELL
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(10, 4), nullable=False)
    filled_quantity = Column(Integer, default=0)
    average_price = Column(Numeric(10, 4), nullable=True)
    
    # Status and Timing
    status = Column(Enum(TradeStatus), default=TradeStatus.PENDING, nullable=False)
    order_time = Column(DateTime, default=datetime.now, nullable=False)
    fill_time = Column(DateTime, nullable=True)
    
    # Financial Details
    brokerage = Column(Numeric(8, 2), default=0)
    taxes = Column(Numeric(8, 2), default=0)
    total_charges = Column(Numeric(8, 2), default=0)
    net_amount = Column(Numeric(12, 2), nullable=True)
    
    # Trade Classification
    leg_type = Column(String(50), nullable=True)  # main_leg, hedge_leg, etc.
    is_hedge = Column(Boolean, default=False)
    execution_priority = Column(Integer, default=1)  # For hedge-first execution
    
    # Market Conditions at Trade
    spot_price_at_trade = Column(Numeric(10, 2), nullable=True)
    vix_at_trade = Column(Float, nullable=True)
    
    # Error Handling
    rejection_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="trades")
    position = relationship("Position", back_populates="trades")
    broker_account = relationship("BrokerAccount", back_populates="trades")
    
    # Indexes
    __table_args__ = (
        Index('idx_trade_symbol_date', 'symbol', 'expiry_date'),
        Index('idx_trade_status_time', 'status', 'order_time'),
        Index('idx_trade_position', 'position_id', 'status'),
        Index('idx_trade_broker_order', 'broker_account_id', 'order_id'),
    )
    
    def __repr__(self):
        return f"<Trade(symbol='{self.symbol}', side='{self.side}', qty={self.quantity}, status='{self.status}')>"

class MarketData(Base):
    """Market data storage for analysis and backtesting"""
    __tablename__ = "market_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Data Identity
    symbol = Column(Enum(InstrumentType), nullable=False)
    data_date = Column(Date, nullable=False)
    data_time = Column(Time, nullable=True)  # For intraday data
    
    # Price Data
    open_price = Column(Numeric(10, 2), nullable=True)
    high_price = Column(Numeric(10, 2), nullable=True)
    low_price = Column(Numeric(10, 2), nullable=True)
    close_price = Column(Numeric(10, 2), nullable=True)
    volume = Column(BigInteger, nullable=True)
    
    # Volatility Data
    vix = Column(Float, nullable=True)
    implied_volatility = Column(Float, nullable=True)
    historical_volatility = Column(Float, nullable=True)
    
    # Technical Indicators
    technical_indicators = Column(JSON, nullable=True)  # RSI, MACD, etc.
    
    # Market Sentiment
    trend_strength = Column(Float, nullable=True)
    market_sentiment = Column(String(20), nullable=True)  # BULLISH, BEARISH, NEUTRAL
    
    # Additional Data
    additional_data = Column(JSON, nullable=True)  # FII/DII data, etc.
    data_source = Column(String(50), nullable=False)  # NSE, Yahoo, etc.
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    
    # Indexes
    __table_args__ = (
        UniqueConstraint('symbol', 'data_date', 'data_time', name='uq_market_data'),
        Index('idx_market_data_date', 'symbol', 'data_date'),
        Index('idx_market_data_vix', 'vix', 'data_date'),
    )
    
    def __repr__(self):
        return f"<MarketData(symbol='{self.symbol}', date='{self.data_date}', close={self.close_price})>"

class StrategyStats(Base):
    """Strategy performance statistics and analytics"""
    __tablename__ = "strategy_stats"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Strategy Reference
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)
    
    # Time Period
    stats_date = Column(Date, nullable=False)
    period_type = Column(String(20), nullable=False)  # DAILY, WEEKLY, MONTHLY
    
    # Performance Metrics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0)
    
    # P&L Statistics
    total_pnl = Column(Numeric(15, 2), default=0)
    avg_profit = Column(Numeric(12, 2), default=0)
    avg_loss = Column(Numeric(12, 2), default=0)
    max_profit = Column(Numeric(12, 2), default=0)
    max_loss = Column(Numeric(12, 2), default=0)
    
    # Risk Metrics
    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown = Column(Numeric(12, 2), default=0)
    profit_factor = Column(Float, nullable=True)
    
    # Execution Metrics
    avg_days_held = Column(Float, default=0)
    success_rate_by_vix = Column(JSON, nullable=True)  # Performance by VIX ranges
    
    # Strategy Health Score (0-100)
    health_score = Column(Float, default=50)
    elimination_score = Column(Float, default=0)  # Higher = more likely to eliminate
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # Relationships
    strategy = relationship("Strategy", back_populates="strategy_stats")
    
    # Indexes
    __table_args__ = (
        UniqueConstraint('strategy_id', 'stats_date', 'period_type', name='uq_strategy_stats'),
        Index('idx_strategy_stats_date', 'strategy_id', 'stats_date'),
        Index('idx_strategy_stats_performance', 'win_rate', 'total_pnl'),
    )
    
    def __repr__(self):
        return f"<StrategyStats(strategy='{self.strategy.name}', date='{self.stats_date}', win_rate={self.win_rate})>"

class RiskEvent(Base):
    """Risk management events and alerts"""
    __tablename__ = "risk_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Event Reference
    position_id = Column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Event Details
    event_type = Column(String(50), nullable=False)  # SL_HIT, TP_ACHIEVED, etc.
    risk_level = Column(Enum(RiskLevel), nullable=False)
    
    # Event Data
    trigger_value = Column(Numeric(12, 2), nullable=True)  # MTM value that triggered
    threshold_value = Column(Numeric(12, 2), nullable=True)  # Threshold that was breached
    
    # Actions Taken
    action_taken = Column(String(100), nullable=True)  # EXIT, ALERT, etc.
    auto_action = Column(Boolean, default=False)  # Was action automatic?
    
    # Event Details
    description = Column(Text, nullable=False)
    additional_data = Column(JSON, nullable=True)
    
    # Resolution
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    
    # Relationships
    position = relationship("Position", back_populates="risk_events")
    user = relationship("User")
    
    # Indexes
    __table_args__ = (
        Index('idx_risk_event_level', 'risk_level', 'created_at'),
        Index('idx_risk_event_position', 'position_id', 'event_type'),
        Index('idx_risk_event_user', 'user_id', 'is_resolved'),
    )
    
    def __repr__(self):
        return f"<RiskEvent(type='{self.event_type}', level='{self.risk_level}', resolved={self.is_resolved})>"

class AuditLog(Base):
    """Comprehensive audit logging for compliance and debugging"""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # User and Action
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    
    # Context
    resource_type = Column(String(50), nullable=True)  # Position, Trade, etc.
    resource_id = Column(String(100), nullable=True)
    
    # Details (encrypted for sensitive operations)
    details = Column(EncryptedJSON, nullable=True)  # Sensitive audit data
    public_details = Column(JSON, nullable=True)     # Non-sensitive details
    
    # Request Information
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    session_id = Column(String(100), nullable=True)
    
    # Result
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    
    # Indexes
    __table_args__ = (
        Index('idx_audit_user_action', 'user_id', 'action'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_time', 'created_at'),
        Index('idx_audit_ip', 'ip_address', 'created_at'),
    )
    
    def __repr__(self):
        return f"<AuditLog(action='{self.action}', user={self.user_id}, success={self.success})>"

class SystemSettings(Base):
    """System-wide configuration and settings"""
    __tablename__ = "system_settings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Setting Identity
    setting_key = Column(String(100), unique=True, nullable=False)
    setting_category = Column(String(50), nullable=True)  # RISK, TRADING, SYSTEM, etc.
    
    # Setting Value (encrypted for sensitive settings)
    setting_value = Column(EncryptedJSON, nullable=True)  # Sensitive settings
    public_value = Column(JSON, nullable=True)             # Non-sensitive settings
    
    # Metadata
    description = Column(Text, nullable=True)
    data_type = Column(String(20), nullable=True)  # STRING, INTEGER, FLOAT, etc.
    is_encrypted = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Validation
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    allowed_values = Column(JSON, nullable=True)  # For enum-like settings
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    last_modified_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_system_settings_category', 'setting_category', 'is_active'),
        Index('idx_system_settings_key', 'setting_key'),
    )
    
    def __repr__(self):
        return f"<SystemSettings(key='{self.setting_key}', category='{self.setting_category}')>"

class EventCalendar(Base):
    """Market events and holiday calendar"""
    __tablename__ = "event_calendar"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Event Details
    event_date = Column(Date, nullable=False)
    event_title = Column(String(200), nullable=False)
    event_type = Column(String(50), nullable=False)  # HOLIDAY, EXPIRY, ECONOMIC, etc.
    event_description = Column(Text, nullable=True)
    
    # Impact Assessment
    impact_level = Column(Enum(RiskLevel), default=RiskLevel.LOW)
    affected_instruments = Column(JSON, nullable=True)  # List of affected symbols
    trading_action = Column(String(50), nullable=True)  # NORMAL, AVOID_ENTRY, etc.
    
    # Event Source
    data_source = Column(String(50), nullable=False)  # NSE, RBI, MANUAL, etc.
    is_confirmed = Column(Boolean, default=True)
    
    # Metadata
    additional_data = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_event_calendar_date', 'event_date', 'event_type'),
        Index('idx_event_calendar_impact', 'impact_level', 'event_date'),
        UniqueConstraint('event_date', 'event_title', 'event_type', name='uq_event_calendar'),
    )
    
    def __repr__(self):
        return f"<EventCalendar(date='{self.event_date}', title='{self.event_title}', impact='{self.impact_level}')>"

class NotificationLog(Base):
    """Log of all notifications sent"""
    __tablename__ = "notification_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Notification Details
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notification_type = Column(String(50), nullable=False)  # WHATSAPP, EMAIL, SMS
    
    # Content
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    
    # Context
    related_resource_type = Column(String(50), nullable=True)  # Position, Trade, etc.
    related_resource_id = Column(String(100), nullable=True)
    
    # Delivery Status  
    status = Column(String(20), default="PENDING")  # PENDING, SENT, FAILED
    delivery_time = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # Priority and Urgency
    priority = Column(String(20), default="NORMAL")  # LOW, NORMAL, HIGH, URGENT
    is_urgent = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    
    # Relationships
    user = relationship("User")
    
    # Indexes
    __table_args__ = (
        Index('idx_notification_user_type', 'user_id', 'notification_type'),
        Index('idx_notification_status', 'status', 'created_at'),
        Index('idx_notification_urgent', 'is_urgent', 'status'),
    )
    
    def __repr__(self):
        return f"<NotificationLog(type='{self.notification_type}', status='{self.status}', title='{self.title[:50]}')>"

# Helper functions for model operations
def get_user_by_username(session, username: str) -> Optional[User]:
    """Get user by username"""
    return session.query(User).filter(User.username == username, User.is_active == True).first()

def get_active_positions(session, user_id: Optional[str] = None) -> List[Position]:
    """Get all active positions, optionally filtered by user"""
    query = session.query(Position).filter(Position.status == PositionStatus.ACTIVE)
    if user_id:
        query = query.filter(Position.user_id == user_id)
    return query.all()

def get_strategy_by_name(session, strategy_name: str) -> Optional[Strategy]:
    """Get strategy by name"""
    return session.query(Strategy).filter(
        Strategy.name == strategy_name,
        Strategy.is_active == True,
        Strategy.is_eliminated == False
    ).first()

def get_recent_trades(session, limit: int = 100) -> List[Trade]:
    """Get recent trades"""
    return session.query(Trade).order_by(Trade.created_at.desc()).limit(limit).all()

def get_system_setting(session, key: str, default_value: Any = None) -> Any:
    """Get system setting value"""
    setting = session.query(SystemSettings).filter(
        SystemSettings.setting_key == key,
        SystemSettings.is_active == True
    ).first()
    
    if setting:
        return setting.setting_value if setting.is_encrypted else setting.public_value
    return default_value

def create_audit_log(session, user_id: Optional[str], action: str, details: Dict[str, Any],
                    resource_type: Optional[str] = None, resource_id: Optional[str] = None,
                    ip_address: Optional[str] = None, success: bool = True) -> AuditLog:
    """Create audit log entry"""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        success=success
    )
    session.add(audit_log)
    return audit_log

# Export all models and helper functions
__all__ = [
    # Enums
    "UserType", "BrokerType", "StrategyType", "InstrumentType", 
    "TradeStatus", "PositionStatus", "OrderSide", "OptionType", "RiskLevel",
    
    # Models
    "User", "BrokerAccount", "Strategy", "Position", "Trade", "MarketData",
    "StrategyStats", "RiskEvent", "AuditLog", "SystemSettings", 
    "EventCalendar", "NotificationLog",
    
    # Helper Functions
    "get_user_by_username", "get_active_positions", "get_strategy_by_name",
    "get_recent_trades", "get_system_setting", "create_audit_log"
]
