"""
Backend Router class for managing multiple backend instances.
Handles failover, load balancing, and health checking across multiple backend deployments.
"""

import requests
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import threading
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class BackendStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"

@dataclass
class BackendInstance:
    """Represents a backend instance with health and performance metrics"""
    url: str
    name: str
    priority: int = 1  # Lower number = higher priority
    status: BackendStatus = BackendStatus.UNKNOWN
    last_check: Optional[datetime] = None
    response_time: float = 0.0
    error_count: int = 0
    success_count: int = 0
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    
    def __post_init__(self):
        if not self.url.endswith('/'):
            self.url += '/'
    
    @property
    def health_score(self) -> float:
        """Calculate health score based on various metrics"""
        if self.status == BackendStatus.DOWN:
            return 0.0
        
        # Base score from status
        base_score = {
            BackendStatus.HEALTHY: 1.0,
            BackendStatus.DEGRADED: 0.6,
            BackendStatus.DOWN: 0.0,
            BackendStatus.UNKNOWN: 0.3
        }.get(self.status, 0.0)
        
        # Adjust for response time (penalize slow responses)
        time_penalty = min(self.response_time / 10.0, 0.3)  # Max 30% penalty
        
        # Adjust for error rate
        total_requests = self.success_count + self.error_count
        if total_requests > 0:
            error_rate = self.error_count / total_requests
            error_penalty = error_rate * 0.4  # Max 40% penalty
        else:
            error_penalty = 0.0
        
        # Adjust for consecutive failures
        failure_penalty = min(self.consecutive_failures * 0.1, 0.5)  # Max 50% penalty
        
        final_score = base_score - time_penalty - error_penalty - failure_penalty
        return max(0.0, min(1.0, final_score))

class BackendRouter:
    """Manages multiple backend instances with automatic failover and load balancing"""
    
    def __init__(self, backends: List[Dict], health_check_interval: int = 30):
        """
        Initialize BackendRouter with backend configurations
        
        Args:
            backends: List of backend configurations with 'url', 'name', and optional 'priority'
            health_check_interval: Seconds between health checks
        """
        self.backends = []
        for backend_config in backends:
            backend = BackendInstance(
                url=backend_config['url'],
                name=backend_config['name'],
                priority=backend_config.get('priority', 1)
            )
            self.backends.append(backend)
        
        self.health_check_interval = health_check_interval
        self.last_health_check = None
        self._lock = threading.Lock()
        self._health_check_thread = None
        self._stop_health_checks = False
        
        # Start health checking
        self.start_health_monitoring()
    
    def start_health_monitoring(self):
        """Start background health monitoring thread"""
        if self._health_check_thread is None or not self._health_check_thread.is_alive():
            self._stop_health_checks = False
            self._health_check_thread = threading.Thread(
                target=self._health_check_loop,
                daemon=True
            )
            self._health_check_thread.start()
            logger.info("Backend health monitoring started")
    
    def stop_health_monitoring(self):
        """Stop background health monitoring"""
        self._stop_health_checks = True
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=5)
        logger.info("Backend health monitoring stopped")
    
    def _health_check_loop(self):
        """Background thread for periodic health checks"""
        while not self._stop_health_checks:
            try:
                self.check_all_backends_health()
                time.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                time.sleep(5)  # Short sleep on error
    
    def check_backend_health(self, backend: BackendInstance) -> BackendStatus:
        """Check health of a single backend instance"""
        try:
            start_time = time.time()
            
            # Make health check request
            response = requests.get(
                f"{backend.url}api/v1/health",
                timeout=10,
                headers={'User-Agent': 'AiArt-BackendRouter/1.0'}
            )
            
            response_time = time.time() - start_time
            
            with self._lock:
                backend.response_time = response_time
                backend.last_check = datetime.utcnow()
            
            if response.status_code == 200:
                health_data = response.json()
                status = health_data.get('status', 'unknown')
                
                with self._lock:
                    backend.success_count += 1
                    backend.consecutive_failures = 0
                    backend.last_error = None
                
                if status == 'healthy':
                    return BackendStatus.HEALTHY
                elif status == 'degraded':
                    return BackendStatus.DEGRADED
                else:
                    return BackendStatus.DEGRADED
            else:
                with self._lock:
                    backend.error_count += 1
                    backend.consecutive_failures += 1
                    backend.last_error = f"HTTP {response.status_code}"
                
                return BackendStatus.DEGRADED
                
        except requests.exceptions.Timeout:
            with self._lock:
                backend.error_count += 1
                backend.consecutive_failures += 1
                backend.last_error = "Timeout"
                backend.response_time = 10.0  # Timeout value
            return BackendStatus.DOWN
            
        except requests.exceptions.ConnectionError:
            with self._lock:
                backend.error_count += 1
                backend.consecutive_failures += 1
                backend.last_error = "Connection Error"
                backend.response_time = 10.0
            return BackendStatus.DOWN
            
        except Exception as e:
            with self._lock:
                backend.error_count += 1
                backend.consecutive_failures += 1
                backend.last_error = str(e)
            return BackendStatus.DOWN
    
    def check_all_backends_health(self):
        """Check health of all backend instances"""
        for backend in self.backends:
            status = self.check_backend_health(backend)
            with self._lock:
                backend.status = status
        
        self.last_health_check = datetime.utcnow()
        logger.debug(f"Health check completed for {len(self.backends)} backends")
    
    def get_available_backend(self) -> Optional[BackendInstance]:
        """Get the best available backend based on health score and priority"""
        with self._lock:
            # Filter to only healthy or degraded backends
            available_backends = [
                b for b in self.backends 
                if b.status in [BackendStatus.HEALTHY, BackendStatus.DEGRADED]
            ]
            
            if not available_backends:
                logger.warning("No available backends found")
                return None
            
            # Sort by health score (descending) and priority (ascending)
            available_backends.sort(
                key=lambda b: (-b.health_score, b.priority)
            )
            
            best_backend = available_backends[0]
            logger.debug(f"Selected backend: {best_backend.name} (score: {best_backend.health_score:.2f})")
            
            return best_backend
    
    def mark_backend_down(self, backend_url: str, error: str = None):
        """Mark a specific backend as down"""
        with self._lock:
            for backend in self.backends:
                if backend.url.rstrip('/') == backend_url.rstrip('/'):
                    backend.status = BackendStatus.DOWN
                    backend.consecutive_failures += 1
                    backend.error_count += 1
                    if error:
                        backend.last_error = error
                    logger.warning(f"Marked backend {backend.name} as down: {error}")
                    break
    
    def get_backend_status(self) -> Dict:
        """Get status of all backends"""
        with self._lock:
            status = {
                'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
                'backends': []
            }
            
            for backend in self.backends:
                backend_info = {
                    'name': backend.name,
                    'url': backend.url,
                    'status': backend.status.value,
                    'health_score': backend.health_score,
                    'priority': backend.priority,
                    'response_time': backend.response_time,
                    'error_count': backend.error_count,
                    'success_count': backend.success_count,
                    'consecutive_failures': backend.consecutive_failures,
                    'last_check': backend.last_check.isoformat() if backend.last_check else None,
                    'last_error': backend.last_error
                }
                status['backends'].append(backend_info)
            
            return status
    
    def make_request(self, endpoint: str, method: str = 'GET', **kwargs) -> Tuple[bool, Dict]:
        """
        Make a request to the best available backend with automatic failover
        
        Args:
            endpoint: API endpoint (without /api/v1/ prefix)
            method: HTTP method
            **kwargs: Additional arguments for requests
            
        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        max_retries = len(self.backends)
        tried_backends = set()
        
        for attempt in range(max_retries):
            backend = self.get_available_backend()
            
            if not backend or backend.url in tried_backends:
                # No more backends to try
                break
            
            tried_backends.add(backend.url)
            
            try:
                url = f"{backend.url}api/v1/{endpoint.lstrip('/')}"
                
                # Set default timeout if not provided
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = 30
                
                # Make the request
                response = requests.request(method, url, **kwargs)
                
                if response.status_code < 500:
                    # Success or client error (don't retry client errors)
                    with self._lock:
                        backend.success_count += 1
                        backend.consecutive_failures = 0
                    
                    try:
                        return True, response.json()
                    except ValueError:
                        return True, {'response': response.text}
                else:
                    # Server error, try next backend
                    self.mark_backend_down(backend.url, f"HTTP {response.status_code}")
                    continue
                    
            except requests.exceptions.RequestException as e:
                self.mark_backend_down(backend.url, str(e))
                continue
            except Exception as e:
                logger.error(f"Unexpected error with backend {backend.name}: {e}")
                self.mark_backend_down(backend.url, str(e))
                continue
        
        # All backends failed
        logger.error(f"All backends failed for endpoint: {endpoint}")
        return False, {
            'error': 'All backends unavailable',
            'message': 'No healthy backends available to process the request'
        }
    
    def __del__(self):
        """Cleanup when router is destroyed"""
        self.stop_health_monitoring()