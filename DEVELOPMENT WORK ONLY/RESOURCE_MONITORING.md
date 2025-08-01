# Resource Monitoring System

## Overview

The resource monitoring system provides real-time tracking of system resources (CPU, memory) and implements intelligent load detection for the AiArt application. It's designed to work within free tier hosting limits and provide soft throttling recommendations when resources are constrained.

## Architecture

### Core Components

1. **ResourceMonitor Class** (`resource_monitor.py`)
   - Simplified, on-demand resource monitoring
   - No background threads to avoid complexity
   - CPU usage smoothing to prevent spikes
   - Configurable thresholds for throttling

2. **Admin Dashboard Integration** (`templates/admin.html`)
   - Real-time resource status display
   - Auto-refresh every 30 seconds
   - Color-coded indicators for system health
   - Threshold monitoring

3. **Flask API Integration** (`app.py`)
   - `/admin/api/resource-status` endpoint
   - Request recording for high-cost endpoints
   - Middleware integration for monitoring

## Key Features

### Resource Metrics
- **CPU Usage**: Real-time CPU percentage with smoothing
- **Memory Usage**: Current memory utilization
- **System Load**: Weighted average (CPU 70%, Memory 30%)
- **Capacity Status**: Available/Limited based on thresholds

### Intelligent Monitoring
- **Threshold Detection**: 80% default threshold for soft throttling
- **Smoothing Algorithm**: Averages last 5 CPU readings to prevent spikes
- **Fallback Handling**: Uses last known values on errors
- **Realistic Defaults**: Minimum 1% CPU to avoid unrealistic 0% readings

### Admin Dashboard
- **Current Status**: Load, capacity, queue length
- **System Metrics**: CPU, memory, trends
- **Thresholds**: Configurable limits display
- **Auto-refresh**: Updates every 30 seconds

## Usage

### Basic Usage
```python
from resource_monitor import get_resource_monitor

# Get monitor instance
monitor = get_resource_monitor()

# Get current metrics
metrics = monitor.get_current_metrics()
print(f"CPU: {metrics['cpu_usage']}%")
print(f"Memory: {metrics['memory_usage']}%")
print(f"Load: {metrics['current_load']}%")

# Check if should throttle
if monitor.should_throttle():
    print("System is under high load")
```

### Flask Integration
```python
from resource_monitor import record_request, should_throttle_request

# Record requests for monitoring
record_request()

# Check throttling status
if should_throttle_request():
    return jsonify({"error": "Server busy, please try again later"}), 429
```

### Configuration
Environment variables can be used to configure thresholds:
- `RESOURCE_CPU_THRESHOLD`: CPU threshold percentage (default: 80.0)
- `RESOURCE_MEMORY_THRESHOLD`: Memory threshold percentage (default: 80.0)

## API Reference

### ResourceMonitor Class

#### Methods
- `get_current_metrics()`: Returns comprehensive system metrics
- `record_request()`: Records a request for tracking
- `should_throttle()`: Returns True if system should throttle requests

#### Metrics Structure
```json
{
  "timestamp": "2025-01-08T12:00:00Z",
  "current_load": 45.2,
  "cpu_usage": 35.0,
  "memory_usage": 65.0,
  "queue_length": 0,
  "capacity_available": true,
  "should_throttle": false,
  "hibernating": false,
  "load_trend": "stable",
  "thresholds": {
    "cpu_threshold": 80.0,
    "memory_threshold": 80.0
  },
  "historical_averages": {
    "cpu_avg": 35.0,
    "memory_avg": 65.0,
    "load_avg": 45.2
  }
}
```

## Testing

Run unit tests to verify functionality:
```bash
python -m unittest test_resource_monitor -v
```

Key test areas:
- Resource metrics accuracy
- Threshold detection
- Error handling
- Flask integration

## Files Structure

```
├── resource_monitor.py          # Main resource monitoring class
├── test_resource_monitor.py     # Unit tests
├── app.py                       # Flask integration
├── templates/admin.html         # Admin dashboard
└── RESOURCE_MONITORING.md       # This documentation
```

## Troubleshooting

### Common Issues

1. **CPU Usage Shows 0%**
   - Fixed with proper psutil initialization and fallback mechanisms
   - Uses short blocking calls when needed for accurate readings

2. **High Memory Usage**
   - Normal for Python applications
   - Monitor trends rather than absolute values

3. **Load Spikes**
   - Smoothing algorithm averages last 5 readings
   - Temporary spikes are filtered out

### Monitoring Health
- Check admin dashboard at `/admin?secret=<admin_key>`
- Monitor logs for resource monitoring errors
- Verify API endpoint `/admin/api/resource-status` returns valid data

## Performance Impact

The simplified resource monitoring system has minimal performance impact:
- No background threads
- On-demand metrics collection
- Lightweight psutil calls
- Efficient caching of recent readings

This design ensures reliable resource monitoring without adding significant overhead to the application.