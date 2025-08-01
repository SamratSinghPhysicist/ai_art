#!/usr/bin/env python3
"""
Demonstration script for the Request Queue Management System

This script shows how the queue management system works under different
load conditions and provides real-time feedback.
"""

import time
import threading
from datetime import datetime, timezone
from request_queue_manager import RequestQueueManager, get_queue_manager
from unittest.mock import Mock

def create_mock_resource_monitor(load_percentage):
    """Create a mock resource monitor with specified load"""
    mock_monitor = Mock()
    mock_monitor.get_current_metrics.return_value = {
        'current_load': load_percentage,
        'cpu_usage': load_percentage * 0.8,
        'memory_usage': load_percentage * 1.2
    }
    return mock_monitor

def simulate_user_requests(queue_manager, num_requests=10, user_type="mixed"):
    """Simulate multiple user requests"""
    print(f"\n🚀 Simulating {num_requests} {user_type} user requests...")
    
    request_ids = []
    for i in range(num_requests):
        if user_type == "mixed":
            is_authenticated = i % 3 == 0  # 1/3 authenticated
            is_donor = i % 10 == 0         # 1/10 donors
        elif user_type == "anonymous":
            is_authenticated = False
            is_donor = False
        elif user_type == "authenticated":
            is_authenticated = True
            is_donor = False
        elif user_type == "donor":
            is_authenticated = True
            is_donor = True
        
        request_id, queue_info = queue_manager.enqueue_request(
            user_id=f"user_{i}" if is_authenticated else None,
            ip_address=f"192.168.1.{i % 255}",
            endpoint="demo_endpoint",
            request_data={"prompt": f"Generate image {i}"},
            is_authenticated=is_authenticated,
            is_donor=is_donor
        )
        
        request_ids.append(request_id)
        
        print(f"  Request {i+1}: {request_id[:8]}... "
              f"(Priority: {queue_info['priority']}, "
              f"Position: {queue_info['position_in_queue']}, "
              f"Wait: {queue_info['estimated_wait_human']})")
        
        # Small delay between requests
        time.sleep(0.1)
    
    return request_ids

def process_requests_simulation(queue_manager, num_to_process=5):
    """Simulate processing requests from the queue"""
    print(f"\n⚡ Processing up to {num_to_process} requests...")
    
    processed = 0
    while processed < num_to_process:
        request = queue_manager.get_next_request()
        if not request:
            print("  No more requests to process")
            break
        
        print(f"  Processing request {request.request_id[:8]}... "
              f"(Priority: {request.priority.name}, "
              f"User: {request.user_id or 'Anonymous'})")
        
        # Simulate processing time
        time.sleep(0.5)
        
        # Complete the request successfully
        result = {"status": "completed", "image_url": f"https://example.com/image_{processed}.png"}
        queue_manager.complete_request(request.request_id, result=result)
        
        processed += 1
        print(f"    ✅ Completed in 0.5s")

def demonstrate_exponential_backoff():
    """Demonstrate exponential backoff calculation"""
    print("\n📈 Demonstrating Exponential Backoff:")
    
    from request_queue_manager import ExponentialBackoffCalculator
    calculator = ExponentialBackoffCalculator()
    
    print("  Retry attempts under different server loads:")
    print("  Retry | Low Load (20%) | High Load (90%)")
    print("  ------|----------------|----------------")
    
    for retry_count in range(5):
        low_load_delay = calculator.calculate_delay(retry_count, 0.2)
        high_load_delay = calculator.calculate_delay(retry_count, 0.9)
        print(f"    {retry_count}   |     {low_load_delay:3d}s       |      {high_load_delay:3d}s")

def demonstrate_real_time_feedback(queue_manager):
    """Demonstrate real-time queue feedback"""
    print("\n📊 Real-time Queue Status:")
    
    # Get current metrics
    metrics = queue_manager.get_queue_metrics()
    
    print(f"  Total Requests: {metrics['total_requests']}")
    print(f"  Queued: {metrics['queued_requests']}")
    print(f"  Processing: {metrics['processing_requests']}")
    print(f"  Completed: {metrics['completed_requests']}")
    print(f"  Failed: {metrics['failed_requests']}")
    print(f"  Server Load: {metrics['server_load']:.1%}")
    print(f"  Average Wait Time: {metrics['average_wait_time']:.1f}s")
    print(f"  Queue Throughput: {metrics['queue_throughput']:.1f} req/min")
    
    print("\n  Queue Lengths by Priority:")
    for priority, length in metrics['queue_lengths'].items():
        print(f"    {priority.replace('_', ' ').title()}: {length}")

def main():
    """Main demonstration function"""
    print("🎯 Request Queue Management System Demonstration")
    print("=" * 55)
    
    # Test 1: Normal Load Scenario
    print("\n🟢 SCENARIO 1: Normal Server Load (30%)")
    print("-" * 40)
    
    normal_load_monitor = create_mock_resource_monitor(30.0)
    queue_manager_normal = RequestQueueManager(
        resource_monitor=normal_load_monitor,
        max_concurrent_requests=3
    )
    
    # Simulate requests
    request_ids = simulate_user_requests(queue_manager_normal, 8, "mixed")
    
    # Show queue status
    demonstrate_real_time_feedback(queue_manager_normal)
    
    # Process some requests
    process_requests_simulation(queue_manager_normal, 4)
    
    # Show updated status
    print("\n📊 Updated Queue Status:")
    demonstrate_real_time_feedback(queue_manager_normal)
    
    queue_manager_normal.shutdown()
    
    # Test 2: High Load Scenario
    print("\n\n🔴 SCENARIO 2: High Server Load (85%)")
    print("-" * 40)
    
    high_load_monitor = create_mock_resource_monitor(85.0)
    queue_manager_high = RequestQueueManager(
        resource_monitor=high_load_monitor,
        max_concurrent_requests=2  # Reduced capacity under high load
    )
    
    # Simulate more requests under high load
    request_ids = simulate_user_requests(queue_manager_high, 12, "mixed")
    
    # Show queue status under high load
    demonstrate_real_time_feedback(queue_manager_high)
    
    # Test should_accept_request under high load
    accept, load_info = queue_manager_high.should_accept_request()
    print(f"\n  Should accept new requests: {accept}")
    print(f"  Load message: {load_info['message']}")
    
    queue_manager_high.shutdown()
    
    # Test 3: Exponential Backoff
    demonstrate_exponential_backoff()
    
    # Test 4: Priority Demonstration
    print("\n\n👑 SCENARIO 3: Priority-based Processing")
    print("-" * 40)
    
    priority_monitor = create_mock_resource_monitor(50.0)
    queue_manager_priority = RequestQueueManager(
        resource_monitor=priority_monitor,
        max_concurrent_requests=2
    )
    
    # Add requests with different priorities
    print("\n  Adding requests with different user types:")
    
    # Anonymous users (low priority)
    for i in range(3):
        request_id, info = queue_manager_priority.enqueue_request(
            user_id=None,
            ip_address=f"192.168.1.{i}",
            endpoint="test",
            request_data={},
            is_authenticated=False,
            is_donor=False
        )
        print(f"    Anonymous user: Priority {info['priority']}, Position {info['position_in_queue']}")
    
    # Registered users (medium priority)
    for i in range(2):
        request_id, info = queue_manager_priority.enqueue_request(
            user_id=f"registered_user_{i}",
            ip_address=f"192.168.2.{i}",
            endpoint="test",
            request_data={},
            is_authenticated=True,
            is_donor=False
        )
        print(f"    Registered user: Priority {info['priority']}, Position {info['position_in_queue']}")
    
    # Donor users (high priority)
    for i in range(2):
        request_id, info = queue_manager_priority.enqueue_request(
            user_id=f"donor_user_{i}",
            ip_address=f"192.168.3.{i}",
            endpoint="test",
            request_data={},
            is_authenticated=True,
            is_donor=True
        )
        print(f"    Donor user: Priority {info['priority']}, Position {info['position_in_queue']}")
    
    print("\n  Processing order (should prioritize donors first):")
    for i in range(4):
        request = queue_manager_priority.get_next_request()
        if request:
            user_type = "Donor" if request.priority.name == "HIGH" else \
                       "Registered" if request.priority.name == "MEDIUM" else "Anonymous"
            print(f"    {i+1}. {user_type} user (Priority: {request.priority.name})")
            queue_manager_priority.complete_request(request.request_id, result={"success": True})
    
    queue_manager_priority.shutdown()
    
    print("\n✅ Demonstration completed successfully!")
    print("\nKey Features Demonstrated:")
    print("  ✓ Queue-based request handling during high load")
    print("  ✓ Exponential backoff for retry suggestions")
    print("  ✓ Real-time feedback on queue position and wait times")
    print("  ✓ Priority-based processing (Donors > Registered > Anonymous)")
    print("  ✓ Server load-aware queue management")
    print("  ✓ Comprehensive metrics and monitoring")

if __name__ == "__main__":
    main()