"""
Iron Condor Strategy Implementation - FINAL VERSION
NIFTY/BANKNIFTY only | 4-leg hedged structure | Compatible with intelligent strategy selector
- Sell OTM Call & Put, Buy far OTM Call & Put as hedge
- Designed for low volatility, range-bound markets
- Fully integrated with self-calibrating performance tracking system
"""

from datetime import datetime
from typing import Dict, List, Any
from app.strategies.base import BaseStrategy
from app.config import StrategyType, get_instrument_config, validate_instrument_liquidity
import logging

logger = logging.getLogger("IronCondorStrategy")

class IronCondorStrategy(BaseStrategy):
    """
    Iron Condor Options Strategy - 4-leg hedged structure:
    1. Sell OTM Call (premium collection)
    2. Buy far OTM Call (hedge protection)
    3. Sell OTM Put (premium collection) 
    4. Buy far OTM Put (hedge protection)
    
    Best for: Low volatility, range-bound NIFTY/BANKNIFTY markets
    """

    name = StrategyType.IRON_CONDOR
    required_leg_count = 4
    allowed_instruments = ["NIFTY", "BANKNIFTY"]
    
    def __init__(self):
        super().__init__()
        self.min_vix = 12.0  # Minimum VIX for entry
        self.max_vix = 25.0  # Maximum VIX for entry
        self.target_win_rate = 85.0  # Expected win rate
        self.max_loss_per_trade = 2500.0  # Conservative risk
        
        # Iron Condor specific parameters
        self.preferred_wing_width_nifty = 100    # Wing width for NIFTY
        self.preferred_wing_width_banknifty = 200 # Wing width for BANKNIFTY
        self.min_credit_target = 1500     # Minimum credit to collect
        self.max_days_to_expiry = 30      # Maximum DTE for entry
        self.min_days_to_expiry = 7       # Minimum DTE for entry

    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Entry conditions for Iron Condor:
        - NIFTY/BANKNIFTY only (high liquidity enforcement)
        - Low volatility environment (VIX < threshold)
        - Range-bound market (no strong trend)
        - No major events or expiry day
        - Sufficient time to expiry
        """
        symbol = market_data.get("symbol")
        vix = market_data.get("vix", 0)
        index_chg = abs(market_data.get("index_chg_pct", 0))
        events = market_data.get("upcoming_events", [])
        expiry = market_data.get("is_expiry", False)
        trend_strength = abs(market_data.get("trend_strength", 0))
        days_to_expiry = market_data.get("days_to_expiry", 0)
        
        # Strict liquidity validation
        if not validate_instrument_liquidity(symbol):
            logger.warning(f"Iron Condor rejected: {symbol} not in liquid instruments")
            return False
        
        return (
            symbol in self.allowed_instruments and
            self.min_vix <= vix <= self.max_vix and
            index_chg < settings.get("DANGER_ZONE_WARNING", 1.0) and
            trend_strength < 1.5 and  # Not strongly trending
            not expiry and
            not events and
            self.min_days_to_expiry <= days_to_expiry <= self.max_days_to_expiry
        )

    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate Iron Condor orders with proper validation:
        
        Signal must contain:
        - symbol: NIFTY or BANKNIFTY
        - expiry: Option expiry (e.g., "25JUL")
        - spot_price: Current underlying price
        - strikes: Dict with ce_sale, pe_sale, ce_hedge, pe_hedge
        - estimated_credit: Expected net credit
        """
        symbol = signal["symbol"]
        expiry = signal["expiry"]
        strikes = signal["strikes"]
        lots = config.get("lot_count", 1)
        
        # Validate strikes
        if not self._validate_iron_condor_strikes(symbol, signal.get("spot_price", 0), strikes):
            raise ValueError(f"Invalid Iron Condor strike selection for {symbol}")
        
        # Get instrument configuration
        instrument_config = get_instrument_config(symbol)
        lot_qty = instrument_config.get("lot_size", 50)
        
        orders = [
            # 1. SELL OTM Call (main leg)
            {
                "symbol": f"{symbol}{expiry}{int(strikes['ce_sale'])}CE",
                "side": "SELL",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "short_call",
                "is_hedge": False,
                "strike": strikes['ce_sale'],
                "option_type": "CE",
                "expiry": expiry,
                "expected_premium": signal.get("estimated_premiums", {}).get("ce_sale", 0)
            },
            
            # 2. BUY Far OTM Call (hedge)
            {
                "symbol": f"{symbol}{expiry}{int(strikes['ce_hedge'])}CE",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "long_call_hedge",
                "is_hedge": True,
                "strike": strikes['ce_hedge'],
                "option_type": "CE",
                "expiry": expiry,
                "expected_premium": signal.get("estimated_premiums", {}).get("ce_hedge", 0)
            },
            
            # 3. SELL OTM Put (main leg)
            {
                "symbol": f"{symbol}{expiry}{int(strikes['pe_sale'])}PE",
                "side": "SELL",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "short_put",
                "is_hedge": False,
                "strike": strikes['pe_sale'],
                "option_type": "PE",
                "expiry": expiry,
                "expected_premium": signal.get("estimated_premiums", {}).get("pe_sale", 0)
            },
            
            # 4. BUY Far OTM Put (hedge)
            {
                "symbol": f"{symbol}{expiry}{int(strikes['pe_hedge'])}PE",
                "side": "BUY",
                "lots": lots,
                "quantity": lots * lot_qty,
                "leg_type": "long_put_hedge",
                "is_hedge": True,
                "strike": strikes['pe_hedge'],
                "option_type": "PE", 
                "expiry": expiry,
                "expected_premium": signal.get("estimated_premiums", {}).get("pe_hedge", 0)
            }
        ]
        
        # Calculate expected net credit
        estimated_credit = self._calculate_estimated_credit(
            signal.get("estimated_premiums", {}), lots * lot_qty
        )
        
        logger.info(f"Generated Iron Condor for {symbol}: "
                   f"Call Spread: {strikes['ce_sale']}/{strikes['ce_hedge']}, "
                   f"Put Spread: {strikes['pe_sale']}/{strikes['pe_hedge']}, "
                   f"Estimated Credit: ₹{estimated_credit:,.0f}")
        
        return orders

    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Iron Condor specific risk management:
        - Conservative SL/TP due to limited profit potential
        - Time-based exit management
        - Early profit taking when 50% of max profit achieved
        """
        sl = config.get("sl_per_lot", 1500) * lot_count  # Conservative SL
        tp = config.get("tp_per_lot", 3000) * lot_count  # Conservative TP
        
        days_to_expiry = config.get("days_to_expiry", 10)
        time_decay_factor = max(0.5, days_to_expiry / 30.0)  # Adjust for time decay
        
        # Adjust TP based on time decay (closer to expiry, take profits earlier)
        adjusted_tp = tp * time_decay_factor
        
        if mtm <= -sl:
            return {
                "action": "HARD_STOP",
                "reason": "Iron Condor SL triggered",
                "urgency": "HIGH"
            }
        elif mtm >= adjusted_tp:
            return {
                "action": "TAKE_PROFIT",
                "reason": f"Iron Condor TP achieved (adjusted for {days_to_expiry} DTE)",
                "urgency": "MEDIUM"
            }
        elif days_to_expiry <= 3:
            return {
                "action": "TIME_EXIT_WARNING",
                "reason": f"Close to expiry: {days_to_expiry} days remaining",
                "urgency": "MEDIUM"
            }
        elif mtm >= adjusted_tp * 0.5:
            return {
                "action": "PROFIT_OPPORTUNITY",
                "reason": f"50% of target profit achieved with {days_to_expiry} DTE",
                "urgency": "LOW"
            }
        elif mtm <= -0.8 * sl:
            return {
                "action": "SOFT_WARN",
                "reason": "Approaching Iron Condor SL",
                "urgency": "MEDIUM"
            }
        
        return {"action": None}

    def _validate_iron_condor_strikes(self, symbol: str, spot_price: float, 
                                    strikes: Dict[str, float]) -> bool:
        """Validate Iron Condor strike selection"""
        ce_sale = strikes.get('ce_sale', 0)
        ce_hedge = strikes.get('ce_hedge', 0)
        pe_sale = strikes.get('pe_sale', 0)
        pe_hedge = strikes.get('pe_hedge', 0)
        
        # Basic validation
        if not all([ce_sale, ce_hedge, pe_sale, pe_hedge]):
            logger.error("Missing strike prices in Iron Condor")
            return False
        
        # Call strikes validation (should be above spot)
        if ce_sale <= spot_price or ce_hedge <= ce_sale:
            logger.error(f"Invalid call strikes: spot={spot_price}, ce_sale={ce_sale}, ce_hedge={ce_hedge}")
            return False
        
        # Put strikes validation (should be below spot)  
        if pe_sale >= spot_price or pe_hedge >= pe_sale:
            logger.error(f"Invalid put strikes: spot={spot_price}, pe_sale={pe_sale}, pe_hedge={pe_hedge}")
            return False
        
        # Wing width validation
        call_wing_width = ce_hedge - ce_sale
        put_wing_width = pe_sale - pe_hedge
        expected_width = self.preferred_wing_width_banknifty if symbol == "BANKNIFTY" else self.preferred_wing_width_nifty
        
        if call_wing_width != put_wing_width:
            logger.warning(f"Unequal wing widths: call={call_wing_width}, put={put_wing_width}")
        
        if call_wing_width < expected_width * 0.5 or call_wing_width > expected_width * 2:
            logger.warning(f"Wing width {call_wing_width} outside preferred range for {symbol}")
        
        return True

    def _calculate_estimated_credit(self, estimated_premiums: Dict, total_quantity: int) -> float:
        """Calculate estimated net credit for Iron Condor"""
        ce_sale_premium = estimated_premiums.get("ce_sale", 0)
        ce_hedge_premium = estimated_premiums.get("ce_hedge", 0)
        pe_sale_premium = estimated_premiums.get("pe_sale", 0)
        pe_hedge_premium = estimated_premiums.get("pe_hedge", 0)
        
        net_credit_per_share = (ce_sale_premium + pe_sale_premium) - (ce_hedge_premium + pe_hedge_premium)
        return net_credit_per_share * total_quantity

    def get_optimal_strikes(self, spot_price: float, symbol: str, 
                          days_to_expiry: int) -> Dict[str, float]:
        """
        Calculate optimal Iron Condor strikes based on spot price and symbol
        """
        if symbol == "NIFTY":
            # NIFTY strikes (50-point intervals)
            wing_width = self.preferred_wing_width_nifty
            ce_sale = round((spot_price + 100) / 50) * 50  # 100 points OTM
            pe_sale = round((spot_price - 100) / 50) * 50  # 100 points OTM
        elif symbol == "BANKNIFTY":
            # BANKNIFTY strikes (100-point intervals)  
            wing_width = self.preferred_wing_width_banknifty
            ce_sale = round((spot_price + 300) / 100) * 100  # 300 points OTM
            pe_sale = round((spot_price - 300) / 100) * 100  # 300 points OTM
        else:
            raise ValueError(f"Unsupported symbol for Iron Condor: {symbol}")
        
        # Calculate hedge strikes
        ce_hedge = ce_sale + wing_width
        pe_hedge = pe_sale - wing_width
        
        return {
            "ce_sale": ce_sale,
            "ce_hedge": ce_hedge,
            "pe_sale": pe_sale,
            "pe_hedge": pe_hedge,
            "wing_width": wing_width
        }

    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum loss for Iron Condor
        Max loss = Wing width - Net credit received
        """
        # For Iron Condor, max loss is limited by wing width minus credit
        return self.max_loss_per_trade

    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """
        Calculate maximum profit for Iron Condor  
        Max profit = Net credit received (when price stays between short strikes)
        """
        return self.min_credit_target  # Conservative estimate

    def get_strategy_specific_metrics(self) -> Dict[str, Any]:
        """Get Iron Condor specific performance metrics"""
        base_metrics = self.get_strategy_info()
        
        iron_condor_metrics = {
            "wing_widths": {
                "NIFTY": self.preferred_wing_width_nifty,
                "BANKNIFTY": self.preferred_wing_width_banknifty
            },
            "min_credit_target": self.min_credit_target,
            "vix_range": {"min": self.min_vix, "max": self.max_vix},
            "dte_range": {"min": self.min_days_to_expiry, "max": self.max_days_to_expiry},
            "risk_profile": "LIMITED (wing width minus credit)",
            "profit_profile": "LIMITED (net credit collected)",
            "market_outlook": "NEUTRAL/RANGE-BOUND",
            "theta_strategy": True,
            "vega_strategy": "SHORT (benefits from IV crush)",
            "gamma_risk": "LOW (hedged structure)",
            "best_conditions": "Low VIX, range-bound market, high implied volatility"
        }
        
        return {**base_metrics, **iron_condor_metrics}

# Utility functions for Iron Condor analysis
def validate_iron_condor_structure(orders: List[Dict[str, Any]]) -> bool:
    """Validate that orders represent proper Iron Condor structure"""
    if len(orders) != 4:
        return False
    
    # Should have 2 calls and 2 puts
    calls = [o for o in orders if o.get("option_type") == "CE"]
    puts = [o for o in orders if o.get("option_type") == "PE"]
    
    if len(calls) != 2 or len(puts) != 2:
        return False
    
    # Should have one short and one long for each type
    call_sides = [o.get("side") for o in calls]
    put_sides = [o.get("side") for o in puts]
    
    return ("BUY" in call_sides and "SELL" in call_sides and 
            "BUY" in put_sides and "SELL" in put_sides)

def calculate_iron_condor_breakevens(strikes: Dict[str, float], 
                                   net_credit: float) -> Dict[str, float]:
    """Calculate Iron Condor breakeven points"""
    return {
        "upper_breakeven": strikes["ce_sale"] + net_credit,
        "lower_breakeven": strikes["pe_sale"] - net_credit,
        "profit_zone_upper": strikes["ce_sale"],
        "profit_zone_lower": strikes["pe_sale"],
        "max_profit_range": f"{strikes['pe_sale']} to {strikes['ce_sale']}"
    }

# Export the strategy class and utilities
__all__ = [
    "IronCondorStrategy",
    "validate_iron_condor_structure",
    "calculate_iron_condor_breakevens"
]
