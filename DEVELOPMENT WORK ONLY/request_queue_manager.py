"""
Request Queue Management System for AiArt Application

This module implements a queue-based system that accepts all requests during high load,
provides exponential backoff for retry suggestions, and offers real-time feedback
for queue position and estimated wait times.
"""

import time
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
import json
from collections import deque
import math

logger = logging.getLogger(__name__)


class RequestStatus(Enum):
    """Status enumeration for queued requests"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RequestPriority(Enum):
    """Priority levels for request processing"""
    HIGH = 1      # Donor users
    MEDIUM = 2    # Registered users
    LOW = 3       # Anonymous users


@dataclass
class QueuedRequest:
    """Represents a request in the processing queue"""
    request_id: str
    user_id: Optional[str]
    ip_address: str
    endpoint: str
    request_data: Dict
    priority: RequestPriority
    status: RequestStatus = RequestStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    estimated_wait_time: int = 0  # seconds
    position_in_queue: int = 0


@dataclass
class QueueMetrics:
    """Metrics for queue performance monitoring"""
    total_requests: int = 0
    queued_requests: int = 0
    processing_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    average_wait_time: float = 0.0
    average_processing_time: float = 0.0
    queue_throughput: float = 0.0  # requests per minute
    server_load: float = 0.0


class ExponentialBackoffCalculator:
    """Calculates exponential backoff times for retry suggestions"""
    
    def __init__(self, base_delay: int = 2, max_delay: int = 300, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
    
    def calculate_delay(self, retry_count: int, server_load: float = 0.0) -> int:
        """
        Calculate exponential backoff delay with optional jitter and load adjustment.
        
        Args:
            retry_count: Number of previous retry attempts
            server_load: Current server load (0.0 to 1.0)
        
        Returns:
            Delay in seconds
        """
        # Base exponential backoff: base_delay * (2 ^ retry_count)
        delay = self.base_delay * (2 ** retry_count)
        
        # Adjust for server load (higher load = longer delays)
        load_multiplier = 1.0 + (server_load * 2.0)  # 1.0x to 3.0x multiplier
        delay = int(delay * load_multiplier)
        
        # Apply jitter to prevent thundering herd
        if self.jitter:
            import random
            jitter_factor = random.uniform(0.5, 1.5)
            delay = int(delay * jitter_factor)
        
        # Cap at maximum delay
        return min(delay, self.max_delay)
    
    def get_retry_suggestion(self, retry_count: int, server_load: float = 0.0) -> Dict:
        """Get user-friendly retry suggestion with timing"""
        delay = self.calculate_delay(retry_count, server_load)
        
        if delay < 60:
            time_str = f"{delay} seconds"
        elif delay < 3600:
            time_str = f"{delay // 60} minutes"
        else:
            time_str = f"{delay // 3600} hours"
        
        # Generate appropriate message based on server load
        if server_load > 0.8:
            message = f"🚀 Server is very busy! Please try again in {time_str}."
        elif server_load > 0.5:
            message = f"⏳ Server is under load. Please wait {time_str} before retrying."
        else:
            message = f"⏱️ Please wait {time_str} before trying again."
        
        return {
            'delay_seconds': delay,
            'delay_human': time_str,
            'message': message,
            'retry_after': datetime.now(timezone.utc) + timedelta(seconds=delay)
        }


class RequestQueueManager:
    """
    Main queue management system that handles request queuing, processing,
    and provides real-time feedback on queue status.
    """
    
    def __init__(self, resource_monitor=None, max_concurrent_requests: int = 5):
        self.resource_monitor = resource_monitor
        self.max_concurrent_requests = max_concurrent_requests
        
        # Queue storage (priority queues)
        self._queues = {
            RequestPriority.HIGH: deque(),
            RequestPriority.MEDIUM: deque(),
            RequestPriority.LOW: deque()
        }
        
        # Active processing requests
        self._processing_requests = {}  # request_id -> QueuedRequest
        
        # Request lookup
        self._all_requests = {}  # request_id -> QueuedRequest
        
        # Metrics tracking
        self._metrics = QueueMetrics()
        self._processing_times = deque(maxlen=100)  # Last 100 processing times
        self._wait_times = deque(maxlen=100)  # Last 100 wait times
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Backoff calculator
        self._backoff_calculator = ExponentialBackoffCalculator()
        
        # Background cleanup thread
        self._cleanup_thread = None
        self._shutdown_event = threading.Event()
        self._start_cleanup_thread()
        
        logger.info(f"RequestQueueManager initialized with max_concurrent_requests={max_concurrent_requests}")
    
    def _start_cleanup_thread(self):
        """Start background thread for cleanup and metrics updates"""
        def cleanup_worker():
            while not self._shutdown_event.wait(30):  # Run every 30 seconds
                try:
                    self._cleanup_old_requests()
                    self._update_metrics()
                except Exception as e:
                    logger.error(f"Error in cleanup thread: {e}")
        
        self._cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self._cleanup_thread.start()
    
    def _get_server_load(self) -> float:
        """Get current server load (0.0 to 1.0)"""
        if self.resource_monitor:
            try:
                metrics = self.resource_monitor.get_current_metrics()
                return min(1.0, metrics.get('current_load', 0.0) / 100.0)
            except Exception as e:
                logger.warning(f"Failed to get server load: {e}")
        return 0.0
    
    def _determine_priority(self, user_id: Optional[str], is_authenticated: bool = False, 
                          is_donor: bool = False) -> RequestPriority:
        """Determine request priority based on user status"""
        if is_donor:
            return RequestPriority.HIGH
        elif is_authenticated:
            return RequestPriority.MEDIUM
        else:
            return RequestPriority.LOW
    
    def _calculate_estimated_wait_time(self, priority: RequestPriority) -> int:
        """Calculate estimated wait time based on queue position and processing times"""
        with self._lock:
            # Count requests ahead in queue
            requests_ahead = 0
            
            # Higher priority queues are processed first
            for p in RequestPriority:
                if p.value < priority.value:
                    requests_ahead += len(self._queues[p])
                elif p.value == priority.value:
                    requests_ahead += len(self._queues[p])
                    break
            
            # Add currently processing requests
            requests_ahead += len(self._processing_requests)
            
            # Calculate average processing time
            if self._processing_times:
                avg_processing_time = sum(self._processing_times) / len(self._processing_times)
            else:
                avg_processing_time = 30  # Default 30 seconds
            
            # Account for concurrent processing
            concurrent_factor = max(1, self.max_concurrent_requests)
            estimated_wait = int((requests_ahead * avg_processing_time) / concurrent_factor)
            
            # Add buffer for server load
            server_load = self._get_server_load()
            load_multiplier = 1.0 + (server_load * 1.5)
            
            return int(estimated_wait * load_multiplier)
    
    def enqueue_request(self, user_id: Optional[str], ip_address: str, endpoint: str,
                       request_data: Dict, is_authenticated: bool = False, 
                       is_donor: bool = False) -> Tuple[str, Dict]:
        """
        Enqueue a new request for processing.
        
        Returns:
            Tuple of (request_id, queue_info)
        """
        request_id = str(uuid.uuid4())
        priority = self._determine_priority(user_id, is_authenticated, is_donor)
        
        # Create queued request
        queued_request = QueuedRequest(
            request_id=request_id,
            user_id=user_id,
            ip_address=ip_address,
            endpoint=endpoint,
            request_data=request_data,
            priority=priority
        )
        
        # Calculate estimated wait time
        estimated_wait = self._calculate_estimated_wait_time(priority)
        queued_request.estimated_wait_time = estimated_wait
        
        with self._lock:
            # Add to appropriate priority queue
            self._queues[priority].append(queued_request)
            self._all_requests[request_id] = queued_request
            
            # Update position in queue
            queued_request.position_in_queue = len(self._queues[priority])
            
            # Update metrics
            self._metrics.total_requests += 1
            self._metrics.queued_requests += 1
        
        # Prepare queue info response
        queue_info = {
            'request_id': request_id,
            'status': RequestStatus.QUEUED.value,
            'position_in_queue': queued_request.position_in_queue,
            'estimated_wait_time': estimated_wait,
            'estimated_wait_human': self._format_wait_time(estimated_wait),
            'priority': priority.name.lower(),
            'created_at': queued_request.created_at.isoformat(),
            'message': self._get_queue_message(queued_request)
        }
        
        logger.info(f"Enqueued request {request_id} with priority {priority.name} "
                   f"(estimated wait: {estimated_wait}s)")
        
        return request_id, queue_info
    
    def get_next_request(self) -> Optional[QueuedRequest]:
        """Get the next request to process (highest priority first)"""
        with self._lock:
            # Check if we can process more requests
            if len(self._processing_requests) >= self.max_concurrent_requests:
                return None
            
            # Get next request from highest priority queue
            for priority in RequestPriority:
                if self._queues[priority]:
                    request = self._queues[priority].popleft()
                    
                    # Move to processing
                    request.status = RequestStatus.PROCESSING
                    request.started_at = datetime.now(timezone.utc)
                    self._processing_requests[request.request_id] = request
                    
                    # Update metrics
                    self._metrics.queued_requests -= 1
                    self._metrics.processing_requests += 1
                    
                    # Calculate wait time for metrics
                    wait_time = (request.started_at - request.created_at).total_seconds()
                    self._wait_times.append(wait_time)
                    
                    logger.info(f"Started processing request {request.request_id} "
                               f"(waited {wait_time:.1f}s)")
                    
                    return request
            
            return None
    
    def complete_request(self, request_id: str, result: Dict = None, 
                        error_message: str = None) -> bool:
        """Mark a request as completed or failed"""
        with self._lock:
            if request_id not in self._processing_requests:
                logger.warning(f"Attempted to complete non-processing request {request_id}")
                return False
            
            request = self._processing_requests.pop(request_id)
            request.completed_at = datetime.now(timezone.utc)
            
            if error_message:
                request.status = RequestStatus.FAILED
                request.error_message = error_message
                self._metrics.failed_requests += 1
            else:
                request.status = RequestStatus.COMPLETED
                request.result = result
                self._metrics.completed_requests += 1
            
            # Update metrics
            self._metrics.processing_requests -= 1
            
            # Calculate processing time
            if request.started_at:
                processing_time = (request.completed_at - request.started_at).total_seconds()
                self._processing_times.append(processing_time)
            
            logger.info(f"Completed request {request_id} with status {request.status.value}")
            return True
    
    def get_request_status(self, request_id: str) -> Optional[Dict]:
        """Get current status of a request"""
        with self._lock:
            if request_id not in self._all_requests:
                return None
            
            request = self._all_requests[request_id]
            
            # Update position in queue if still queued
            if request.status == RequestStatus.QUEUED:
                self._update_queue_positions()
            
            status_info = {
                'request_id': request_id,
                'status': request.status.value,
                'created_at': request.created_at.isoformat(),
                'priority': request.priority.name.lower(),
                'estimated_wait_time': request.estimated_wait_time,
                'estimated_wait_human': self._format_wait_time(request.estimated_wait_time),
                'position_in_queue': request.position_in_queue if request.status == RequestStatus.QUEUED else 0,
                'message': self._get_status_message(request)
            }
            
            # Add timing information
            if request.started_at:
                status_info['started_at'] = request.started_at.isoformat()
            if request.completed_at:
                status_info['completed_at'] = request.completed_at.isoformat()
            
            # Add result or error
            if request.status == RequestStatus.COMPLETED and request.result:
                status_info['result'] = request.result
            elif request.status == RequestStatus.FAILED and request.error_message:
                status_info['error_message'] = request.error_message
            
            return status_info
    
    def get_retry_suggestion(self, request_id: str) -> Optional[Dict]:
        """Get retry suggestion for a failed request"""
        with self._lock:
            if request_id not in self._all_requests:
                return None
            
            request = self._all_requests[request_id]
            if request.status != RequestStatus.FAILED:
                return None
            
            server_load = self._get_server_load()
            return self._backoff_calculator.get_retry_suggestion(request.retry_count, server_load)
    
    def should_accept_request(self) -> Tuple[bool, Dict]:
        """
        Determine if new requests should be accepted based on server load.
        Always returns True (accept all requests) but provides load information.
        """
        server_load = self._get_server_load()
        queue_length = sum(len(queue) for queue in self._queues.values())
        
        # Always accept requests, but provide load information
        accept = True
        
        info = {
            'accept': accept,
            'server_load': server_load,
            'queue_length': queue_length,
            'processing_requests': len(self._processing_requests),
            'estimated_wait_time': self._calculate_estimated_wait_time(RequestPriority.LOW),
            'message': self._get_load_message(server_load, queue_length)
        }
        
        return accept, info
    
    def get_queue_metrics(self) -> Dict:
        """Get comprehensive queue metrics"""
        with self._lock:
            self._update_metrics()
            
            return {
                'total_requests': self._metrics.total_requests,
                'queued_requests': self._metrics.queued_requests,
                'processing_requests': self._metrics.processing_requests,
                'completed_requests': self._metrics.completed_requests,
                'failed_requests': self._metrics.failed_requests,
                'average_wait_time': self._metrics.average_wait_time,
                'average_processing_time': self._metrics.average_processing_time,
                'queue_throughput': self._metrics.queue_throughput,
                'server_load': self._get_server_load(),
                'queue_lengths': {
                    'high_priority': len(self._queues[RequestPriority.HIGH]),
                    'medium_priority': len(self._queues[RequestPriority.MEDIUM]),
                    'low_priority': len(self._queues[RequestPriority.LOW])
                },
                'max_concurrent_requests': self.max_concurrent_requests
            }
    
    def _update_queue_positions(self):
        """Update position in queue for all queued requests"""
        for priority, queue in self._queues.items():
            for i, request in enumerate(queue):
                request.position_in_queue = i + 1
    
    def _update_metrics(self):
        """Update queue metrics"""
        # Calculate averages
        if self._wait_times:
            self._metrics.average_wait_time = sum(self._wait_times) / len(self._wait_times)
        
        if self._processing_times:
            self._metrics.average_processing_time = sum(self._processing_times) / len(self._processing_times)
        
        # Calculate throughput (requests per minute)
        if self._processing_times:
            # Use recent processing times to estimate throughput
            recent_times = list(self._processing_times)[-10:]  # Last 10 requests
            if recent_times:
                avg_time = sum(recent_times) / len(recent_times)
                self._metrics.queue_throughput = (60.0 / avg_time) * self.max_concurrent_requests
    
    def _cleanup_old_requests(self, max_age_hours: int = 24):
        """Clean up old completed/failed requests"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        with self._lock:
            requests_to_remove = []
            
            for request_id, request in self._all_requests.items():
                if (request.status in [RequestStatus.COMPLETED, RequestStatus.FAILED] and
                    request.completed_at and request.completed_at < cutoff_time):
                    requests_to_remove.append(request_id)
            
            for request_id in requests_to_remove:
                del self._all_requests[request_id]
            
            if requests_to_remove:
                logger.info(f"Cleaned up {len(requests_to_remove)} old requests")
    
    def _format_wait_time(self, seconds: int) -> str:
        """Format wait time in human-readable format"""
        if seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            return f"{seconds // 60} minutes"
        else:
            return f"{seconds // 3600} hours"
    
    def _get_queue_message(self, request: QueuedRequest) -> str:
        """Get user-friendly message for queued request"""
        if request.position_in_queue == 1:
            return "🎯 You're next in line! Processing will begin shortly."
        elif request.position_in_queue <= 3:
            return f"⏳ You're #{request.position_in_queue} in line. Almost there!"
        else:
            wait_str = self._format_wait_time(request.estimated_wait_time)
            return f"📋 You're #{request.position_in_queue} in queue. Estimated wait: {wait_str}"
    
    def _get_status_message(self, request: QueuedRequest) -> str:
        """Get user-friendly status message"""
        if request.status == RequestStatus.QUEUED:
            return self._get_queue_message(request)
        elif request.status == RequestStatus.PROCESSING:
            return "🔄 Your request is being processed..."
        elif request.status == RequestStatus.COMPLETED:
            return "✅ Your request has been completed successfully!"
        elif request.status == RequestStatus.FAILED:
            return "❌ Your request failed. You can retry with exponential backoff."
        else:
            return f"Status: {request.status.value}"
    
    def _get_load_message(self, server_load: float, queue_length: int) -> str:
        """Get user-friendly message about server load"""
        if server_load > 0.8:
            return f"🚀 Server is very busy ({queue_length} requests queued). All requests are accepted but may take longer."
        elif server_load > 0.5:
            return f"⏳ Server is under moderate load ({queue_length} requests queued). Requests are being processed normally."
        else:
            return f"✅ Server is running smoothly ({queue_length} requests queued)."
    
    def shutdown(self):
        """Shutdown the queue manager"""
        self._shutdown_event.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        logger.info("RequestQueueManager shutdown complete")


# Global queue manager instance
_queue_manager = None


def get_queue_manager(resource_monitor=None, max_concurrent_requests: int = 5) -> RequestQueueManager:
    """Get global RequestQueueManager instance"""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = RequestQueueManager(resource_monitor, max_concurrent_requests)
    return _queue_manager


def initialize_queue_management(resource_monitor=None, max_concurrent_requests: int = 5):
    """Initialize global queue management"""
    manager = get_queue_manager(resource_monitor, max_concurrent_requests)
    logger.info("Global request queue management initialized")
    return manager