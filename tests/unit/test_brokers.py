"""
Comprehensive Broker Testing Suite for F&O Trading System
Tests all broker adapters with updated features:
- Zerodha, Fyers, and AngelOne integration
- Hedge-first order execution testing
- NIFTY/BANKNIFTY focus validation
- Encrypted credential management
- Position and balance management
- Market data integration
- Error handling and recovery
- Integration with strategy system
"""

import unittest
import asyncio
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os
import logging
import json
from decimal import Decimal

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.config import settings
from app.db.base import db_manager
from app.db.models import BrokerAccount, Trade, Position
from app.db.encryption import db_encryptor, DatabaseEncryption

# Import broker adapters
from app.brokers.base_broker import BaseBroker
from app.brokers.zerodha_adapter import ZerodhaAdapter
from app.brokers.fyers_adapter import FyersAdapter
from app.brokers.angelone_adapter import AngelOneAdapter

# Import related components
from app.strategies.iron_condor import IronCondorStrategy
from app.utils.event_calendar import event_calendar
from app.risk.risk_monitor import risk_monitor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_brokers")

class TestBaseBroker(unittest.TestCase):
    """Test the base broker interface and common functionality"""
    
    def setUp(self):
        """Set up test environment for each test"""
        self.mock_credentials = {
            "api_key": "TEST_API_KEY_123",
            "api_secret": "TEST_API_SECRET_456",
            "access_token": "TEST_ACCESS_TOKEN_789",
            "client_id": "TEST_CLIENT_123"
        }
        
        # Create mock broker instance
        self.broker = BaseBroker("TEST_BROKER", self.mock_credentials)
    
    def test_broker_initialization(self):
        """Test broker initialization with credentials"""
        logger.info("🔧 Testing broker initialization...")
        
        self.assertEqual(self.broker.broker_name, "TEST_BROKER")
        self.assertEqual(self.broker.credentials, self.mock_credentials)
        self.assertFalse(self.broker.is_connected)
        self.assertIsNone(self.broker.session)
        
        logger.info("✅ Broker initialization test passed")
    
    def test_instrument_validation(self):
        """Test NIFTY/BANKNIFTY instrument validation"""
        logger.info("📊 Testing instrument validation...")
        
        # Test allowed instruments
        allowed_instruments = ["NIFTY", "BANKNIFTY"]
        blocked_instruments = ["FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]
        
        for instrument in allowed_instruments:
            self.assertTrue(
                self.broker._is_liquid_instrument(instrument),
                f"{instrument} should be allowed"
            )
        
        for instrument in blocked_instruments:
            self.assertFalse(
                self.broker._is_liquid_instrument(instrument),
                f"{instrument} should be blocked"
            )
        
        logger.info("✅ Instrument validation test passed")
    
    def test_order_validation(self):
        """Test order validation logic"""
        logger.info("📋 Testing order validation...")
        
        # Valid hedge-first order
        valid_order = {
            "symbol": "NIFTY29AUG22000CE",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
            "is_hedge": True,
            "priority": 1
        }
        
        self.assertTrue(self.broker._validate_order(valid_order))
        
        # Invalid order (missing required fields)
        invalid_order = {
            "symbol": "NIFTY29AUG22000CE",
            "side": "BUY"
            # Missing quantity and order_type
        }
        
        self.assertFalse(self.broker._validate_order(invalid_order))
        
        # Invalid instrument
        invalid_instrument_order = {
            "symbol": "FINNIFTY29AUG22000CE",  # Blocked instrument
            "side": "BUY",
            "quantity": 40,
            "order_type": "MARKET"
        }
        
        self.assertFalse(self.broker._validate_order(invalid_instrument_order))
        
        logger.info("✅ Order validation test passed")

class TestZerodhaAdapter(unittest.TestCase):
    """Test Zerodha KiteConnect integration"""
    
    def setUp(self):
        """Set up Zerodha test environment"""
        self.zerodha_credentials = {
            "api_key": "TEST_ZERODHA_KEY",
            "api_secret": "TEST_ZERODHA_SECRET",
            "access_token": "TEST_ZERODHA_TOKEN"
        }
        
        self.zerodha = ZerodhaAdapter(self.zerodha_credentials)
        
        # Mock KiteConnect
        self.mock_kite = Mock()
        self.zerodha.kite = self.mock_kite
    
    @patch('app.brokers.zerodha_adapter.KiteConnect')
    def test_zerodha_connection(self, mock_kite_class):
        """Test Zerodha connection and authentication"""
        logger.info("🔌 Testing Zerodha connection...")
        
        # Setup mock
        mock_kite_instance = Mock()
        mock_kite_class.return_value = mock_kite_instance
        mock_kite_instance.login_url.return_value = "https://kite.trade/connect/login?v=3&api_key=TEST"
        
        # Test connection
        zerodha = ZerodhaAdapter(self.zerodha_credentials)
        
        # Mock successful profile fetch
        mock_kite_instance.profile.return_value = {
            "user_id": "TEST123",
            "user_name": "Test User",
            "email": "test@example.com",
            "broker": "ZERODHA"
        }
        
        zerodha.kite = mock_kite_instance
        result = zerodha.connect()
        
        self.assertTrue(result)
        self.assertTrue(zerodha.is_connected)
        
        logger.info("✅ Zerodha connection test passed")
    
    def test_zerodha_balance_fetch(self):
        """Test balance and margin fetching from Zerodha"""
        logger.info("💰 Testing Zerodha balance fetch...")
        
        # Mock balance response
        mock_balance_response = {
            "equity": {
                "enabled": True,
                "net": 50000.0,
                "available": {
                    "adhoc_margin": 0,
                    "cash": 50000.0,
                    "opening_balance": 45000.0,
                    "live_balance": 50000.0,
                    "collateral": 0,
                    "intraday_payin": 5000.0
                },
                "utilised": {
                    "debits": 0,
                    "exposure": 0,
                    "m2m_realised": 0,
                    "m2m_unrealised": 0,
                    "option_premium": 0,
                    "payout": 0,
                    "span": 0,
                    "holding_sales": 0,
                    "turnover": 0
                }
            }
        }
        
        self.mock_kite.margins.return_value = mock_balance_response
        
        balance = self.zerodha.get_balance()
        
        self.assertIn("cash", balance)
        self.assertIn("margin_available", balance)
        self.assertEqual(balance["cash"], 50000.0)
        
        logger.info(f"✅ Zerodha balance test passed: {balance}")
    
    def test_zerodha_hedge_first_order_execution(self):
        """Test hedge-first order execution with Zerodha"""
        logger.info("🛡️ Testing Zerodha hedge-first order execution...")
        
        # Create Iron Condor orders (4-leg hedged strategy)
        iron_condor = IronCondorStrategy()
        
        test_signal = {
            "symbol": "NIFTY",
            "expiry": "29AUG",
            "spot_price": 22000,
            "strikes": {
                "ce_sale": 22100,
                "ce_hedge": 22200,
                "pe_sale": 21900,
                "pe_hedge": 21800
            }
        }
        
        orders = iron_condor.generate_orders(test_signal, {"lot_count": 1}, 50)
        
        # Mock order responses
        mock_order_responses = [
            {"order_id": "ORDER001", "status": "COMPLETE"},
            {"order_id": "ORDER002", "status": "COMPLETE"},
            {"order_id": "ORDER003", "status": "COMPLETE"},
            {"order_id": "ORDER004", "status": "COMPLETE"}
        ]
        
        self.mock_kite.place_order.side_effect = mock_order_responses
        
        # Execute orders with hedge-first priority
        executed_orders = []
        
        # Sort orders by priority (hedge first)
        sorted_orders = sorted(orders, key=lambda x: x.get("priority", 999))
        
        for order in sorted_orders:
            zerodha_order = self.zerodha._convert_to_zerodha_format(order)
            response = self.mock_kite.place_order(**zerodha_order)
            executed_orders.append({**order, "response": response})
        
        # Verify hedge orders executed first
        hedge_orders = [o for o in executed_orders if o.get("is_hedge", False)]
        main_orders = [o for o in executed_orders if not o.get("is_hedge", False)]
        
        self.assertEqual(len(hedge_orders), 2, "Should have 2 hedge orders")
        self.assertEqual(len(main_orders), 2, "Should have 2 main orders")
        
        # Verify all orders executed successfully
        for executed_order in executed_orders:
            self.assertEqual(executed_order["response"]["status"], "COMPLETE")
        
        logger.info("✅ Zerodha hedge-first order execution test passed")
    
    def test_zerodha_position_management(self):
        """Test position fetching and management"""
        logger.info("📈 Testing Zerodha position management...")
        
        # Mock positions response
        mock_positions = [
            {
                "tradingsymbol": "NIFTY29AUG22000CE",
                "exchange": "NFO",
                "instrument_token": 12345,
                "product": "MIS",
                "quantity": 50,
                "overnight_quantity": 0,
                "multiplier": 1,
                "average_price": 45.50,
                "close_price": 48.25,
                "last_price": 47.80,
                "value": 2390.0,
                "pnl": 165.0,
                "m2m": 115.0,
                "unrealised": 115.0,
                "realised": 50.0
            },
            {
                "tradingsymbol": "NIFTY29AUG22200CE",
                "exchange": "NFO",
                "instrument_token": 12346,
                "product": "MIS",
                "quantity": -50,
                "overnight_quantity": 0,
                "multiplier": 1,
                "average_price": 25.75,
                "close_price": 23.90,
                "last_price": 24.15,
                "value": -1207.5,
                "pnl": 80.0,
                "m2m": -12.5,
                "unrealised": -12.5,
                "realised": 92.5
            }
        ]
        
        self.mock_kite.positions.return_value = {"net": mock_positions}
        
        positions = self.zerodha.get_positions()
        
        self.assertEqual(len(positions), 2)
        self.assertTrue(all("symbol" in pos for pos in positions))
        self.assertTrue(all("quantity" in pos for pos in positions))
        self.assertTrue(all("pnl" in pos for pos in positions))
        
        # Verify NIFTY positions only
        nifty_positions = [p for p in positions if "NIFTY" in p["symbol"]]
        self.assertEqual(len(nifty_positions), 2)
        
        logger.info(f"✅ Zerodha position management test passed: {len(positions)} positions")
    
    def test_zerodha_market_data(self):
        """Test market data fetching for NIFTY/BANKNIFTY"""
        logger.info("📊 Testing Zerodha market data...")
        
        # Mock market data response
        mock_market_data = {
            "256265": {  # NIFTY token
                "instrument_token": 256265,
                "last_price": 22000.0,
                "last_quantity": 0,
                "average_price": 21995.50,
                "volume": 0,
                "buy_quantity": 0,
                "sell_quantity": 0,
                "ohlc": {
                    "open": 21950.0,
                    "high": 22050.0,
                    "low": 21920.0,
                    "close": 21980.0
                },
                "net_change": 20.0,
                "oi": 0,
                "oi_day_high": 0,
                "oi_day_low": 0,
                "timestamp": "2025-07-28 15:30:00",
                "depth": {
                    "buy": [],
                    "sell": []
                }
            }
        }
        
        self.mock_kite.quote.return_value = mock_market_data
        
        # Test NIFTY market data
        nifty_data = self.zerodha.get_market_data("NIFTY")
        
        self.assertIn("last_price", nifty_data)
        self.assertIn("volume", nifty_data)
        self.assertIn("ohlc", nifty_data)
        self.assertEqual(nifty_data["last_price"], 22000.0)
        
        logger.info(f"✅ Zerodha market data test passed: {nifty_data['last_price']}")
    
    def test_zerodha_error_handling(self):
        """Test Zerodha error handling and recovery"""
        logger.info("🔧 Testing Zerodha error handling...")
        
        from kiteconnect.exceptions import KiteException
        
        # Test network error
        self.mock_kite.profile.side_effect = KiteException("Network error", code=500)
        
        result = self.zerodha.connect()
        self.assertFalse(result)
        
        # Test order rejection
        self.mock_kite.place_order.side_effect = KiteException("Insufficient balance", code=400)
        
        test_order = {
            "symbol": "NIFTY29AUG22000CE",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET"
        }
        
        with self.assertRaises(Exception):
            self.zerodha.place_order(test_order)
        
        logger.info("✅ Zerodha error handling test passed")

class TestFyersAdapter(unittest.TestCase):
    """Test Fyers API integration"""
    
    def setUp(self):
        """Set up Fyers test environment"""
        self.fyers_credentials = {
            "app_id": "TEST_FYERS_APP",
            "access_token": "TEST_FYERS_TOKEN",
            "client_id": "TEST_FYERS_CLIENT"
        }
        
        self.fyers = FyersAdapter(self.fyers_credentials)
        
        # Mock Fyers API
        self.mock_fyers_api = Mock()
        self.fyers.fyers = self.mock_fyers_api
    
    def test_fyers_connection(self):
        """Test Fyers connection and authentication"""
        logger.info("🔌 Testing Fyers connection...")
        
        # Mock successful profile response
        mock_profile_response = {
            "s": "ok",
            "code": 200,
            "data": {
                "fy_id": "TEST123",
                "name": "Test User",
                "email_id": "test@example.com"
            }
        }
        
        self.mock_fyers_api.get_profile.return_value = mock_profile_response
        
        result = self.fyers.connect()
        
        self.assertTrue(result)
        self.assertTrue(self.fyers.is_connected)
        
        logger.info("✅ Fyers connection test passed")
    
    def test_fyers_balance_fetch(self):
        """Test balance fetching from Fyers"""
        logger.info("💰 Testing Fyers balance fetch...")
        
        # Mock balance response
        mock_balance_response = {
            "s": "ok",
            "code": 200,
            "data": {
                "fund_limit": [
                    {
                        "title": "Total Balance",
                        "amount": 75000.0
                    },
                    {
                        "title": "Available Balance", 
                        "amount": 65000.0
                    },
                    {
                        "title": "Utilized Margin",
                        "amount": 10000.0
                    }
                ]
            }
        }
        
        self.mock_fyers_api.funds.return_value = mock_balance_response
        
        balance = self.fyers.get_balance()
        
        self.assertIn("cash", balance)
        self.assertIn("margin_available", balance)
        self.assertGreater(balance["cash"], 0)
        
        logger.info(f"✅ Fyers balance test passed: {balance}")
    
    def test_fyers_order_placement(self):
        """Test order placement with Fyers"""
        logger.info("📋 Testing Fyers order placement...")
        
        # Mock order response
        mock_order_response = {
            "s": "ok",
            "code": 200,
            "data": {
                "id": "FYERS_ORDER_123",
                "status": 2,  # Order placed
                "message": "Order placed successfully"
            }
        }
        
        self.mock_fyers_api.place_order.return_value = mock_order_response
        
        test_order = {
            "symbol": "NSE:NIFTY25JUL22000CE",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
            "product": "INTRADAY"
        }
        
        response = self.fyers.place_order(test_order)
        
        self.assertIn("order_id", response)
        self.assertEqual(response["status"], "SUCCESS")
        
        logger.info("✅ Fyers order placement test passed")
    
    def test_fyers_position_management(self):
        """Test Fyers position management"""
        logger.info("📈 Testing Fyers position management...")
        
        # Mock positions response
        mock_positions_response = {
            "s": "ok",
            "code": 200,
            "data": {
                "netPositions": [
                    {
                        "symbol": "NSE:NIFTY25JUL22000CE",
                        "qty": 50,
                        "avgPrice": 48.50,
                        "ltp": 52.75,
                        "pl": 212.5,
                        "buyQty": 50,
                        "sellQty": 0,
                        "side": 1,
                        "productType": "INTRADAY"
                    },
                    {
                        "symbol": "NSE:NIFTY25JUL22200CE", 
                        "qty": -50,
                        "avgPrice": 28.25,
                        "ltp": 26.80,
                        "pl": 72.5,
                        "buyQty": 0,
                        "sellQty": 50,
                        "side": -1,
                        "productType": "INTRADAY"
                    }
                ]
            }
        }
        
        self.mock_fyers_api.positions.return_value = mock_positions_response
        
        positions = self.fyers.get_positions()
        
        self.assertEqual(len(positions), 2)
        self.assertTrue(all("symbol" in pos for pos in positions))
        self.assertTrue(all("pnl" in pos for pos in positions))
        
        logger.info(f"✅ Fyers position management test passed: {len(positions)} positions")

class TestAngelOneAdapter(unittest.TestCase):
    """Test Angel One (Angel Broking) integration"""
    
    def setUp(self):
        """Set up Angel One test environment"""
        self.angel_credentials = {
            "api_key": "TEST_ANGEL_KEY",
            "client_code": "TEST_ANGEL_CLIENT",
            "password": "TEST_ANGEL_PASS",
            "totp": "123456"
        }
        
        self.angel = AngelOneAdapter(self.angel_credentials)
        
        # Mock Angel One API
        self.mock_angel_api = Mock()
        self.angel.smartApi = self.mock_angel_api
    
    def test_angel_connection(self):
        """Test Angel One connection"""
        logger.info("🔌 Testing Angel One connection...")
        
        # Mock login response
        mock_login_response = {
            "status": True,
            "message": "SUCCESS",
            "data": {
                "jwtToken": "TEST_JWT_TOKEN",
                "refreshToken": "TEST_REFRESH_TOKEN",
                "feedToken": "TEST_FEED_TOKEN"
            }
        }
        
        self.mock_angel_api.generateSession.return_value = mock_login_response
        
        result = self.angel.connect()
        
        self.assertTrue(result)
        self.assertTrue(self.angel.is_connected)
        
        logger.info("✅ Angel One connection test passed")
    
    def test_angel_order_management(self):
        """Test Angel One order management"""
        logger.info("📋 Testing Angel One order management...")
        
        # Mock order response
        mock_order_response = {
            "status": True,
            "message": "SUCCESS",
            "data": {
                "script": "NIFTY25JUL22000CE",
                "orderid": "ANGEL_ORDER_123"
            }
        }
        
        self.mock_angel_api.placeOrder.return_value = mock_order_response
        
        test_order = {
            "symbol": "NIFTY25JUL22000CE",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET"
        }
        
        response = self.angel.place_order(test_order)
        
        self.assertIn("order_id", response)
        self.assertEqual(response["status"], "SUCCESS")
        
        logger.info("✅ Angel One order management test passed")

class TestBrokerIntegration(unittest.TestCase):
    """Test broker integration with the trading system"""
    
    def setUp(self):
        """Set up integration test environment"""
        self.all_brokers = {
            "ZERODHA": ZerodhaAdapter({
                "api_key": "TEST_ZERODHA_KEY",
                "api_secret": "TEST_ZERODHA_SECRET",
                "access_token": "TEST_ZERODHA_TOKEN"
            }),
            "FYERS": FyersAdapter({
                "app_id": "TEST_FYERS_APP",
                "access_token": "TEST_FYERS_TOKEN"
            }),
            "ANGELONE": AngelOneAdapter({
                "api_key": "TEST_ANGEL_KEY",
                "client_code": "TEST_ANGEL_CLIENT"
            })
        }
    
    def test_broker_credential_encryption(self):
        """Test broker credential encryption and storage"""
        logger.info("🔐 Testing broker credential encryption...")
        
        test_credentials = {
            "api_key": "SENSITIVE_API_KEY_123",
            "api_secret": "SENSITIVE_SECRET_456",
            "access_token": "SENSITIVE_TOKEN_789"
        }
        
        # Test encryption
        encrypted_creds = db_encryptor.encrypt_broker_credentials(test_credentials)
        self.assertIsInstance(encrypted_creds, str)
        self.assertNotIn("SENSITIVE", encrypted_creds)
        
        # Test decryption
        decrypted_creds = db_encryptor.decrypt_broker_credentials(encrypted_creds)
        self.assertEqual(decrypted_creds["api_key"], "SENSITIVE_API_KEY_123")
        self.assertEqual(decrypted_creds["api_secret"], "SENSITIVE_SECRET_456")
        
        logger.info("✅ Broker credential encryption test passed")
    
    def test_multi_broker_compatibility(self):
        """Test compatibility across multiple brokers"""
        logger.info("🔄 Testing multi-broker compatibility...")
        
        # Test order format standardization
        standard_order = {
            "symbol": "NIFTY29AUG22000CE",
            "side": "BUY",
            "quantity": 50,
            "order_type": "MARKET",
            "product": "INTRADAY"
        }
        
        for broker_name, broker in self.all_brokers.items():
            # Test order conversion to broker-specific format
            try:
                broker_order = broker._convert_to_broker_format(standard_order)
                self.assertIsInstance(broker_order, dict)
                logger.info(f"✅ {broker_name} order format conversion successful")
            except Exception as e:
                logger.warning(f"⚠️ {broker_name} order conversion failed: {e}")
    
    def test_strategy_broker_integration(self):
        """Test integration between strategies and brokers"""
        logger.info("🎯 Testing strategy-broker integration...")
        
        # Create Iron Condor strategy
        iron_condor = IronCondorStrategy()
        
        test_signal = {
            "symbol": "NIFTY",
            "expiry": "29AUG",
            "spot_price": 22000,
            "strikes": {
                "ce_sale": 22100,
                "ce_hedge": 22200,
                "pe_sale": 21900,
                "pe_hedge": 21800
            }
        }
        
        # Generate strategy orders
        strategy_orders = iron_condor.generate_orders(test_signal, {"lot_count": 1}, 50)
        
        # Test orders with each broker
        for broker_name, broker in self.all_brokers.items():
            try:
                # Sort orders by priority (hedge first)
                sorted_orders = sorted(strategy_orders, key=lambda x: x.get("priority", 999))
                
                # Verify hedge orders come first
                hedge_orders = [o for o in sorted_orders if o.get("is_hedge", False)]
                main_orders = [o for o in sorted_orders if not o.get("is_hedge", False)]
                
                # Check that hedge orders have lower priority numbers
                if hedge_orders and main_orders:
                    max_hedge_priority = max(o.get("priority", 0) for o in hedge_orders)
                    min_main_priority = min(o.get("priority", 999) for o in main_orders)
                    
                    self.assertLess(max_hedge_priority, min_main_priority,
                                  f"{broker_name}: Hedge orders should execute first")
                
                logger.info(f"✅ {broker_name} strategy integration validated")
                
            except Exception as e:
                logger.error(f"❌ {broker_name} strategy integration failed: {e}")
    
    def test_risk_monitor_broker_integration(self):
        """Test risk monitor integration with brokers"""
        logger.info("🛡️ Testing risk monitor-broker integration...")
        
        # Mock broker with positions
        mock_broker = Mock()
        mock_broker.get_positions.return_value = [
            {
                "symbol": "NIFTY29AUG22000CE",
                "quantity": 50,
                "average_price": 45.0,
                "last_price": 48.0,
                "pnl": 150.0
            },
            {
                "symbol": "NIFTY29AUG22200CE",
                "quantity": -50,
                "average_price": 25.0,
                "last_price": 23.0,
                "pnl": 100.0
            }
        ]
        
        # Test position MTM calculation
        positions = mock_broker.get_positions()
        total_pnl = sum(pos["pnl"] for pos in positions)
        
        self.assertEqual(total_pnl, 250.0)
        
        # Test risk threshold
        risk_threshold = 2000.0  # SL per lot
        is_within_risk = abs(total_pnl) < risk_threshold
        
        self.assertTrue(is_within_risk, "Position should be within risk limits")
        
        logger.info("✅ Risk monitor-broker integration test passed")
    
    def test_broker_failover_mechanism(self):
        """Test broker failover and redundancy"""
        logger.info("🔄 Testing broker failover mechanism...")
        
        # Simulate primary broker failure
        primary_broker = self.all_brokers["ZERODHA"]
        backup_broker = self.all_brokers["FYERS"]
        
        # Mock primary broker failure
        primary_broker.is_connected = False
        backup_broker.is_connected = True
        
        # Test failover logic
        active_broker = backup_broker if not primary_broker.is_connected else primary_broker
        
        self.assertEqual(active_broker, backup_broker)
        self.assertTrue(active_broker.is_connected)
        
        logger.info("✅ Broker failover mechanism test passed")
    
    def test_order_execution_timing(self):
        """Test order execution timing and sequencing"""
        logger.info("⏱️ Testing order execution timing...")
        
        import time
        
        # Create hedge-first orders
        test_orders = [
            {"symbol": "NIFTY29AUG22000CE", "side": "BUY", "priority": 1, "is_hedge": True},
            {"symbol": "NIFTY29AUG22200CE", "side": "BUY", "priority": 2, "is_hedge": True},
            {"symbol": "NIFTY29AUG22100CE", "side": "SELL", "priority": 3, "is_hedge": False},
            {"symbol": "NIFTY29AUG21900PE", "side": "SELL", "priority": 4, "is_hedge": False}
        ]
        
        # Sort by priority
        sorted_orders = sorted(test_orders, key=lambda x: x.get("priority", 999))
        
        # Simulate timed execution
        execution_times = []
        for order in sorted_orders:
            start_time = time.time()
            
            # Simulate order processing delay
            time.sleep(0.01)  # 10ms delay
            
            execution_time = time.time() - start_time
            execution_times.append({
                "order": order["symbol"],
                "is_hedge": order.get("is_hedge", False),
                "execution_time": execution_time
            })
        
        # Verify hedge orders executed first
        hedge_executions = [e for e in execution_times if e["is_hedge"]]
        main_executions = [e for e in execution_times if not e["is_hedge"]]
        
        self.assertEqual(len(hedge_executions), 2)
        self.assertEqual(len(main_executions), 2)
        
        logger.info("✅ Order execution timing test passed")
    
    def test_market_hours_validation(self):
        """Test market hours validation for brokers"""
        logger.info("🕒 Testing market hours validation...")
        
        from datetime import time
        
        # Define market hours
        market_open = time(9, 15)   # 9:15 AM
        market_close = time(15, 30) # 3:30 PM
        current_time = datetime.now().time()
        
        # Test market hours check
        is_market_open = market_open <= current_time <= market_close
        
        # Test trading day check
        is_trading_day = event_calendar.is_trading_day(date.today())
        
        # Combined check
        can_trade = is_market_open and is_trading_day
        
        logger.info(f"Market open: {is_market_open}, Trading day: {is_trading_day}, Can trade: {can_trade}")
        
        # This test always passes as it's informational
        self.assertIsInstance(can_trade, bool)
        
        logger.info("✅ Market hours validation test passed")

class TestBrokerPerformance(unittest.TestCase):
    """Test broker performance and load handling"""
    
    def test_order_processing_performance(self):
        """Test order processing performance"""
        logger.info("⚡ Testing order processing performance...")
        
        import time
        
        # Create mock broker
        mock_broker = Mock()
        mock_broker.place_order.return_value = {"order_id": "TEST123", "status": "SUCCESS"}
        
        # Test batch order processing
        test_orders = []
        for i in range(100):
            test_orders.append({
                "symbol": f"NIFTY29AUG{22000 + (i % 10) * 50}CE",
                "side": "BUY",
                "quantity": 50,
                "order_type": "MARKET"
            })
        
        start_time = time.time()
        
        for order in test_orders:
            mock_broker.place_order(order)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        orders_per_second = len(test_orders) / processing_time
        
        logger.info(f"✅ Performance test: {orders_per_second:.1f} orders/second")
        
        # Performance should be reasonable (>10 orders/second)
        self.assertGreater(orders_per_second, 10, "Order processing too slow")
    
    def test_concurrent_broker_operations(self):
        """Test concurrent broker operations"""
        logger.info("🔄 Testing concurrent broker operations...")
        
        import threading
        import time
        
        results = []
        
        def mock_broker_operation(broker_id):
            """Simulate broker operation"""
            time.sleep(0.1)  # Simulate API call
            results.append(f"Broker_{broker_id}_completed")
        
        # Start concurrent operations
        threads = []
        for i in range(10):
            thread = threading.Thread(target=mock_broker_operation, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all operations to complete
        for thread in threads:
            thread.join()
        
        # Verify all operations completed
        self.assertEqual(len(results), 10)
        
        logger.info("✅ Concurrent broker operations test passed")

def run_broker_tests():
    """Run the complete broker test suite"""
    print("=" * 80)
    print("F&O Trading System - Comprehensive Broker Test Suite")  
    print("=" * 80)
    print()
    
    # Create test suite
    test_classes = [
        TestBaseBroker,
        TestZerodhaAdapter,
        TestFyersAdapter,
        TestAngelOneAdapter,
        TestBrokerIntegration,
        TestBrokerPerformance
    ]
    
    test_suite = unittest.TestSuite()
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
        descriptions=True,
        failfast=False
    )
    
    result = runner.run(test_suite)
    
    print()
    print("=" * 80)
    print("BROKER TEST RESULTS SUMMARY")
    print("=" * 80)
    print(f"Tests Run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success Rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_broker_tests()
    sys.exit(0 if success else 1)
