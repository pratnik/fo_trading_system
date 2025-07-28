"""
Fyers API v3 Broker Adapter
Implements BaseBroker interface for Fyers trading platform
Supports F&O trading with proper error handling and authentication
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from fyers_apiv3 import fyersModel
from app.brokers.base_broker import (
    BaseBroker, OrderRequest, OrderResponse, Position, Holding, MarketQuote,
    OrderType, OrderStatus, TransactionType, ProductType,
    BrokerException, AuthenticationError, OrderError, ConnectivityError
)

logger = logging.getLogger("fyers_adapter")

class FyersAdapter(BaseBroker):
    """
    Fyers API v3 implementation
    Handles authentication, order management, and data retrieval
    """
    
    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.client# API ID from Fyers
        self.secret_key = credentials.get('secret_key')  # Secret key from Fyers
        self.access_token = credentials.get('access_token')
        self.redirect_uri = credentials.get('redirect_uri', 'https://trade.fyers.in/api-login')
        
        # Initialize Fyers client
        if self.access_token:
            self.client = fyersModel.FyersModel(
                token=self.access_token,
                is_async=False,
                client_id=self.client_id,
                log_path=""
            )
        else:
            self.client = None
        
        # Fyers-specific mappings
        self.order_type_map = {
            OrderType.MARKET: 2,      # Market order
            OrderType.LIMIT: 1,       # Limit order
            OrderType.SL: 3,          # Stop Loss order
            OrderType.SL_M: 4         # Stop Loss Market order
        }
        
        self.transaction_type_map = {
            TransactionType.BUY: 1,   # Buy
            TransactionType.SELL: -1  # Sell
        }
        
        self.product_type_map = {
            ProductType.MIS: "INTRADAY",     # Intraday
            ProductType.NRML: "MARGIN",      # Normal/Margin
            ProductType.CNC: "CNC"           # Cash and Carry
        }
        
        # Fyers lot sizes (will be updated from live data)
        self.lot_sizes = {
            "NIFTY": 50,
            "BANKNIFTY": 15,
            "FINNIFTY": 40,
            "MIDCPNIFTY": 75,
            "SENSEX": 10,
            "BANKEX": 15
        }
        
        # Fyers error code mappings
        self.error_codes = {
            -22: "Authentication failed",
            -413: "Auth code expired",
            -50: "Invalid input parameters",
            -96: "General API error",
            -300: "Missing data",
            -10: "Symbol not found"
        }
    
    def authenticate(self) -> bool:
        """
        Authenticate with Fyers API v3
        Uses access_token if available
        """
        try:
            if self.access_token and self.client_id:
                self.client = fyersModel.FyersModel(
                    token=self.access_token,
                    is_async=False,
                    client_id=self.client_id,
                    log_path=""
                )
                
                # Test authentication by getting profile
                profile_response = self.client.get_profile()
                
                if profile_response.get('s') == 'ok':
                    self.is_authenticated = True
                    self.session_token = self.access_token
                    logger.info(f"Authenticated successfully for client: {self.client_id}")
                    return True
                else:
                    logger.error(f"Authentication failed: {profile_response}")
                    return False
            
            logger.error("No valid access token or client ID provided")
            return False
            
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"Fyers authentication failed: {e}")
    
    def get_profile(self) -> Dict[str, Any]:
        """Get user profile from Fyers"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            response = self.client.get_profile()
            
            if response.get('s') == 'ok':
                data = response.get('data', {})
                return {
                    "user_id": data.get("fy_id"),
                    "user_name": data.get("name"),
                    "email": data.get("email_id"),
                    "broker": "fyers",
                    "mobile": data.get("mobile_number"),
                    "exchanges": data.get("exchange", [])
                }
            else:
                raise BrokerException(f"Profile fetch failed: {response.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Failed to get profile: {e}")
            raise BrokerException(f"Profile fetch failed: {e}")
    
    def get_margins(self) -> Dict[str, float]:
        """Get margin information from Fyers"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            response = self.client.funds()
            
            if response.get('s') == 'ok':
                funds = response.get('fund_limit', [])
                equity_margin = next((f for f in funds if f.get('title') == 'Total Balance'), {})
                
                return {
                    "available_cash": float(equity_margin.get('equityAmount', 0)),
                    "used_margin": float(equity_margin.get('utilized_amount', 0)),
                    "total_margin": float(equity_margin.get('equityAmount', 0)),
                    "opening_balance": float(equity_margin.get('start_day_balance', 0))
                }
            else:
                raise BrokerException(f"Margin fetch failed: {response.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Failed to get margins: {e}")
            raise BrokerException(f"Margin fetch failed: {e}")
    
    def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """Place order with Fyers"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Map order parameters to Fyers format
            order_data = {
                "symbol": self._format_symbol(order_request.symbol),
                "qty": order_request.quantity,
                "type": self.order_type_map[order_request.order_type],
                "side": self.transaction_type_map[order_request.transaction_type],
                "productType": self.product_type_map[order_request.product_type],
                "validity": order_request.validity,
                "disclosedQty": order_request.disclosed_quantity,
                "offlineOrder": False
            }
            
            # Add price for limit orders
            if order_request.order_type in [OrderType.LIMIT, OrderType.SL]:
                order_data["limitPrice"] = order_request.price
            else:
                order_data["limitPrice"] = 0
            
            # Add trigger price for stop loss orders
            if order_request.order_type in [OrderType.SL, OrderType.SL_M]:
                order_data["stopPrice"] = order_request.trigger_price
            else:
                order_data["stopPrice"] = 0
            
            # Place stop loss and take profit if specified
            if hasattr(order_request, 'stop_loss') and order_request.stop_loss:
                order_data["stopLoss"] = order_request.stop_loss
            else:
                order_data["stopLoss"] = 0
                
            if hasattr(order_request, 'take_profit') and order_request.take_profit:
                order_data["takeProfit"] = order_request.take_profit  
            else:
                order_data["takeProfit"] = 0
            
            response = self.client.place_order(order_data)
            
            if response.get('s') == 'ok':
                order_id = response.get('id', '')
                logger.info(f"Order placed successfully: {order_id}")
                
                return OrderResponse(
                    order_id=str(order_id),
                    status=OrderStatus.PENDING,
                    message="Order placed successfully",
                    timestamp=datetime.now()
                )
            else:
                error_msg = response.get('message', 'Unknown error')
                error_code = response.get('code', 0)
                raise OrderError(f"Order placement failed: {error_msg} (Code: {error_code})")
                
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            raise OrderError(f"Failed to place order: {e}")
    
    def modify_order(self, order_id: str, **kwargs) -> OrderResponse:
        """Modify existing order"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Prepare modification parameters
            modify_data = {"id": order_id}
            
            # Map common modification parameters
            if "quantity" in kwargs:
                modify_data["qty"] = kwargs["quantity"]
            if "price" in kwargs:
                modify_data["limitPrice"] = kwargs["price"]
            if "trigger_price" in kwargs:
                modify_data["stopPrice"] = kwargs["trigger_price"]
            if "order_type" in kwargs:
                modify_data["type"] = self.order_type_map[kwargs["order_type"]]
            
            response = self.client.modify_order(modify_data)
            
            if response.get('s') == 'ok':
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.PENDING,
                    message="Order modified successfully",
                    timestamp=datetime.now()
                )
            else:
                error_msg = response.get('message', 'Unknown error')
                raise OrderError(f"Order modification failed: {error_msg}")
                
        except Exception as e:
            logger.error(f"Order modification failed: {e}")
            raise OrderError(f"Failed to modify order: {e}")
    
    def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel existing order"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            cancel_data = {"id": order_id}
            response = self.client.cancel_order(cancel_data)
            
            if response.get('s') == 'ok':
                return OrderResponse(
                    order_id=order_id,
                    status=OrderStatus.CANCELLED,
                    message="Order cancelled successfully",
                    timestamp=datetime.now()
                )
            else:
                error_msg = response.get('message', 'Unknown error')
                raise OrderError(f"Order cancellation failed: {error_msg}")
                
        except Exception as e:
            logger.error(f"Order cancellation failed: {e}")
            raise OrderError(f"Failed to cancel order: {e}")
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get status of specific order"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Get all orders and filter by ID
            response = self.client.orderbook()
            
            if response.get('s') == 'ok':
                orders = response.get('orderBook', [])
                order = next((o for o in orders if o.get('id') == order_id), None)
                
                if order:
                    return {
                        "order_id": order.get("id"),
                        "status": self._map_order_status(order.get("status")),
                        "transaction_type": "BUY" if order.get("side") == 1 else "SELL",
                        "quantity": order.get("qty"),
                        "filled_quantity": order.get("filledQty", 0),
                        "price": order.get("limitPrice", 0),
                        "average_price": order.get("avgPrice", 0),
                        "order_timestamp": order.get("orderDateTime")
                    }
                return {}
            else:
                raise BrokerException(f"Order status fetch failed: {response.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Failed to get order status: {e}")
            raise BrokerException(f"Order status fetch failed: {e}")
    
    def get_orderbook(self) -> List[Dict[str, Any]]:
        """Get all orders for the day"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            response = self.client.orderbook()
            
            if response.get('s') == 'ok':
                return response.get('orderBook', [])
            else:
                raise BrokerException(f"Orderbook fetch failed: {response.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Failed to get orderbook: {e}")
            raise BrokerException(f"Orderbook fetch failed: {e}")
    
    def get_positions(self) -> List[Position]:
        """Get current positions"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            response = self.client.positions()
            
            if response.get('s') == 'ok':
                positions_data = response.get('netPositions', [])
                positions = []
                
                for pos in positions_data:
                    if pos.get('netQty', 0) != 0:  # Only active positions
                        positions.append(Position(
                            symbol=pos.get('symbol', ''),
                            quantity=pos.get('netQty', 0),
                            average_price=pos.get('avgPrice', 0.0),
                            last_price=pos.get('ltp', 0.0),
                            pnl=pos.get('pl', 0.0),
                            product_type=ProductType.MIS  # Default to MIS
                        ))
                
                return positions
            else:
                raise BrokerException(f"Positions fetch failed: {response.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise BrokerException(f"Positions fetch failed: {e}")
    
    def get_holdings(self) -> List[Holding]:
        """Get holdings/investments"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            response = self.client.holdings()
            
            if response.get('s') == 'ok':
                holdings_data = response.get('holdings', [])
                holdings = []
                
                for holding in holdings_data:
                    if holding.get('qty', 0) > 0:
                        holdings.append(Holding(
                            symbol=holding.get('symbol', ''),
                            quantity=holding.get('qty', 0),
                            average_price=holding.get('costPrice', 0.0),
                            last_price=holding.get('ltp', 0.0),
                            pnl=holding.get('pl', 0.0)
                        ))
                
                return holdings
            else:
                raise BrokerException(f"Holdings fetch failed: {response.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Failed to get holdings: {e}")
            raise BrokerException(f"Holdings fetch failed: {e}")
    
    def get_quote(self, symbols: List[str]) -> Dict[str, MarketQuote]:
        """Get live market quotes"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Format symbols for Fyers (comma-separated)
            formatted_symbols = [self._format_symbol(symbol) for symbol in symbols]
            symbol_string = ",".join(formatted_symbols)
            
            quote_data = {"symbols": symbol_string}
            response = self.client.quotes(quote_data)
            
            if response.get('s') == 'ok':
                quotes_data = response.get('d', {})
                quotes = {}
                
                for symbol, data in quotes_data.items():
                    clean_symbol = symbol.split(":")[-1]  # Remove exchange prefix
                    quotes[clean_symbol] = MarketQuote(
                        symbol=clean_symbol,
                        last_price=data.get('lp', 0.0),
                        bid_price=data.get('bid', 0.0),
                        ask_price=data.get('ask', 0.0),
                        volume=data.get('v', 0),
                        timestamp=datetime.now()
                    )
                
                return quotes
            else:
                raise BrokerException(f"Quote fetch failed: {response.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Failed to get quotes: {e}")
            raise BrokerException(f"Quote fetch failed: {e}")
    
    def get_historical_data(self, symbol: str, from_date: datetime, 
                          to_date: datetime, interval: str) -> List[Dict[str, Any]]:
        """Get historical OHLCV data"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Convert dates to timestamps
            range_from = int(from_date.timestamp())
            range_to = int(to_date.timestamp())
            
            # Map intervals to Fyers format
            interval_map = {
                "1m": "1", "2m": "2", "3m": "3", "5m": "5", "10m": "10",
                "15m": "15", "30m": "30", "45m": "45", "1h": "60", 
                "2h": "120", "3h": "180", "4h": "240", "1d": "D"
            }
            
            fyers_interval = interval_map.get(interval, "D")
            
            history_data = {
                "symbol": self._format_symbol(symbol),
                "resolution": fyers_interval,
                "date_format": "0",  # Unix timestamp
                "range_from": str(range_from),
                "range_to": str(range_to),
                "cont_flag": "1"
            }
            
            response = self.client.history(history_data)
            
            if response.get('s') == 'ok':
                candles = response.get('candles', [])
                formatted_data = []
                
                for candle in candles:
                    if len(candle) >= 6:
                        formatted_data.append({
                            "timestamp": candle[0],
                            "open": candle[1],
                            "high": candle[2], 
                            "low": candle[3],
                            "close": candle[4],
                            "volume": candle[5]
                        })
                
                return formatted_data
            else:
                error_msg = response.get('message', 'Unknown error')
                if response.get('s') == 'no_data':
                    return []  # No data available for the range
                raise BrokerException(f"Historical data fetch failed: {error_msg}")
                
        except Exception as e:
            logger.error(f"Failed to get historical data: {e}")
            raise BrokerException(f"Historical data fetch failed: {e}")
    
    def search_instruments(self, query: str) -> List[Dict[str, Any]]:
        """Search for tradeable instruments"""
        try:
            if not self.is_authenticated:
                raise AuthenticationError("Not authenticated")
            
            # Fyers doesn't have a direct search API
            # This is a simplified implementation
            # In practice, you'd use a master instrument file
            
            results = []
            common_symbols = [
                {"symbol": "NSE:NIFTY50-INDEX", "name": "NIFTY 50", "exchange": "NSE"},
                {"symbol": "NSE:BANKNIFTY-INDEX", "name": "BANK NIFTY", "exchange": "NSE"},
                {"symbol": "BSE:SENSEX-INDEX", "name": "SENSEX", "exchange": "BSE"}
            ]
            
            query_lower = query.lower()
            for instrument in common_symbols:
                if (query_lower in instrument["name"].lower() or 
                    query_lower in instrument["symbol"].lower()):
                    results.append({
                        "symbol": instrument["symbol"],
                        "name": instrument["name"],
                        "exchange": instrument["exchange"],
                        "instrument_type": "INDEX"
                    })
            
            return results[:20]  # Limit results
            
        except Exception as e:
            logger.error(f"Failed to search instruments: {e}")
            raise BrokerException(f"Instrument search failed: {e}")
    
    def calculate_lot_size(self, symbol: str) -> int:
        """Get lot size for a symbol"""
        try:
            # Extract base symbol
            base_symbol = symbol.split("FUT")[0].split("CE")[0].split("PE")[0].replace("NSE:", "").replace("NFO:", "")
            return self.lot_sizes.get(base_symbol, 1)
        except:
            return 1
    
    def _format_symbol(self, symbol: str) -> str:
        """Format symbol for Fyers API"""
        # If symbol already has exchange prefix, return as is
        if ":" in symbol:
            return symbol
            
        # Add NSE prefix for equity, NFO for F&O
        if any(x in symbol for x in ["FUT", "CE", "PE"]):
            return f"NFO:{symbol}"
        else:
            return f"NSE:{symbol}-EQ"
    
    def _map_order_status(self, fyers_status: int) -> OrderStatus:
        """Map Fyers order status to standard status"""
        status_map = {
            1: OrderStatus.CANCELLED,
            2: OrderStatus.COMPLETE,
            3: OrderStatus.PENDING,
            4: OrderStatus.REJECTED,
            5: OrderStatus.PENDING,
            6: OrderStatus.COMPLETE
        }
        return status_map.get(fyers_status, OrderStatus.PENDING)
    
    def generate_auth_url(self) -> str:
        """Generate Fyers authentication URL"""
        session = fyersModel.SessionModel(
            client_id=self.client_id,
            secret_key=self.secret_key,
            redirect_uri=self.redirect_uri,
            response_type="code",
            grant_type="authorization_code"
        )
        return session.generate_authcode()
    
    def generate_access_token(self, auth_code: str) -> str:
        """Generate access token from auth code"""
        try:
            session = fyersModel.SessionModel(
                client_id=self.client_id,
                secret_key=self.secret_key,
                redirect_uri=self.redirect_uri,
                response_type="code", 
                grant_type="authorization_code"
            )
            
            session.set_token(auth_code)
            response = session.generate_token()
            
            if response.get('s') == 'ok':
                access_token = response.get('access_token')
                self.access_token = access_token
                return access_token
            else:
                error_msg = response.get('message', 'Unknown error')
                raise AuthenticationError(f"Token generation failed: {error_msg}")
                
        except Exception as e:
            logger.error(f"Token generation failed: {e}")
            raise AuthenticationError(f"Failed to generate access token: {e}")

# Export the adapter class
__all__ = ['FyersAdapter']
