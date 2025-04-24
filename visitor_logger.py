import logging
import requests
from flask import request
import os
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime

class VisitorLogger:
    """Class to handle logging of visitor information including IP and geolocation"""
    
    def __init__(self, app, log_dir=None):
        """Initialize the visitor logger
        
        Args:
            app: Flask application instance
            log_dir: Directory to store visitor logs (defaults to 'logs' in app directory)
        """
        self.app = app
        
        # Set up logging directory
        if log_dir is None:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            self.log_dir = os.path.join(app_dir, 'logs')
        else:
            self.log_dir = log_dir
            
        # Ensure log directory exists
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Set up visitor logger
        self.visitor_logger = logging.getLogger('visitor_logger')
        self.visitor_logger.setLevel(logging.INFO)
        
        # Create a file handler for visitor logs
        visitor_handler = RotatingFileHandler(
            os.path.join(self.log_dir, 'visitors.log'),
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        
        # Set formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        visitor_handler.setFormatter(formatter)
        
        # Add handler to logger if it doesn't already have one
        if not self.visitor_logger.handlers:
            self.visitor_logger.addHandler(visitor_handler)
        
        # Register the before_request handler
        self.app.before_request(self.log_visitor)
    
    def get_client_ip(self):
        """Extract client IP address from request
        
        Returns:
            str: The client's IP address
        """
        # Check for IP in various headers (for proxies/load balancers)
        headers_to_check = [
            'X-Forwarded-For',
            'X-Real-IP',
            'CF-Connecting-IP'  # Cloudflare
        ]
        
        for header in headers_to_check:
            if header in request.headers:
                # X-Forwarded-For may contain multiple IPs - take the first one
                return request.headers[header].split(',')[0].strip()
        
        # Fall back to remote_addr if no headers found
        return request.remote_addr
    
    def get_geolocation(self, ip):
        """Get geolocation data for an IP address
        
        Args:
            ip (str): IP address to look up
            
        Returns:
            dict: Geolocation data or None if lookup failed
        """
        # Skip lookup for localhost/private IPs
        if ip in ('127.0.0.1', 'localhost', '::1') or ip.startswith('192.168.') or ip.startswith('10.'):
            return {
                'country': 'Local',
                'region': 'Development',
                'city': 'Localhost',
                'error': False
            }
        
        try:
            # Use free IP geolocation API
            response = requests.get(f'https://ipapi.co/{ip}/json/', timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for error response from API
                if 'error' in data and data['error']:
                    self.visitor_logger.warning(f"Geolocation API error for IP {ip}: {data.get('reason', 'Unknown error')}")
                    return {
                        'country': 'Unknown',
                        'region': 'Unknown',
                        'city': 'Unknown',
                        'error': True,
                        'error_message': data.get('reason', 'Unknown error')
                    }
                
                # Return relevant geolocation data
                return {
                    'country': data.get('country_name', 'Unknown'),
                    'region': data.get('region', 'Unknown'),
                    'city': data.get('city', 'Unknown'),
                    'error': False
                }
            else:
                self.visitor_logger.warning(f"Geolocation API returned status code {response.status_code} for IP {ip}")
                return {
                    'country': 'Unknown',
                    'region': 'Unknown',
                    'city': 'Unknown',
                    'error': True,
                    'error_message': f"API returned status code {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            self.visitor_logger.error(f"Geolocation request failed for IP {ip}: {str(e)}")
            return {
                'country': 'Unknown',
                'region': 'Unknown',
                'city': 'Unknown',
                'error': True,
                'error_message': str(e)
            }
    
    def log_visitor(self):
        """Log visitor information before processing the request"""
        # Skip logging for static files and certain paths
        if request.path.startswith('/static/') or request.path in ['/favicon.ico', '/robots.txt']:
            return
        
        try:
            # Get client IP
            ip = self.get_client_ip()
            
            # Get geolocation data
            geo_data = self.get_geolocation(ip)
            
            # Prepare log data
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'ip': ip,
                'path': request.path,
                'method': request.method,
                'user_agent': request.headers.get('User-Agent', 'Unknown'),
                'referrer': request.referrer or 'Direct',
                'location': {
                    'country': geo_data.get('country', 'Unknown'),
                    'region': geo_data.get('region', 'Unknown'),
                    'city': geo_data.get('city', 'Unknown')
                }
            }
            
            # Log structured data
            self.visitor_logger.info(json.dumps(log_data))
            
            # Also log to console in a readable format
            print(f"Visitor: {ip} from {geo_data.get('city', 'Unknown')}, {geo_data.get('country', 'Unknown')} - {request.path}")
            
        except Exception as e:
            # Ensure logging errors don't break the application
            self.visitor_logger.error(f"Error logging visitor: {str(e)}")
            print(f"Error logging visitor: {str(e)}")