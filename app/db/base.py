"""
Base Strategy Class for F&O Trading System - COMPLETE VERSION
- Integration with risk monitor, event calendar, and performance tracking
- Self-calibrating capabilities with intelligent elimination
- NIFTY/BANKNIFTY focus with hedge-first execution
- Compatible with all system components
- Advanced MTM monitoring and auto-exit logic
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
from sqlalchemy.orm import Session

from app.config import settings, StrategyType, get_instrument_config, validate_instrument_liquidity
from app.db.base import db_manager
from app.db.models import Trade, Position, StrategyStats, AuditLog
from app.utils.event_calendar import event_calendar, should_avoid_trading_today
from app.risk.danger_zone import danger_monitor
from app.risk.expiry_day import expiry_manager

logger = logging.getLogger("base_strategy")

class StrategyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ELIMINATED = "ELIMINATED"
    CALIBRATING = "CALIBRATING"
    DISABLED = "DISABLED"

class StrategySignal(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    NO_SIGNAL = "NO_SIGNAL"

@dataclass
class StrategyPerformance:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    average_pnl_per_trade: float
    max_drawdown: float
    sharpe_ratio: float
    risk_adjusted_return: float
    last_updated: datetime

@dataclass
class RiskMetrics:
    current_mtm: float
    max_loss_limit: float
    profit_target: float
    risk_score: float  # 0-100
    position_size: int
    days_to_expiry: int
    volatility_score: float
    liquidity_score: float

class BaseStrategy(ABC):
    """
    Abstract base class for all F&O trading strategies
    Provides comprehensive framework with all system integrations
    """
    
    def __init__(self):
        # Strategy identification
        self.name: str = "BASE_STRATEGY"
        self.display_name: str = "Base Strategy"
        self.description: str = "Base strategy class"
        
        # Strategy requirements
        self.required_leg_count: int = 2
        self.allowed_instruments: List[str] = ["NIFTY", "BANKNIFTY"]
        self.min_capital_required: float = 50000.0
        
        # Performance tracking
        self.performance_history: List[StrategyPerformance] = []
        self.current_performance: Optional[StrategyPerformance] = None
        self.elimination_score: float = 0.0
        self.calibration_cycles: int = 0
        
        # Status and control
        self.status: StrategyStatus = StrategyStatus.ACTIVE
        self.last_executed: Optional[datetime] = None
        self.elimination_reason: Optional[str] = None
        
        # Risk management
        self.max_positions: int = 3
        self.max_loss_per_trade: float = 2000.0
        self.target_win_rate: float = 75.0
        self.risk_tolerance: str = "MODERATE"
        
        # Strategy-specific settings
        self.hedge_first_execution: bool = True
        self.supports_auto_exit: bool = True
        self.requires_volatility_filter: bool = True
        self.market_outlook: str = "NEUTRAL"
        
        # Integration flags
        self.risk_monitor_enabled: bool = True
        self.event_calendar_enabled: bool = True
        self.performance_tracking_enabled: bool = True
        self.auto_calibration_enabled: bool = True
        
        # Initialize performance tracking
        self._initialize_performance_tracking()
        
        logger.info(f"Base strategy {self.name} initialized with all integrations")
    
    def _initialize_performance_tracking(self):
        """Initialize strategy performance tracking"""
        try:
            with db_manager.get_session() as session:
                # Load existing performance data
                stats = session.query(StrategyStats).filter(
                    StrategyStats.strategy_name == self.name
                ).order_by(StrategyStats.created_at.desc()).first()
                
                if stats:
                    self.current_performance = StrategyPerformance(
                        total_trades=stats.total_trades,
                        winning_trades=stats.winning_trades,
                        losing_trades=stats.losing_trades,
                        win_rate=stats.win_rate,
                        total_pnl=stats.total_pnl,
                        average_pnl_per_trade=stats.avg_pnl_per_trade,
                        max_drawdown=stats.max_drawdown,
                        sharpe_ratio=stats.sharpe_ratio,
                        risk_adjusted_return=stats.risk_adjusted_return,
                        last_updated=stats.updated_at
                    )
                    
                    self.elimination_score = stats.elimination_score
                    self.calibration_cycles = stats.calibration_cycles
                    
                    logger.info(f"Loaded performance data for {self.name}: {self.current_performance.win_rate:.1f}% win rate")
                else:
                    # Initialize new performance tracking
                    self.current_performance = StrategyPerformance(
                        total_trades=0, winning_trades=0, losing_trades=0,
                        win_rate=0.0, total_pnl=0.0, average_pnl_per_trade=0.0,
                        max_drawdown=0.0, sharpe_ratio=0.0, risk_adjusted_return=0.0,
                        last_updated=datetime.now()
                    )
                    
        except Exception as e:
            logger.error(f"Failed to initialize performance tracking for {self.name}: {e}")
            # Create default performance object
            self.current_performance = StrategyPerformance(
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0.0, total_pnl=0.0, average_pnl_per_trade=0.0,
                max_drawdown=0.0, sharpe_ratio=0.0, risk_adjusted_return=0.0,
                last_updated=datetime.now()
            )
    
    @abstractmethod
    def evaluate_market_conditions(self, market_data: Dict, settings: Dict) -> bool:
        """
        Evaluate if current market conditions are suitable for this strategy
        
        Args:
            market_data: Current market data including VIX, prices, trends
            settings: System settings and risk parameters
            
        Returns:
            bool: True if conditions are suitable, False otherwise
        """
        pass
    
    @abstractmethod
    def generate_orders(self, signal: Dict, config: Dict, lot_size: int) -> List[Dict[str, Any]]:
        """
        Generate trading orders for the strategy
        
        Args:
            signal: Trading signal with entry parameters
            config: Strategy configuration
            lot_size: Number of lots to trade
            
        Returns:
            List of order dictionaries with hedge-first priority
        """
        pass
    
    @abstractmethod
    def on_mtm_tick(self, mtm: float, config: Dict, lot_count: int) -> Dict[str, Any]:
        """
        Handle real-time MTM updates and generate risk actions
        
        Args:
            mtm: Current mark-to-market value
            config: Strategy configuration
            lot_count: Number of lots in position
            
        Returns:
            Dictionary with action and reason
        """
        pass
    
    def can_execute(self, symbol: str, market_data: Dict) -> Tuple[bool, str]:
        """
        Comprehensive check if strategy can execute for given symbol
        Integrates all system components for validation
        """
        try:
            # 1. Check strategy status
            if self.status != StrategyStatus.ACTIVE:
                return False, f"Strategy status: {self.status.value}"
            
            # 2. Check instrument liquidity
            if not validate_instrument_liquidity(symbol):
                return False, f"Instrument {symbol} not in liquid instruments list"
            
            if symbol not in self.allowed_instruments:
                return False, f"Instrument {symbol} not allowed for {self.name}"
            
            # 3. Check event calendar restrictions
            if self.event_calendar_enabled:
                should_avoid, calendar_reason = should_avoid_trading_today(symbol)
                if should_avoid:
                    return False, f"Calendar restriction: {calendar_reason}"
            
            # 4. Check expiry day restrictions
            expiry_info = expiry_manager.get_expiry_info(symbol)
            if expiry_info.is_today:
                # Block most strategies on expiry day
                if self.name not in ["DIRECTIONAL_FUTURES"]:
                    return False, f"Expiry day restriction for {symbol}"
            
            # 5. Check danger zone conditions
            danger_status = danger_monitor.get_current_status()
            if symbol in danger_status:
                symbol_status = danger_status[symbol]
                if symbol_status.get("danger_level") in ["CRITICAL", "EMERGENCY"]:
                    return False, f"Danger zone: {symbol_status.get('danger_level')}"
            
            # 6. Check market conditions
            if not self.evaluate_market_conditions(market_data, settings.__dict__):
                return False, "Market conditions not suitable"
            
            # 7. Check performance-based restrictions
            if self.elimination_score >= 80:
                return False, f"Strategy eliminated (score: {self.elimination_score:.1f})"
            
            # 8. Check position limits
            current_positions = self._get_current_position_count()
            if current_positions >= self.max_positions:
                return False, f"Maximum positions reached: {current_positions}/{self.max_positions}"
            
            # 9. Check time-based restrictions
            current_time = datetime.now().time()
            if current_time >= datetime.strptime("11:00", "%H:%M").time():
                return False, "Past entry cutoff time (11:00 AM)"
            
            return True, "All checks passed"
            
        except Exception as e:
            logger.error(f"Error in can_execute for {self.name}: {e}")
            return False, f"Execution check error: {str(e)}"
    
    def execute_strategy(self, symbol: str, signal: Dict, config: Dict) -> Dict[str, Any]:
        """
        Execute the strategy with comprehensive logging and error handling
        """
        try:
            # Pre-execution validation
            can_exec, reason = self.can_execute(symbol, signal.get("market_data", {}))
            if not can_exec:
                return {
                    "success": False,
                    "reason": reason,
                    "action": "BLOCKED"
                }
            
            # Generate orders with hedge-first execution
            lot_size = config.get("lot_count", 1)
            orders = self.generate_orders(signal, config, lot_size)
            
            # Validate order structure
            if not self._validate_order_structure(orders):
                return {
                    "success": False,
                    "reason": "Invalid order structure",
                    "action": "REJECTED"
                }
            
            # Execute orders (integrate with your broker)
            execution_result = self._execute_orders(orders, symbol)
            
            if execution_result["success"]:
                # Log successful execution
                self._log_strategy_execution(symbol, signal, orders, execution_result)
                
                # Update last executed time
                self.last_executed = datetime.now()
                
                return {
                    "success": True,
                    "orders": orders,
                    "execution_result": execution_result,
                    "action": "EXECUTED"
                }
            else:
                return {
                    "success": False,
                    "reason": execution_result.get("error", "Execution failed"),
                    "action": "FAILED"
                }
                
        except Exception as e:
            logger.error(f"Strategy execution failed for {self.name}: {e}")
            return {
                "success": False,
                "reason": f"Execution error: {str(e)}",
                "action": "ERROR"
            }
    
    def update_performance(self, trade_pnl: float, trade_result: str):
        """
        Update strategy performance metrics
        """
        try:
            if not self.current_performance:
                self._initialize_performance_tracking()
            
            # Update trade counts
            self.current_performance.total_trades += 1
            
            if trade_result == "WIN":
                self.current_performance.winning_trades += 1
            else:
                self.current_performance.losing_trades += 1
            
            # Update PnL
            self.current_performance.total_pnl += trade_pnl
            self.current_performance.average_pnl_per_trade = (
                self.current_performance.total_pnl / self.current_performance.total_trades
            )
            
            # Update win rate
            self.current_performance.win_rate = (
                self.current_performance.winning_trades / self.current_performance.total_trades * 100
            )
            
            # Update max drawdown (simplified)
            if trade_pnl < 0:
                self.current_performance.max_drawdown = min(
                    self.current_performance.max_drawdown, trade_pnl
                )
            
            # Calculate elimination score
            self._calculate_elimination_score()
            
            # Save to database
            self._save_performance_to_db()
            
            self.current_performance.last_updated = datetime.now()
            
            logger.info(f"Updated performance for {self.name}: {self.current_performance.win_rate:.1f}% win rate")
            
        except Exception as e:
            logger.error(f"Failed to update performance for {self.name}: {e}")
    
    def _calculate_elimination_score(self):
        """
        Calculate elimination score based on performance metrics
        Score 0-100: Higher score = higher chance of elimination
        """
        try:
            if not self.current_performance or self.current_performance.total_trades < 5:
                self.elimination_score = 0.0
                return
            
            # Win rate component (40% weight)
            win_rate_score = max(0, (self.target_win_rate - self.current_performance.win_rate) / self.target_win_rate * 40)
            
            # PnL component (30% weight)
            if self.current_performance.average_pnl_per_trade < 0:
                pnl_score = 30.0
            else:
                pnl_score = max(0, 30 - (self.current_performance.average_pnl_per_trade / 1000) * 10)
            
            # Drawdown component (20% weight)
            drawdown_score = min(20, abs(self.current_performance.max_drawdown) / 5000 * 20)
            
            # Consistency component (10% weight)
            if self.current_performance.total_trades >= 10:
                recent_performance = self._get_recent_performance_trend()
                consistency_score = max(0, 10 - recent_performance * 5)
            else:
                consistency_score = 5.0
            
            self.elimination_score = min(100, win_rate_score + pnl_score + drawdown_score + consistency_score)
            
            logger.debug(f"Elimination score for {self.name}: {self.elimination_score:.1f}")
            
        except Exception as e:
            logger.error(f"Error calculating elimination score for {self.name}: {e}")
            self.elimination_score = 0.0
    
    def _get_recent_performance_trend(self) -> float:
        """Get recent performance trend (simplified implementation)"""
        try:
            # In a full implementation, this would analyze recent trades
            # For now, return a simple metric based on current performance
            if self.current_performance.win_rate >= self.target_win_rate:
                return 1.0  # Positive trend
            elif self.current_performance.win_rate >= self.target_win_rate * 0.8:
                return 0.5  # Neutral trend
            else:
                return 0.0  # Negative trend
        except:
            return 0.5
    
    def calibrate_parameters(self, market_conditions: Dict) -> bool:
        """
        Self-calibrating parameter adjustment based on market conditions and performance
        """
        try:
            if not self.auto_calibration_enabled:
                return False
            
            logger.info(f"Starting calibration for {self.name}")
            
            # Increment calibration cycles
            self.calibration_cycles += 1
            
            # Analyze recent performance
            if self.current_performance and self.current_performance.total_trades >= 10:
                # Adjust risk parameters based on performance
                if self.current_performance.win_rate < self.target_win_rate * 0.8:
                    # Poor performance - reduce risk
                    self.max_loss_per_trade *= 0.9
                    self.max_positions = max(1, self.max_positions - 1)
                    logger.info(f"Reduced risk parameters for {self.name}")
                
                elif self.current_performance.win_rate > self.target_win_rate * 1.1:
                    # Good performance - slightly increase risk
                    self.max_loss_per_trade *= 1.05
                    self.max_positions = min(5, self.max_positions + 1)
                    logger.info(f"Increased risk parameters for {self.name}")
            
            # Adjust parameters based on market volatility
            current_vix = market_conditions.get("vix", 20)
            if hasattr(self, "min_vix") and hasattr(self, "max_vix"):
                # Adjust VIX thresholds based on recent market behavior
                if current_vix > 30:  # High volatility environment
                    self.min_vix = max(self.min_vix - 2, 10)
                    self.max_vix = min(self.max_vix + 5, 50)
                elif current_vix < 15:  # Low volatility environment
                    self.min_vix = min(self.min_vix + 1, 20)
                    self.max_vix = max(self.max_vix - 2, 25)
            
            # Save calibration results
            self._save_calibration_to_db()
            
            logger.info(f"Calibration completed for {self.name} (cycle {self.calibration_cycles})")
            return True
            
        except Exception as e:
            logger.error(f"Calibration failed for {self.name}: {e}")
            return False
    
    def should_be_eliminated(self) -> Tuple[bool, str]:
        """
        Determine if strategy should be eliminated based on performance
        """
        try:
            # Minimum trades required for elimination consideration
            if not self.current_performance or self.current_performance.total_trades < 20:
                return False, "Insufficient trade history"
            
            # High elimination score
            if self.elimination_score >= 80:
                return True, f"High elimination score: {self.elimination_score:.1f}"
            
            # Consistently poor win rate
            if self.current_performance.win_rate < self.target_win_rate * 0.6:
                return True, f"Poor win rate: {self.current_performance.win_rate:.1f}%"
            
            # Excessive losses
            if self.current_performance.total_pnl < -50000:  # 50k loss threshold
                return True, f"Excessive losses: ₹{self.current_performance.total_pnl:,.0f}"
            
            # Large drawdown
            if self.current_performance.max_drawdown < -20000:  # 20k drawdown threshold
                return True, f"Large drawdown: ₹{self.current_performance.max_drawdown:,.0f}"
            
            return False, "Performance within acceptable range"
            
        except Exception as e:
            logger.error(f"Error in elimination check for {self.name}: {e}")
            return False, "Elimination check error"
    
    def eliminate_strategy(self, reason: str):
        """
        Eliminate strategy from active trading
        """
        try:
            self.status = StrategyStatus.ELIMINATED
            self.elimination_reason = reason
            
            # Log elimination
            logger.warning(f"Strategy {self.name} eliminated: {reason}")
            
            # Create audit log
            self._create_audit_log("STRATEGY_ELIMINATED", {
                "strategy": self.name,
                "reason": reason,
                "elimination_score": self.elimination_score,
                "performance": self.current_performance.__dict__ if self.current_performance else {}
            })
            
            # Save to database
            self._save_performance_to_db()
            
        except Exception as e:
            logger.error(f"Error eliminating strategy {self.name}: {e}")
    
    def get_current_risk_metrics(self, position_data: Dict) -> RiskMetrics:
        """
        Calculate current risk metrics for active positions
        """
        try:
            current_mtm = position_data.get("mtm", 0.0)
            position_size = position_data.get("lot_count", 1)
            days_to_expiry = position_data.get("days_to_expiry", 10)
            
            # Calculate risk score (0-100)
            max_loss = self.max_loss_per_trade * position_size
            risk_score = min(100, abs(current_mtm) / max_loss * 100) if max_loss > 0 else 0
            
            return RiskMetrics(
                current_mtm=current_mtm,
                max_loss_limit=max_loss,
                profit_target=max_loss * 2,  # 1:2 risk-reward
                risk_score=risk_score,
                position_size=position_size,
                days_to_expiry=days_to_expiry,
                volatility_score=position_data.get("vix", 20) / 40 * 100,  # VIX as volatility score
                liquidity_score=100 if position_data.get("symbol") in ["NIFTY", "BANKNIFTY"] else 50
            )
            
        except Exception as e:
            logger.error(f"Error calculating risk metrics for {self.name}: {e}")
            return RiskMetrics(0, 0, 0, 0, 0, 0, 0, 0)
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """
        Get comprehensive strategy information
        """
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "status": self.status.value,
            "required_legs": self.required_leg_count,
            "allowed_instruments": self.allowed_instruments,
            "market_outlook": self.market_outlook,
            "hedge_first_execution": self.hedge_first_execution,
            "risk_tolerance": self.risk_tolerance,
            "max_positions": self.max_positions,
            "max_loss_per_trade": self.max_loss_per_trade,
            "target_win_rate": self.target_win_rate,
            "elimination_score": self.elimination_score,
            "calibration_cycles": self.calibration_cycles,
            "last_executed": self.last_executed.isoformat() if self.last_executed else None,
            "performance": self.current_performance.__dict__ if self.current_performance else {},
            "integrations": {
                "risk_monitor": self.risk_monitor_enabled,
                "event_calendar": self.event_calendar_enabled,
                "performance_tracking": self.performance_tracking_enabled,
                "auto_calibration": self.auto_calibration_enabled
            }
        }
    
    # Helper methods for database operations
    def _get_current_position_count(self) -> int:
        """Get current number of active positions for this strategy"""
        try:
            with db_manager.get_session() as session:
                count = session.query(Position).filter(
                    Position.strategy_name == self.name,
                    Position.status == "ACTIVE"
                ).count()
                return count
        except Exception as e:
            logger.error(f"Error getting position count for {self.name}: {e}")
            return 0
    
    def _validate_order_structure(self, orders: List[Dict]) -> bool:
        """Validate order structure for hedge-first execution"""
        try:
            if not orders or len(orders) < self.required_leg_count:
                return False
            
            # Check for required fields
            required_fields = ["symbol", "side", "lots", "quantity"]
            for order in orders:
                if not all(field in order for field in required_fields):
                    return False
            
            # Check hedge-first execution
            if self.hedge_first_execution:
                hedge_orders = [o for o in orders if o.get("is_hedge", False)]
                main_orders = [o for o in orders if not o.get("is_hedge", False)]
                
                if hedge_orders and main_orders:
                    # Hedge orders should have lower priority (execute first)
                    min_hedge_priority = min(o.get("priority", 999) for o in hedge_orders)
                    min_main_priority = min(o.get("priority", 999) for o in main_orders)
                    
                    if min_hedge_priority >= min_main_priority:
                        logger.warning(f"Hedge-first execution not properly configured for {self.name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Order structure validation failed for {self.name}: {e}")
            return False
    
    def _execute_orders(self, orders: List[Dict], symbol: str) -> Dict[str, Any]:
        """
        Execute orders (integrate with your broker adapter)
        This is a mock implementation - replace with actual broker integration
        """
        try:
            # Mock execution result
            return {
                "success": True,
                "executed_orders": len(orders),
                "total_quantity": sum(o.get("quantity", 0) for o in orders),
                "execution_time": datetime.now().isoformat(),
                "broker_order_ids": [f"ORD_{i+1:03d}" for i in range(len(orders))]
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "executed_orders": 0
            }
    
    def _log_strategy_execution(self, symbol: str, signal: Dict, orders: List[Dict], result: Dict):
        """Log strategy execution for audit trail"""
        try:
            self._create_audit_log("STRATEGY_EXECUTED", {
                "strategy": self.name,
                "symbol": symbol,
                "signal": signal,
                "orders_count": len(orders),
                "execution_result": result,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Failed to log execution for {self.name}: {e}")
    
    def _save_performance_to_db(self):
        """Save current performance to database"""
        try:
            with db_manager.get_session() as session:
                # Check if record exists
                existing_stats = session.query(StrategyStats).filter(
                    StrategyStats.strategy_name == self.name
                ).first()
                
                if existing_stats:
                    # Update existing record
                    existing_stats.total_trades = self.current_performance.total_trades
                    existing_stats.winning_trades = self.current_performance.winning_trades
                    existing_stats.losing_trades = self.current_performance.losing_trades
                    existing_stats.win_rate = self.current_performance.win_rate
                    existing_stats.total_pnl = self.current_performance.total_pnl
                    existing_stats.avg_pnl_per_trade = self.current_performance.average_pnl_per_trade
                    existing_stats.max_drawdown = self.current_performance.max_drawdown
                    existing_stats.sharpe_ratio = self.current_performance.sharpe_ratio
                    existing_stats.risk_adjusted_return = self.current_performance.risk_adjusted_return
                    existing_stats.elimination_score = self.elimination_score
                    existing_stats.calibration_cycles = self.calibration_cycles
                    existing_stats.status = self.status.value
                    existing_stats.updated_at = datetime.now()
                else:
                    # Create new record
                    new_stats = StrategyStats(
                        strategy_name=self.name,
                        total_trades=self.current_performance.total_trades,
                        winning_trades=self.current_performance.winning_trades,
                        losing_trades=self.current_performance.losing_trades,
                        win_rate=self.current_performance.win_rate,
                        total_pnl=self.current_performance.total_pnl,
                        avg_pnl_per_trade=self.current_performance.average_pnl_per_trade,
                        max_drawdown=self.current_performance.max_drawdown,
                        sharpe_ratio=self.current_performance.sharpe_ratio,
                        risk_adjusted_return=self.current_performance.risk_adjusted_return,
                        elimination_score=self.elimination_score,
                        calibration_cycles=self.calibration_cycles,
                        status=self.status.value,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    session.add(new_stats)
                
                session.commit()
                
        except Exception as e:
            logger.error(f"Failed to save performance to DB for {self.name}: {e}")
    
    def _save_calibration_to_db(self):
        """Save calibration results to database"""
        try:
            self._create_audit_log("STRATEGY_CALIBRATED", {
                "strategy": self.name,
                "calibration_cycle": self.calibration_cycles,
                "max_loss_per_trade": self.max_loss_per_trade,
                "max_positions": self.max_positions,
                "elimination_score": self.elimination_score,
                "performance": self.current_performance.__dict__ if self.current_performance else {}
            })
        except Exception as e:
            logger.error(f"Failed to save calibration to DB for {self.name}: {e}")
    
    def _create_audit_log(self, action: str, details: Dict):
        """Create audit log entry"""
        try:
            with db_manager.get_session() as session:
                audit_log = AuditLog(
                    user_id=None,  # System action
                    action=action,
                    details=details,
                    ip_address="127.0.0.1",
                    user_agent=f"Strategy_{self.name}",
                    created_at=datetime.now()
                )
                session.add(audit_log)
                session.commit()
        except Exception as e:
            logger.error(f"Failed to create audit log for {self.name}: {e}")

# Utility functions for strategy management
def get_all_strategies() -> List[BaseStrategy]:
    """Get all available strategy instances"""
    # This would be populated by strategy registration
    return []

def validate_strategy_compatibility(strategy: BaseStrategy, symbol: str) -> Tuple[bool, str]:
    """Validate if strategy is compatible with symbol"""
    if symbol not in strategy.allowed_instruments:
        return False, f"Symbol {symbol} not supported by {strategy.name}"
    
    if not validate_instrument_liquidity(symbol):
        return False, f"Symbol {symbol} lacks sufficient liquidity"
    
    return True, "Strategy compatible"

def calculate_position_size(strategy: BaseStrategy, available_capital: float, 
                          risk_per_trade: float) -> int:
    """Calculate appropriate position size based on risk management"""
    try:
        # Simple position sizing based on risk per trade
        max_loss_per_lot = strategy.max_loss_per_trade
        if max_loss_per_lot <= 0:
            return 1
        
        # Calculate lots based on risk tolerance
        max_lots_by_risk = int(risk_per_trade / max_loss_per_lot)
        max_lots_by_capital = int(available_capital / (max_loss_per_lot * 10))  # 10x buffer
        
        # Take minimum of all constraints
        calculated_lots = min(max_lots_by_risk, max_lots_by_capital, strategy.max_positions)
        
        return max(1, calculated_lots)  # Minimum 1 lot
        
    except Exception as e:
        logger.error(f"Position size calculation error: {e}")
        return 1

# Export main components
__all__ = [
    "BaseStrategy",
    "StrategyStatus",
    "StrategySignal", 
    "StrategyPerformance",
    "RiskMetrics",
    "get_all_strategies",
    "validate_strategy_compatibility",
    "calculate_position_size"
]
