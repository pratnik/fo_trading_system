"""
Abstract Base Broker Interface for F&O Trading System
All broker adapters (Zerodha, Angel One, Fyers, etc.) must implement this interface
Ensures consistent API across different brokers for seamless switching
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger("broker")

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN" 
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class ProductType(str, Enum):
    MIS = "MIS"  # Intraday
    NRML = "NRML"  # Normal/Carryforward
    CNC = "CNC"  # Cash and Carry

@dataclass
class Order
    quantity: int
    price: float
    order_type: OrderType
    transaction_type: TransactionType
    product_type: ProductType = ProductType.MIS
    validity: str = "DAY"
    disclosed_quantity: int = 0
    trigger_price: float = 0.0
    tag: Optional[str] = None

@dataclass
class OrderResponse:
    """Standard order response structure"""
    order_id: str
    status: OrderStatus
    message: str
    timestamp: datetime
    
@dataclass
class Position:
    """Standard position structure"""
    symbol: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    product_type: ProductType

@dataclass
class Holding:
    """Standard holdings structure"""
    symbol: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float

@dataclass
class MarketQuote:
    """Standard market quote structure"""
    symbol: str
    last_price: float
    bid_price: float
    ask_price: float
    volume: int
    timestamp: datetime

class BaseBroker(ABC):
    """
    Abstract base class for all broker implementations
    Defines the standard interface for trading operations
    """
    
    def __init__(self, credentials: Dict[str, Any]):
        self.credentials = credentials
        self.is_authenticated = False
        self.session_token = None
        self.client = None
        
    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with broker API using provided credentials
        Returns: True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_profile(self) -> Dict[str, Any]:
        """
        Get user profile information
        Returns: Dictionary containing user profile data
        """
        pass
    
    @abstractmethod
    def get_margins(self) -> Dict[str, float]:
        """
        Get margin information
        Returns: Dictionary with available cash, used margin, etc.
        """
        pass
    
    @abstractmethod
    def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """
        Place a new order
        Args: OrderRequest object with order details
        Returns: OrderResponse with order ID and status
        """
        pass
    
    @abstractmethod
    def modify_order(self, order_id: str, **kwargs) -> OrderResponse:
        """
        Modify an existing order
        Args: order_id and fields to modify
        Returns: OrderResponse with updated status
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> OrderResponse:
        """
        Cancel an existing order
        Args: order_id to cancel
        Returns: OrderResponse with cancellation status
        """
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Get status of a specific order
        Args: order_id to check
        Returns: Dictionary with order details and current status
        """
        pass
    
    @abstractmethod
    def get_orderbook(self) -> List[Dict[str, Any]]:
        """
        Get all orders for the day
        Returns: List of order dictionaries
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Position]:
        """
        Get current positions
        Returns: List of Position objects
        """
        pass
    
    @abstractmethod
    def get_holdings(self) -> List[Holding]:
        """
        Get holdings/investments
        Returns: List of Holding objects  
        """
        pass
    
    @abstractmethod
    def get_quote(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        """
        Get live market quotes for symbols
        Args: List of instrument symbols
        Returns: Dictionary mapping symbols to MarketQuote objects
        """
        pass
    
    @abstractmethod
    def get_historical_data(self, symbol: str, from_date: datetime, 
                          to_date: datetime, interval: str) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV data
        Args: symbol, date range, interval (minute, day, etc.)
        Returns: List of OHLCV dictionaries
        """
        pass
    
    @abstractmethod
    def search_instruments(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for tradeable instruments
        Args: Search query string
        Returns: List of matching instruments
        """
        pass
    
    # Health check and connection management
    def health_check(self) -> Dict[str, Any]:
        """
        Check broker API health and connectivity
        Returns: Dictionary with health status
        """
        try:
            if not self.is_authenticated:
                return {"status": "error", "message": "Not authenticated"}
            
            # Try to get profile as a basic connectivity test
            profile = self.get_profile()
            if profile:
                return {"status": "healthy", "message": "Connection OK", "timestamp": datetime.now()}
            else:
                return {"status": "warning", "message": "Profile fetch failed"}
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def disconnect(self):
        """Clean up and disconnect from broker"""
        self.is_authenticated = False
        self.session_token = None
        self.client = None
    
    # Helper methods for order management
    def place_bracket_order(self, main_order: OrderRequest, 
                          stop_loss: float, target: float) -> List[OrderResponse]:
        """
        Place bracket order (main + SL + target)
        This is a convenience method that may be overridden by specific brokers
        """
        responses = []
        
        # Place main order
        main_response = self.place_order(main_order)
        responses.append(main_response)
        
        if main_response.status == OrderStatus.COMPLETE:
            # Place stop loss
            sl_order = OrderRequest(
                symbol=main_order.symbol,
                quantity=main_order.quantity,
                price=stop_loss,
                order_type=OrderType.SL,
                transaction_type=TransactionType.SELL if main_order.transaction_type == TransactionType.BUY else TransactionType.BUY,
                product_type=main_order.product_type
            )
            responses.append(self.place_order(sl_order))
            
            # Place target order  
            target_order = OrderRequest(
                symbol=main_order.symbol,
                quantity=main_order.quantity,
                price=target,
                order_type=OrderType.LIMIT,
                transaction_type=TransactionType.SELL if main_order.transaction_type == TransactionType.BUY else TransactionType.BUY,
                product_type=main_order.product_type
            )
            responses.append(self.place_order(target_order))
        
        return responses
    
    def calculate_lot_size(self, symbol: str) -> int:
        """
        Get lot size for a symbol
        Should be overridden by broker-specific implementations
        """
        # Default lot sizes (will be overridden by specific brokers)
        lot_sizes = {
            "NIFTY": 50,
            "BANKNIFTY": 15, 
            "FINNIFTY": 40,
            "MIDCPNIFTY": 75
        }
        
        base_symbol = symbol.split("FUT")[0].split("CE")[0].split("PE")[0]
        return lot_sizes.get(base_symbol, 1)

# Exception classes for broker operations
class BrokerException(Exception):
    """Base exception for broker operations"""
    pass

class AuthenticationError(BrokerException):
    """Raised when authentication fails"""
    pass

class OrderError(BrokerException):
    """Raised when order operations fail"""
    pass

class ConnectivityError(BrokerException):
    """Raised when broker connectivity fails"""
    pass

class InsufficientFundsError(BrokerException):
    """Raised when insufficient funds for trade"""
    pass

# Export all classes and enums
__all__ = [
    'BaseBroker',
    'OrderRequest', 
    'OrderResponse',
    'Position',
    'Holding', 
    'MarketQuote',
    'OrderType',
    'OrderStatus', 
    'TransactionType',
    'ProductType',
    'BrokerException',
    'AuthenticationError',
    'OrderError', 
    'ConnectivityError',
    'InsufficientFundsError'
]
