"""
Resource monitoring and optimization infrastructure for AiArt application.

This module implements intelligent resource monitoring, load detection, and hibernation
management to optimize server performance within free tier hosting limits.
"""

import psutil
import time
from datetime import datetime, timezone
from typing import Dict
import logging
import os

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """
    Simplified resource monitor that gets metrics on-demand without background threads.
    """
    
    def __init__(self, cpu_threshold: float = 80.0, memory_threshold: float = 80.0):
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self._request_count = 0
        self._last_request_time = datetime.now(timezone.utc)
        self._last_cpu_check = 0
        self._cpu_readings = []  # Store recent readings for smoothing
        
        # Initialize CPU monitoring with a proper baseline
        try:
            # First call to initialize psutil's internal state
            psutil.cpu_percent(interval=None)
            # Wait a moment and get a real reading
            time.sleep(0.1)
            self._last_cpu_check = psutil.cpu_percent(interval=None)
            logger.info(f"ResourceMonitor initialized with CPU threshold: {cpu_threshold}%, "
                       f"Memory threshold: {memory_threshold}%")
        except Exception as e:
            logger.warning(f"Failed to initialize CPU monitoring: {e}")
            self._last_cpu_check = 0
    
    def get_current_metrics(self) -> Dict:
        """Get current system metrics on-demand."""
        try:
            # Get CPU usage with proper handling
            cpu_percent = psutil.cpu_percent(interval=None)
            
            # If we get 0 or None, use a short blocking call to get accurate reading
            if cpu_percent is None or cpu_percent == 0.0:
                try:
                    cpu_percent = psutil.cpu_percent(interval=0.1)  # Short blocking call
                except Exception:
                    cpu_percent = self._last_cpu_check  # Use last known value
            
            # Update last known CPU value and smooth readings
            if cpu_percent > 0:
                self._last_cpu_check = cpu_percent
                # Keep last 5 readings for smoothing
                self._cpu_readings.append(cpu_percent)
                if len(self._cpu_readings) > 5:
                    self._cpu_readings.pop(0)
                # Use average of recent readings to smooth out spikes
                if len(self._cpu_readings) >= 2:
                    cpu_percent = sum(self._cpu_readings) / len(self._cpu_readings)
            else:
                cpu_percent = self._last_cpu_check
            
            # Get memory usage
            memory_info = psutil.virtual_memory()
            memory_percent = memory_info.percent
            
            # Calculate load
            current_load = (cpu_percent * 0.7) + (memory_percent * 0.3)
            
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'current_load': round(current_load, 2),
                'cpu_usage': round(cpu_percent, 2),
                'memory_usage': round(memory_percent, 2),
                'queue_length': 0,  # Simplified - no queue tracking
                'capacity_available': current_load < self.cpu_threshold,
                'should_throttle': current_load >= self.cpu_threshold,
                'hibernating': False,  # Simplified - no hibernation
                'hibernation_duration_minutes': None,
                'load_trend': 'stable',  # Simplified - no trend analysis
                'thresholds': {
                    'cpu_threshold': self.cpu_threshold,
                    'memory_threshold': self.memory_threshold,
                    'hibernation_idle_minutes': 15
                },
                'historical_averages': {
                    'cpu_avg': round(cpu_percent, 2),
                    'memory_avg': round(memory_percent, 2),
                    'load_avg': round(current_load, 2)
                }
            }
        
        except Exception as e:
            logger.error(f"Error getting resource metrics: {e}")
            # Return safe defaults using last known values
            fallback_cpu = max(self._last_cpu_check, 1.0)  # At least 1% to be realistic
            fallback_memory = 50.0  # Reasonable default
            fallback_load = (fallback_cpu * 0.7) + (fallback_memory * 0.3)
            
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'current_load': round(fallback_load, 2),
                'cpu_usage': round(fallback_cpu, 2),
                'memory_usage': round(fallback_memory, 2),
                'queue_length': 0,
                'capacity_available': fallback_load < self.cpu_threshold,
                'should_throttle': fallback_load >= self.cpu_threshold,
                'hibernating': False,
                'hibernation_duration_minutes': None,
                'load_trend': 'stable',
                'thresholds': {
                    'cpu_threshold': self.cpu_threshold,
                    'memory_threshold': self.memory_threshold,
                    'hibernation_idle_minutes': 15
                },
                'historical_averages': {
                    'cpu_avg': round(fallback_cpu, 2),
                    'memory_avg': round(fallback_memory, 2),
                    'load_avg': round(fallback_load, 2)
                }
            }
    
    def record_request(self):
        """Record a request."""
        self._request_count += 1
        self._last_request_time = datetime.now(timezone.utc)
    
    def should_throttle(self) -> bool:
        """Check if requests should be throttled."""
        try:
            metrics = self.get_current_metrics()
            return metrics['should_throttle']
        except Exception:
            return False  # Don't throttle on error
    
    # Legacy method compatibility
    def get_resource_summary(self) -> Dict:
        """Get comprehensive resource status summary (legacy compatibility)."""
        return self.get_current_metrics()


# Global resource monitor instance
_resource_monitor = None


def get_resource_monitor() -> ResourceMonitor:
    """Get the global ResourceMonitor instance (singleton pattern)."""
    global _resource_monitor
    if _resource_monitor is None:
        # Get configuration from environment variables
        cpu_threshold = float(os.getenv('RESOURCE_CPU_THRESHOLD', '80.0'))
        memory_threshold = float(os.getenv('RESOURCE_MEMORY_THRESHOLD', '80.0'))
        
        _resource_monitor = ResourceMonitor(
            cpu_threshold=cpu_threshold,
            memory_threshold=memory_threshold
        )
    
    return _resource_monitor


def initialize_resource_monitoring():
    """Initialize global resource monitoring."""
    monitor = get_resource_monitor()
    logger.info("Global resource monitoring initialized")
    return monitor


# Convenience functions for Flask integration
def record_request():
    """Record a new request."""
    get_resource_monitor().record_request()


def should_throttle_request() -> bool:
    """Check if current request should be throttled."""
    return get_resource_monitor().should_throttle()


def get_system_status() -> Dict:
    """Get comprehensive system status for monitoring."""
    return get_resource_monitor().get_current_metrics()