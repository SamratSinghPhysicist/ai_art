from flask import request
from datetime import datetime, timedelta
from models import blocked_ips_collection, request_logs_collection, custom_rate_limits_collection

def get_client_ip():
    """Extract client IP address from request, handling proxies."""
    # Check for IP in various headers (for proxies/load balancers like on Render)
    headers_to_check = [
        'X-Forwarded-For',
        'X-Real-IP',
        'CF-Connecting-IP'  # Cloudflare
    ]
    
    for header in headers_to_check:
        if header in request.headers:
            # X-Forwarded-For may contain multiple IPs - take the first one
            return request.headers[header].split(',')[0].strip()
    
    # Fall back to remote_addr if no proxy headers are found
    return request.remote_addr

def is_ip_blocked(ip):
    """Check if an IP is in the blocked_ips collection and return the block document if found."""
    if blocked_ips_collection is None:
        return None
    return blocked_ips_collection.find_one({"ip": ip})

def block_ip(ip, reason=""):
    """Adds an IP to the blocked_ips collection."""
    if blocked_ips_collection is None:
        return False, "Database not connected"
    if is_ip_blocked(ip):
        return False, "IP already blocked"
    
    blocked_ips_collection.insert_one({
        "ip": ip,
        "reason": reason,
        "timestamp": datetime.utcnow()
    })
    return True, "IP blocked successfully"

def unblock_ip(ip):
    """Removes an IP from the blocked_ips collection."""
    if blocked_ips_collection is None:
        return False, "Database not connected"
    if not is_ip_blocked(ip):
        return False, "IP not found in blocklist"
        
    result = blocked_ips_collection.delete_one({"ip": ip})
    if result.deleted_count > 0:
        return True, "IP unblocked successfully"
    return False, "Failed to unblock IP"

def get_blocked_ips():
    """Retrieves all blocked IPs from the collection."""
    if blocked_ips_collection is None:
        return []
    # Convert ObjectId to string for JSON serialization
    blocked_ips = []
    for doc in blocked_ips_collection.find():
        doc['_id'] = str(doc['_id'])
        blocked_ips.append(doc)
    return blocked_ips

def log_request(ip, endpoint):
    """Logs a request to the request_logs collection."""
    if request_logs_collection is None:
        return
    request_logs_collection.insert_one({
        "ip": ip,
        "endpoint": endpoint,
        "timestamp": datetime.utcnow()
    })

def get_ip_history(ip):
    """Retrieves the request history for a specific IP."""
    if request_logs_collection is None:
        return []
    # Convert ObjectId to string for JSON serialization
    history = []
    for doc in request_logs_collection.find({"ip": ip}).sort("timestamp", -1):
        doc['_id'] = str(doc['_id'])
        history.append(doc)
    return history

def get_custom_rate_limit(ip):
    """Check for a custom rate limit for a given IP."""
    if custom_rate_limits_collection is None:
        return None
    return custom_rate_limits_collection.find_one({"ip": ip})

def is_potential_abuser(ip):
    """
    Checks if an IP is a potential abuser based on request patterns.
    Criteria:
    - More than 25 requests in the last 10 minutes.
    - Sustained rate of 2-4 requests per minute within that 10-minute window.
    """
    if request_logs_collection is None:
        return False

    time_threshold = datetime.utcnow() - timedelta(minutes=10)
    
    # Get requests within the last 10 minutes
    recent_requests = list(request_logs_collection.find({
        "ip": ip,
        "timestamp": {"$gte": time_threshold}
    }).sort("timestamp", 1)) # Sort ascending to check time differences

    num_recent_requests = len(recent_requests)

    # Condition 1: More than 25 requests in 10 minutes
    if num_recent_requests > 25:
        return True
    
    # Condition 2: Sustained moderate rate (2-4 req/min over 10 min implies 20-40 requests)
    # And the requests must be spread out, not a quick burst.
    if 20 <= num_recent_requests <= 40:
        if len(recent_requests) > 1: # Need at least two requests to calculate duration
            first_req_time = recent_requests[0]['timestamp']
            last_req_time = recent_requests[-1]['timestamp']
            duration_of_requests = (last_req_time - first_req_time).total_seconds()
            
            # If requests are spread over at least 8 minutes (480 seconds) of the 10-minute window
            if duration_of_requests >= 8 * 60: # 8 minutes
                return True
            
    return False
