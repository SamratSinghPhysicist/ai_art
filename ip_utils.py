from flask import request
from datetime import datetime
from models import blocked_ips_collection, request_logs_collection

def get_client_ip():
    """Get client IP address, handling proxies."""
    if request.headers.getlist("X-Forwarded-For"):
       return request.headers.getlist("X-Forwarded-For")[0]
    else:
       return request.remote_addr

def is_ip_blocked(ip):
    """Check if an IP is in the blocked_ips collection."""
    if blocked_ips_collection is None:
        return False
    return blocked_ips_collection.find_one({"ip": ip}) is not None

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
import json
import os

def get_client_ip():
    """
    Get the client's IP address, handling proxies like X-Forwarded-For.
    """
    # The X-Forwarded-For header is the de facto standard for identifying 
    # the originating IP address of a client connecting to a web server 
    # through an HTTP proxy or a load balancer.
    if request.headers.getlist("X-Forwarded-For"):
        # The header can be a comma-separated list of IPs. The first one is the original client.
        ip = request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    else:
        # If the header is not present, fall back to remote_addr.
        ip = request.remote_addr
    return ip

# Path to the blocklist file
BLOCKED_IPS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blocked_ips.json')

def load_blocked_ips():
    """Loads the set of blocked IPs from the JSON file."""
    if not os.path.exists(BLOCKED_IPS_FILE):
        return set()
    try:
        with open(BLOCKED_IPS_FILE, 'r') as f:
            # Handle empty file case
            content = f.read()
            if not content:
                return set()
            return set(json.loads(content))
    except (IOError, json.JSONDecodeError):
        # In case of file read error or invalid JSON, return an empty set
        return set()

def save_blocked_ips(ips):
    """Saves the set of blocked IPs to the JSON file."""
    try:
        with open(BLOCKED_IPS_FILE, 'w') as f:
            json.dump(list(ips), f, indent=4)
    except IOError:
        # Handle file write error if necessary
        pass
import json
import os

def get_client_ip():
    """
    Get the client's IP address, handling proxies like X-Forwarded-For.
    """
    # The X-Forwarded-For header is the de facto standard for identifying 
    # the originating IP address of a client connecting to a web server 
    # through an HTTP proxy or a load balancer.
    if request.headers.getlist("X-Forwarded-For"):
        # The header can be a comma-separated list of IPs. The first one is the original client.
        ip = request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    else:
        # If the header is not present, fall back to remote_addr.
        ip = request.remote_addr
    return ip

# Path to the blocklist file
BLOCKED_IPS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blocked_ips.json')

def load_blocked_ips():
    """Loads the set of blocked IPs from the JSON file."""
    if not os.path.exists(BLOCKED_IPS_FILE):
        return set()
    try:
        with open(BLOCKED_IPS_FILE, 'r') as f:
            # Handle empty file case
            content = f.read()
            if not content:
                return set()
            return set(json.loads(content))
    except (IOError, json.JSONDecodeError):
        # In case of file read error or invalid JSON, return an empty set
        return set()

def save_blocked_ips(ips):
    """Saves the set of blocked IPs to the JSON file."""
    try:
        with open(BLOCKED_IPS_FILE, 'w') as f:
            json.dump(list(ips), f, indent=4)
    except IOError:
        # Handle file write error if necessary
        pass

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
