"""
Abstract Base Strategy Interface for F&O Trading System
All hedged strategies must implement this interface
Enforces consistent structure and risk management across all strategies
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

logger = logging.getLogger("base_strategy")

@dataclass
class StrategySignal:
    """Standardized strategy signal structure"""
    action: str  # "ENTER", "EXIT", "HOLD", "ADJUST"
    confidence: float  # 0.0 to 1.0
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    expected_return: float
    max_loss: float
    time_horizon: int  # Days
    message: str

@dataclass
class OrderLeg:
    """Individual order leg in a multi-leg strategy"""
    symbol: str
    side: str  # "BUY", "SELL"
    quantity: int
    order_type: str  # "MARKET", "LIMIT", "SL"
    price: float
    is_hedge: bool
    leg_type: str  # "main_leg", "hedge_leg", "adjustment_leg"
    priority: int  # Execution order (1 = highest priority)

class BaseStrategy(ABC):
    """
    Abstract base class for all Fces minimum 2-leg hedged structure and consistent interface
    """
    
    def __init__(self):
        self.name: str = ""
        self.min_legs: int = 2  # Minimum hedged structure
        self.max_legs: int = 6  # Maximum complexity allowed
        self.required_hedge: bool = True  # Must have hedge protection
        self.is_active: bool = True
        self.last_signal: Optional[StrategySignal] = None
        self.performance_metrics: Dict[str, float] = {}
        
        # Risk parameters (overridden by subclasses)
        self.max_position_size: int = 10  # Maximum lots
        self.max_loss_per_trade: float = 5000.0  # Maximum loss per trade
        self.target_win_rate: float = 75.0  # Target win rate percentage
        
        # Market condition filters
        self.min_vix: float = 0.0
        self.max_vix: float = 50.0
        self.allowed_instruments: List[str] = ["NIFTY", "BANKNIFTY"]
        self.blocked_on_expiry: bool = True
        self.blocked_on_events: bool = True
    
    @abstractmethod
    def evaluate_market_conditions(self, market_data: Dict[str, Any], 
                                 settings: Dict[str, Any]) -> bool:
        """
        Evaluate if current market conditions are suitable for this strategy
        
        Args:
            market_data: Current market data (VIX, price, volume, etc.)
            settings: System settings and risk parameters
            
        Returns:
            bool: True if conditions are suitable, False otherwise
        """
        pass
    
    @abstractmethod
    def generate_orders(self, signal: Dict[str, Any], config: Dict[str, Any], 
                       lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate the complete order set for the strategy
        
        Args:
            signal: Entry signal with strikes, expiry, etc.
            config: Strategy-specific configuration
            lot_size: Number of lots to trade
            
        Returns:
            List of order dictionaries with all legs
        """
        pass
    
    @abstractmethod
    def on_mtm_tick(self, mtm: float, config: Dict[str, Any], 
                    lot_count: int) -> Dict[str, Any]:
        """
        Handle real-time MTM updates and generate exit/adjust signals
        
        Args:
            mtm: Current mark-to-market P&L
            config: Strategy configuration
            lot_count: Number of lots in position
            
        Returns:
            Dict with action ("HOLD", "EXIT", "ADJUST") and reason
        """
        pass
    
    def validate_strategy_structure(self, orders: List[Dict[str, Any]]) -> bool:
        """
        Validate that strategy meets hedged requirements
        """
        if len(orders) < self.min_legs:
            logger.error(f"Strategy {self.name} has insufficient legs: {len(orders)} < {self.min_legs}")
            return False
        
        if len(orders) > self.max_legs:
            logger.error(f"Strategy {self.name} too complex: {len(orders)} > {self.max_legs}")
            return False
        
        # Check for hedge protection
        if self.required_hedge:
            has_hedge = any(order.get("is_hedge", False) for order in orders)
            if not has_hedge:
                logger.error(f"Strategy {self.name} missing required hedge protection")
                return False
        
        # Validate instruments
        for order in orders:
            symbol = order.get("symbol", "")
            base_symbol = self._extract_base_symbol(symbol)
            if base_symbol not in self.allowed_instruments:
                logger.error(f"Strategy {self.name} using blocked instrument: {base_symbol}")
                return False
        
        return True
    
    def calculate_position_risk(self, orders: List[Dict[str, Any]], 
                              spot_price: float) -> Dict[str, float]:
        """
        Calculate comprehensive risk metrics for the position
        """
        risk_metrics = {
            "max_loss": 0.0,
            "max_profit": 0.0,
            "breakeven_points": [],
            "gamma_risk": 0.0,
            "theta_decay": 0.0,
            "vega_risk": 0.0,
            "margin_required": 0.0
        }
        
        try:
            # Calculate maximum theoretical loss
            buy_orders = [o for o in orders if o.get("side") == "BUY"]
            sell_orders = [o for o in orders if o.get("side") == "SELL"]
            
            total_premium_paid = sum(
                o.get("quantity", 0) * o.get("price", 0) for o in buy_orders
            )
            total_premium_received = sum(
                o.get("quantity", 0) * o.get("price", 0) for o in sell_orders
            )
            
            net_premium = total_premium_received - total_premium_paid
            
            # For most hedged strategies, max loss is limited
            if net_premium > 0:  # Net credit
                risk_metrics["max_profit"] = net_premium
                # Max loss calculation depends on strategy type
                risk_metrics["max_loss"] = self._calculate_max_loss(orders, spot_price)
            else:  # Net debit
                risk_metrics["max_loss"] = abs(net_premium)
                risk_metrics["max_profit"] = self._calculate_max_profit(orders, spot_price)
            
            # Estimate margin requirement (simplified)
            risk_metrics["margin_required"] = max(
                risk_metrics["max_loss"] * 1.5,  # SPAN margin approximation
                50000  # Minimum margin
            )
            
        except Exception as e:
            logger.error(f"Risk calculation failed for {self.name}: {e}")
            risk_metrics["max_loss"] = self.max_loss_per_trade  # Fallback
        
        return risk_metrics
    
    def _calculate_max_loss(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """Calculate maximum possible loss (strategy-specific override)"""
        # Default implementation - override in specific strategies
        return self.max_loss_per_trade
    
    def _calculate_max_profit(self, orders: List[Dict[str, Any]], spot_price: float) -> float:
        """Calculate maximum possible profit (strategy-specific override)"""
        # Default implementation - override in specific strategies
        return self.max_loss_per_trade * 2  # 1:2 risk reward default
    
    def check_exit_conditions(self, current_data: Dict[str, Any], 
                            entry_data: Dict[str, Any]) -> Optional[StrategySignal]:
        """
        Check various exit conditions beyond MTM-based exits
        """
        exit_reasons = []
        
        # Time-based exit
        if self._check_time_exit(current_data, entry_data):
            exit_reasons.append("TIME_EXIT")
        
        # Volatility-based exit
        if self._check_volatility_exit(current_data, entry_data):
            exit_reasons.append("VOLATILITY_EXIT")
        
        # Market condition change exit
        if self._check_market_regime_exit(current_data, entry_data):
            exit_reasons.append("REGIME_CHANGE")
        
        if exit_reasons:
            return StrategySignal(
                action="EXIT",
                confidence=0.8,
                risk_level="MEDIUM",
                expected_return=0.0,
                max_loss=0.0,
                time_horizon=0,
                message=f"Exit triggered: {', '.join(exit_reasons)}"
            )
        
        return None
    
    def _check_time_exit(self, current_data: Dict[str, Any], 
                        entry_data: Dict[str, Any]) -> bool:
        """Check if position should be exited based on time"""
        entry_time = entry_data.get("entry_time", datetime.now())
        current_time = current_data.get("current_time", datetime.now())
        
        # Exit before expiry day
        expiry_date = entry_data.get("expiry_date")
        if expiry_date:
            days_to_expiry = (expiry_date - current_time).days
            if days_to_expiry <= 1:  # Exit 1 day before expiry
                return True
        
        # Exit at end of day
        if current_time.hour >= 15 and current_time.minute >= 10:
            return True
        
        return False
    
    def _check_volatility_exit(self, current_data: Dict[str, Any], 
                             entry_data: Dict[str, Any]) -> bool:
        """Check if volatility has changed significantly"""
        entry_vix = entry_data.get("entry_vix", 20.0)
        current_vix = current_data.get("vix", 20.0)
        
        # Exit if VIX has changed by more than 50%
        vix_change_pct = abs(current_vix - entry_vix) / entry_vix * 100
        return vix_change_pct > 50.0
    
    def _check_market_regime_exit(self, current_data: Dict[str, Any], 
                                entry_data: Dict[str, Any]) -> bool:
        """Check if market regime has changed"""
        entry_regime = entry_data.get("market_regime", "UNKNOWN")
        current_regime = current_data.get("market_regime", "UNKNOWN")
        
        # Exit if regime has changed significantly
        incompatible_regimes = {
            ("LOW_VOLATILITY", "HIGH_VOLATILITY"),
            ("SIDEWAYS", "TRENDING_UP"),
            ("SIDEWAYS", "TRENDING_DOWN")
        }
        
        return (entry_regime, current_regime) in incompatible_regimes
    
    def _extract_base_symbol(self, symbol: str) -> str:
        """Extract base symbol from option/futures symbol"""
        import re
        base = re.sub(r'\d{2}[A-Z]{3}\d+[CP]E?|FUT', '', symbol)
        return base.replace("NSE:", "").replace("NFO:", "").replace("BSE:", "")
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get comprehensive strategy information"""
        return {
            "name": self.name,
            "min_legs": self.min_legs,
            "max_legs": self.max_legs,
            "required_hedge": self.required_hedge,
            "is_active": self.is_active,
            "max_position_size": self.max_position_size,
            "max_loss_per_trade": self.max_loss_per_trade,
            "target_win_rate": self.target_win_rate,
            "allowed_instruments": self.allowed_instruments,
            "vix_range": {"min": self.min_vix, "max": self.max_vix},
            "blocked_on_expiry": self.blocked_on_expiry,
            "blocked_on_events": self.blocked_on_events
        }
    
    def update_performance_metrics(self, trade_result: Dict[str, Any]):
        """Update strategy performance metrics"""
        if "performance_metrics" not in self.__dict__:
            self.performance_metrics = {
                "total_trades": 0,
                "winning_trades": 0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0,
                "win_rate": 0.0,
                "max_drawdown": 0.0
            }
        
        # Update metrics
        self.performance_metrics["total_trades"] += 1
        pnl = trade_result.get("pnl", 0.0)
        self.performance_metrics["total_pnl"] += pnl
        
        if pnl > 0:
            self.performance_metrics["winning_trades"] += 1
        
        # Recalculate derived metrics
        self.performance_metrics["avg_pnl"] = (
            self.performance_metrics["total_pnl"] / 
            self.performance_metrics["total_trades"]
        )
        self.performance_metrics["win_rate"] = (
            self.performance_metrics["winning_trades"] / 
            self.performance_metrics["total_trades"] * 100
        )
        
        logger.info(f"Updated {self.name} performance: "
                   f"Trades: {self.performance_metrics['total_trades']}, "
                   f"Win Rate: {self.performance_metrics['win_rate']:.1f}%, "
                   f"Avg P&L: ₹{self.performance_metrics['avg_pnl']:.0f}")

# Utility functions for strategy validation
def validate_hedged_structure(orders: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Validate that order structure represents a properly hedged strategy
    """
    if len(orders) < 2:
        return False, "Insufficient legs for hedged strategy"
    
    has_long = any(order.get("side") == "BUY" for order in orders)
    has_short = any(order.get("side") == "SELL" for order in orders)
    
    if not (has_long and has_short):
        return False, "Strategy must have both long and short positions"
    
    # Check for explicit hedge
    has_hedge = any(order.get("is_hedge", False) for order in orders)
    if not has_hedge:
        return False, "Strategy missing explicit hedge protection"
    
    return True, "Valid hedged structure"

def calculate_net_premium(orders: List[Dict[str, Any]]) -> float:
    """Calculate net premium for the strategy"""
    net_premium = 0.0
    
    for order in orders:
        quantity = order.get("quantity", 0)
        price = order.get("price", 0.0)
        side = order.get("side", "")
        
        if side == "SELL":
            net_premium += quantity * price
        elif side == "BUY":
            net_premium -= quantity * price
    
    return net_premium

# Export all classes and functions
__all__ = [
    "BaseStrategy",
    "StrategySignal", 
    "OrderLeg",
    "validate_hedged_structure",
    "calculate_net_premium"
]
