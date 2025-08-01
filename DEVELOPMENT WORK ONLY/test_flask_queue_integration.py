#!/usr/bin/env python3
"""
Integration test for Flask queue management system

This test verifies that the queue management system integrates correctly
with Flask endpoints and provides the expected behavior.
"""

import json
import time
from unittest.mock import Mock, patch
from flask import Flask
from queue_flask_integration import initialize_queue_integration, queue_aware_endpoint

def create_test_app():
    """Create a test Flask app with queue integration"""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    # Mock resource monitor
    mock_resource_monitor = Mock()
    mock_resource_monitor.get_current_metrics.return_value = {
        'current_load': 50.0,  # Medium load
        'cpu_usage': 40.0,
        'memory_usage': 60.0
    }
    
    # Initialize queue integration
    queue_manager, processor = initialize_queue_integration(
        app, 
        resource_monitor=mock_resource_monitor,
        num_workers=1
    )
    
    # Create test endpoints
    @app.route('/test/immediate', methods=['POST'])
    @queue_aware_endpoint("test_immediate")
    def test_immediate():
        """Test endpoint that should process immediately under normal load"""
        return {"result": "processed_immediately", "timestamp": time.time()}
    
    @app.route('/test/high-load', methods=['POST'])
    @queue_aware_endpoint("test_high_load")
    def test_high_load():
        """Test endpoint that should be queued under high load"""
        # Mock high server load for this endpoint
        queue_manager._get_server_load = lambda: 0.9  # 90% load
        return {"result": "processed_under_high_load", "timestamp": time.time()}
    
    return app, queue_manager, processor

def test_immediate_processing():
    """Test that requests are processed immediately under normal load"""
    print("🧪 Testing immediate processing under normal load...")
    
    app, queue_manager, processor = create_test_app()
    
    with app.test_client() as client:
        # Mock low server load
        queue_manager._get_server_load = lambda: 0.3  # 30% load
        
        response = client.post('/test/immediate', 
                             json={"test": "data"},
                             content_type='application/json')
        
        # Should process immediately
        assert response.status_code == 200
        data = response.get_json()
        assert data['result'] == 'processed_immediately'
        print("  ✅ Request processed immediately under low load")
    
    queue_manager.shutdown()
    processor.shutdown()

def test_queue_under_high_load():
    """Test that requests are queued under high server load"""
    print("🧪 Testing request queuing under high load...")
    
    app, queue_manager, processor = create_test_app()
    
    with app.test_client() as client:
        # Mock high server load
        queue_manager._get_server_load = lambda: 0.9  # 90% load
        
        response = client.post('/test/high-load',
                             json={"test": "data"},
                             content_type='application/json')
        
        # Should be queued (HTTP 202 Accepted)
        assert response.status_code == 202
        data = response.get_json()
        assert data['queued'] == True
        assert 'request_id' in data
        assert 'queue_info' in data
        print(f"  ✅ Request queued with ID: {data['request_id'][:8]}...")
        print(f"  📊 Queue position: {data['queue_info']['position_in_queue']}")
        print(f"  ⏱️ Estimated wait: {data['queue_info']['estimated_wait_human']}")
    
    queue_manager.shutdown()
    processor.shutdown()

def test_queue_status_endpoint():
    """Test the queue status endpoint"""
    print("🧪 Testing queue status endpoint...")
    
    app, queue_manager, processor = create_test_app()
    
    with app.test_client() as client:
        # First, queue a request
        queue_manager._get_server_load = lambda: 0.9  # High load
        
        response = client.post('/test/high-load',
                             json={"test": "data"},
                             content_type='application/json')
        
        assert response.status_code == 202
        data = response.get_json()
        request_id = data['request_id']
        
        # Check status
        status_response = client.get(f'/api/queue/status/{request_id}')
        assert status_response.status_code == 200
        
        status_data = status_response.get_json()
        assert status_data['request_id'] == request_id
        assert status_data['status'] == 'queued'
        assert 'position_in_queue' in status_data
        print(f"  ✅ Status retrieved for request {request_id[:8]}...")
        print(f"  📊 Status: {status_data['status']}")
        print(f"  📍 Position: {status_data['position_in_queue']}")
    
    queue_manager.shutdown()
    processor.shutdown()

def test_queue_metrics_endpoint():
    """Test the queue metrics endpoint"""
    print("🧪 Testing queue metrics endpoint...")
    
    app, queue_manager, processor = create_test_app()
    
    with app.test_client() as client:
        # Add some requests to the queue
        queue_manager._get_server_load = lambda: 0.9  # High load
        
        for i in range(3):
            client.post('/test/high-load',
                       json={"test": f"data_{i}"},
                       content_type='application/json')
        
        # Get metrics
        metrics_response = client.get('/api/queue/metrics')
        assert metrics_response.status_code == 200
        
        metrics_data = metrics_response.get_json()
        assert metrics_data['total_requests'] >= 3
        assert metrics_data['queued_requests'] >= 3
        assert 'server_load' in metrics_data
        assert 'queue_lengths' in metrics_data
        print(f"  ✅ Metrics retrieved successfully")
        print(f"  📊 Total requests: {metrics_data['total_requests']}")
        print(f"  📋 Queued requests: {metrics_data['queued_requests']}")
        print(f"  🖥️ Server load: {metrics_data['server_load']:.1%}")
    
    queue_manager.shutdown()
    processor.shutdown()

def test_queue_health_endpoint():
    """Test the queue health check endpoint"""
    print("🧪 Testing queue health endpoint...")
    
    app, queue_manager, processor = create_test_app()
    
    with app.test_client() as client:
        # Test health under normal conditions
        queue_manager._get_server_load = lambda: 0.3  # Low load
        
        health_response = client.get('/api/queue/health')
        assert health_response.status_code == 200
        
        health_data = health_response.get_json()
        assert health_data['status'] in ['healthy', 'warning', 'degraded']
        assert 'server_load' in health_data
        assert 'queue_length' in health_data
        print(f"  ✅ Health check successful")
        print(f"  💚 Status: {health_data['status']}")
        print(f"  📊 Server load: {health_data['server_load']:.1%}")
        print(f"  📋 Queue length: {health_data['queue_length']}")
    
    queue_manager.shutdown()
    processor.shutdown()

def main():
    """Run all integration tests"""
    print("🚀 Flask Queue Integration Tests")
    print("=" * 40)
    
    try:
        test_immediate_processing()
        print()
        
        test_queue_under_high_load()
        print()
        
        test_queue_status_endpoint()
        print()
        
        test_queue_metrics_endpoint()
        print()
        
        test_queue_health_endpoint()
        print()
        
        print("✅ All integration tests passed!")
        print("\nQueue integration features verified:")
        print("  ✓ Immediate processing under normal load")
        print("  ✓ Request queuing under high server load")
        print("  ✓ Queue status tracking and retrieval")
        print("  ✓ Comprehensive queue metrics")
        print("  ✓ Health check monitoring")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)