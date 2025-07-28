"""
Zerodha Kite Connect Broker Adapter
Implements BaseBroker interface for Zerodha trading platform
Supports F&O trading with proper error handling and authentication
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from kiteconnect import KiteConnect, KiteTicker
from app.brokers.base_broker import (
    BaseBroker, OrderRequest, OrderResponse, Position, Holding, MarketQuote,
    OrderType, OrderStatus, TransactionType, ProductType,
    BrokerException, AuthenticationError, OrderError, ConnectivityError
)

logger = logging.getLogger("zerodha_adapter")

class ZerodhaAdapter(BaseBroker):
    """
    Zerodha Kite Connect API implementation
    Handles authentication, order management, and data retrieval
    """
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)_key = credentials.get('api_key')
        self.api_secret = credentials.get('api_secret')
        self.access_token = credentials.get('access_token')
        self.client = KiteConnect(api_key=self.api_key)
        
        # Zerodha-specific mappings
        self.order_type_map = {
            OrderType.MARKET: self.client.ORDER_TYPE_MARKET,
            OrderType.LIMIT: self.client.ORDER_TYPE_LIMIT,
            OrderType.SL: self.client.ORDER_TYPE_SL,
            OrderType.SL_M: self.client.ORDER_TYPE_SLM
        }
        
        self.transaction_type_map = {
            TransactionType.BUY: self.client.TRANSACTION_TYPE_BUY,
            TransactionType.SELL: self.client.TRANSACTION_TYPE_SELL
        }
        
        self.product_type_map = {
            ProductType.MIS: self.client.PRODUCT_MIS,
            ProductType.NRML: self.client.PRODUCT_NRML,
            ProductType.CNC: self.client.PRODUCT_CNC
        }
        
        # Zerodha lot sizes (updated periodically)
        self.lot_sizes = {
            "NIFTY": 50,
            "BANKNIFTY": 15,
            "FINNIFTY": 40,
            "MIDCPNIFTY": 75,
            "SENSEX": 10,
            "BANKEX": 15
        }
    
    def authenticate(self) -> bool:
        """
        Authenticate with Zerodha Kite Connect
        Uses access_token if available, otherwise requires login flow
        """
        try:
            if self.access_token:
                self.client.set_access_token(self.access_token)
                # Test authentication by getting profile
                profile = self.client.profile()
                if profile:
                    self.is_authenticated = True
                    self.session_token = self.access_token
                    logger.info(f"Authenticated successfully for user: {profile.get('user_name')}")
                    return True
            
            logger.error("No valid access token provided")
            return False
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"Zerodha authentication failed: {e}")
    
    def get_profile(self) -> Dict[str, Any]:
        """Get user profile from Zerodha"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            profile = self.client.profile()
            return {
                "user_id": profile.get("user_id"),
                "user_name": profile.get("user_name"),
                "email": profile.get("email"),
                "broker": "zerodha",
                "exchanges": profile.get("exchanges", [])
            }
        except Exception as e:
            logger.error(f"Failed to get profile: {e}")
            raise BrokerException(f"Profile fetch failed: {e}")
    
    def get_margins(self) -> Dict[str, float]:
        """Get margin information from Zerodha"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            margins = self.client.margins()
            equity = margins.get("equity", {})
            
            return {
                "available_cash": float(equity.get("available", {}).get("cash", 0)),
                "used_margin": float(equity.get("utilised", {}).get("debits", 0)),
                "total_margin": float(equity.get("net", 0)),
                "opening_balance": float(equity.get("available", {}).get("opening_balance", 0))
            }
        except Exception as e:
            logger.error(f"Failed to get margins: {e}")
            raise BrokerException(f"Margin fetch failed: {e}")
    
    def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """Place order with Zerodha"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Map order parameters to Zerodha format
            params = {
                "exchange": self._get_exchange(order_request.symbol),
                "tradingsymbol": order_request.symbol,
                "transaction_type": self.transaction_type_map[order_request.transaction_type],
                "quantity": order_request.quantity,
                "product": self.product_type_map[order_request.product_type],
                "order_type": self.order_type_map[order_request.order_type],
                "validity": order_request.validity,
                "disclosed_quantity": order_request.disclosed_quantity
            }
            
            # Add price for limit orders
            if order_request.order_type in [OrderType.LIMIT, OrderType.SL]:
                params["price"] = order_request.price
            
            # Add trigger price for stop loss orders
            if order_request.order_type in [OrderType.SL, OrderType.SL_M]:
                params["trigger_price"] = order_request.trigger_price
            
            # Add tag if provided
            if order_request.tag:
                params["tag"] = order_request.tag
            
            response = self.client.place_order(**params)
            order_id = response.get("order_id")
            
            logger.info(f"Order placed successfully: {order_id}")
            
            return OrderResponse(
                order_id=str(order_id),
                status=OrderStatus.PENDING,
                message="Order placed successfully",
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            raise OrderError(f"Failed to place order: {e}")
    
    def modify_order(self, order_id: str, **kwargs) -> OrderResponse:
        """Modify existing order"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Prepare modification parameters
            params = {"order_id": order_id}
            
            # Map common modification parameters
            if "quantity" in kwargs:
                params["quantity"] = kwargs["quantity"]
            if "price" in kwargs:
                params["price"] = kwargs["price"]
            if "trigger_price" in kwargs:
                params["trigger_price"] = kwargs["trigger_price"]
            if "order_type" in kwargs:
                params["order_type"] = self.order_type_map[kwargs["order_type"]]
            
            response = self.client.modify_order(**params)
            
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.PENDING,
                message="Order modified successfully",
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Order modification failed: {e}")
            raise OrderError(f"Failed to modify order: {e}")
    
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel existing order"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            response = self.client.cancel_order(order_id=order_id)
            
            return OrderResponse(
                order_id=order_id,
                status=OrderStatus.CANCELLED,
                message="Order cancelled successfully", 
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            raise OrderError(f"Failed to cancel order: {e}")
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get status of specific order"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            orders = self.client.order_history(order_id=order_id)
            if orders:
                latest_order = orders[-1]  # Get latest status
                return {
                    "order_id": latest_order.get("order_id"),
                    "status": latest_order.get("status"),
                    "transaction_type": latest_order.get("transaction_type"),
                    "quantity": latest_order.get("quantity"),
                    "filled_quantity": latest_order.get("filled_quantity"),
                    "price": latest_order.get("price"),
                    "average_price": latest_order.get("average_price"),
                    "order_timestamp": latest_order.get("order_timestamp")
                }
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            raise BrokerException(f"Order status fetch failed: {e}")
    
    def get_orderbook(self) -> List[Dict[str, Any]]:
        """Get all orders for the day"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            orders = self.client.orders()
            return orders or []
            
        except Exception as e:
            logger.error(f"Failed to get orderbook: {e}")
            raise BrokerException(f"Orderbook fetch failed: {e}")
    
    def get_positions(self) -> List[Position]:
        """Get current positions"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            positions_data = self.client.positions()
            positions = []
            
            for pos_type in ["net", "day"]:
                for pos in positions_data.get(pos_type, []):
                    if pos["quantity"] != 0:  # Only active positions
                        positions.append(Position(
                            symbol=pos["tradingsymbol"],
                            quantity=pos["quantity"],
                            average_price=pos["average_price"],
                            last_price=pos["last_price"],
                            pnl=pos["pnl"],
                            product_type=ProductType(pos["product"].upper())
                        ))
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise BrokerException(f"Positions fetch failed: {e}")
    
    def get_holdings(self) -> List[Holding]:
        """Get holdings/investments"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            holdings_data = self.client.holdings()
            holdings = []
            
            for holding in holdings_data:
                if holding["quantity"] > 0:
                    holdings.append(Holding(
                        symbol=holding["tradingsymbol"],
                        quantity=holding["quantity"],
                        average_price=holding["average_price"],
                        last_price=holding["last_price"],
                        pnl=holding["pnl"]
                    ))
            
            return holdings
            
        except Exception as e:
            logger.error(f"Failed to get holdings: {e}")
            raise BrokerException(f"Holdings fetch failed: {e}")
    
    def get_quote(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        """Get live market quotes"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Prepare instruments list for Zerodha
            instruments = []
            for symbol in symbols:
                exchange = self._get_exchange(symbol)
                instruments.append(f"{exchange}:{symbol}")
            
            quotes_data = self.client.quote(instruments)
            quotes = {}
            
            for instrument, data in quotes_data.items():
                symbol = instrument.split(":")[-1]
                quotes[symbol] = MarketQuote(
                    symbol=symbol,
                    last_price=data["last_price"],
                    bid_price=data["depth"]["buy"][0]["price"] if data["depth"]["buy"] else 0.0,
                    ask_price=data["depth"]["sell"][0]["price"] if data["depth"]["sell"] else 0.0,
                    volume=data["volume"],
                    timestamp=datetime.now()
                )
            
            return quotes
            
        except Exception as e:
            logger.error(f"Failed to get quotes: {e}")
            raise BrokerException(f"Quote fetch failed: {e}")
    
    def get_historical_data(self, symbol: str, from_date: datetime, 
                          to_date: datetime, interval: str) -> List[Dict[str, Any]]:
        """Get historical OHLCV data"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Get instrument token for the symbol
            instrument_token = self._get_instrument_token(symbol)
            
            historical_data = self.client.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
            
            return historical_data or []
            
        except Exception as e:
            logger.error(f"Failed to get historical data: {e}")
            raise BrokerException(f"Historical data fetch failed: {e}")
    
    def search_instruments(self, query: str) -> List[Dict[str, Any]]:
        """Search for tradeable instruments"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Zerodha doesn't have direct search API, so we'll filter from instruments
            instruments = self.client.instruments()
            results = []
            
            query_lower = query.lower()
            for instrument in instruments:
                if (query_lower in instrument["name"].lower() or 
                    query_lower in instrument["tradingsymbol"].lower()):
                    results.append({
                        "symbol": instrument["tradingsymbol"],
                        "name": instrument["name"],
                        "exchange": instrument["exchange"],
                        "instrument_type": instrument["instrument_type"],
                        "lot_size": instrument["lot_size"]
                    })
                    
                    if len(results) >= 50:  # Limit results
                        break
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search instruments: {e}")
            raise BrokerException(f"Instrument search failed: {e}")
    
    def calculate_lot_size(self, symbol: str) -> int:
        """Get lot size for a symbol"""
        try:
            # Extract base symbol
            base_symbol = symbol.split("FUT")[0].split("CE")[0].split("PE")[0]
            return self.lot_sizes.get(base_symbol, 1)
        except:
            return 1
    
    def _get_exchange(self, symbol: str) -> str:
        """Determine exchange for a symbol"""
        if any(idx in symbol for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY"]):
            return "NFO"
        elif "SENSEX" in symbol or "BANKEX" in symbol:
            return "BFO" 
        else:
            return "NSE"
    
    def _get_instrument_token(self, symbol: str) -> str:
        """Get instrument token for a symbol (simplified)"""
        # In a real implementation, this would lookup from instruments master
        # For now, return the symbol itself
        return symbol
    
    def get_login_url(self) -> str:
        """Get Zerodha login URL for authentication"""
        return self.client.login_url()
    
    def generate_session(self, request_token: str) -> str:
        """Generate access token from request token"""
        try:
            data = self.client.generate_session(request_token, api_secret=self.api_secret)
            access_token = data.get("access_token")
            self.access_token = access_token
            return access_token
        except Exception as e:
            logger.error(f"Session generation failed: {e}")
            raise AuthenticationError(f"Failed to generate session: {e}")

# Export the adapter class
__all__ = ['ZerodhaAdapter']
