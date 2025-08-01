"""
Flask Integration for Request Queue Management System

This module provides decorators and utilities to integrate the request queue
management system with existing Flask endpoints.
"""

import time
import threading
from functools import wraps
from flask import request, jsonify, g, current_app
from typing import Dict, Optional, Callable, Any
import logging

from request_queue_manager import get_queue_manager, RequestStatus

logger = logging.getLogger(__name__)


class QueuedRequestProcessor:
    """Handles processing of queued requests in background threads"""
    
    def __init__(self, queue_manager):
        self.queue_manager = queue_manager
        self._worker_threads = []
        self._shutdown_event = threading.Event()
        self._processing_functions = {}  # endpoint -> processing function
        
    def register_endpoint_processor(self, endpoint: str, processor_func: Callable):
        """Register a processing function for a specific endpoint"""
        self._processing_functions[endpoint] = processor_func
        logger.info(f"Registered processor for endpoint: {endpoint}")
    
    def start_workers(self, num_workers: int = 3):
        """Start background worker threads"""
        for i in range(num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"QueueWorker-{i}",
                daemon=True
            )
            worker.start()
            self._worker_threads.append(worker)
        
        logger.info(f"Started {num_workers} queue worker threads")
    
    def _worker_loop(self):
        """Main worker loop for processing queued requests"""
        while not self._shutdown_event.wait(1):  # Check every second
            try:
                # Get next request from queue
                queued_request = self.queue_manager.get_next_request()
                if not queued_request:
                    continue
                
                # Process the request
                self._process_request(queued_request)
                
            except Exception as e:
                logger.error(f"Error in queue worker: {e}")
    
    def _process_request(self, queued_request):
        """Process a single queued request"""
        try:
            endpoint = queued_request.endpoint
            
            if endpoint not in self._processing_functions:
                error_msg = f"No processor registered for endpoint: {endpoint}"
                logger.error(error_msg)
                self.queue_manager.complete_request(
                    queued_request.request_id,
                    error_message=error_msg
                )
                return
            
            # Get the processing function
            processor_func = self._processing_functions[endpoint]
            
            # Process the request
            logger.info(f"Processing request {queued_request.request_id} for endpoint {endpoint}")
            
            # Call the processor with request data
            result = processor_func(queued_request.request_data)
            
            # Mark as completed
            self.queue_manager.complete_request(
                queued_request.request_id,
                result=result
            )
            
        except Exception as e:
            error_msg = f"Error processing request {queued_request.request_id}: {str(e)}"
            logger.error(error_msg)
            self.queue_manager.complete_request(
                queued_request.request_id,
                error_message=error_msg
            )
    
    def shutdown(self):
        """Shutdown worker threads"""
        self._shutdown_event.set()
        for worker in self._worker_threads:
            worker.join(timeout=5)
        logger.info("Queue worker threads shutdown complete")


# Global processor instance
_request_processor = None


def get_request_processor() -> QueuedRequestProcessor:
    """Get global QueuedRequestProcessor instance"""
    global _request_processor
    if _request_processor is None:
        queue_manager = get_queue_manager()
        _request_processor = QueuedRequestProcessor(queue_manager)
    return _request_processor


def queue_aware_endpoint(endpoint_name: str, processor_func: Optional[Callable] = None):
    """
    Decorator to make Flask endpoints queue-aware.
    
    When server load is high (>80%), requests are queued instead of processed immediately.
    Provides real-time feedback about queue position and estimated wait times.
    
    Args:
        endpoint_name: Name of the endpoint for queue management
        processor_func: Optional function to process queued requests in background
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get queue manager and check server load
            queue_manager = get_queue_manager()
            
            # Check if we should accept the request
            accept, load_info = queue_manager.should_accept_request()
            
            # Get user information
            user_id = None
            is_authenticated = False
            is_donor = False
            
            # Try to get user info from Flask-Login current_user
            try:
                from flask_login import current_user
                if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                    user_id = getattr(current_user, 'id', None) or str(getattr(current_user, '_id', ''))
                    is_authenticated = True
                    # Check if user is a donor (implement based on your user model)
                    is_donor = getattr(current_user, 'is_donor', False)
            except (ImportError, AttributeError, RuntimeError):
                # Handle cases where Flask-Login is not available or not configured
                pass
            
            # Get client IP
            from ip_utils import get_client_ip
            ip_address = get_client_ip()
            
            # Determine if request should be queued based on server load
            server_load = load_info.get('server_load', 0.0)
            should_queue = server_load > 0.8  # Queue when load exceeds 80%
            
            # If server load is high, queue the request
            if should_queue:
                # Prepare request data for queuing
                request_data = {
                    'args': args,
                    'kwargs': kwargs,
                    'form_data': dict(request.form) if request.form else {},
                    'json_data': request.get_json() if request.is_json else {},
                    'query_params': dict(request.args),
                    'headers': dict(request.headers),
                    'method': request.method,
                    'url': request.url
                }
                
                # Enqueue the request
                request_id, queue_info = queue_manager.enqueue_request(
                    user_id=user_id,
                    ip_address=ip_address,
                    endpoint=endpoint_name,
                    request_data=request_data,
                    is_authenticated=is_authenticated,
                    is_donor=is_donor
                )
                
                # Register processor if provided
                if processor_func:
                    processor = get_request_processor()
                    processor.register_endpoint_processor(endpoint_name, processor_func)
                
                # Create user-friendly queue message
                from user_friendly_errors import create_server_busy_error
                
                busy_response, _ = create_server_busy_error(
                    server_load=server_load,
                    queue_length=queue_info.get('queue_position', 0),
                    estimated_wait=queue_info.get('estimated_wait_time', 300)
                )
                
                # Return queue information with user-friendly messaging
                response_data = {
                    'queued': True,
                    'request_id': request_id,
                    'status': 'queued',
                    'message': busy_response['message'],
                    'title': busy_response['title'],
                    'action_message': busy_response['action_message'],
                    'show_donation_prompt': busy_response['show_donation_prompt'],
                    'donation_message': busy_response['donation_message'],
                    'donation_link': busy_response['donation_link'],
                    'upgrade_available': busy_response['upgrade_available'],
                    'upgrade_message': busy_response['upgrade_message'],
                    'alternatives': busy_response['alternatives'],
                    'queue_info': queue_info,
                    'server_load': server_load,
                    'status_url': f'/api/queue/status/{request_id}',
                    'retry_suggestion': None  # Will be provided if request fails
                }
                
                return jsonify(response_data), 202  # HTTP 202 Accepted
            
            else:
                # Server load is acceptable, process immediately
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    # If immediate processing fails, provide user-friendly error response
                    from user_friendly_errors import create_generation_failed_error
                    
                    # Determine service name from endpoint
                    service_name = "AI service"
                    if "image" in endpoint_name:
                        service_name = "AI image generator"
                    elif "video" in endpoint_name:
                        service_name = "AI video generator"
                    
                    error_response, status_code = create_generation_failed_error(
                        service_name=service_name,
                        retry_count=0
                    )
                    
                    # Add server load and retry suggestion for compatibility
                    queue_manager = get_queue_manager()
                    backoff_calc = queue_manager._backoff_calculator
                    retry_suggestion = backoff_calc.get_retry_suggestion(0, server_load)
                    
                    error_response['retry_suggestion'] = retry_suggestion
                    error_response['server_load'] = server_load
                    error_response['technical_error'] = str(e)
                    
                    return jsonify(error_response), status_code
        
        return decorated_function
    return decorator


def create_queue_status_endpoints(app):
    """Create Flask endpoints for queue status checking"""
    
    @app.route('/api/queue/status/<request_id>', methods=['GET'])
    def get_queue_status(request_id):
        """Get status of a queued request"""
        queue_manager = get_queue_manager()
        status = queue_manager.get_request_status(request_id)
        
        if not status:
            return jsonify({'error': 'Request not found'}), 404
        
        # Add retry suggestion if request failed
        if status['status'] == 'failed':
            retry_suggestion = queue_manager.get_retry_suggestion(request_id)
            if retry_suggestion:
                status['retry_suggestion'] = retry_suggestion
        
        return jsonify(status)
    
    @app.route('/api/queue/metrics', methods=['GET'])
    def get_queue_metrics():
        """Get comprehensive queue metrics"""
        queue_manager = get_queue_manager()
        metrics = queue_manager.get_queue_metrics()
        return jsonify(metrics)
    
    @app.route('/api/queue/health', methods=['GET'])
    def queue_health_check():
        """Health check endpoint for queue system"""
        queue_manager = get_queue_manager()
        metrics = queue_manager.get_queue_metrics()
        
        # Determine health status
        server_load = metrics['server_load']
        queue_length = sum(metrics['queue_lengths'].values())
        
        if server_load > 0.9 or queue_length > 100:
            health_status = 'degraded'
        elif server_load > 0.7 or queue_length > 50:
            health_status = 'warning'
        else:
            health_status = 'healthy'
        
        return jsonify({
            'status': health_status,
            'server_load': server_load,
            'queue_length': queue_length,
            'processing_requests': metrics['processing_requests'],
            'timestamp': time.time()
        })


def initialize_queue_integration(app, resource_monitor=None, num_workers: int = 3):
    """
    Initialize queue integration with Flask app.
    
    Args:
        app: Flask application instance
        resource_monitor: Resource monitor instance
        num_workers: Number of background worker threads
    """
    # Initialize queue manager
    from request_queue_manager import initialize_queue_management
    queue_manager = initialize_queue_management(resource_monitor)
    
    # Create queue status endpoints
    create_queue_status_endpoints(app)
    
    # Start background workers
    processor = get_request_processor()
    processor.start_workers(num_workers)
    
    # Register shutdown handler
    @app.teardown_appcontext
    def shutdown_queue_system(exception):
        if exception:
            logger.error(f"App context teardown with exception: {exception}")
    
    # Add cleanup on app shutdown
    import atexit
    def cleanup():
        processor.shutdown()
        queue_manager.shutdown()
    
    atexit.register(cleanup)
    
    logger.info(f"Queue integration initialized with {num_workers} workers")
    
    return queue_manager, processor


# Utility functions for common queue operations

def get_user_queue_status(user_id: str) -> Dict:
    """Get queue status for all requests from a specific user"""
    queue_manager = get_queue_manager()
    
    # This would require extending the queue manager to track requests by user
    # For now, return basic info
    metrics = queue_manager.get_queue_metrics()
    
    return {
        'user_id': user_id,
        'queue_metrics': metrics,
        'message': 'Use individual request IDs to check specific request status'
    }


def cancel_queued_request(request_id: str) -> bool:
    """Cancel a queued request (if still in queue)"""
    queue_manager = get_queue_manager()
    
    # Get request status
    status = queue_manager.get_request_status(request_id)
    if not status:
        return False
    
    # Can only cancel queued requests
    if status['status'] != 'queued':
        return False
    
    # Mark as cancelled (this would require extending the queue manager)
    # For now, we'll just return False as cancellation isn't implemented
    return False


def estimate_queue_wait_time(user_id: Optional[str] = None, 
                           is_authenticated: bool = False,
                           is_donor: bool = False) -> Dict:
    """Estimate wait time for a new request"""
    queue_manager = get_queue_manager()
    
    # Determine priority
    from request_queue_manager import RequestPriority
    if is_donor:
        priority = RequestPriority.HIGH
    elif is_authenticated:
        priority = RequestPriority.MEDIUM
    else:
        priority = RequestPriority.LOW
    
    # Calculate estimated wait time
    estimated_wait = queue_manager._calculate_estimated_wait_time(priority)
    
    return {
        'estimated_wait_seconds': estimated_wait,
        'estimated_wait_human': queue_manager._format_wait_time(estimated_wait),
        'priority': priority.name.lower(),
        'queue_metrics': queue_manager.get_queue_metrics()
    }