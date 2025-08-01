"""
Unit tests for Request Queue Management System

Tests queue management under peak load conditions, exponential backoff,
real-time feedback, and Flask integration.
"""

import unittest
import time
import threading
import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from request_queue_manager import (
    RequestQueueManager, ExponentialBackoffCalculator, RequestStatus, 
    RequestPriority, QueuedRequest, get_queue_manager
)
from queue_flask_integration import (
    QueuedRequestProcessor, queue_aware_endpoint, get_request_processor
)


class TestExponentialBackoffCalculator(unittest.TestCase):
    """Test exponential backoff calculation"""
    
    def setUp(self):
        self.calculator = ExponentialBackoffCalculator(base_delay=2, max_delay=300)
    
    def test_basic_exponential_backoff(self):
        """Test basic exponential backoff calculation"""
        # Test progression: 2, 4, 8, 16, 32...
        self.assertEqual(self.calculator.calculate_delay(0, 0.0), 2)
        
        # Allow for jitter variation (±50%)
        delay_1 = self.calculator.calculate_delay(1, 0.0)
        self.assertGreaterEqual(delay_1, 2)  # At least 2 seconds (4 * 0.5)
        self.assertLessEqual(delay_1, 12)    # At most 12 seconds (4 * 3.0 load multiplier * 1.5 jitter)
        
        delay_2 = self.calculator.calculate_delay(2, 0.0)
        self.assertGreaterEqual(delay_2, 4)  # At least 4 seconds
        self.assertLessEqual(delay_2, 24)    # At most 24 seconds
    
    def test_server_load_adjustment(self):
        """Test delay adjustment based on server load"""
        # High server load should increase delays
        low_load_delay = self.calculator.calculate_delay(1, 0.1)
        high_load_delay = self.calculator.calculate_delay(1, 0.9)
        
        # High load delay should be significantly higher
        self.assertGreater(high_load_delay, low_load_delay)
    
    def test_max_delay_cap(self):
        """Test that delays are capped at maximum"""
        # Very high retry count should be capped
        delay = self.calculator.calculate_delay(20, 1.0)  # Very high retry count and load
        self.assertLessEqual(delay, 300)  # Should not exceed max_delay
    
    def test_retry_suggestion_format(self):
        """Test retry suggestion formatting"""
        suggestion = self.calculator.get_retry_suggestion(1, 0.5)
        
        self.assertIn('delay_seconds', suggestion)
        self.assertIn('delay_human', suggestion)
        self.assertIn('message', suggestion)
        self.assertIn('retry_after', suggestion)
        
        # Check that retry_after is a future datetime
        self.assertGreater(suggestion['retry_after'], datetime.now(timezone.utc))


class TestRequestQueueManager(unittest.TestCase):
    """Test request queue management functionality"""
    
    def setUp(self):
        # Mock resource monitor
        self.mock_resource_monitor = Mock()
        self.mock_resource_monitor.get_current_metrics.return_value = {
            'current_load': 50.0,  # 50% load
            'cpu_usage': 40.0,
            'memory_usage': 60.0
        }
        
        self.queue_manager = RequestQueueManager(
            resource_monitor=self.mock_resource_monitor,
            max_concurrent_requests=2
        )
    
    def tearDown(self):
        self.queue_manager.shutdown()
    
    def test_enqueue_request_basic(self):
        """Test basic request enqueueing"""
        request_id, queue_info = self.queue_manager.enqueue_request(
            user_id="test_user",
            ip_address="192.168.1.1",
            endpoint="test_endpoint",
            request_data={"test": "data"},
            is_authenticated=True,
            is_donor=False
        )
        
        self.assertIsInstance(request_id, str)
        self.assertEqual(queue_info['status'], 'queued')
        self.assertEqual(queue_info['priority'], 'medium')  # Authenticated user
        self.assertGreater(queue_info['estimated_wait_time'], 0)
    
    def test_priority_ordering(self):
        """Test that requests are processed in priority order"""
        # Enqueue requests with different priorities
        low_id, _ = self.queue_manager.enqueue_request(
            user_id=None, ip_address="192.168.1.1", endpoint="test",
            request_data={}, is_authenticated=False, is_donor=False
        )
        
        high_id, _ = self.queue_manager.enqueue_request(
            user_id="donor", ip_address="192.168.1.2", endpoint="test",
            request_data={}, is_authenticated=True, is_donor=True
        )
        
        medium_id, _ = self.queue_manager.enqueue_request(
            user_id="user", ip_address="192.168.1.3", endpoint="test",
            request_data={}, is_authenticated=True, is_donor=False
        )
        
        # Get requests in processing order
        first_request = self.queue_manager.get_next_request()
        second_request = self.queue_manager.get_next_request()
        third_request = self.queue_manager.get_next_request()
        
        # Should be processed in priority order: HIGH, MEDIUM, LOW
        self.assertEqual(first_request.request_id, high_id)
        self.assertEqual(second_request.request_id, medium_id)
        self.assertIsNone(third_request)  # Max concurrent reached
    
    def test_concurrent_request_limit(self):
        """Test that concurrent request limit is enforced"""
        # Enqueue more requests than the limit
        request_ids = []
        for i in range(5):
            request_id, _ = self.queue_manager.enqueue_request(
                user_id=f"user_{i}",
                ip_address=f"192.168.1.{i}",
                endpoint="test",
                request_data={},
                is_authenticated=True,
                is_donor=True  # High priority
            )
            request_ids.append(request_id)
        
        # Should only be able to get max_concurrent_requests
        processing_requests = []
        for _ in range(10):  # Try to get more than the limit
            request = self.queue_manager.get_next_request()
            if request:
                processing_requests.append(request)
            else:
                break
        
        self.assertEqual(len(processing_requests), 2)  # max_concurrent_requests
    
    def test_request_completion(self):
        """Test request completion and metrics update"""
        # Enqueue and start processing a request
        request_id, _ = self.queue_manager.enqueue_request(
            user_id="test_user", ip_address="192.168.1.1", endpoint="test",
            request_data={}, is_authenticated=True, is_donor=False
        )
        
        request = self.queue_manager.get_next_request()
        self.assertIsNotNone(request)
        
        # Complete the request successfully
        result = {"success": True, "data": "test_result"}
        success = self.queue_manager.complete_request(request_id, result=result)
        
        self.assertTrue(success)
        
        # Check status
        status = self.queue_manager.get_request_status(request_id)
        self.assertEqual(status['status'], 'completed')
        self.assertEqual(status['result'], result)
    
    def test_request_failure(self):
        """Test request failure handling"""
        # Enqueue and start processing a request
        request_id, _ = self.queue_manager.enqueue_request(
            user_id="test_user", ip_address="192.168.1.1", endpoint="test",
            request_data={}, is_authenticated=True, is_donor=False
        )
        
        request = self.queue_manager.get_next_request()
        self.assertIsNotNone(request)
        
        # Fail the request
        error_message = "Test error occurred"
        success = self.queue_manager.complete_request(request_id, error_message=error_message)
        
        self.assertTrue(success)
        
        # Check status and retry suggestion
        status = self.queue_manager.get_request_status(request_id)
        self.assertEqual(status['status'], 'failed')
        self.assertEqual(status['error_message'], error_message)
        
        retry_suggestion = self.queue_manager.get_retry_suggestion(request_id)
        self.assertIsNotNone(retry_suggestion)
        self.assertIn('delay_seconds', retry_suggestion)
    
    def test_queue_metrics(self):
        """Test queue metrics calculation"""
        # Enqueue several requests
        for i in range(3):
            self.queue_manager.enqueue_request(
                user_id=f"user_{i}", ip_address=f"192.168.1.{i}", endpoint="test",
                request_data={}, is_authenticated=True, is_donor=False
            )
        
        metrics = self.queue_manager.get_queue_metrics()
        
        self.assertEqual(metrics['total_requests'], 3)
        self.assertEqual(metrics['queued_requests'], 3)
        self.assertEqual(metrics['processing_requests'], 0)
        self.assertGreaterEqual(metrics['server_load'], 0.0)
        self.assertIn('queue_lengths', metrics)
    
    def test_high_load_behavior(self):
        """Test behavior under high server load"""
        # Mock high server load
        self.mock_resource_monitor.get_current_metrics.return_value = {
            'current_load': 90.0,  # 90% load
            'cpu_usage': 85.0,
            'memory_usage': 95.0
        }
        
        # Should still accept requests
        accept, info = self.queue_manager.should_accept_request()
        self.assertTrue(accept)
        self.assertGreater(info['server_load'], 0.8)
        self.assertIn('message', info)
    
    def test_estimated_wait_time_calculation(self):
        """Test estimated wait time calculation"""
        # Enqueue requests to build up queue
        for i in range(5):
            self.queue_manager.enqueue_request(
                user_id=f"user_{i}", ip_address=f"192.168.1.{i}", endpoint="test",
                request_data={}, is_authenticated=True, is_donor=False
            )
        
        # New request should have reasonable wait time estimate
        request_id, queue_info = self.queue_manager.enqueue_request(
            user_id="new_user", ip_address="192.168.1.100", endpoint="test",
            request_data={}, is_authenticated=True, is_donor=False
        )
        
        self.assertGreater(queue_info['estimated_wait_time'], 0)
        self.assertIn('estimated_wait_human', queue_info)
        self.assertGreater(queue_info['position_in_queue'], 0)


class TestQueuedRequestProcessor(unittest.TestCase):
    """Test queued request processor functionality"""
    
    def setUp(self):
        self.mock_queue_manager = Mock()
        self.processor = QueuedRequestProcessor(self.mock_queue_manager)
    
    def tearDown(self):
        self.processor.shutdown()
    
    def test_processor_registration(self):
        """Test endpoint processor registration"""
        def test_processor(request_data):
            return {"result": "processed"}
        
        self.processor.register_endpoint_processor("test_endpoint", test_processor)
        
        self.assertIn("test_endpoint", self.processor._processing_functions)
        self.assertEqual(self.processor._processing_functions["test_endpoint"], test_processor)
    
    def test_request_processing(self):
        """Test request processing workflow"""
        # Mock queued request
        mock_request = Mock()
        mock_request.request_id = "test_request_id"
        mock_request.endpoint = "test_endpoint"
        mock_request.request_data = {"test": "data"}
        
        # Register processor
        def test_processor(request_data):
            return {"result": "processed", "input": request_data}
        
        self.processor.register_endpoint_processor("test_endpoint", test_processor)
        
        # Process the request
        self.processor._process_request(mock_request)
        
        # Verify completion was called
        self.mock_queue_manager.complete_request.assert_called_once()
        call_args = self.mock_queue_manager.complete_request.call_args
        self.assertEqual(call_args[0][0], "test_request_id")  # request_id
        self.assertIn("result", call_args[1])  # result parameter
    
    def test_processing_error_handling(self):
        """Test error handling during request processing"""
        # Mock queued request
        mock_request = Mock()
        mock_request.request_id = "test_request_id"
        mock_request.endpoint = "test_endpoint"
        mock_request.request_data = {"test": "data"}
        
        # Register processor that raises exception
        def failing_processor(request_data):
            raise ValueError("Test processing error")
        
        self.processor.register_endpoint_processor("test_endpoint", failing_processor)
        
        # Process the request
        self.processor._process_request(mock_request)
        
        # Verify completion was called with error
        self.mock_queue_manager.complete_request.assert_called_once()
        call_args = self.mock_queue_manager.complete_request.call_args
        self.assertEqual(call_args[0][0], "test_request_id")  # request_id
        self.assertIn("error_message", call_args[1])  # error_message parameter


class TestFlaskIntegration(unittest.TestCase):
    """Test Flask integration functionality"""
    
    def setUp(self):
        # Mock Flask app and request context
        self.mock_app = Mock()
        self.mock_request = Mock()
        self.mock_request.form = {}
        self.mock_request.is_json = False
        self.mock_request.args = {}
        self.mock_request.headers = {}
        self.mock_request.method = 'POST'
        self.mock_request.url = 'http://test.com/api/test'
    
    @patch('queue_flask_integration.request')
    @patch('queue_flask_integration.get_client_ip')
    @patch('queue_flask_integration.get_queue_manager')
    def test_queue_aware_endpoint_high_load(self, mock_get_queue_manager, 
                                          mock_get_client_ip, mock_request):
        """Test queue-aware endpoint behavior under high load"""
        # Setup mocks
        mock_request.form = {}
        mock_request.is_json = False
        mock_request.args = {}
        mock_request.headers = {}
        mock_request.method = 'POST'
        mock_request.url = 'http://test.com/api/test'
        mock_request.get_json.return_value = None
        
        mock_get_client_ip.return_value = "192.168.1.1"
        
        mock_queue_manager = Mock()
        mock_queue_manager.should_accept_request.return_value = (True, {
            'server_load': 0.9,  # High load
            'queue_length': 10
        })
        mock_queue_manager.enqueue_request.return_value = ("test_request_id", {
            'status': 'queued',
            'position_in_queue': 5,
            'estimated_wait_time': 120,
            'message': 'Test queue message'
        })
        mock_get_queue_manager.return_value = mock_queue_manager
        
        # Create test endpoint
        @queue_aware_endpoint("test_endpoint")
        def test_endpoint():
            return {"result": "immediate_processing"}
        
        # Call endpoint
        with patch('queue_flask_integration.current_user') as mock_current_user:
            mock_current_user.is_authenticated = False
            
            result = test_endpoint()
            
            # Should return queue response due to high load
            self.assertEqual(result[1], 202)  # HTTP 202 Accepted
            response_data = result[0].get_json()
            self.assertTrue(response_data['queued'])
            self.assertEqual(response_data['request_id'], 'test_request_id')
    
    @patch('queue_flask_integration.request')
    @patch('queue_flask_integration.get_client_ip')
    @patch('queue_flask_integration.get_queue_manager')
    def test_queue_aware_endpoint_low_load(self, mock_get_queue_manager,
                                         mock_get_client_ip, mock_request):
        """Test queue-aware endpoint behavior under low load"""
        # Setup mocks
        mock_request.form = {}
        mock_request.is_json = False
        mock_request.args = {}
        mock_request.headers = {}
        mock_request.method = 'POST'
        mock_request.url = 'http://test.com/api/test'
        mock_request.get_json.return_value = None
        
        mock_get_client_ip.return_value = "192.168.1.1"
        
        mock_queue_manager = Mock()
        mock_queue_manager.should_accept_request.return_value = (True, {
            'server_load': 0.3,  # Low load
            'queue_length': 2
        })
        mock_get_queue_manager.return_value = mock_queue_manager
        
        # Create test endpoint
        @queue_aware_endpoint("test_endpoint")
        def test_endpoint():
            return {"result": "immediate_processing"}
        
        # Call endpoint
        with patch('queue_flask_integration.current_user') as mock_current_user:
            mock_current_user.is_authenticated = False
            
            result = test_endpoint()
            
            # Should process immediately due to low load
            self.assertEqual(result, {"result": "immediate_processing"})


class TestPeakLoadScenarios(unittest.TestCase):
    """Test queue management under peak load conditions"""
    
    def setUp(self):
        # Mock high-load resource monitor
        self.mock_resource_monitor = Mock()
        self.mock_resource_monitor.get_current_metrics.return_value = {
            'current_load': 95.0,  # Very high load
            'cpu_usage': 90.0,
            'memory_usage': 95.0
        }
        
        self.queue_manager = RequestQueueManager(
            resource_monitor=self.mock_resource_monitor,
            max_concurrent_requests=3
        )
    
    def tearDown(self):
        self.queue_manager.shutdown()
    
    def test_peak_load_request_handling(self):
        """Test handling of many concurrent requests during peak load"""
        # Simulate 50 concurrent requests (typical peak load scenario)
        request_ids = []
        
        for i in range(50):
            request_id, queue_info = self.queue_manager.enqueue_request(
                user_id=f"user_{i}",
                ip_address=f"192.168.1.{i % 255}",
                endpoint="generate_image",
                request_data={"prompt": f"test prompt {i}"},
                is_authenticated=i % 3 == 0,  # 1/3 authenticated
                is_donor=i % 10 == 0  # 1/10 donors
            )
            request_ids.append(request_id)
        
        # Verify all requests were accepted
        self.assertEqual(len(request_ids), 50)
        
        # Check queue metrics
        metrics = self.queue_manager.get_queue_metrics()
        self.assertEqual(metrics['total_requests'], 50)
        self.assertEqual(metrics['queued_requests'], 50)
        
        # Verify priority distribution
        queue_lengths = metrics['queue_lengths']
        self.assertGreater(queue_lengths['low_priority'], 0)  # Anonymous users
        self.assertGreater(queue_lengths['medium_priority'], 0)  # Registered users
        self.assertGreater(queue_lengths['high_priority'], 0)  # Donors
    
    def test_queue_processing_under_load(self):
        """Test queue processing efficiency under high load"""
        # Enqueue many requests
        request_ids = []
        for i in range(20):
            request_id, _ = self.queue_manager.enqueue_request(
                user_id=f"user_{i}",
                ip_address=f"192.168.1.{i}",
                endpoint="test",
                request_data={},
                is_authenticated=True,
                is_donor=i < 5  # First 5 are donors
            )
            request_ids.append(request_id)
        
        # Process requests up to concurrent limit
        processing_requests = []
        for _ in range(self.queue_manager.max_concurrent_requests):
            request = self.queue_manager.get_next_request()
            if request:
                processing_requests.append(request)
        
        # Verify concurrent limit is respected
        self.assertEqual(len(processing_requests), 3)
        
        # Verify donors are processed first
        for request in processing_requests:
            user_id = request.user_id
            user_index = int(user_id.split('_')[1])
            # First few should be donors (high priority)
            if user_index < 5:
                self.assertEqual(request.priority, RequestPriority.HIGH)
    
    def test_exponential_backoff_under_peak_load(self):
        """Test exponential backoff behavior during peak load"""
        calculator = ExponentialBackoffCalculator()
        
        # Test backoff progression under high load
        high_load = 0.95
        
        delays = []
        for retry_count in range(5):
            delay = calculator.calculate_delay(retry_count, high_load)
            delays.append(delay)
        
        # Verify delays increase exponentially
        for i in range(1, len(delays)):
            self.assertGreater(delays[i], delays[i-1])
        
        # Verify high load increases delays significantly
        low_load_delay = calculator.calculate_delay(2, 0.1)
        high_load_delay = calculator.calculate_delay(2, 0.9)
        self.assertGreater(high_load_delay, low_load_delay * 1.5)
    
    def test_real_time_feedback_accuracy(self):
        """Test accuracy of real-time queue feedback"""
        # Enqueue requests and verify position tracking
        request_ids = []
        for i in range(10):
            request_id, queue_info = self.queue_manager.enqueue_request(
                user_id=f"user_{i}",
                ip_address=f"192.168.1.{i}",
                endpoint="test",
                request_data={},
                is_authenticated=True,
                is_donor=False  # All same priority for position testing
            )
            request_ids.append(request_id)
            
            # Verify position in queue
            expected_position = i + 1
            self.assertEqual(queue_info['position_in_queue'], expected_position)
        
        # Start processing some requests
        for _ in range(3):
            request = self.queue_manager.get_next_request()
            if request:
                # Complete immediately for testing
                self.queue_manager.complete_request(request.request_id, result={"test": "result"})
        
        # Check updated positions for remaining requests
        for i, request_id in enumerate(request_ids[3:], start=3):
            status = self.queue_manager.get_request_status(request_id)
            if status['status'] == 'queued':
                # Position should be updated after processing
                self.assertLessEqual(status['position_in_queue'], 10 - 3)  # 3 were processed


if __name__ == '__main__':
    # Configure logging for tests
    logging.basicConfig(level=logging.INFO)
    
    # Run tests
    unittest.main(verbosity=2)