from flask import request

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
