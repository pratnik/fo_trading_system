"""
System health check utilities
Monitors all system components and provides comprehensive health status
"""

import logging
import psutil
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import requests
import subprocess
from app.config import settings
from app.db.base import db_manager

logger = logging.getLogger("healthcheck")

class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    DOWN = "DOWN"

@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    last_check: datetime
    response_time_ms: Optional[float] = None

class SystemHealthCheck:
    """
    Comprehensive system health monitoring
    Checks database, redis, brokers, disk space, memory, etc.
    """
    
    def __init__(self):
        self.redis_client = None
        self.broker_adapters = {}
        self.health_history: Dict[str, List[ComponentHealth]] = {}
        self.alert_thresholds = {
            "disk_usage_critical": 90,     # % disk usage
            "disk_usage_warning": 80,
            "memory_usage_critical": 90,   # % memory usage
            "memory_usage_warning": 80,
            "cpu_usage_critical": 90,      # % CPU usage
            "cpu_usage_warning": 80,
            "response_time_warning": 1000, # ms
            "response_time_critical": 3000 # ms
        }
        
    def check_all_components(self) -> Dict[str, ComponentHealth]:
        """Run health check on all system components"""
        components = {}
        
        # Database health
        components["database"] = self.check_database_health()
        
        # Redis health
        components["redis"] = self.check_redis_health()
        
        # System resources
        components["system_resources"] = self.check_system_resources()
        
        # Disk space
        components["disk_space"] = self.check_disk_space()
        
        # Network connectivity
        components["network"] = self.check_network_connectivity()
        
        # Application processes
        components["application"] = self.check_application_health()
        
        # Broker connectivity (if configured)
        broker_health = self.check_broker_health()
        if broker_health:
            components["brokers"] = broker_health
            
        # Store health history
        self._store_health_history(components)
        
        return components
    
    def check_database_health(self) -> ComponentHealth:
        """Check PostgreSQL database health"""
        start_time = datetime.now()  
        
        try:
            # Test connection
            is_connected = db_manager.check_connection()
            
            if not is_connected:
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.DOWN,
                    message="Database connection failed",
                    details={"error": "Connection timeout or refused"},
                    last_check=datetime.now()
                )
            
            # Test query performance
            with db_manager.get_session() as session:
                session.execute("SELECT 1")
                
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Check connection pool
            pool_status = {
                "pool_size": db_manager.engine.pool.size(),
                "checked_out": db_manager.engine.pool.checkedout(),
                "overflow": db_manager.engine.pool.overflow(),
                "checked_in": db_manager.engine.pool.checkedin()
            }
            
            # Determine status
            if response_time > self.alert_thresholds["response_time_critical"]:
                status = HealthStatus.CRITICAL
                message = f"Database slow response: {response_time:.0f}ms"
            elif response_time > self.alert_thresholds["response_time_warning"]:
                status = HealthStatus.WARNING
                message = f"Database slow response: {response_time:.0f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = "Database connection healthy"
            
            return ComponentHealth(
                name="database",
                status=status,
                message=message,
                details=pool_status,
                last_check=datetime.now(),
                response_time_ms=response_time
            )
            
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return ComponentHealth(
                name="database",
                status=HealthStatus.DOWN,
                message=f"Database error: {str(e)}",
                details={"error": str(e)},
                last_check=datetime.now()
            )
    
    def check_redis_health(self) -> ComponentHealth:
        """Check Redis health"""
        start_time = datetime.now()
        
        try:
            if not self.redis_client:
                self.redis_client = redis.from_url(settings.REDIS_URL)
            
            # Test basic operations
            self.redis_client.ping()
            self.redis_client.set("health_check", "ok", ex=60)
            result = self.redis_client.get("health_check")
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Get Redis info
            redis_info = self.redis_client.info()
            
            details = {
                "version": redis_info.get("redis_version"),
                "connected_clients": redis_info.get("connected_clients"),
                "used_memory_human": redis_info.get("used_memory_human"),
                "total_commands_processed": redis_info.get("total_commands_processed"),
                "keyspace_hits": redis_info.get("keyspace_hits"),
                "keyspace_misses": redis_info.get("keyspace_misses")
            }
            
            # Determine status
            if response_time > self.alert_thresholds["response_time_critical"]:
                status = HealthStatus.CRITICAL
                message = f"Redis slow response: {response_time:.0f}ms"
            elif response_time > self.alert_thresholds["response_time_warning"]:
                status = HealthStatus.WARNING
                message = f"Redis slow response: {response_time:.0f}ms"
            else:
                status = HealthStatus.HEALTHY
                message = "Redis connection healthy"
            
            return ComponentHealth(
                name="redis",
                status=status,
                message=message,
                details=details,
                last_check=datetime.now(),
                response_time_ms=response_time
            )
            
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return ComponentHealth(
                name="redis",
                status=HealthStatus.DOWN,
                message=f"Redis error: {str(e)}",
                details={"error": str(e)},
                last_check=datetime.now()
            )
    
    def check_system_resources(self) -> ComponentHealth:
        """Check system resource usage"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Load average (Unix systems)
            try:
                load_avg = psutil.getloadavg()
            except AttributeError:
                load_avg = (0, 0, 0)  # Windows doesn't have load average
            
            details = {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "load_average_1m": load_avg[0],
                "load_average_5m": load_avg[1],
                "load_average_15m": load_avg[2]
            }
            
            # Determine status
            if cpu_percent > self.alert_thresholds["cpu_usage_critical"] or \
               memory_percent > self.alert_thresholds["memory_usage_critical"]:
                status = HealthStatus.CRITICAL
                message = f"High resource usage: CPU={cpu_percent:.1f}%, Memory={memory_percent:.1f}%"
            elif cpu_percent > self.alert_thresholds["cpu_usage_warning"] or \
                 memory_percent > self.alert_thresholds["memory_usage_warning"]:
                status = HealthStatus.WARNING
                message = f"Moderate resource usage: CPU={cpu_percent:.1f}%, Memory={memory_percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"System resources healthy: CPU={cpu_percent:.1f}%, Memory={memory_percent:.1f}%"
            
            return ComponentHealth(
                name="system_resources",
                status=status,
                message=message,
                details=details,
                last_check=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"System resource check failed: {e}")
            return ComponentHealth(
                name="system_resources",
                status=HealthStatus.DOWN,
                message=f"Resource check error: {str(e)}",
                details={"error": str(e)},
                last_check=datetime.now()
            )
    
    def check_disk_space(self) -> ComponentHealth:
        """Check disk space usage"""
        try:
            # Check main disk usage
            disk_usage = psutil.disk_usage('/')
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            
            details = {
                "total_gb": round(disk_usage.total / (1024**3), 2),
                "used_gb": round(disk_usage.used / (1024**3), 2),
                "free_gb": round(disk_usage.free / (1024**3), 2),
                "percent_used": round(disk_percent, 2)
            }
            
            # Determine status
            if disk_percent > self.alert_thresholds["disk_usage_critical"]:
                status = HealthStatus.CRITICAL
                message = f"Critical disk space: {disk_percent:.1f}% used"
            elif disk_percent > self.alert_thresholds["disk_usage_warning"]:
                status = HealthStatus.WARNING
                message = f"Low disk space: {disk_percent:.1f}% used"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk space healthy: {disk_percent:.1f}% used"
            
            return ComponentHealth(
                name="disk_space",
                status=status,
                message=message,
                details=details,
                last_check=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Disk space check failed: {e}")
            return ComponentHealth(
                name="disk_space",
                status=HealthStatus.DOWN,
                message=f"Disk check error: {str(e)}",
                details={"error": str(e)},
                last_check=datetime.now()
            )
    
    def check_network_connectivity(self) -> ComponentHealth:
        """Check external network connectivity"""
        try:
            # Test connectivity to important endpoints
            test_urls = [
                "https://google.com",
                "https://zerodha.com",
                "https://api.fyers.in"
            ]
            
            results = {}
            total_response_time = 0
            successful_tests = 0
            
            for url in test_urls:
                try:
                    start_time = datetime.now()
                    response = requests.get(url, timeout=10)
                    response_time = (datetime.now() - start_time).total_seconds() * 1000
                    
                    results[url] = {
                        "status_code": response.status_code,
                        "response_time_ms": response_time,
                        "success": response.status_code == 200
                    }
                    
                    if response.status_code == 200:
                        successful_tests += 1
                        total_response_time += response_time
                        
                except Exception as e:
                    results[url] = {
                        "error": str(e),
                        "success": False
                    }
            
            # Calculate average response time
            avg_response_time = total_response_time / successful_tests if successful_tests > 0 else 0
            
            # Determine status
            if successful_tests == 0:
                status = HealthStatus.DOWN
                message = "No network connectivity"
            elif successful_tests < len(test_urls):
                status = HealthStatus.WARNING
                message = f"Partial connectivity: {successful_tests}/{len(test_urls)} endpoints reachable"
            elif avg_response_time > self.alert_thresholds["response_time_critical"]:
                status = HealthStatus.CRITICAL
                message = f"Slow network: {avg_response_time:.0f}ms average"
            elif avg_response_time > self.alert_thresholds["response_time_warning"]:
                status = HealthStatus.WARNING
                message = f"Slow network: {avg_response_time:.0f}ms average"
            else:
                status = HealthStatus.HEALTHY
                message = f"Network healthy: {avg_response_time:.0f}ms average"
            
            return ComponentHealth(
                name="network",
                status=status,
                message=message,
                details={
                    "test_results": results,
                    "successful_tests": successful_tests,
                    "total_tests": len(test_urls),
                    "average_response_time_ms": avg_response_time
                },
                last_check=datetime.now(),
                response_time_ms=avg_response_time
            )
            
        except Exception as e:
            logger.error(f"Network connectivity check failed: {e}")
            return ComponentHealth(
                name="network",
                status=HealthStatus.DOWN,
                message=f"Network check error: {str(e)}",
                details={"error": str(e)},
                last_check=datetime.now()
            )
    
    def check_application_health(self) -> ComponentHealth:
        """Check application-specific health"""
        try:
            # Check if main processes are running
            processes = {}
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                proc_name = proc.info['name'].lower()
                if any(keyword in proc_name for keyword in ['streamlit', 'celery', 'python']):
                    processes[proc.info['pid']] = {
                        'name': proc.info['name'],
                        'cpu_percent': proc.info['cpu_percent'],
                        'memory_percent': proc.info['memory_percent']
                    }
            
            # Check Streamlit health
            streamlit_healthy = False
            try:
                response = requests.get("http://localhost:8501/_stcore/health", timeout=5)
                streamlit_healthy = response.status_code == 200
            except:
                pass
            
            details = {
                "processes": processes,
                "process_count": len(processes),
                "streamlit_healthy": streamlit_healthy
            }
            
            # Determine status
            if not streamlit_healthy:
                status = HealthStatus.CRITICAL
                message = "Streamlit application not responding"
            elif len(processes) == 0:
                status = HealthStatus.WARNING
                message = "No application processes detected"
            else:
                status = HealthStatus.HEALTHY
                message = f"Application healthy: {len(processes)} processes running"
            
            return ComponentHealth(
                name="application",
                status=status,
                message=message,
                details=details,
                last_check=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Application health check failed: {e}")
            return ComponentHealth(
                name="application",
                status=HealthStatus.DOWN,
                message=f"Application check error: {str(e)}",
                details={"error": str(e)},
                last_check=datetime.now()
            )
    
    def check_broker_health(self) -> Optional[ComponentHealth]:
        """Check broker connectivity (if configured)"""
        # This would check configured brokers
        # Implementation depends on broker configuration
        return None
    
    def _store_health_history(self, components: Dict[str, ComponentHealth]):
        """Store health check history"""
        for component_name, health in components.items():
            if component_name not in self.health_history:
                self.health_history[component_name] = []
            
            self.health_history[component_name].append(health)
            
            # Keep only last 100 health checks per component
            if len(self.health_history[component_name]) > 100:
                self.health_history[component_name].pop(0)
    
    def get_overall_health_status(self) -> HealthStatus:
        """Get overall system health status"""
        components = self.check_all_components()
        
        # Check for any DOWN components
        if any(comp.status == HealthStatus.DOWN for comp in components.values()):
            return HealthStatus.DOWN
        
        # Check for any CRITICAL components
        if any(comp.status == HealthStatus.CRITICAL for comp in components.values()):
            return HealthStatus.CRITICAL
        
        # Check for any WARNING components
        if any(comp.status == HealthStatus.WARNING for comp in components.values()):
            return HealthStatus.WARNING
        
        return HealthStatus.HEALTHY
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary"""
        components = self.check_all_components()
        overall_status = self.get_overall_health_status()
        
        return {
            "overall_status": overall_status.value,
            "timestamp": datetime.now().isoformat(),
            "components": {
                name: {
                    "status": comp.status.value,
                    "message": comp.message,
                    "response_time_ms": comp.response_time_ms,
                    "last_check": comp.last_check.isoformat()
                }
                for name, comp in components.items()
            },
            "summary": {
                "total_components": len(components),
                "healthy": sum(1 for comp in components.values() if comp.status == HealthStatus.HEALTHY),
                "warning": sum(1 for comp in components.values() if comp.status == HealthStatus.WARNING),
                "critical": sum(1 for comp in components.values() if comp.status == HealthStatus.CRITICAL),
                "down": sum(1 for comp in components.values() if comp.status == HealthStatus.DOWN)
            }
        }

# Global health checker instance
health_checker = SystemHealthCheck()

# Convenience functions
def quick_health_check() -> bool:
    """Quick health check - returns True if system is healthy"""
    return health_checker.get_overall_health_status() == HealthStatus.HEALTHY

def get_health_status() -> Dict[str, Any]:
    """Get current health status"""
    return health_checker.get_health_summary()

# Export main components
__all__ = [
    "SystemHealthCheck",
    "ComponentHealth",
    "HealthStatus", 
    "health_checker",
    "quick_health_check",
    "get_health_status"
]
