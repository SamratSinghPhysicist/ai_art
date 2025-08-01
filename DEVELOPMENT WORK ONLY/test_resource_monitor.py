"""
Unit tests for ResourceMonitor class to verify resource monitoring accuracy.
"""

import unittest
import time
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import sys
import os

# Add the current directory to the path so we can import resource_monitor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from resource_monitor import ResourceMonitor, get_resource_monitor


class TestResourceMonitor(unittest.TestCase):
    """Test cases for ResourceMonitor class."""
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.monitor = ResourceMonitor(
            cpu_threshold=80.0,
            memory_threshold=80.0
        )
    
    def tearDown(self):
        """Clean up after each test method."""
        pass  # No cleanup needed for simplified monitor
    
    def test_initialization(self):
        """Test ResourceMonitor initialization with correct parameters."""
        self.assertEqual(self.monitor.cpu_threshold, 80.0)
        self.assertEqual(self.monitor.memory_threshold, 80.0)
        self.assertEqual(self.monitor._request_count, 0)
        self.assertIsInstance(self.monitor._cpu_readings, list)
    
    def test_get_current_metrics(self):
        """Test getting current system metrics."""
        metrics = self.monitor.get_current_metrics()
        
        # Verify metrics structure
        expected_keys = [
            'timestamp', 'current_load', 'cpu_usage', 'memory_usage',
            'queue_length', 'capacity_available', 'should_throttle',
            'hibernating', 'load_trend', 'thresholds', 'historical_averages'
        ]
        for key in expected_keys:
            self.assertIn(key, metrics)
        
        # Verify data types
        self.assertIsInstance(metrics['current_load'], (int, float))
        self.assertIsInstance(metrics['cpu_usage'], (int, float))
        self.assertIsInstance(metrics['memory_usage'], (int, float))
        self.assertIsInstance(metrics['capacity_available'], bool)
        self.assertIsInstance(metrics['should_throttle'], bool)
    
    @patch('resource_monitor.psutil.cpu_percent')
    @patch('resource_monitor.psutil.virtual_memory')
    def test_mocked_resource_metrics(self, mock_memory, mock_cpu):
        """Test resource metrics with mocked system data."""
        # Mock system resource data
        mock_cpu.return_value = 75.0
        mock_memory.return_value = MagicMock(percent=60.0)
        
        # Get metrics
        metrics = self.monitor.get_current_metrics()
        
        # Verify metrics were calculated correctly
        self.assertGreater(metrics['cpu_usage'], 0)
        self.assertEqual(metrics['memory_usage'], 60.0)
        
        # Verify load calculation
        expected_load = (metrics['cpu_usage'] * 0.7) + (60.0 * 0.3)
        self.assertAlmostEqual(metrics['current_load'], expected_load, places=1)
    
    def test_capacity_available(self):
        """Test capacity availability logic."""
        # Mock low load scenario
        with patch.object(self.monitor, 'get_current_metrics') as mock_metrics:
            mock_metrics.return_value = {
                'current_load': 50.0,
                'capacity_available': True,
                'should_throttle': False
            }
            self.assertFalse(self.monitor.should_throttle())
        
        # Mock high load scenario
        with patch.object(self.monitor, 'get_current_metrics') as mock_metrics:
            mock_metrics.return_value = {
                'current_load': 85.0,
                'capacity_available': False,
                'should_throttle': True
            }
            self.assertTrue(self.monitor.should_throttle())
    
    def test_request_recording(self):
        """Test request recording functionality."""
        initial_count = self.monitor._request_count
        initial_time = self.monitor._last_request_time
        
        # Record a request
        self.monitor.record_request()
        
        # Verify request was recorded
        self.assertEqual(self.monitor._request_count, initial_count + 1)
        self.assertGreater(self.monitor._last_request_time, initial_time)
    

    
    def test_resource_summary(self):
        """Test comprehensive resource summary generation."""
        summary = self.monitor.get_resource_summary()
        
        # Verify summary contains expected keys
        expected_keys = [
            'timestamp', 'current_load', 'cpu_usage', 'memory_usage',
            'queue_length', 'capacity_available', 'should_throttle',
            'hibernating', 'load_trend', 'thresholds', 'historical_averages'
        ]
        for key in expected_keys:
            self.assertIn(key, summary)
        
        # Verify data types
        self.assertIsInstance(summary['current_load'], (int, float))
        self.assertIsInstance(summary['cpu_usage'], (int, float))
        self.assertIsInstance(summary['memory_usage'], (int, float))
        self.assertIsInstance(summary['capacity_available'], bool)
        self.assertIsInstance(summary['should_throttle'], bool)
        self.assertFalse(summary['hibernating'])  # Always false in simplified version
    
    def test_error_handling(self):
        """Test error handling in resource monitoring."""
        # Test that errors don't crash the monitor
        with patch('resource_monitor.psutil.cpu_percent', side_effect=Exception("Test error")):
            metrics = self.monitor.get_current_metrics()
            # Should return fallback values
            self.assertIsInstance(metrics, dict)
            self.assertIn('current_load', metrics)
            self.assertGreater(metrics['cpu_usage'], 0)  # Should use fallback


class TestGlobalResourceMonitor(unittest.TestCase):
    """Test cases for global resource monitor functions."""
    
    def test_singleton_pattern(self):
        """Test that get_resource_monitor returns the same instance."""
        monitor1 = get_resource_monitor()
        monitor2 = get_resource_monitor()
        self.assertIs(monitor1, monitor2)
    
    def test_convenience_functions(self):
        """Test convenience functions work correctly."""
        from resource_monitor import (
            record_request, should_throttle_request, get_system_status
        )
        
        # These should not raise exceptions
        record_request()
        throttle_result = should_throttle_request()
        self.assertIsInstance(throttle_result, bool)
        
        status = get_system_status()
        self.assertIsInstance(status, dict)
        self.assertIn('current_load', status)
        self.assertIn('cpu_usage', status)
        self.assertIn('memory_usage', status)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)