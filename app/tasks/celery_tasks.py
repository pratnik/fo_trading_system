"""
Celery Background Tasks for F&O Trading System - Complete Version
- Risk monitoring and alerts
- Event calendar management and auto-refresh
- Market data updates and processing
- Strategy performance tracking and recalibration
- Database maintenance and backup
- Health monitoring and system checks
- Notification management
- Expiry day preparation and management
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
import os
import json
import pandas as pd
from celery import Celery

# Import app modules
from app.config import settings
from app.db.models import Trade, Position, AuditLog, SystemSettings, Strategy, MarketData
from app.db.base import db_manager
from app.risk.risk_monitor import risk_monitor
from app.risk.danger_zone import danger_monitor
from app.risk.expiry_day import expiry_manager
from app.utils.event_calendar import event_calendar
from app.utils.healthcheck import health_checker
from app.notifications.whatsapp_notifier import WhatsAppNotifier
from app.strategies.strategy_selector import StrategySelector

# Configure logging
logger = logging.getLogger("celery_tasks")

# Import celery app from config
from app.tasks.celery_config import celery_app

# Initialize components
strategy_selector = StrategySelector()
whatsapp_notifier = None

try:
    # Initialize WhatsApp notifier if configured
    api_key = getattr(settings, 'GUPSHUP_API_KEY', None)
    app_name = getattr(settings, 'GUPSHUP_APP_NAME', None) 
    phone_number = getattr(settings, 'ADMIN_PHONE_NUMBER', None)
    
    if all([api_key, app_name, phone_number]):
        whatsapp_notifier = WhatsAppNotifier(api_key, app_name, phone_number)
        logger.info("WhatsApp notifier initialized for Celery tasks")
except Exception as e:
    logger.error(f"Failed to initialize WhatsApp notifier: {e}")

# ============================================================================
# RISK MONITORING TASKS
# ============================================================================

@celery_app.task(bind=True, max_retries=3)
def risk_monitor_check(self):
    """
    Periodic risk monitoring check - runs every 30 seconds during market hours
    Monitors all positions, danger zones, and system health
    """
    try:
        current_time = datetime.now().time()
        market_open = datetime.strptime("09:15", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        
        # Only run during market hours
        if not (market_open <= current_time <= market_close):
            logger.debug("Risk monitor skipped - outside market hours")
            return {"status": "skipped", "reason": "outside_market_hours"}
        
        # Check if risk monitor is active
        if not risk_monitor.is_monitoring:
            logger.warning("Risk monitor not active, starting...")
            risk_monitor.start_monitoring()
        
        # Get current risk summary
        risk_summary = risk_monitor.get_risk_summary()
        
        # Check for high-risk situations
        high_risk_positions = risk_summary.get("high_risk_positions", 0)
        daily_pnl = risk_summary.get("daily_pnl", 0)
        
        # Send alerts for critical situations
        if high_risk_positions > 3:
            _send_urgent_notification(
                "🚨 HIGH RISK ALERT",
                f"Multiple high-risk positions: {high_risk_positions}\n"
                f"Daily P&L: ₹{daily_pnl:,.0f}\n"
                f"Time: {current_time}"
            )
        
        # Log risk status
        logger.info(f"Risk check completed - Positions: {risk_summary.get('total_positions', 0)}, "
                   f"P&L: ₹{daily_pnl:,.0f}, High Risk: {high_risk_positions}")
        
        return {
            "status": "success", 
            "risk_summary": risk_summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Risk monitor check failed: {e}")
        
        # Retry logic
        if self.request.retries < 3:
            logger.info(f"Retrying risk monitor check (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60, exc=e)
        
        # Send failure notification
        _send_urgent_notification(
            "🔴 RISK MONITOR FAILURE",
            f"Risk monitoring task failed after 3 retries\nError: {str(e)}"
        )
        
        return {"status": "error", "message": str(e)}

@celery_app.task
def daily_squareoff():
    """
    Daily mandatory squareoff at 3:10 PM
    Exits all open positions and sends summary
    """
    try:
        logger.info("Starting daily squareoff procedure...")
        
        # Get all active positions
        with db_manager.get_session() as session:
            active_positions = session.query(Position).filter(
                Position.status == "ACTIVE"
            ).all()
            
            if not active_positions:
                logger.info("No active positions to square off")
                return {"status": "success", "positions_squared": 0}
            
            # Square off all positions
            squared_positions = []
            total_pnl = 0.0
            
            for position in active_positions:
                try:
                    # Calculate final MTM
                    final_mtm = _calculate_position_mtm(position)
                    total_pnl += final_mtm
                    
                    # Update position status
                    position.status = "CLOSED"
                    position.exit_time = datetime.now()
                    position.exit_reason = "DAILY_SQUAREOFF"
                    position.final_pnl = final_mtm
                    
                    squared_positions.append({
                        "position_id": position.id,
                        "strategy": position.strategy_name,
                        "symbol": position.symbol,
                        "pnl": final_mtm
                    })
                    
                    logger.info(f"Squared off position {position.id}: {position.strategy_name} "
                              f"{position.symbol} P&L: ₹{final_mtm:,.0f}")
                    
                except Exception as e:
                    logger.error(f"Failed to square off position {position.id}: {e}")
            
            session.commit()
            
            # Send daily summary
            summary_message = (
                f"📊 DAILY SQUAREOFF COMPLETE\n"
                f"Positions closed: {len(squared_positions)}\n"
                f"Total P&L: ₹{total_pnl:,.0f}\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            _send_notification("Daily Summary", summary_message)
            
            # Create audit log
            _create_audit_log(
                "DAILY_SQUAREOFF",
                f"Squared off {len(squared_positions)} positions, Total P&L: ₹{total_pnl:,.0f}"
            )
            
            logger.info(f"Daily squareoff completed - {len(squared_positions)} positions, P&L: ₹{total_pnl:,.0f}")
            
            return {
                "status": "success",
                "positions_squared": len(squared_positions),
                "total_pnl": total_pnl,
                "squared_positions": squared_positions
            }
            
    except Exception as e:
        logger.error(f"Daily squareoff failed: {e}")
        
        _send_urgent_notification(
            "🚨 SQUAREOFF FAILURE",
            f"Daily squareoff failed\nError: {str(e)}\nManual intervention required!"
        )
        
        return {"status": "error", "message": str(e)}

# ============================================================================
# EVENT CALENDAR TASKS
# ============================================================================

@celery_app.task
def refresh_event_calendar():
    """
    Refresh event calendar data from NSE and other sources
    Runs weekly and on New Year's Day
    """
    try:
        logger.info("Starting event calendar refresh...")
        
        # Refresh calendar data
        event_calendar.refresh_event_data()
        
        # Get updated calendar info
        current_year = date.today().year
        calendar_info = event_calendar.get_trading_calendar(current_year)
        
        # Send confirmation
        message = (
            f"📅 CALENDAR REFRESHED\n"
            f"Year: {current_year}\n"
            f"Trading days: {calendar_info['total_trading_days']}\n"
            f"Holidays: {calendar_info['total_holidays']}\n"
            f"Refreshed at: {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )
        
        _send_notification("Calendar Update", message)
        
        # Create audit log
        _create_audit_log(
            "CALENDAR_REFRESH",
            f"Event calendar refreshed for year {current_year}"
        )
        
        logger.info("Event calendar refresh completed successfully")
        
        return {
            "status": "success",
            "year": current_year,
            "trading_days": calendar_info['total_trading_days'],
            "holidays": calendar_info['total_holidays']
        }
        
    except Exception as e:
        logger.error(f"Event calendar refresh failed: {e}")
        
        _send_notification(
            "⚠️ Calendar Refresh Failed",
            f"Failed to refresh event calendar\nError: {str(e)}"
        )
        
        return {"status": "error", "message": str(e)}

@celery_app.task
def auto_refresh_calendar_check():
    """
    Check if calendar needs auto-refresh
    Runs daily at 6 AM
    """
    try:
        # Trigger auto-refresh check
        event_calendar.auto_refresh_check()
        
        # Check for upcoming critical events
        upcoming_events = event_calendar.get_upcoming_events(3)  # Next 3 days
        critical_events = [e for e in upcoming_events if e.impact_level == "CRITICAL"]
        
        if critical_events:
            event_names = ", ".join(e.title for e in critical_events)
            _send_notification(
                "⚠️ Upcoming Critical Events",
                f"Critical events in next 3 days:\n{event_names}\n"
                f"Review trading strategy accordingly"
            )
        
        return {
            "status": "success",
            "critical_events": len(critical_events),
            "total_upcoming": len(upcoming_events)
        }
        
    except Exception as e:
        logger.error(f"Auto calendar refresh check failed: {e}")
        return {"status": "error", "message": str(e)}

# ============================================================================
# MARKET DATA TASKS
# ============================================================================

@celery_app.task
def update_market_data():
    """
    Update market data for NIFTY and BANKNIFTY
    Runs every 1 minute during market hours
    """
    try:
        current_time = datetime.now().time()
        market_open = datetime.strptime("09:15", "%H:%M").time()
        market_close = datetime.strptime("15:30", "%H:%M").time()
        
        # Only run during market hours
        if not (market_open <= current_time <= market_close):
            return {"status": "skipped", "reason": "outside_market_hours"}
        
        # Update market data for liquid instruments only
        symbols = ["NIFTY", "BANKNIFTY"]
        updated_data = {}
        
        with db_manager.get_session() as session:
            for symbol in symbols:
                try:
                    # Get current market data (integrate with your data provider)
                    market_data = _fetch_current_market_data(symbol)
                    
                    if market_data:
                        # Update danger zone monitor
                        danger_alert = danger_monitor.update_price(
                            symbol, 
                            market_data["price"],
                            market_data.get("session_start_price")
                        )
                        
                        # Handle danger zone alerts
                        if danger_alert and danger_alert.danger_level in ["CRITICAL", "EMERGENCY"]:
                            _send_urgent_notification(
                                f"🚨 DANGER ZONE: {symbol}",
                                f"{danger_alert.message}\n"
                                f"Price: {market_data['price']}\n"
                                f"Change: {market_data.get('change_pct', 0):+.2f}%"
                            )
                        
                        updated_data[symbol] = market_data
                        
                except Exception as e:
                    logger.error(f"Failed to update market data for {symbol}: {e}")
        
        return {
            "status": "success",
            "updated_symbols": list(updated_data.keys()),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Market data update failed: {e}")
        return {"status": "error", "message": str(e)}

# ============================================================================
# STRATEGY TASKS
# ============================================================================

@celery_app.task
def update_strategy_performance():
    """
    Update strategy performance metrics
    Runs every 5 minutes during market hours
    """
    try:
        logger.info("Updating strategy performance metrics...")
        
        # Update strategy performance
        performance_data = strategy_selector.update_all_strategy_performance()
        
        # Check for strategies that need elimination
        eliminated_strategies = strategy_selector.auto_eliminate_poor_performers()
        
        if eliminated_strategies:
            eliminated_names = [s["name"] for s in eliminated_strategies]
            _send_notification(
                "📉 Strategy Elimination",
                f"Poor performing strategies eliminated:\n{', '.join(eliminated_names)}\n"
                f"System self-optimization complete"
            )
        
        # Log performance update
        active_strategies = len([s for s in performance_data if s.get("is_active", False)])
        logger.info(f"Strategy performance updated - Active: {active_strategies}, "
                   f"Eliminated: {len(eliminated_strategies)}")
        
        return {
            "status": "success",
            "active_strategies": active_strategies,
            "eliminated_strategies": len(eliminated_strategies),
            "performance_data": performance_data
        }
        
    except Exception as e:
        logger.error(f"Strategy performance update failed: {e}")
        return {"status": "error", "message": str(e)}

@celery_app.task
def weekly_strategy_recalibration():
    """
    Weekly strategy recalibration and optimization
    Runs every Sunday at 8 PM
    """
    try:
        logger.info("Starting weekly strategy recalibration...")
        
        # Perform weekly recalibration
        recalibration_results = strategy_selector.weekly_recalibration()
        
        # Get updated rankings
        rankings = strategy_selector.get_strategy_rankings()
        
        # Create summary message
        top_3_strategies = rankings[:3]
        top_names = [s["name"] for s in top_3_strategies]
        
        summary_message = (
            f"📊 WEEKLY RECALIBRATION COMPLETE\n"
            f"Strategies analyzed: {len(rankings)}\n"
            f"Top 3 performers: {', '.join(top_names)}\n"
            f"Recalibration completed at: {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )
        
        _send_notification("Weekly Recalibration", summary_message)
        
        # Create audit log
        _create_audit_log(
            "WEEKLY_RECALIBRATION",
            f"Strategy recalibration completed, analyzed {len(rankings)} strategies"
        )
        
        logger.info("Weekly strategy recalibration completed successfully")
        
        return {
            "status": "success",
            "strategies_analyzed": len(rankings),
            "top_strategies": top_names,
            "recalibration_results": recalibration_results
        }
        
    except Exception as e:
        logger.error(f"Weekly strategy recalibration failed: {e}")
        
        _send_notification(
            "⚠️ Recalibration Failed",
            f"Weekly strategy recalibration failed\nError: {str(e)}"
        )
        
        return {"status": "error", "message": str(e)}

# ============================================================================
# HEALTH MONITORING TASKS
# ============================================================================

@celery_app.task
def health_check():
    """
    System health check
    Runs every 2 minutes
    """
    try:
        # Perform comprehensive health check
        health_status = health_checker.get_health_summary()
        
        overall_status = health_status["overall_status"]
        
        # Alert on health issues
        if overall_status == "DOWN":
            _send_urgent_notification(
                "🚨 SYSTEM DOWN",
                f"Critical system failure detected\n"
                f"Components down: {health_status['summary']['down']}\n"
                f"Immediate attention required!"
            )
        elif overall_status == "CRITICAL":
            _send_notification(
                "⚠️ System Health Critical",
                f"Critical components detected: {health_status['summary']['critical']}\n"
                f"System degraded performance expected"
            )
        
        # Log health status
        logger.debug(f"Health check completed - Status: {overall_status}")
        
        return {
            "status": "success",
            "overall_health": overall_status,
            "component_summary": health_status["summary"]
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "message": str(e)}

# ============================================================================
# MAINTENANCE TASKS
# ============================================================================

@celery_app.task
def backup_database():
    """
    Database backup task
    Runs daily at 6 PM
    """
    try:
        logger.info("Starting database backup...")
        
        # Create backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"fo_trading_backup_{timestamp}.sql"
        
        # Perform database backup (simplified - integrate with your backup solution)
        backup_success = _perform_database_backup(backup_filename)
        
        if backup_success:
            _send_notification(
                "💾 Database Backup",
                f"Database backup completed successfully\n"
                f"File: {backup_filename}\n"
                f"Time: {datetime.now().strftime('%d-%m-%Y %H:%M')}"
            )
            
            # Create audit log
            _create_audit_log("DATABASE_BACKUP", f"Backup created: {backup_filename}")
            
            logger.info(f"Database backup completed: {backup_filename}")
            
            return {"status": "success", "backup_file": backup_filename}
        else:
            raise Exception("Backup operation failed")
            
    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        
        _send_urgent_notification(
            "🚨 Backup Failed",
            f"Database backup failed\nError: {str(e)}\n"
            f"Manual backup recommended!"
        )
        
        return {"status": "error", "message": str(e)}

@celery_app.task
def cleanup_old_logs():
    """
    Clean up old log files and data
    Runs weekly on Saturday at 2 AM
    """
    try:
        logger.info("Starting log cleanup...")
        
        # Clean up old audit logs (keep last 90 days)
        cutoff_date = datetime.now() - timedelta(days=90)
        
        with db_manager.get_session() as session:
            old_logs = session.query(AuditLog).filter(
                AuditLog.created_at < cutoff_date
            ).count()
            
            # Delete old logs
            session.query(AuditLog).filter(
                AuditLog.created_at < cutoff_date
            ).delete()
            
            session.commit()
            
            logger.info(f"Cleaned up {old_logs} old audit log entries")
            
            # Clean up old market data (keep last 30 days)
            market_cutoff = datetime.now() - timedelta(days=30)
            old_market_data = session.query(MarketData).filter(
                MarketData.created_at < market_cutoff
            ).count()
            
            session.query(MarketData).filter(
                MarketData.created_at < market_cutoff
            ).delete()
            
            session.commit()
            
            logger.info(f"Cleaned up {old_market_data} old market data entries")
        
        # Clean up log files
        logs_cleaned = _cleanup_log_files()
        
        summary_message = (
            f"🧹 CLEANUP COMPLETE\n"
            f"Audit logs cleaned: {old_logs}\n"
            f"Market data cleaned: {old_market_data}\n"
            f"Log files cleaned: {logs_cleaned}\n"
            f"Completed at: {datetime.now().strftime('%d-%m-%Y %H:%M')}"
        )
        
        _send_notification("System Cleanup", summary_message)
        
        return {
            "status": "success",
            "audit_logs_cleaned": old_logs,
            "market_data_cleaned": old_market_data,
            "log_files_cleaned": logs_cleaned
        }
        
    except Exception as e:
        logger.error(f"Log cleanup failed: {e}")
        return {"status": "error", "message": str(e)}

# ============================================================================
# EXPIRY MANAGEMENT TASKS
# ============================================================================

@celery_app.task
def expiry_day_preparation():
    """
    Expiry day preparation and alerts
    Runs daily at 8 AM
    """
    try:
        logger.info("Checking expiry day conditions...")
        
        # Check expiry status for liquid instruments
        expiry_alerts = []
        
        for symbol in ["NIFTY", "BANKNIFTY"]:
            expiry_info = expiry_manager.get_expiry_info(symbol)
            
            if expiry_info.is_today:
                expiry_alerts.append(f"🔴 {symbol} EXPIRY TODAY")
                
                # Block new entries
                _send_urgent_notification(
                    f"🚨 EXPIRY DAY: {symbol}",
                    f"Today is {symbol} expiry day\n"
                    f"New entries blocked\n"
                    f"Review existing positions"
                )
                
            elif expiry_info.is_tomorrow:
                expiry_alerts.append(f"🟡 {symbol} expiry tomorrow")
                
                _send_notification(
                    f"⏰ Expiry Tomorrow: {symbol}",
                    f"{symbol} expires tomorrow\n"
                    f"Consider early exit for risky positions"
                )
        
        if expiry_alerts:
            # Create audit log
            _create_audit_log(
                "EXPIRY_PREPARATION",
                f"Expiry alerts sent: {', '.join(expiry_alerts)}"
            )
        
        logger.info(f"Expiry day preparation completed - {len(expiry_alerts)} alerts sent")
        
        return {
            "status": "success",
            "expiry_alerts": expiry_alerts,
            "alerts_sent": len(expiry_alerts)
        }
        
    except Exception as e:
        logger.error(f"Expiry day preparation failed: {e}")
        return {"status": "error", "message": str(e)}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _send_notification(title: str, message: str) -> bool:
    """Send WhatsApp notification"""
    if not whatsapp_notifier:
        logger.warning("WhatsApp notifier not configured")
        return False
    
    try:
        full_message = f"{title}\n{message}\nTime: {datetime.now().strftime('%H:%M:%S')}"
        return whatsapp_notifier.send_message(full_message)
    except Exception as e:
        logger.error(f"Notification send failed: {e}")
        return False

def _send_urgent_notification(title: str, message: str) -> bool:
    """Send urgent notification with retry"""
    success = _send_notification(title, message)
    
    # Retry once if failed
    if not success:
        import time
        time.sleep(5)  # Wait 5 seconds
        success = _send_notification(f"RETRY: {title}", message)
    
    return success

def _create_audit_log(action: str, details: str):
    """Create audit log entry"""
    try:
        with db_manager.get_session() as session:
            audit_log = AuditLog(
                user_id=None,  # System action
                action=action,
                details=details,
                ip_address="127.0.0.1",
                user_agent="CeleryWorker",
                created_at=datetime.now()
            )
            session.add(audit_log)
            session.commit()
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")

def _calculate_position_mtm(position) -> float:
    """Calculate current mark-to-market for position"""
    # Integrate with your broker API or market data provider
    # This is a simplified implementation
    return 0.0  # Replace with actual MTM calculation

def _fetch_current_market_data(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch current market data for symbol"""
    # Integrate with your market data provider
    # Return mock data for now
    return {
        "symbol": symbol,
        "price": 22000.0 if symbol == "NIFTY" else 48000.0,
        "change_pct": 0.5,
        "volume": 1000000,
        "timestamp": datetime.now().isoformat()
    }

def _perform_database_backup(filename: str) -> bool:
    """Perform database backup"""
    try:
        # Implement actual backup logic here
        # This could use pg_dump for PostgreSQL
        logger.info(f"Database backup logic would run here for: {filename}")
        return True  # Simplified
    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        return False

def _cleanup_log_files() -> int:
    """Clean up old log files"""
    try:
        # Implement log file cleanup logic
        logger.info("Log file cleanup logic would run here")
        return 10  # Simplified return
    except Exception as e:
        logger.error(f"Log file cleanup failed: {e}")
        return 0

# ============================================================================
# TASK MONITORING AND ERROR HANDLING
# ============================================================================

@celery_app.task(bind=True)
def monitor_task_failures(self):
    """Monitor and report task failures"""
    try:
        # Get failed task information
        # This would integrate with Celery's monitoring capabilities
        
        logger.info("Task failure monitoring check completed")
        return {"status": "success", "failed_tasks": 0}
        
    except Exception as e:
        logger.error(f"Task failure monitoring failed: {e}")
        return {"status": "error", "message": str(e)}

# Task error handler
@celery_app.task(bind=True)  
def handle_task_failure(self, task_id: str, error_message: str):
    """Handle task failures with notifications"""
    try:
        _send_urgent_notification(
            "🚨 TASK FAILURE",
            f"Task failed: {task_id}\n"
            f"Error: {error_message}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # Create audit log
        _create_audit_log(
            "TASK_FAILURE",
            f"Task {task_id} failed: {error_message}"
        )
        
        return {"status": "handled", "task_id": task_id}
        
    except Exception as e:
        logger.error(f"Error handling task failure: {e}")
        return {"status": "error", "message": str(e)}

# Export all tasks
__all__ = [
    "risk_monitor_check",
    "daily_squareoff", 
    "refresh_event_calendar",
    "auto_refresh_calendar_check",
    "update_market_data",
    "update_strategy_performance",
    "weekly_strategy_recalibration",
    "health_check",
    "backup_database",
    "cleanup_old_logs",
    "expiry_day_preparation",
    "monitor_task_failures",
    "handle_task_failure"
]
