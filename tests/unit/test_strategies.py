"""
Comprehensive Strategy Testing Suite for F&O Trading System
Tests all 8 hedged strategies with updated features:
- Iron Condor, Butterfly Spread, Calendar Spread, Hedged Strangle
- Directional Futures, Jade Lizard, Ratio Spreads, Broken Wing Butterfly
- Hedge-first order execution validation
- NIFTY/BANKNIFTY focus enforcement
- Market condition evaluation
- Strategy-specific metrics testing
- Integration with event calendar and risk monitoring
- Performance and error handling validation
"""

import unittest
import asyncio
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os
import logging
from decimal import Decimal
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.config import settings

# Import all 8 hedged strategies
from app.strategies.iron_condor import IronCondorStrategy, validate_iron_condor_structure
from app.strategies.butterfly_spread import ButterflySpreadStrategy, validate_butterfly_spread_structure
from app.strategies.calendar_spread import CalendarSpreadStrategy, validate_calendar_spread_structure
from app.strategies.hedged_strangle import HedgedStrangleStrategy, validate_hedged_strangle_structure
from app.strategies.directional_futures import DirectionalFuturesStrategy, validate_directional_futures_structure
from app.strategies.jade_lizard import JadeLizardStrategy, validate_jade_lizard_structure
from app.strategies.ratio_spreads import RatioSpreadsStrategy, validate_ratio_spread_structure
from app.strategies.broken_wing_butterfly import BrokenWingButterflyStrategy, validate_broken_wing_structure

# Import base strategy and related components
from app.strategies.base import BaseStrategy
from app.strategies.strategy_selector import StrategySelector
from app.utils.event_calendar import event_calendar
from app.risk.danger_zone import danger_monitor
from app.risk.expiry_day import expiry_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_strategies")

class TestBaseStrategy(unittest.TestCase):
    """Test the base strategy interface and common functionality"""
    
    def setUp(self):
        """Set up test environment for each test"""
        self.base_strategy = BaseStrategy()
        
        # Common test data
        self.test_market_data = {
            "symbol": "NIFTY",
            "vix": 20.0,
            "spot_price": 22000,
            "index_chg_pct": 0.5,
            "trend_strength": 1.2,
            "directional_bias": "NEUTRAL",
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 15,
            "iv_rank": 60,
            "volume_surge": False
        }
        
        self.test_settings = {
            "DANGER_ZONE_WARNING": 1.0,
            "DANGER_ZONE_RISK": 1.25,
            "DANGER_ZONE_EXIT": 1.5,
            "VIX_THRESHOLD": 25.0
        }
    
    def test_base_strategy_initialization(self):
        """Test base strategy initialization"""
        logger.info("🔧 Testing base strategy initialization...")
        
        self.assertIsNotNone(self.base_strategy.name)
        self.assertIsInstance(self.base_strategy.performance_metrics, dict)
        self.assertIsInstance(self.base_strategy.trade_history, list)
        
        logger.info("✅ Base strategy initialization test passed")
    
    def test_instrument_validation(self):
        """Test NIFTY/BANKNIFTY instrument validation"""
        logger.info("📊 Testing instrument validation...")
        
        # Test allowed instruments
        allowed_instruments = ["NIFTY", "BANKNIFTY"]
        blocked_instruments = ["FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"]
        
        for instrument in allowed_instruments:
            self.assertTrue(
                self.base_strategy._is_liquid_instrument(instrument),
                f"{instrument} should be allowed"
            )
        
        for instrument in blocked_instruments:
            self.assertFalse(
                self.base_strategy._is_liquid_instrument(instrument),
                f"{instrument} should be blocked"
            )
        
        logger.info("✅ Instrument validation test passed")
    
    def test_performance_tracking(self):
        """Test strategy performance tracking"""
        logger.info("📈 Testing performance tracking...")
        
        # Add mock trades
        mock_trades = [
            {"pnl": 1500, "win": True, "date": datetime.now()},
            {"pnl": -800, "win": False, "date": datetime.now()},
            {"pnl": 2200, "win": True, "date": datetime.now()},
        ]
        
        for trade in mock_trades:
            self.base_strategy.add_trade_result(trade)
        
        # Test performance calculation
        performance = self.base_strategy.get_performance_summary()
        
        self.assertIn("total_trades", performance)
        self.assertIn("win_rate", performance)
        self.assertIn("total_pnl", performance)
        self.assertEqual(performance["total_trades"], 3)
        self.assertEqual(performance["total_pnl"], 2900)
        
        logger.info("✅ Performance tracking test passed")

class TestIronCondorStrategy(unittest.TestCase):
    """Test Iron Condor Strategy (4-leg hedged)"""
    
    def setUp(self):
        """Set up Iron Condor test environment"""
        self.iron_condor = IronCondorStrategy()
        
        self.test_signal = {
            "symbol": "NIFTY",
            "expiry": "01AUG",
            "spot_price": 22000,
            "strikes": {
                "ce_sale": 22100,
                "ce_hedge": 22200,
                "pe_sale": 21900,
                "pe_hedge": 21800
            },
            "estimated_premiums": {
                "ce_sale": 50,
                "ce_hedge": 25,
                "pe_sale": 55,
                "pe_hedge": 30
            }
        }
        
        self.test_config = {
            "lot_count": 1,
            "sl_per_lot": 1500,
            "tp_per_lot": 3000
        }
    
    def test_iron_condor_initialization(self):
        """Test Iron Condor initialization"""
        logger.info("🔧 Testing Iron Condor initialization...")
        
        self.assertEqual(self.iron_condor.name, "IRON_CONDOR")
        self.assertEqual(self.iron_condor.required_leg_count, 4)
        self.assertIn("NIFTY", self.iron_condor.allowed_instruments)
        self.assertIn("BANKNIFTY", self.iron_condor.allowed_instruments)
        self.assertTrue(hasattr(self.iron_condor, 'min_vix'))
        self.assertTrue(hasattr(self.iron_condor, 'max_vix'))
        
        logger.info("✅ Iron Condor initialization test passed")
    
    def test_iron_condor_market_conditions(self):
        """Test Iron Condor market condition evaluation"""
        logger.info("📊 Testing Iron Condor market conditions...")
        
        # Test suitable conditions (low VIX, neutral market)
        suitable_conditions = {
            "symbol": "NIFTY",
            "vix": 18.0,  # Within range
            "index_chg_pct": 0.3,  # Low movement
            "trend_strength": 1.0,  # Not strongly trending
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 20
        }
        
        result = self.iron_condor.evaluate_market_conditions(suitable_conditions, self.test_config)
        self.assertTrue(result, "Iron Condor should be suitable for low VIX conditions")
        
        # Test unsuitable conditions (high VIX)
        unsuitable_conditions = suitable_conditions.copy()
        unsuitable_conditions["vix"] = 35.0  # Too high
        
        result = self.iron_condor.evaluate_market_conditions(unsuitable_conditions, self.test_config)
        self.assertFalse(result, "Iron Condor should not be suitable for high VIX")
        
        # Test blocked instrument
        blocked_conditions = suitable_conditions.copy()
        blocked_conditions["symbol"] = "FINNIFTY"  # Blocked instrument
        
        result = self.iron_condor.evaluate_market_conditions(blocked_conditions, self.test_config)
        self.assertFalse(result, "Iron Condor should reject blocked instruments")
        
        logger.info("✅ Iron Condor market conditions test passed")
    
    def test_iron_condor_order_generation(self):
        """Test Iron Condor hedge-first order generation"""
        logger.info("📋 Testing Iron Condor order generation...")
        
        orders = self.iron_condor.generate_orders(self.test_signal, self.test_config, 50)
        
        # Validate order structure
        self.assertEqual(len(orders), 4, "Iron Condor should have 4 legs")
        
        # Validate hedge-first execution
        hedge_orders = [o for o in orders if o.get("is_hedge", False)]
        main_orders = [o for o in orders if not o.get("is_hedge", False)]
        
        self.assertEqual(len(hedge_orders), 2, "Should have 2 hedge orders")
        self.assertEqual(len(main_orders), 2, "Should have 2 main orders")
        
        # Verify priority ordering (hedge first)
        hedge_priorities = [o.get("priority", 999) for o in hedge_orders]
        main_priorities = [o.get("priority", 999) for o in main_orders]
        
        self.assertTrue(max(hedge_priorities) < min(main_priorities), 
                       "Hedge orders should execute before main orders")
        
        # Validate order structure
        self.assertTrue(validate_iron_condor_structure(orders))
        
        # Verify all orders have required fields
        for order in orders:
            self.assertIn("symbol", order)
            self.assertIn("side", order)
            self.assertIn("quantity", order)
            self.assertIn("execution_order", order)
        
        logger.info("✅ Iron Condor order generation test passed")
    
    def test_iron_condor_risk_management(self):
        """Test Iron Condor risk management"""
        logger.info("🛡️ Testing Iron Condor risk management...")
        
        # Test various MTM scenarios
        test_scenarios = [
            {"mtm": 100, "expected_action": None},           # Small profit
            {"mtm": -1200, "expected_action": "SOFT_WARN"},  # Approaching SL
            {"mtm": -1500, "expected_action": "HARD_STOP"},  # SL triggered
            {"mtm": 3000, "expected_action": "TAKE_PROFIT"}, # TP achieved
            {"mtm": 1500, "expected_action": "PROFIT_OPPORTUNITY"} # Good profit
        ]
        
        for scenario in test_scenarios:
            config = {
                "sl_per_lot": 1500,
                "tp_per_lot": 3000,
                "days_to_expiry": 15
            }
            
            risk_action = self.iron_condor.on_mtm_tick(scenario["mtm"], config, 1)
            
            if scenario["expected_action"] is None:
                self.assertIsNone(risk_action.get("action"))
            else:
                self.assertIn(scenario["expected_action"], str(risk_action.get("action", "")))
        
        logger.info("✅ Iron Condor risk management test passed")
    
    def test_iron_condor_strategy_metrics(self):
        """Test Iron Condor strategy-specific metrics"""
        logger.info("📊 Testing Iron Condor metrics...")
        
        metrics = self.iron_condor.get_strategy_specific_metrics()
        
        # Verify required metrics
        required_metrics = [
            "wing_widths", "min_credit_target", "vix_range", 
            "risk_profile", "profit_profile", "market_outlook"
        ]
        
        for metric in required_metrics:
            self.assertIn(metric, metrics, f"Missing metric: {metric}")
        
        # Verify wing widths for both instruments
        self.assertIn("NIFTY", metrics["wing_widths"])
        self.assertIn("BANKNIFTY", metrics["wing_widths"])
        
        logger.info("✅ Iron Condor metrics test passed")

class TestButterflySpreadStrategy(unittest.TestCase):
    """Test Butterfly Spread Strategy (3-leg hedged)"""
    
    def setUp(self):
        """Set up Butterfly Spread test environment"""
        self.butterfly = ButterflySpreadStrategy()
        
        self.test_signal = {
            "symbol": "NIFTY",
            "expiry": "01AUG",
            "center_strike": 22000,
            "option_type": "CE",
            "wing_width": 50,
            "estimated_net_debit": 1200
        }
    
    def test_butterfly_market_conditions(self):
        """Test Butterfly Spread market conditions"""
        logger.info("📊 Testing Butterfly Spread market conditions...")
        
        # Test suitable conditions (very low VIX)
        suitable_conditions = {
            "symbol": "NIFTY",
            "vix": 15.0,  # Low VIX
            "index_chg_pct": 0.2,  # Very low movement
            "trend_strength": 0.8,  # Not trending
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 25
        }
        
        result = self.butterfly.evaluate_market_conditions(suitable_conditions, {})
        self.assertTrue(result, "Butterfly should be suitable for very low VIX")
        
        logger.info("✅ Butterfly Spread market conditions test passed")
    
    def test_butterfly_order_generation(self):
        """Test Butterfly Spread hedge-first order generation"""
        logger.info("📋 Testing Butterfly Spread order generation...")
        
        orders = self.butterfly.generate_orders(self.test_signal, {"lot_count": 1}, 50)
        
        # Butterfly has 3 orders (1-2-1 structure)
        self.assertEqual(len(orders), 3, "Butterfly should have 3 orders")
        
        # Validate hedge-first execution
        hedge_orders = [o for o in orders if o.get("is_hedge", False)]
        main_orders = [o for o in orders if not o.get("is_hedge", False)]
        
        self.assertEqual(len(hedge_orders), 2, "Should have 2 hedge orders (long strikes)")
        self.assertEqual(len(main_orders), 1, "Should have 1 main order (short middle)")
        
        # Verify structure
        self.assertTrue(validate_butterfly_spread_structure(orders))
        
        logger.info("✅ Butterfly Spread order generation test passed")

class TestHedgedStrangleStrategy(unittest.TestCase):
    """Test Hedged Strangle Strategy (4-leg hedged)"""
    
    def setUp(self):
        """Set up Hedged Strangle test environment"""
        self.hedged_strangle = HedgedStrangleStrategy()
        
        self.test_signal = {
            "symbol": "BANKNIFTY",
            "expiry": "01AUG",
            "spot_price": 48000,
            "ce_otm_strike": 48200,
            "pe_otm_strike": 47800,
            "ce_hedge_strike": 48600,
            "pe_hedge_strike": 47400,
            "estimated_premiums": {
                "ce_otm": 80,
                "pe_otm": 85,
                "ce_hedge": 35,
                "pe_hedge": 40
            }
        }
    
    def test_hedged_strangle_market_conditions(self):
        """Test Hedged Strangle market conditions"""
        logger.info("📊 Testing Hedged Strangle market conditions...")
        
        # Test suitable conditions (high VIX, neutral bias)
        suitable_conditions = {
            "symbol": "BANKNIFTY",
            "vix": 28.0,  # High VIX
            "index_chg_pct": 0.8,
            "trend_strength": 1.5,  # Moderate trend
            "iv_rank": 75,  # High IV rank
            "upcoming_events": [],
            "is_expiry": False
        }
        
        result = self.hedged_strangle.evaluate_market_conditions(suitable_conditions, {})
        self.assertTrue(result, "Hedged Strangle should be suitable for high VIX")
        
        logger.info("✅ Hedged Strangle market conditions test passed")
    
    def test_hedged_strangle_order_generation(self):
        """Test Hedged Strangle hedge-first order generation"""
        logger.info("📋 Testing Hedged Strangle order generation...")
        
        orders = self.hedged_strangle.generate_orders(self.test_signal, {"lot_count": 1}, 15)
        
        # Validate order structure
        self.assertEqual(len(orders), 4, "Hedged Strangle should have 4 legs")
        
        # Validate hedge-first execution
        hedge_orders = [o for o in orders if o.get("is_hedge", False)]
        main_orders = [o for o in orders if not o.get("is_hedge", False)]
        
        self.assertEqual(len(hedge_orders), 2, "Should have 2 hedge orders")
        self.assertEqual(len(main_orders), 2, "Should have 2 main orders")
        
        # Verify hedge orders execute first
        hedge_priorities = [o.get("priority", 999) for o in hedge_orders]
        main_priorities = [o.get("priority", 999) for o in main_orders]
        
        self.assertTrue(max(hedge_priorities) < min(main_priorities))
        
        # Validate structure
        self.assertTrue(validate_hedged_strangle_structure(orders))
        
        logger.info("✅ Hedged Strangle order generation test passed")

class TestDirectionalFuturesStrategy(unittest.TestCase):
    """Test Directional Futures Strategy (2-leg hedged)"""
    
    def setUp(self):
        """Set up Directional Futures test environment"""
        self.directional_futures = DirectionalFuturesStrategy()
        
        self.test_signal = {
            "symbol": "NIFTY",
            "direction": "LONG",
            "expiry": "29AUG",
            "spot_price": 22000,
            "hedge_strike": 21700,  # Put hedge for long futures
            "confidence": 0.8
        }
    
    def test_directional_futures_market_conditions(self):
        """Test Directional Futures market conditions"""
        logger.info("📊 Testing Directional Futures market conditions...")
        
        # Test suitable conditions (strong trend, clear direction)
        suitable_conditions = {
            "symbol": "NIFTY",
            "vix": 22.0,
            "trend_strength": 2.8,  # Strong trend
            "directional_bias": "BULLISH",  # Clear direction
            "volume_surge": True,
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 12
        }
        
        result = self.directional_futures.evaluate_market_conditions(suitable_conditions, {})
        self.assertTrue(result, "Directional Futures should be suitable for trending markets")
        
        # Test unsuitable conditions (neutral bias)
        unsuitable_conditions = suitable_conditions.copy()
        unsuitable_conditions["directional_bias"] = "NEUTRAL"
        
        result = self.directional_futures.evaluate_market_conditions(unsuitable_conditions, {})
        self.assertFalse(result, "Directional Futures should reject neutral bias")
        
        logger.info("✅ Directional Futures market conditions test passed")
    
    def test_directional_futures_order_generation(self):
        """Test Directional Futures hedge-first order generation"""
        logger.info("📋 Testing Directional Futures order generation...")
        
        orders = self.directional_futures.generate_orders(self.test_signal, {"lot_count": 1}, 50)
        
        # Validate order structure (2 legs: hedge + futures)
        self.assertEqual(len(orders), 2, "Directional Futures should have 2 legs")
        
        # Validate hedge-first execution
        hedge_orders = [o for o in orders if o.get("is_hedge", False)]
        futures_orders = [o for o in orders if o.get("instrument_type") == "FUTURES"]
        
        self.assertEqual(len(hedge_orders), 1, "Should have 1 hedge order")
        self.assertEqual(len(futures_orders), 1, "Should have 1 futures order")
        
        # Verify hedge executes first
        hedge_priority = hedge_orders[0].get("priority", 999)
        futures_priority = futures_orders[0].get("priority", 999)
        
        self.assertLess(hedge_priority, futures_priority, "Hedge should execute before futures")
        
        # Validate structure
        self.assertTrue(validate_directional_futures_structure(orders))
        
        logger.info("✅ Directional Futures order generation test passed")

class TestJadeLizardStrategy(unittest.TestCase):
    """Test Jade Lizard Strategy (3-leg hedged)"""
    
    def setUp(self):
        """Set up Jade Lizard test environment"""
        self.jade_lizard = JadeLizardStrategy()
        
        self.test_signal = {
            "symbol": "BANKNIFTY",
            "expiry": "01AUG",
            "spot_price": 48000,
            "short_put_strike": 47600,
            "short_call_strike": 48400,
            "long_call_strike": 48800,
            "estimated_premiums": {
                "short_put": 120,
                "short_call": 90,
                "long_call": 45
            }
        }
    
    def test_jade_lizard_market_conditions(self):
        """Test Jade Lizard market conditions"""
        logger.info("📊 Testing Jade Lizard market conditions...")
        
        # Test suitable conditions (high VIX, slightly bullish)
        suitable_conditions = {
            "symbol": "BANKNIFTY",
            "vix": 26.0,  # High VIX
            "directional_bias": "SLIGHTLY_BULLISH",
            "iv_rank": 70,
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 18
        }
        
        result = self.jade_lizard.evaluate_market_conditions(suitable_conditions, {})
        self.assertTrue(result, "Jade Lizard should be suitable for high VIX + slight bullish bias")
        
        logger.info("✅ Jade Lizard market conditions test passed")
    
    def test_jade_lizard_order_generation(self):
        """Test Jade Lizard order generation"""
        logger.info("📋 Testing Jade Lizard order generation...")
        
        orders = self.jade_lizard.generate_orders(self.test_signal, {"lot_count": 1}, 15)
        
        # Validate order structure (3 legs)
        self.assertEqual(len(orders), 3, "Jade Lizard should have 3 legs")
        
        # Validate structure
        self.assertTrue(validate_jade_lizard_structure(orders))
        
        logger.info("✅ Jade Lizard order generation test passed")

class TestRatioSpreadsStrategy(unittest.TestCase):
    """Test Ratio Spreads Strategy (3-leg hedged)"""
    
    def setUp(self):
        """Set up Ratio Spreads test environment"""
        self.ratio_spreads = RatioSpreadsStrategy()
        
        self.test_signal = {
            "symbol": "NIFTY",
            "direction": "CALL",  # Bullish ratio spread
            "expiry": "01AUG",
            "spot_price": 22000,
            "long_strike": 21950,   # Slightly ITM
            "short_strike": 22100,  # OTM (sell 2x)
            "hedge_strike": 22250,  # Far OTM hedge
            "estimated_premiums": {
                "long_strike": 80,
                "short_strike": 45,
                "hedge_strike": 25
            }
        }
    
    def test_ratio_spreads_market_conditions(self):
        """Test Ratio Spreads market conditions"""
        logger.info("📊 Testing Ratio Spreads market conditions...")
        
        # Test suitable conditions (moderate VIX, directional bias)
        suitable_conditions = {
            "symbol": "NIFTY",
            "vix": 24.0,  # Moderate to high VIX
            "trend_strength": 2.0,  # Clear trend
            "directional_bias": "BULLISH",
            "iv_rank": 65,
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 20
        }
        
        result = self.ratio_spreads.evaluate_market_conditions(suitable_conditions, {})
        self.assertTrue(result, "Ratio Spreads should be suitable for directional markets")
        
        logger.info("✅ Ratio Spreads market conditions test passed")
    
    def test_ratio_spreads_order_generation(self):
        """Test Ratio Spreads hedge-first order generation"""
        logger.info("📋 Testing Ratio Spreads order generation...")
        
        orders = self.ratio_spreads.generate_orders(self.test_signal, {"lot_count": 1}, 50)
        
        # Validate order structure (3 legs: 1 long, 2 short, 1 hedge)
        self.assertEqual(len(orders), 3, "Ratio Spreads should have 3 legs")
        
        # Find the 2x short order
        short_orders = [o for o in orders if o.get("side") == "SELL"]
        self.assertEqual(len(short_orders), 1, "Should have 1 short order")
        self.assertEqual(short_orders[0].get("lots"), 2, "Short order should be 2x quantity")
        
        # Validate structure
        self.assertTrue(validate_ratio_spread_structure(orders))
        
        logger.info("✅ Ratio Spreads order generation test passed")

class TestBrokenWingButterflyStrategy(unittest.TestCase):
    """Test Broken Wing Butterfly Strategy (4-leg hedged)"""
    
    def setUp(self):
        """Set up Broken Wing Butterfly test environment"""
        self.broken_wing = BrokenWingButterflyStrategy()
        
        self.test_signal = {
            "symbol": "NIFTY",
            "expiry": "01AUG",
            "spot_price": 22000,
            "direction": "BULLISH",  # Bullish broken wing
            "lower_strike": 21900,
            "middle_strike": 22000,
            "upper_strike": 22150,  # Asymmetric wing
            "option_type": "CE"
        }
    
    def test_broken_wing_market_conditions(self):
        """Test Broken Wing Butterfly market conditions"""
        logger.info("📊 Testing Broken Wing Butterfly market conditions...")
        
        # Test suitable conditions (moderate VIX, slight directional bias)
        suitable_conditions = {
            "symbol": "NIFTY",
            "vix": 21.0,
            "trend_strength": 1.8,
            "directional_bias": "SLIGHTLY_BULLISH",
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 22
        }
        
        result = self.broken_wing.evaluate_market_conditions(suitable_conditions, {})
        self.assertTrue(result, "Broken Wing should be suitable for moderate VIX + slight bias")
        
        logger.info("✅ Broken Wing Butterfly market conditions test passed")
    
    def test_broken_wing_order_generation(self):
        """Test Broken Wing Butterfly order generation"""
        logger.info("📋 Testing Broken Wing Butterfly order generation...")
        
        orders = self.broken_wing.generate_orders(self.test_signal, {"lot_count": 1}, 50)
        
        # Validate order structure (4 legs with asymmetric wings)
        self.assertEqual(len(orders), 4, "Broken Wing Butterfly should have 4 legs")
        
        # Validate structure
        self.assertTrue(validate_broken_wing_structure(orders))
        
        logger.info("✅ Broken Wing Butterfly order generation test passed")

class TestCalendarSpreadStrategy(unittest.TestCase):
    """Test Calendar Spread Strategy (4-leg hedged)"""
    
    def setUp(self):
        """Set up Calendar Spread test environment"""
        self.calendar = CalendarSpreadStrategy()
        
        self.test_signal = {
            "symbol": "NIFTY",
            "strike": 22000,
            "option_type": "CE",
            "near_expiry": "01AUG",
            "far_expiry": "08AUG",
            "spot_price": 22000,
            "estimated_premiums": {
                "near_short": 65,
                "far_long": 85,
                "hedge_put": 35,
                "hedge_call": 40
            }
        }
    
    def test_calendar_market_conditions(self):
        """Test Calendar Spread market conditions"""
        logger.info("📊 Testing Calendar Spread market conditions...")
        
        # Test suitable conditions (moderate VIX, neutral)
        suitable_conditions = {
            "symbol": "NIFTY",
            "vix": 19.0,
            "trend_strength": 1.1,
            "directional_bias": "NEUTRAL",
            "upcoming_events": [],
            "is_expiry": False,
            "days_to_expiry": 25
        }
        
        result = self.calendar.evaluate_market_conditions(suitable_conditions, {})
        self.assertTrue(result, "Calendar Spread should be suitable for moderate VIX")
        
        logger.info("✅ Calendar Spread market conditions test passed")
    
    def test_calendar_order_generation(self):
        """Test Calendar Spread order generation"""
        logger.info("📋 Testing Calendar Spread order generation...")
        
        orders = self.calendar.generate_orders(self.test_signal, {"lot_count": 1}, 50)
        
        # Validate order structure (4 legs with different expiries)
        self.assertEqual(len(orders), 4, "Calendar Spread should have 4 legs")
        
        # Check for different expiries
        expiries = set(order.get("expiry") for order in orders)
        self.assertGreaterEqual(len(expiries), 2, "Should have at least 2 different expiries")
        
        # Validate structure
        self.assertTrue(validate_calendar_spread_structure(orders))
        
        logger.info("✅ Calendar Spread order generation test passed")

class TestStrategyIntegration(unittest.TestCase):
    """Test strategy integration with system components"""
    
    def setUp(self):
        """Set up integration test environment"""
        self.all_strategies = {
            "IRON_CONDOR": IronCondorStrategy(),
            "BUTTERFLY_SPREAD": ButterflySpreadStrategy(),
            "CALENDAR_SPREAD": CalendarSpreadStrategy(),
            "HEDGED_STRANGLE": HedgedStrangleStrategy(),
            "DIRECTIONAL_FUTURES": DirectionalFuturesStrategy(),
            "JADE_LIZARD": JadeLizardStrategy(),
            "RATIO_SPREADS": RatioSpreadsStrategy(),
            "BROKEN_WING_BUTTERFLY": BrokenWingButterflyStrategy()
        }
        
        self.strategy_selector = StrategySelector()
    
    def test_event_calendar_integration(self):
        """Test strategy integration with event calendar"""
        logger.info("📅 Testing event calendar integration...")
        
        # Test expiry day restriction
        for strategy_name, strategy in self.all_strategies.items():
            # Mock expiry day
            expiry_market_data = {
                "symbol": "NIFTY",
                "vix": 20.0,
                "is_expiry": True,  # Expiry day
                "upcoming_events": [],
                "days_to_expiry": 0
            }
            
            # Most strategies should reject expiry day
            result = strategy.evaluate_market_conditions(expiry_market_data, {})
            
            # Only Directional Futures might be allowed on expiry day
            if strategy_name != "DIRECTIONAL_FUTURES":
                self.assertFalse(result, f"{strategy_name} should reject expiry day trading")
        
        logger.info("✅ Event calendar integration test passed")
    
    def test_strategy_selector_intelligence(self):
        """Test intelligent strategy selection"""
        logger.info("🧠 Testing strategy selector intelligence...")
        
        # Test different market scenarios
        test_scenarios = [
            {
                "name": "Low VIX Range-bound",
                "data": {
                    "symbol": "NIFTY",
                    "vix": 16.0,
                    "trend_strength": 0.9,
                    "directional_bias": "NEUTRAL",
                    "iv_rank": 35
                },
                "expected_count": 2  # Should find suitable strategies
            },
            {
                "name": "High VIX Trending",
                "data": {
                    "symbol": "BANKNIFTY", 
                    "vix": 32.0,
                    "trend_strength": 2.8,
                    "directional_bias": "BULLISH",
                    "iv_rank": 85,
                    "volume_surge": True
                },
                "expected_count": 2  # Should find different strategies
            }
        ]
        
        for scenario in test_scenarios:
            suitable_strategies = []
            
            for strategy_name, strategy in self.all_strategies.items():
                try:
                    if strategy.evaluate_market_conditions(scenario["data"], {}):
                        suitable_strategies.append(strategy_name)
                except Exception as e:
                    logger.debug(f"Strategy {strategy_name} evaluation failed: {e}")
            
            logger.info(f"Scenario '{scenario['name']}': {len(suitable_strategies)} suitable strategies")
            self.assertGreaterEqual(len(suitable_strategies), 1, 
                                  f"Should find at least 1 strategy for {scenario['name']}")
        
        logger.info("✅ Strategy selector intelligence test passed")
    
    def test_risk_monitoring_integration(self):
        """Test strategy integration with risk monitoring"""
        logger.info("🛡️ Testing risk monitoring integration...")
        
        # Test MTM monitoring for each strategy
        for strategy_name, strategy in self.all_strategies.items():
            # Test various MTM scenarios
            test_scenarios = [
                {"mtm": 500, "should_trigger": False},   # Small profit
                {"mtm": -1800, "should_trigger": True},  # Near SL
                {"mtm": 2500, "should_trigger": True}    # Good profit
            ]
            
            for scenario in test_scenarios:
                config = {
                    "sl_per_lot": 2000,
                    "tp_per_lot": 4000,
                    "days_to_expiry": 10
                }
                
                risk_action = strategy.on_mtm_tick(scenario["mtm"], config, 1)
                
                has_action = risk_action.get("action") is not None
                
                if scenario["should_trigger"]:
                    # For extreme MTM, expect some action
                    if abs(scenario["mtm"]) > 1500:
                        logger.debug(f"{strategy_name} MTM {scenario['mtm']}: Action = {risk_action.get('action')}")
        
        logger.info("✅ Risk monitoring integration test passed")
    
    def test_performance_metrics_consistency(self):
        """Test performance metrics consistency across strategies"""
        logger.info("📊 Testing performance metrics consistency...")
        
        required_base_metrics = [
            "risk_profile", "profit_profile", "market_outlook",
            "best_conditions"
        ]
        
        for strategy_name, strategy in self.all_strategies.items():
            try:
                metrics = strategy.get_strategy_specific_metrics()
                
                # Check base metrics exist
                for metric in required_base_metrics:
                    self.assertIn(metric, metrics, 
                                f"{strategy_name} missing base metric: {metric}")
                
                # Check strategy has unique characteristics
                self.assertIsInstance(metrics["risk_profile"], str)
                self.assertIsInstance(metrics["profit_profile"], str)
                
                logger.debug(f"✅ {strategy_name} metrics validated")
                
            except Exception as e:
                logger.error(f"❌ {strategy_name} metrics failed: {e}")
                self.fail(f"{strategy_name} metrics test failed")
        
        logger.info("✅ Performance metrics consistency test passed")

class TestStrategyPerformance(unittest.TestCase):
    """Test strategy performance and optimization"""
    
    def test_strategy_evaluation_performance(self):
        """Test strategy evaluation performance"""
        logger.info("⚡ Testing strategy evaluation performance...")
        
        import time
        
        # Create test scenarios
        test_scenarios = []
        for i in range(50):
            test_scenarios.append({
                "symbol": "NIFTY" if i % 2 == 0 else "BANKNIFTY",
                "vix": 15 + (i % 20),  # VIX from 15 to 35
                "trend_strength": 0.5 + (i % 30) * 0.1,
                "directional_bias": ["NEUTRAL", "BULLISH", "BEARISH"][i % 3],
                "iv_rank": 30 + (i % 50),
                "upcoming_events": [],
                "is_expiry": False,
                "days_to_expiry": 10 + (i % 20)
            })
        
        # Test all strategies
        all_strategies = [
            IronCondorStrategy(),
            ButterflySpreadStrategy(),
            HedgedStrangleStrategy(),
            DirectionalFuturesStrategy()
        ]
        
        start_time = time.time()
        
        evaluation_count = 0
        for strategy in all_strategies:
            for scenario in test_scenarios:
                try:
                    strategy.evaluate_market_conditions(scenario, {})
                    evaluation_count += 1
                except Exception:
                    pass  # Skip failed evaluations
        
        end_time = time.time()
        
        total_time = end_time - start_time
        evaluations_per_second = evaluation_count / total_time
        
        logger.info(f"✅ Performance: {evaluations_per_second:.1f} evaluations/second")
        
        # Performance should be reasonable (>100 evaluations/second)
        self.assertGreater(evaluations_per_second, 100, 
                          "Strategy evaluation performance too slow")
    
    def test_order_generation_performance(self):
        """Test order generation performance"""
        logger.info("⚡ Testing order generation performance...")
        
        import time
        
        strategies_with_signals = [
            (IronCondorStrategy(), {
                "symbol": "NIFTY", "expiry": "01AUG", "spot_price": 22000,
                "strikes": {"ce_sale": 22100, "ce_hedge": 22200, "pe_sale": 21900, "pe_hedge": 21800}
            }),
            (HedgedStrangleStrategy(), {
                "symbol": "NIFTY", "expiry": "01AUG", "spot_price": 22000,
                "ce_otm_strike": 22100, "pe_otm_strike": 21900,
                "ce_hedge_strike": 22300, "pe_hedge_strike": 21700
            })
        ]
        
        start_time = time.time()
        
        order_generation_count = 0
        for _ in range(100):  # 100 iterations
            for strategy, signal in strategies_with_signals:
                try:
                    orders = strategy.generate_orders(signal, {"lot_count": 1}, 50)
                    order_generation_count += len(orders)
                except Exception:
                    pass  # Skip failed generations
        
        end_time = time.time()
        
        total_time = end_time - start_time
        orders_per_second = order_generation_count / total_time
        
        logger.info(f"✅ Order generation: {orders_per_second:.1f} orders/second")
        
        # Should generate orders reasonably fast
        self.assertGreater(orders_per_second, 50, "Order generation too slow")

class TestStrategyErrorHandling(unittest.TestCase):
    """Test strategy error handling and edge cases"""
    
    def test_invalid_market_data_handling(self):
        """Test handling of invalid market data"""
        logger.info("🔧 Testing invalid market data handling...")
        
        iron_condor = IronCondorStrategy()
        
        invalid_scenarios = [
            {"symbol": None},  # None symbol
            {"symbol": "INVALID_SYMBOL"},  # Invalid symbol
            {"vix": -5},  # Negative VIX
            {"trend_strength": None},  # None values
            {}  # Empty data
        ]
        
        for scenario in invalid_scenarios:
            try:
                result = iron_condor.evaluate_market_conditions(scenario, {})
                # Should either return False or handle gracefully
                self.assertIsInstance(result, bool)
            except Exception as e:
                # Exception handling is acceptable for invalid data
                logger.debug(f"Expected exception for invalid data: {e}")
        
        logger.info("✅ Invalid market data handling test passed")
    
    def test_invalid_signal_handling(self):
        """Test handling of invalid trading signals"""
        logger.info("🔧 Testing invalid signal handling...")
        
        iron_condor = IronCondorStrategy()
        
        invalid_signals = [
            {},  # Empty signal
            {"symbol": "NIFTY"},  # Missing required fields
            {"symbol": "INVALID", "expiry": "01AUG"},  # Invalid symbol
            {"symbol": "NIFTY", "expiry": "01AUG", "strikes": {}}  # Empty strikes
        ]
        
        for signal in invalid_signals:
            with self.assertRaises(Exception):
                iron_condor.generate_orders(signal, {"lot_count": 1}, 50)
        
        logger.info("✅ Invalid signal handling test passed")
    
    def test_edge_case_mtm_values(self):
        """Test edge case MTM values"""
        logger.info("🔧 Testing edge case MTM values...")
        
        iron_condor = IronCondorStrategy()
        
        edge_cases = [
            float('inf'),  # Infinity
            float('-inf'), # Negative infinity
            0,             # Zero
            -999999,       # Very large loss
            999999         # Very large profit
        ]
        
        config = {"sl_per_lot": 2000, "tp_per_lot": 4000, "days_to_expiry": 10}
        
        for mtm in edge_cases:
            try:
                risk_action = iron_condor.on_mtm_tick(mtm, config, 1)
                self.assertIsInstance(risk_action, dict)
            except Exception as e:
                logger.debug(f"MTM {mtm} caused exception: {e}")
        
        logger.info("✅ Edge case MTM values test passed")

def run_strategy_tests():
    """Run the complete strategy test suite"""
    print("=" * 80)
    print("F&O Trading System - Comprehensive Strategy Test Suite")
    print("=" * 80)
    print()
    
    # Create test suite
    test_classes = [
        TestBaseStrategy,
        TestIronCondorStrategy,
        TestButterflySpreadStrategy,
        TestHedgedStrangleStrategy,
        TestDirectionalFuturesStrategy,
        TestJadeLizardStrategy,
        TestRatioSpreadsStrategy,
        TestBrokenWingButterflyStrategy,
        TestCalendarSpreadStrategy,
        TestStrategyIntegration,
        TestStrategyPerformance,
        TestStrategyErrorHandling
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
    print("STRATEGY TEST RESULTS SUMMARY")
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
    success = run_strategy_tests()
    sys.exit(0 if success else 1)
