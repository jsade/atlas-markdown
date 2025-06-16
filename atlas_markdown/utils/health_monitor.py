"""
Health monitoring system for the scraper
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import psutil

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors system health and resource usage"""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.start_time = datetime.now()
        self.warnings: list[str] = []

    async def check_system_health(self) -> dict[str, Any]:
        """Perform comprehensive health check"""
        checks = {
            "disk_space": await self.check_disk_space(),
            "memory": await self.check_memory(),
            "cpu": await self.check_cpu(),
            "network": await self.check_network(),
            "output_directory": await self.check_output_directory(),
        }

        # Overall health status
        all_healthy = all(check.get("healthy", False) for check in checks.values())

        return {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "healthy": all_healthy,
            "checks": checks,
            "warnings": self.warnings[-10:],  # Last 10 warnings
        }

    async def check_disk_space(self) -> dict[str, Any]:
        """Check available disk space"""
        try:
            import shutil
            from pathlib import Path

            # Create output directory if it doesn't exist
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)

            stat = shutil.disk_usage(self.output_dir)

            free_gb = stat.free / (1024**3)
            total_gb = stat.total / (1024**3)
            used_percent = (stat.used / stat.total) * 100

            # Warn if less than 1GB free or more than 90% used
            healthy = free_gb > 1.0 and used_percent < 90

            if not healthy:
                warning = f"Low disk space: {free_gb:.1f}GB free ({used_percent:.1f}% used)"
                self.warnings.append(warning)
                logger.warning(warning)

            return {
                "healthy": healthy,
                "free_gb": round(free_gb, 2),
                "total_gb": round(total_gb, 2),
                "used_percent": round(used_percent, 1),
                "message": f"{free_gb:.1f}GB free of {total_gb:.1f}GB ({used_percent:.1f}% used)",
            }

        except Exception as e:
            logger.error(f"Failed to check disk space: {e}")
            return {"healthy": False, "error": str(e), "message": f"Disk check failed: {e}"}

    async def check_memory(self) -> dict[str, Any]:
        """Check memory usage"""
        try:
            mem = psutil.virtual_memory()

            available_gb = mem.available / (1024**3)
            total_gb = mem.total / (1024**3)
            used_percent = mem.percent

            # Get process memory usage
            process = psutil.Process()
            process_mb = process.memory_info().rss / (1024**2)

            # Warn if less than 500MB available or more than 85% used
            healthy = available_gb > 0.5 and used_percent < 85

            if not healthy:
                warning = f"Low memory: {available_gb:.1f}GB available ({used_percent:.1f}% used)"
                self.warnings.append(warning)
                logger.warning(warning)

            return {
                "healthy": healthy,
                "available_gb": round(available_gb, 2),
                "total_gb": round(total_gb, 2),
                "used_percent": round(used_percent, 1),
                "process_mb": round(process_mb, 1),
                "message": f"{available_gb:.1f}GB available of {total_gb:.1f}GB, process using {process_mb:.0f}MB",
            }

        except Exception as e:
            logger.error(f"Failed to check memory: {e}")
            return {"healthy": False, "error": str(e), "message": f"Memory check failed: {e}"}

    async def check_cpu(self) -> dict[str, Any]:
        """Check CPU usage"""
        try:
            # Get CPU percent over 1 second interval
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Get process CPU usage
            process = psutil.Process()
            process_cpu = process.cpu_percent()

            # Warn if CPU usage is over 90%
            healthy = cpu_percent < 90

            if not healthy:
                warning = f"High CPU usage: {cpu_percent}%"
                self.warnings.append(warning)
                logger.warning(warning)

            return {
                "healthy": healthy,
                "system_percent": cpu_percent,
                "process_percent": process_cpu,
                "cpu_count": psutil.cpu_count(),
                "message": f"CPU at {cpu_percent}%, process using {process_cpu}%",
            }

        except Exception as e:
            logger.error(f"Failed to check CPU: {e}")
            return {"healthy": False, "error": str(e), "message": f"CPU check failed: {e}"}

    async def check_network(self) -> dict[str, Any]:
        """Check network connectivity"""
        test_urls = [
            "https://support.atlassian.com",
            "https://www.google.com",
        ]

        results = []
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in test_urls:
                try:
                    response = await client.get(url)
                    results.append(
                        {
                            "url": url,
                            "status": response.status_code,
                            "success": 200 <= response.status_code < 300,
                        }
                    )
                except Exception as e:
                    results.append({"url": url, "error": str(e), "success": False})

        healthy = any(r["success"] for r in results)

        if not healthy:
            warning = "Network connectivity issues detected"
            self.warnings.append(warning)
            logger.warning(warning)

        return {
            "healthy": healthy,
            "tests": results,
            "message": "Network connected" if healthy else "Network issues detected",
        }

    async def check_output_directory(self) -> dict[str, Any]:
        """Check output directory accessibility"""
        try:
            # Check if directory exists and is writable
            if not self.output_dir.exists():
                self.output_dir.mkdir(parents=True, exist_ok=True)

            # Try to write a test file
            test_file = self.output_dir / ".health_check"
            test_file.write_text("test")
            test_file.unlink()

            # Count files in output
            file_count = sum(1 for _ in self.output_dir.rglob("*.md"))

            return {
                "healthy": True,
                "exists": True,
                "writable": True,
                "file_count": file_count,
                "message": f"Output directory OK, {file_count} markdown files",
            }

        except Exception as e:
            logger.error(f"Output directory check failed: {e}")
            return {"healthy": False, "error": str(e), "message": f"Output directory error: {e}"}

    def add_warning(self, warning: str) -> None:
        """Add a warning to the monitor"""
        self.warnings.append(f"[{datetime.now().isoformat()}] {warning}")
        if len(self.warnings) > 100:
            self.warnings = self.warnings[-100:]  # Keep last 100


class CircuitBreaker:
    """Circuit breaker pattern for handling repeated failures"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = "closed"  # closed, open, half-open

    def record_success(self) -> None:
        """Record a successful operation"""
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        """Record a failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    def can_attempt(self) -> bool:
        """Check if we can attempt an operation"""
        if self.state == "closed":
            return True

        if self.state == "open":
            # Check if recovery timeout has passed
            if self.last_failure_time:
                time_since_failure = (datetime.now() - self.last_failure_time).total_seconds()
                if time_since_failure > self.recovery_timeout:
                    self.state = "half-open"
                    logger.info("Circuit breaker entering half-open state")
                    return True

        return self.state == "half-open"

    def get_status(self) -> dict[str, Any]:
        """Get circuit breaker status"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "threshold": self.failure_threshold,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
        }

    def reset(self) -> None:
        """Reset the circuit breaker to closed state"""
        self.failure_count = 0
        self.state = "closed"
        self.last_failure_time = None
        logger.info("Circuit breaker reset to closed state")
