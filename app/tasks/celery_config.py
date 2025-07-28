"""
Celery Configuration for F&O Trading System - Complete Updated Version
Handles periodic tasks, monitoring, async job processing, and event calendar management
Includes all trading system automation and background tasks
"""

import os
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# Create Celery instance
celery_app = Celery(
    "fo_trading_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.celery_tasks"]
)

# Celery configuration
celery_app.conf.update(
    # Task routing
    task_routes={
        "app.tasks.celery_tasks.risk_monitor_check": {"queue": "risk"},
        "app.tasks.celery_tasks.daily_squareoff": {"queue": "trading"},
        "app.tasks.celery_tasks.backup_database": {"queue": "maintenance"},
        "app.tasks.celery_tasks.health_check": {"queue": "monitoring"},
        "app.tasks.celery_tasks.refresh_event_calendar": {"queue": "maintenance"},
        "app.tasks.celery_tasks.auto_refresh_calendar_check": {"queue": "maintenance"},
        "app.tasks.celery_tasks.update_market_data": {"queue": "trading"},
        "app.tasks.celery_tasks.update_strategy_performance": {"queue": "monitoring"},
        "app.tasks.celery_tasks.weekly_strategy_recalibration": {"queue": "maintenance"},
        "app.tasks.celery_tasks.expiry_day_preparation": {"queue": "trading"},
        "app.tasks.celery_tasks.cleanup_old_logs": {"queue": "maintenance"},
        "app.tasks.celery_tasks.danger_zone_monitor": {"queue": "risk"},
        "app.tasks.celery_tasks.position_mtm_update": {"queue": "trading"},
        "app.tasks.celery_tasks.broker_heartbeat_check": {"queue": "monitoring"},
        "app.tasks.celery_tasks.whatsapp_notification_queue": {"queue": "notifications"}
    },
    
    # Task execution
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=False,
    
    # Task time limits
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    
    # Worker configuration
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=True,
    worker_send_task_events=True,
    
    # Result backend settings
    result_expires=3600,  # 1 hour
    result_persistent=True,
    
    # Monitoring
    task_send_sent_event=True,
    task_track_started=True,
    
    # Error handling
    task_reject_on_worker_lost=True,
    task_acks_late=True,
    
    # Queue priorities
    task_inherit_parent_priority=True,
    task_default_priority=5,
)

# Comprehensive periodic task schedule
celery_app.conf.beat_schedule = {
    # ============== CRITICAL RISK MONITORING ==============
    
    # Risk monitoring every 30 seconds during market hours
    "risk-monitor-check": {
        "task": "app.tasks.celery_tasks.risk_monitor_check",
        "schedule": 30.0,  # Every 30 seconds
        "options": {"queue": "risk", "priority": 10}  # Highest priority
    },
    
    # Danger zone monitoring every 15 seconds during market hours
    "danger-zone-monitor": {
        "task": "app.tasks.celery_tasks.danger_zone_monitor",
        "schedule": 15.0,  # Every 15 seconds
        "options": {"queue": "risk", "priority": 10}
    },
    
    # Position MTM update every 45 seconds
    "position-mtm-update": {
        "task": "app.tasks.celery_tasks.position_mtm_update",
        "schedule": 45.0,  # Every 45 seconds
        "options": {"queue": "trading", "priority": 9}
    },
    
    # ============== TRADING OPERATIONS ==============
    
    # Market data update every 1 minute
    "market-data-update": {
        "task": "app.tasks.celery_tasks.update_market_data",
        "schedule": 60.0,  # Every 1 minute
        "options": {"queue": "trading", "priority": 8}
    },
    
    # Daily squareoff at 3:10 PM
    "daily-squareoff": {
        "task": "app.tasks.celery_tasks.daily_squareoff",
        "schedule": crontab(hour=15, minute=10),  # 3:10 PM IST
        "options": {"queue": "trading", "priority": 10}
    },
    
    # Pre-market preparation at 9:00 AM
    "pre-market-preparation": {
        "task": "app.tasks.celery_tasks.pre_market_preparation",
        "schedule": crontab(hour=9, minute=0),  # 9:00 AM IST
        "options": {"queue": "trading", "priority": 8}
    },
    
    # Post-market cleanup at 4:00 PM
    "post-market-cleanup": {
        "task": "app.tasks.celery_tasks.post_market_cleanup",
        "schedule": crontab(hour=16, minute=0),  # 4:00 PM IST
        "options": {"queue": "trading", "priority": 7}
    },
    
    # ============== EVENT CALENDAR MANAGEMENT ==============
    
    # Daily calendar auto-refresh check at 6:00 AM
    "calendar-auto-refresh-check": {
        "task": "app.tasks.celery_tasks.auto_refresh_calendar_check",
        "schedule": crontab(hour=6, minute=0),  # 6:00 AM daily
        "options": {"queue": "maintenance", "priority": 7}
    },
    
    # Weekly forced calendar refresh on Sunday at 7:00 AM  
    "weekly-calendar-refresh": {
        "task": "app.tasks.celery_tasks.refresh_event_calendar",
        "schedule": crontab(hour=7, minute=0, day_of_week=0),  # Sunday 7:00 AM
        "options": {"queue": "maintenance", "priority": 8}
    },
    
    # New year calendar refresh on Jan 1st at 6:00 AM
    "new-year-calendar-refresh": {
        "task": "app.tasks.celery_tasks.refresh_event_calendar", 
        "schedule": crontab(hour=6, minute=0, day_of_month=1, month_of_year=1),  # Jan 1st 6:00 AM
        "options": {"queue": "maintenance", "priority": 9}
    },
    
    # Monthly calendar validation on 1st of each month at 7:30 AM
    "monthly-calendar-validation": {
        "task": "app.tasks.celery_tasks.validate_calendar_data",
        "schedule": crontab(hour=7, minute=30, day_of_month=1),  # 1st of month 7:30 AM
        "options": {"queue": "maintenance", "priority": 6}
    },
    
    # ============== STRATEGY MANAGEMENT ==============
    
    # Strategy performance update every 5 minutes
    "strategy-performance-update": {
        "task": "app.tasks.celery_tasks.update_strategy_performance",
        "schedule": 300.0,  # Every 5 minutes
        "options": {"queue": "monitoring", "priority": 6}
    },
    
    # Weekly strategy recalibration on Sunday at 8:00 PM
    "weekly-recalibration": {
        "task": "app.tasks.celery_tasks.weekly_strategy_recalibration", 
        "schedule": crontab(hour=20, minute=0, day_of_week=0),  # Sunday 8:00 PM
        "options": {"queue": "maintenance", "priority": 7}
    },
    
    # Monthly strategy analysis on last Sunday at 9:00 PM
    "monthly-strategy-analysis": {
        "task": "app.tasks.celery_tasks.monthly_strategy_analysis",
        "schedule": crontab(hour=21, minute=0, day_of_week=0, day_of_month="25-31"),  # Last Sunday
        "options": {"queue": "maintenance", "priority": 6}
    },
    
    # Strategy elimination check every Monday at 7:00 PM
    "strategy-elimination-check": {
        "task": "app.tasks.celery_tasks.strategy_elimination_check",
        "schedule": crontab(hour=19, minute=0, day_of_week=1),  # Monday 7:00 PM
        "options": {"queue": "maintenance", "priority": 7}
    },
    
    # ============== EXPIRY MANAGEMENT ==============
    
    # Expiry day preparation at 8:00 AM daily (checks if expiry)
    "expiry-day-preparation": {
        "task": "app.tasks.celery_tasks.expiry_day_preparation",
        "schedule": crontab(hour=8, minute=0),  # 8:00 AM daily
        "options": {"queue": "trading", "priority": 8}
    },
    
    # Weekly expiry alert on Wednesday at 8:00 PM
    "weekly-expiry-alert": {
        "task": "app.tasks.celery_tasks.weekly_expiry_alert",
        "schedule": crontab(hour=20, minute=0, day_of_week=3),  # Wednesday 8:00 PM
        "options": {"queue": "notifications", "priority": 6}
    },
    
    # Monthly expiry preparation on last Wednesday at 7:00 PM
    "monthly-expiry-preparation": {
        "task": "app.tasks.celery_tasks.monthly_expiry_preparation",
        "schedule": crontab(hour=19, minute=0, day_of_week=3, day_of_month="25-31"),  # Last Wed
        "options": {"queue": "trading", "priority": 8}
    },
    
    # ============== SYSTEM MONITORING ==============
    
    # System health check every 2 minutes
    "system-health-check": {
        "task": "app.tasks.celery_tasks.health_check",
        "schedule": 120.0,  # Every 2 minutes
        "options": {"queue": "monitoring", "priority": 6}
    },
    
    # Broker heartbeat check every 3 minutes during market hours
    "broker-heartbeat-check": {
        "task": "app.tasks.celery_tasks.broker_heartbeat_check",
        "schedule": 180.0,  # Every 3 minutes
        "options": {"queue": "monitoring", "priority": 7}
    },
    
    # Database health check every 10 minutes
    "database-health-check": {
        "task": "app.tasks.celery_tasks.database_health_check",
        "schedule": 600.0,  # Every 10 minutes
        "options": {"queue": "monitoring", "priority": 5}
    },
    
    # Redis health check every 5 minutes
    "redis-health-check": {
        "task": "app.tasks.celery_tasks.redis_health_check",
        "schedule": 300.0,  # Every 5 minutes
        "options": {"queue": "monitoring", "priority": 5}
    },
    
    # ============== DATA MANAGEMENT ==============
    
    # Database backup at 6:00 PM daily
    "daily-backup": {
        "task": "app.tasks.celery_tasks.backup_database",
        "schedule": crontab(hour=18, minute=0),  # 6:00 PM IST
        "options": {"queue": "maintenance", "priority": 4}
    },
    
    # Clean old logs weekly on Saturday at 2:00 AM
    "cleanup-old-logs": {
        "task": "app.tasks.celery_tasks.cleanup_old_logs",
        "schedule": crontab(hour=2, minute=0, day_of_week=6),  # Saturday 2:00 AM
        "options": {"queue": "maintenance", "priority": 3}
    },
    
    # Archive old trades monthly on 1st at 3:00 AM
    "archive-old-trades": {
        "task": "app.tasks.celery_tasks.archive_old_trades",
        "schedule": crontab(hour=3, minute=0, day_of_month=1),  # 1st of month 3:00 AM
        "options": {"queue": "maintenance", "priority": 3}
    },
    
    # Clean temporary files daily at 1:00 AM
    "cleanup-temp-files": {
        "task": "app.tasks.celery_tasks.cleanup_temp_files",
        "schedule": crontab(hour=1, minute=0),  # 1:00 AM daily
        "options": {"queue": "maintenance", "priority": 2}
    },
    
    # ============== NOTIFICATION MANAGEMENT ==============
    
    # Process WhatsApp notification queue every 30 seconds
    "whatsapp-notification-queue": {
        "task": "app.tasks.celery_tasks.whatsapp_notification_queue",
        "schedule": 30.0,  # Every 30 seconds
        "options": {"queue": "notifications", "priority": 7}
    },
    
    # Daily P&L report at 4:30 PM
    "daily-pnl-report": {
        "task": "app.tasks.celery_tasks.daily_pnl_report",
        "schedule": crontab(hour=16, minute=30),  # 4:30 PM IST
        "options": {"queue": "notifications", "priority": 6}
    },
    
    # Weekly performance summary on Sunday at 7:00 PM
    "weekly-performance-summary": {
        "task": "app.tasks.celery_tasks.weekly_performance_summary",
        "schedule": crontab(hour=19, minute=0, day_of_week=0),  # Sunday 7:00 PM
        "options": {"queue": "notifications", "priority": 5}
    },
    
    # Monthly performance report on last day at 8:00 PM
    "monthly-performance-report": {
        "task": "app.tasks.celery_tasks.monthly_performance_report",
        "schedule": crontab(hour=20, minute=0, day_of_month="28-31"),  # Last day of month
        "options": {"queue": "notifications", "priority": 6}
    },
    
    # ============== REGULATORY & COMPLIANCE ==============
    
    # Audit log cleanup weekly on Friday at 11:00 PM
    "audit-log-maintenance": {
        "task": "app.tasks.celery_tasks.audit_log_maintenance",
        "schedule": crontab(hour=23, minute=0, day_of_week=5),  # Friday 11:00 PM
        "options": {"queue": "maintenance", "priority": 4}
    },
    
    # Compliance check daily at 5:00 PM
    "compliance-check": {
        "task": "app.tasks.celery_tasks.compliance_check",
        "schedule": crontab(hour=17, minute=0),  # 5:00 PM daily
        "options": {"queue": "monitoring", "priority": 6}
    },
    
    # Risk limit validation every 6 hours
    "risk-limit-validation": {
        "task": "app.tasks.celery_tasks.risk_limit_validation",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
        "options": {"queue": "risk", "priority": 7}
    }
}

# Queue configuration with priorities
celery_app.conf.task_default_queue = "default"
celery_app.conf.task_queues = {
    "risk": {
        "exchange": "risk",
        "exchange_type": "direct",
        "routing_key": "risk",
        "priority": 10  # Highest priority queue
    },
    "trading": {
        "exchange": "trading", 
        "exchange_type": "direct",
        "routing_key": "trading",
        "priority": 8  # High priority for trading operations
    },
    "monitoring": {
        "exchange": "monitoring",
        "exchange_type": "direct", 
        "routing_key": "monitoring",
        "priority": 6  # Medium priority for monitoring
    },
    "notifications": {
        "exchange": "notifications",
        "exchange_type": "direct",
        "routing_key": "notifications", 
        "priority": 7  # High priority for notifications
    },
    "maintenance": {
        "exchange": "maintenance",
        "exchange_type": "direct",
        "routing_key": "maintenance",
        "priority": 4  # Lower priority for maintenance tasks
    },
    "default": {
        "exchange": "default",
        "exchange_type": "direct",
        "routing_key": "default",
        "priority": 5  # Default priority
    }
}

# Environment-specific settings
if settings.DEBUG:
    # Development settings - less frequent tasks
    celery_app.conf.beat_schedule["risk-monitor-check"]["schedule"] = 60.0  # Every minute
    celery_app.conf.beat_schedule["market-data-update"]["schedule"] = 120.0  # Every 2 minutes
    celery_app.conf.beat_schedule["danger-zone-monitor"]["schedule"] = 45.0  # Every 45 seconds
    
    # Reduced worker limits for development
    celery_app.conf.worker_prefetch_multiplier = 2
    celery_app.conf.worker_max_tasks_per_child = 100
    
else:
    # Production optimization
    celery_app.conf.worker_prefetch_multiplier = 4
    celery_app.conf.worker_max_tasks_per_child = 5000
    
    # Production-specific task limits
    celery_app.conf.task_time_limit = 600  # 10 minutes for production
    celery_app.conf.task_soft_time_limit = 540  # 9 minutes soft limit

# Task-specific configurations
celery_app.conf.task_annotations = {
    # Global rate limits and timeouts
    "*": {
        "rate_limit": "100/m",  # Max 100 tasks per minute globally
        "time_limit": 300,       # 5 minutes max per task
        "soft_time_limit": 240,  # 4 minutes soft limit
    },
    
    # Critical risk monitoring tasks
    "app.tasks.celery_tasks.risk_monitor_check": {
        "rate_limit": "300/m",   # Higher rate for risk monitoring
        "time_limit": 60,        # Shorter time limit for critical tasks
        "soft_time_limit": 45,
        "priority": 10
    },
    "app.tasks.celery_tasks.danger_zone_monitor": {
        "rate_limit": "400/m",   # Highest rate for danger zone
        "time_limit": 30,        # Very short time limit
        "soft_time_limit": 25,
        "priority": 10
    },
    "app.tasks.celery_tasks.position_mtm_update": {
        "rate_limit": "200/m",
        "time_limit": 90,
        "soft_time_limit": 75,
        "priority": 9
    },
    
    # Trading operations
    "app.tasks.celery_tasks.daily_squareoff": {
        "rate_limit": "1/m",     # Only once per minute
        "time_limit": 600,       # 10 minutes for squareoff
        "soft_time_limit": 540,
        "priority": 10
    },
    "app.tasks.celery_tasks.update_market_data": {
        "rate_limit": "120/m",
        "time_limit": 120,
        "soft_time_limit": 100,
        "priority": 8
    },
    
    # Event calendar tasks
    "app.tasks.celery_tasks.refresh_event_calendar": {
        "rate_limit": "10/h",    # Max 10 times per hour
        "time_limit": 300,       # 5 minutes
        "soft_time_limit": 240,
        "priority": 7
    },
    "app.tasks.celery_tasks.auto_refresh_calendar_check": {
        "rate_limit": "50/h",    # Max 50 times per hour
        "time_limit": 60,        # 1 minute
        "soft_time_limit": 45,
        "priority": 6
    },
    
    # Strategy management
    "app.tasks.celery_tasks.weekly_strategy_recalibration": {
        "rate_limit": "1/d",     # Once per day max
        "time_limit": 1800,      # 30 minutes
        "soft_time_limit": 1500,
        "priority": 7
    },
    "app.tasks.celery_tasks.strategy_elimination_check": {
        "rate_limit": "7/w",     # 7 times per week max
        "time_limit": 600,       # 10 minutes
        "soft_time_limit": 540,
        "priority": 6
    },
    
    # Maintenance tasks
    "app.tasks.celery_tasks.backup_database": {
        "rate_limit": "2/d",     # Max 2 backups per day
        "time_limit": 3600,      # 1 hour for backup
        "soft_time_limit": 3300,
        "priority": 4
    },
    "app.tasks.celery_tasks.cleanup_old_logs": {
        "rate_limit": "1/d",     # Once per day
        "time_limit": 1800,      # 30 minutes
        "soft_time_limit": 1500,
        "priority": 3
    },
    
    # Notification tasks
    "app.tasks.celery_tasks.whatsapp_notification_queue": {
        "rate_limit": "200/m",   # High rate for notifications
        "time_limit": 30,        # Short time limit
        "soft_time_limit": 25,
        "priority": 7
    }
}

# Logging configuration
celery_app.conf.worker_log_format = (
    "[%(asctime)s: %(levelname)s/%(processName)s/%(name)s] %(message)s"
)
celery_app.conf.worker_task_log_format = (
    "[%(asctime)s: %(levelname)s/%(processName)s/%(name)s][%(task_name)s(%(task_id)s)] %(message)s"
)

# Result backend configuration
celery_app.conf.result_backend_transport_options = {
    "priority_steps": list(range(10)),
    "sep": ":",
    "queue_order_strategy": "priority",
}

# Error handling and retries
celery_app.conf.task_default_retry_delay = 60  # 1 minute
celery_app.conf.task_max_retries = 3
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True

# Worker pool configuration
celery_app.conf.worker_pool = "prefork"  # Use prefork pool for CPU-bound tasks
celery_app.conf.worker_concurrency = 4   # 4 concurrent workers
celery_app.conf.worker_max_memory_per_child = 200000  # 200MB memory limit per child

# Beat scheduler configuration
celery_app.conf.beat_scheduler = "celery.beat:PersistentScheduler"
celery_app.conf.beat_schedule_filename = "celerybeat-schedule"

# Security settings
celery_app.conf.task_always_eager = False  # Never run tasks eagerly in production
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True

# Monitoring and events
celery_app.conf.worker_send_task_events = True
celery_app.conf.task_send_sent_event = True
celery_app.conf.worker_enable_remote_control = True

# Export celery app
__all__ = ["celery_app"]
