from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash, g
import os
import uuid
from image_generator import main_image_function
from prompt_translate import translate_to_english
from models import User, db, request_logs_collection, QwenApiKey, UserGenerationHistory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from flask import send_file
from visitor_logger import VisitorLogger
import json
from firebase_admin import auth as firebase_admin_auth
from firebase_config import firebase_auth, firebase_config
import requests
from werkzeug.exceptions import BadRequest
import uuid
import base64
from img2img_stability import img2img, save_image
from img2video_stability import img2video, get_video_result
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from ip_utils import get_client_ip, is_ip_blocked, block_ip as block_ip_util, unblock_ip as unblock_ip_util, get_blocked_ips as get_blocked_ips_util, log_request, get_ip_history, get_custom_rate_limit
from models import custom_rate_limits_collection
from functools import wraps
import hashlib
import time
import secrets
import jwt
from datetime import datetime, timedelta, timezone
import os
import requests
from turnstile_utils import verify_turnstile
from qwen_generator import generate_qwen_video
from models import VideoTask, VideoUrlMapping
import threading
from flask import Response, stream_with_context
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Initialize resource monitoring
try:
    from resource_monitor import initialize_resource_monitoring
    resource_monitor = initialize_resource_monitoring()
    app.logger.info("Resource monitoring initialized successfully")
except Exception as e:
    app.logger.error(f"Failed to initialize resource monitoring: {e}")
    resource_monitor = None




# Load admin secret key for IP blocking management
ADMIN_SECRET_KEY = os.getenv('ADMIN_SECRET_KEY')
if not ADMIN_SECRET_KEY:
    print("WARNING: ADMIN_SECRET_KEY is not set. IP blocking management endpoints will be disabled.")

# New middleware for logging and blocking
@app.before_request
def log_and_block_check():
    ip = get_client_ip()
    
    # First, check if the IP is blocked to deny access immediately for ANY request
    blocked_doc = is_ip_blocked(ip)
    if blocked_doc:
        ban_reason = blocked_doc.get('reason', 'No reason provided.')
        # If the user is already trying to access the blocked page, don't redirect again to prevent a loop
        if request.endpoint == 'blocked_page':
            return # Allow the request to proceed to the blocked_page route
        # Otherwise, redirect to the blocked page
        return redirect(url_for('blocked_page', reason=ban_reason))
    
    # If not blocked, log the request for monitoring purposes, but only for specific high-cost endpoints
    endpoints_to_log_and_check = [
        'api_generate_image', 
        'img2img_transform', 
        'api_img2video_generate', 
        'generate_image', 
        'img2video_generate',
        'api_img2img_transform',
        'api_img2video_result',
        'generate_qwen_video_route',
        'api_text_to_video_generate'


    ]
    if request.endpoint in endpoints_to_log_and_check:
        log_request(ip, request.endpoint)
        # Record request for resource monitoring
        if resource_monitor:
            try:
                resource_monitor.record_request()
            except Exception as e:
                app.logger.error(f"Error recording request for resource monitoring: {e}")

def get_rate_limit():
    ip = get_client_ip()
    endpoint = request.endpoint
    
    # Check for custom rate limit first
    custom_limit = get_custom_rate_limit(ip, endpoint)
    
    if custom_limit:
        limit_string = custom_limit.get('limit_string')
        app.logger.info(f"Custom rate limit found for IP {ip}, endpoint {endpoint}: {limit_string}")
        
        # Handle unlimited or very high limits
        if limit_string:
            # Check for unlimited keyword
            if 'unlimited' in limit_string.lower():
                app.logger.info(f"Applying unlimited rate limit for IP {ip}")
                return "1000000 per hour"
            
            # Check for extremely large numbers (more than 15 digits)
            if any(len(part.split('/')[0]) > 15 for part in limit_string.split(';') if '/' in part):
                app.logger.info(f"Applying high rate limit for IP {ip} (extremely large numbers detected)")
                return "1000000 per hour"
            
            # Check for high daily limits
            try:
                if '/day' in limit_string:
                    # Extract the number before '/day'
                    parts = limit_string.split(';')
                    for part in parts:
                        if '/day' in part:
                            number = int(part.split('/')[0])
                            if number > 100000:
                                app.logger.info(f"Applying high rate limit for IP {ip} (high daily limit: {number})")
                                return "1000000 per hour"
            except (ValueError, IndexError):
                app.logger.warning(f"Could not parse rate limit string for IP {ip}: {limit_string}")
                return "1000000 per hour"  # Default to high limit if parsing fails
        
        return limit_string
    else:
        app.logger.debug(f"No custom rate limit for IP {ip}, endpoint {endpoint}, using default")
    
    return get_remote_address

# Initialize Limiter with stricter limits
limiter = Limiter(
    get_rate_limit, 
    app=app,
    default_limits=["1440000 per day", "60000 per hour"], # Stricter default limits
    storage_uri="memory://",  # Use memory for storage, consider Redis for production
    strategy="moving-window", # Moving window for better abuse prevention
    headers_enabled=True  # Enable rate limit headers for debugging
)

# Connection pooling for Qwen service requests
def create_qwen_session():
    """Create a requests session with connection pooling and retry strategy for Qwen service"""
    session = requests.Session()
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"],
        backoff_factor=1
    )
    
    # Configure HTTP adapter with connection pooling
    adapter = HTTPAdapter(
        pool_connections=10,  # Number of connection pools to cache
        pool_maxsize=20,      # Maximum number of connections to save in the pool
        max_retries=retry_strategy
    )
    
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set default timeout
    session.timeout = 30
    
    return session

# Global session for Qwen requests with connection pooling
qwen_session = create_qwen_session()

# Imagen 4 specific rate limits
IMAGEN4_MINUTE_LIMIT = 3
IMAGEN4_DAY_LIMIT = 20
IMAGEN4_MINUTE_WINDOW = timedelta(minutes=1)
IMAGEN4_DAY_WINDOW = timedelta(days=1)

# In-memory storage for Imagen 4 rate limiting
# Structure: {'ip': {'minute_timestamps': [datetime, ...], 'day_count': int, 'last_day_reset': datetime}}
imagen4_request_history = {}

# Configure the upload folder for storing generated images
app_dir = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(app_dir, 'images')
app.config['TEST_ASSETS'] = os.path.join(app_dir, 'test_assets')
app.config['PROCESSED_FOLDER'] = os.path.join(app_dir, 'processed_images')
app.config['PROCESSED_VIDEOS_FOLDER'] = os.path.join(app_dir, 'processed_videos')

# URL path prefixes for images (not file system paths)
app.config['IMAGES_URL_PATH'] = 'images'
app.config['TEST_ASSETS_URL_PATH'] = 'test_assets'
app.config['PROCESSED_URL_PATH'] = 'processed_images'
app.config['PROCESSED_VIDEOS_URL_PATH'] = 'processed_videos'

# Configure Flask-Login
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# API key
GEMINI_API_KEY = "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II"

# Ensure the images directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_VIDEOS_FOLDER'], exist_ok=True)

# Also fix the logs directory path
LOGS_DIR = os.path.join(app_dir, 'logs')

# Initialize visitor logger to track IP addresses and locations
# This needs to be done in the global scope to work in production (e.g., with Gunicorn)
visitor_logger = VisitorLogger(app)

# Admin security decorator
# JWT-based protection for API endpoints
def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        if 'x-access-token' in request.headers:
            token = request.headers['x-access-token']

        if not token:
            return jsonify({'error': 'Token is missing.'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            
            # Pass the decoded data to the request context
            g.token_data = data

            # Handle anonymous user limits
            if data.get('anonymous'):
                user_id = data['user_id']
                
                # Define endpoints that should NOT count towards the free limit (e.g., status polling)
                rate_limit_exempt_endpoints = ['get_qwen_video_status', 'api_img2video_result', 'img2video_result']

                # Only apply the anonymous user limit for non-exempt endpoints
                if request.endpoint not in rate_limit_exempt_endpoints:
                    current_ip = get_client_ip() # Get the current IP
                    current_endpoint = request.endpoint # Get the current endpoint

                    # Check if a custom rate limit exists for this IP and endpoint
                    custom_limit = get_custom_rate_limit(current_ip, current_endpoint)
                    
                    if custom_limit:
                        # If a custom limit exists, we rely on flask_limiter to enforce it.
                        # So, we bypass this in-memory anonymous limit check.
                        pass 
                    else:
                        # If no custom limit, apply the default anonymous user limit
                        if 'anonymous_requests' not in app.config:
                            app.config['anonymous_requests'] = {}
                        
                        now = datetime.utcnow()
                        if user_id not in app.config['anonymous_requests']:
                            app.config['anonymous_requests'][user_id] = []
                        
                        # Clean up old requests
                        app.config['anonymous_requests'][user_id] = [t for t in app.config['anonymous_requests'][user_id] if now - t < timedelta(days=1)]
                        
                        # Enforce the default anonymous limit (e.g., 25 requests per day)
                        if len(app.config['anonymous_requests'][user_id]) >= 25: # Revert to a reasonable default if no custom limit
                            return jsonify({'error': 'Free generation limit reached. Please log in to continue or try again tomorrow'}), 429
                                                    
                        app.config['anonymous_requests'][user_id].append(now)

        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid.'}), 401
        except Exception as e: # Add a general exception handler
            app.logger.error(f"Error in token_required: {e}")
            return jsonify({'error': 'An unexpected error occurred during token validation.'}), 500
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Ensure the admin key is present and correct
        if not ADMIN_SECRET_KEY:
            return jsonify({"error": "Admin secret key is not configured on the server."}), 500
        if request.headers.get('X-Admin-Secret-Key') != ADMIN_SECRET_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Admin Dashboard ---
@app.route('/admin')
def admin_dashboard():
    # This route serves the admin panel.
    # A simple query parameter is used for initial access.
    # The API calls from the panel are secured by the header key.
    secret_key = request.args.get('secret')
    if not ADMIN_SECRET_KEY or secret_key != ADMIN_SECRET_KEY:
        return "Unauthorized", 401
    return render_template('admin.html')

# --- Admin API Endpoints ---
@app.route('/admin/api/blocked-ips', methods=['GET'])
@admin_required
def get_all_blocked_ips():
    """API endpoint to get the list of all blocked IPs.""" 
    ips = get_blocked_ips_util()
    return jsonify(ips)

@app.route('/admin/api/block-ip', methods=['POST'])
@admin_required
def block_ip():
    """API endpoint to block a new IP address."""
    data = request.get_json()
    ip = data.get('ip')
    reason = data.get('reason', '')
    if not ip:
        return jsonify({"error": "IP address is required"}), 400
    
    success, message = block_ip_util(ip, reason)
    if success:
        return jsonify({"message": message})
    else:
        return jsonify({"error": message}), 400

@app.route('/admin/api/unblock-ip', methods=['POST'])
@admin_required
def unblock_ip():
    """API endpoint to unblock an IP address."""
    data = request.get_json()
    ip = data.get('ip')
    if not ip:
        return jsonify({"error": "IP address is required"}), 400
        
    success, message = unblock_ip_util(ip)
    if success:
        return jsonify({"message": message})
    else:
        return jsonify({"error": message}), 400

@app.route('/admin/api/ip-history/<string:ip>', methods=['GET'])
@admin_required
def ip_history(ip):
    """API endpoint to get the request history for a specific IP."""
    history = get_ip_history(ip)
    return jsonify(history)

@app.route('/admin/rate-limits')
def admin_rate_limits():
    secret_key = request.args.get('secret')
    if not ADMIN_SECRET_KEY or secret_key != ADMIN_SECRET_KEY:
        return "Unauthorized", 401
    return render_template('admin/rate_limits.html')

@app.route('/admin/api/custom-rate-limits', methods=['GET'])
@admin_required
def get_custom_rate_limits():
    limits = []
    if custom_rate_limits_collection is not None:
        for limit in custom_rate_limits_collection.find():
            limits.append({
                'ip': limit['ip'],
                'endpoint': limit['endpoint'],
                'limit_string': limit['limit_string']
            })
    return jsonify(limits)

@app.route('/admin/api/set-custom-rate-limit', methods=['POST'])
@admin_required
def set_custom_rate_limit():
    data = request.get_json()
    ip = data.get('ip')
    endpoint = data.get('endpoint')
    limit_string = data.get('limit_string')

    if not all([ip, endpoint, limit_string]):
        return jsonify({'success': False, 'error': 'Missing data'}), 400

    if custom_rate_limits_collection is not None:
        if endpoint == 'all':
            endpoints = ['generate_image', 'api_generate_image', 'img2img_transform', 'api_img2img_transform', 'img2video_generate', 'api_img2video_generate', 'generate_qwen_video_route', 'api_text_to_video_generate']
            for ep in endpoints:
                custom_rate_limits_collection.update_one(
                    {'ip': ip, 'endpoint': ep},
                    {'$set': {'limit_string': limit_string}},
                    upsert=True
                )
        else:
            custom_rate_limits_collection.update_one(
                {'ip': ip, 'endpoint': endpoint},
                {'$set': {'limit_string': limit_string}},
                upsert=True
            )
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Database not connected'}), 500

@app.route('/admin/api/delete-custom-rate-limit', methods=['POST'])
@admin_required
def delete_custom_rate_limit():
    data = request.get_json()
    ip = data.get('ip')
    endpoint = data.get('endpoint')

    if not all([ip, endpoint]):
        return jsonify({'success': False, 'error': 'Missing data'}), 400

    if custom_rate_limits_collection is not None:
        result = custom_rate_limits_collection.delete_one({'ip': ip, 'endpoint': endpoint})
        if result.deleted_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Rule not found'}), 404
    else:
        return jsonify({'success': False, 'error': 'Database not connected'}), 500

def is_potential_abuser(ip):
    if request_logs_collection is None:
        app.logger.error("request_logs_collection is not initialized for abuse detection.")
        return False

    now = datetime.now()
    
    # Criteria 1: More than 25 requests in the last 10 minutes
    time_window_10_min = now - timedelta(minutes=10)
    recent_requests_count = request_logs_collection.count_documents({
        "ip": ip,
        "timestamp": {"$gte": time_window_10_min}
    })
    if recent_requests_count > 25:
        app.logger.info(f"Potential abuser detected (burst): {ip} with {recent_requests_count} requests in 10 min.")
        return True

    # Criteria 2: Sustained rate of 2-4 requests per minute over a longer period (e.g., last 60 minutes)
    # This is more complex. Let's define "long time" as 60 minutes for now.
    time_window_60_min = now - timedelta(minutes=60)
    long_term_requests = list(request_logs_collection.find({
        "ip": ip,
        "timestamp": {"$gte": time_window_60_min}
    }).sort("timestamp", 1)) # Sort by timestamp ascending

    if len(long_term_requests) > 0:
        # Calculate average rate if there are enough requests over a significant period
        # Only consider if there are at least 30 minutes of data for a meaningful average
        if (now - long_term_requests[0]['timestamp']).total_seconds() >= 15 * 60: # At least 15 minutes of data
            total_requests = len(long_term_requests)
            duration_seconds = (now - long_term_requests[0]['timestamp']).total_seconds()
            
            if duration_seconds > 0:
                avg_requests_per_minute = (total_requests / duration_seconds) * 60
                
                # Check if average rate is between 2 and 4 requests per minute
                # And total requests over this long period is substantial (e.g., > 60 requests for 30 min, or > 120 for 60 min)
                # This prevents flagging IPs with just a few requests over a long time
                if 4 <= avg_requests_per_minute or total_requests >= 40: # 40 requests in 15 min is 2/min, 120 in 60 min is 2/min
                    app.logger.info(f"Potential abuser detected (sustained): {ip} with avg {avg_requests_per_minute:.2f} req/min over {duration_seconds/60:.1f} min.")
                    return True

    return False

@app.route('/admin/api/potential-abusers', methods=['GET'])
@admin_required
def get_potential_abusers():
    """API endpoint to get a list of potential abuser IPs."""
    if request_logs_collection is None:
        return jsonify({"error": "Request logs database not connected"}), 500

    potential_abusers = []
    # Get all unique IPs from the request logs
    unique_ips = request_logs_collection.distinct("ip")

    for ip in unique_ips:
        if is_potential_abuser(ip):
            potential_abusers.append(ip)
            
    return jsonify(potential_abusers)

@app.route('/admin/api/resource-status', methods=['GET'])
@admin_required
def get_resource_status():
    """API endpoint to get current resource monitoring status."""
    try:
        from resource_monitor import get_system_status
        status = get_system_status()
        return jsonify(status)
    except Exception as e:
        app.logger.error(f"Error getting resource status: {e}")
        return jsonify({"error": "Failed to get resource status"}), 500

@app.route('/admin/qwen-keys', methods=['GET', 'POST'])
def admin_qwen_keys():
    secret_key = request.args.get('secret')
    if not ADMIN_SECRET_KEY or secret_key != ADMIN_SECRET_KEY:
        return "Unauthorized", 401

    if request.method == 'POST':
        auth_token = request.form.get('auth_token')
        chat_id = request.form.get('chat_id')
        fid = request.form.get('fid')
        children_ids = request.form.get('children_ids').split(',')
        x_request_id = request.form.get('x_request_id')

        key = QwenApiKey(
            auth_token=auth_token,
            chat_id=chat_id,
            fid=fid,
            children_ids=children_ids,
            x_request_id=x_request_id
        )
        
        # Debug: Log the status before saving
        app.logger.info(f"Creating new Qwen API key with status: {key.status}")
        
        key_id = key.save()
        
        # Debug: Verify the key was saved with correct status
        saved_key = db['qwen_api_keys'].find_one({'_id': key_id})
        app.logger.info(f"Saved Qwen API key with status: {saved_key.get('status') if saved_key else 'NOT FOUND'}")
        
        flash('Qwen API key added successfully!', 'success')
        return redirect(url_for('admin_qwen_keys', secret=secret_key))

    keys = QwenApiKey.get_all()
    return render_template('admin/qwen_keys.html', keys=keys)

@app.route('/admin/qwen-keys/delete/<key_id>', methods=['POST'])
def admin_delete_qwen_key(key_id):
    secret_key = request.args.get('secret')
    if not ADMIN_SECRET_KEY or secret_key != ADMIN_SECRET_KEY:
        return "Unauthorized", 401

    QwenApiKey.delete(key_id)
    flash('Qwen API key deleted successfully!', 'success')
    return redirect(url_for('admin_qwen_keys', secret=secret_key))

# Text to Video API Endpoints
@app.route('/api/text-to-video/generate', methods=['POST'])
@limiter.limit("10 per hour")
def api_text_to_video_generate():
    """API endpoint for text-to-video generation"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        prompt = data.get('prompt', '').strip()
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        
        if len(prompt) > 500:
            return jsonify({'error': 'Prompt must be 500 characters or less'}), 400
        
        # Get client IP for tracking
        client_ip = get_client_ip()
        
        # Get a random Qwen API key
        qwen_keys = QwenApiKey.get_all()
        if not qwen_keys:
            return jsonify({'error': 'Video generation service temporarily unavailable'}), 503
        
        import random
        selected_key = random.choice(qwen_keys)
        
        # Debug logging
        app.logger.info(f"Selected key type: {type(selected_key)}")
        app.logger.info(f"Selected key keys: {selected_key.keys() if isinstance(selected_key, dict) else 'Not a dict'}")
        
        # Handle both dictionary and object access patterns
        try:
            if isinstance(selected_key, dict):
                key_dict = {
                    'auth_token': selected_key.get('auth_token'),
                    'chat_id': selected_key.get('chat_id'),
                    'fid': selected_key.get('fid'),
                    'children_ids': selected_key.get('children_ids'),
                    'x_request_id': selected_key.get('x_request_id')
                }
            else:
                # Handle object access
                key_dict = {
                    'auth_token': getattr(selected_key, 'auth_token', None),
                    'chat_id': getattr(selected_key, 'chat_id', None),
                    'fid': getattr(selected_key, 'fid', None),
                    'children_ids': getattr(selected_key, 'children_ids', None),
                    'x_request_id': getattr(selected_key, 'x_request_id', None)
                }
            
            # Validate that we have all required keys
            required_keys = ['auth_token', 'chat_id', 'fid', 'children_ids', 'x_request_id']
            missing_keys = [key for key in required_keys if not key_dict.get(key)]
            if missing_keys:
                app.logger.error(f"Missing required Qwen API key fields: {missing_keys}")
                return jsonify({'error': 'Video generation service configuration error'}), 503
                
        except Exception as e:
            app.logger.error(f"Error processing Qwen API key: {e}")
            return jsonify({'error': 'Video generation service configuration error'}), 503
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        # Create video task record
        video_task = VideoTask.create(prompt)
        if not video_task:
            return jsonify({'error': 'Failed to create video task'}), 500
        
        task_id = video_task['task_id']
        
        # Capture host URL before starting background thread
        host_url = request.host_url
        
        # Start video generation in background thread
        def generate_video_async():
            try:
                result = generate_qwen_video(prompt, key_dict)
                
                if 'error' in result:
                    VideoTask.update(task_id, 'failed', error_message=result['error'])
                    app.logger.error(f"Video generation failed for task {task_id}: {result['error']}")
                else:
                    video_url = result.get('video_url')
                    if video_url:
                        # Create URL mapping for privacy
                        mapping = VideoUrlMapping()
                        proxy_id = mapping.create_mapping(video_url, task_id)
                        
                        # Create full proxy URL using captured host_url
                        proxy_url = f"{host_url}proxy/video/{proxy_id}"
                        
                        VideoTask.update(task_id, 'completed', result_url=video_url, proxy_url=proxy_url)
                        app.logger.info(f"Video generation completed for task {task_id}")
                    else:
                        VideoTask.update(task_id, 'failed', error_message='No video URL in response')
                        app.logger.error(f"Video generation failed for task {task_id}: No video URL")
                        
            except Exception as e:
                VideoTask.update(task_id, 'failed', error_message=str(e))
                app.logger.error(f"Video generation error for task {task_id}: {e}")
        
        # Start background thread
        thread = threading.Thread(target=generate_video_async)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'status': 'processing',
            'message': 'Video generation started. Use the status endpoint to check progress.',
            'status_url': f'/api/text-to-video/status/{task_id}'
        }), 202
        
    except Exception as e:
        app.logger.error(f"API text-to-video generation error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/text-to-video/status/<task_id>', methods=['GET'])
def api_text_to_video_status(task_id):
    """API endpoint to check text-to-video generation status"""
    try:
        video_task = VideoTask.get_by_id(task_id)
        if not video_task:
            return jsonify({'error': 'Task not found'}), 404
        
        response_data = {
            'task_id': task_id,
            'status': video_task.get('status', 'unknown'),
            'created_at': video_task.get('created_at').isoformat() if video_task.get('created_at') else None
        }
        
        if video_task.get('status') == 'completed' and video_task.get('proxy_url'):
            response_data['video_url'] = video_task.get('proxy_url')
            response_data['message'] = 'Video generation completed successfully'
        elif video_task.get('status') == 'failed':
            response_data['error_message'] = video_task.get('error_message', 'Video generation failed')
        elif video_task.get('status') in ['processing', 'pending']:
            response_data['message'] = 'Video generation in progress'
        
        return jsonify(response_data)
        
    except Exception as e:
        app.logger.error(f"API text-to-video status error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Video Proxy Endpoint
@app.route('/proxy/video/<proxy_id>')
def proxy_video(proxy_id):
    """Proxy endpoint to serve videos through privacy-protected URLs"""
    try:
        # Get the original Qwen URL from the proxy mapping
        mapping = VideoUrlMapping()
        qwen_url = mapping.get_qwen_url(proxy_id)
        
        if not qwen_url:
            return jsonify({'error': 'Video not found or expired'}), 404
        
        # Stream the video from Qwen URL to the client
        try:
            # Use the global qwen_session for connection pooling
            response = qwen_session.get(qwen_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Create a streaming response
            def generate():
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            
            # Get content type from the original response
            content_type = response.headers.get('content-type', 'video/mp4')
            content_length = response.headers.get('content-length')
            
            # Create Flask response with proper headers
            flask_response = Response(
                stream_with_context(generate()),
                content_type=content_type,
                headers={
                    'Accept-Ranges': 'bytes',
                    'Cache-Control': 'public, max-age=3600',
                    'Access-Control-Allow-Origin': '*'
                }
            )
            
            if content_length:
                flask_response.headers['Content-Length'] = content_length
            
            return flask_response
            
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Error proxying video {proxy_id}: {e}")
            return jsonify({'error': 'Video temporarily unavailable'}), 503
            
    except Exception as e:
        app.logger.error(f"Error in video proxy for {proxy_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# Video URL Mapping Admin Endpoints
@app.route('/admin/api/video-mapping-stats', methods=['GET'])
@admin_required
def get_video_mapping_stats():
    """API endpoint to get video URL mapping storage statistics"""
    try:
        mapping = VideoUrlMapping()
        stats = mapping.get_storage_usage_stats()
        cleanup_status = VideoUrlMapping.get_cleanup_status()
        
        # Combine stats and cleanup status
        response = {**stats, **cleanup_status}
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/video-mapping-cleanup', methods=['POST'])
@admin_required
def manual_video_mapping_cleanup():
    """API endpoint to manually trigger cleanup of expired video URL mappings"""
    try:
        mapping = VideoUrlMapping()
        deleted_count = mapping.cleanup_expired_mappings()
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Cleaned up {deleted_count} expired video URL mappings'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/admin/video-mappings')
def admin_video_mappings():
    """Admin page for video URL mapping management"""
    secret_key = request.args.get('secret')
    if not ADMIN_SECRET_KEY or secret_key != ADMIN_SECRET_KEY:
        return "Unauthorized", 401
    return render_template('admin/video_mappings.html')

@app.route('/debug/rate-limit-info')
def debug_rate_limit_info():
    """Debug endpoint to check current rate limit configuration"""
    ip = get_client_ip()
    endpoint = request.endpoint
    
    # Get custom rate limit
    custom_limit = get_custom_rate_limit(ip, endpoint)
    
    # Get current limiter state
    limiter_info = {
        'client_ip': ip,
        'endpoint': endpoint,
        'custom_limit': custom_limit,
        'default_limits': ["1440000 per day", "60000 per hour"],  # Our configured defaults
        'storage_uri': getattr(limiter, 'storage_uri', 'memory://'),
        'strategy': getattr(limiter, 'strategy', 'moving-window')
    }
    
    # Try to get current rate limit status
    try:
        # Get the rate limit function result for this request
        rate_limit_key = get_rate_limit()
        
        # Convert function to string representation if needed
        if callable(rate_limit_key):
            limiter_info['rate_limit_key_function_result'] = f"Function: {rate_limit_key.__name__}"
        else:
            limiter_info['rate_limit_key_function_result'] = rate_limit_key
        
        # Check if this endpoint has specific limits
        if hasattr(request, 'endpoint') and request.endpoint:
            limiter_info['endpoint_specific_limits'] = 'Check route decorators'
    except Exception as e:
        limiter_info['rate_limit_function_error'] = str(e)
    
    return jsonify(limiter_info)

@app.route('/debug/test-rate-limit')
@limiter.limit("5 per minute")  # Simple test limit
def debug_test_rate_limit():
    """Simple endpoint to test rate limiting"""
    ip = get_client_ip()
    return jsonify({
        'message': 'Rate limit test successful',
        'your_ip': ip,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/debug/ip-info')
def debug_ip_info():
    """Debug endpoint to show all IP-related information"""
    ip_info = {
        'detected_ip': get_client_ip(),
        'request_remote_addr': request.remote_addr,
        'headers': {}
    }
    
    # Check all relevant headers
    headers_to_check = [
        'X-Forwarded-For',
        'X-Real-IP', 
        'CF-Connecting-IP',
        'X-Forwarded-Proto',
        'Host',
        'User-Agent'
    ]
    
    for header in headers_to_check:
        if header in request.headers:
            ip_info['headers'][header] = request.headers[header]
    
    # Check if there's a custom rate limit for this IP
    custom_limit = get_custom_rate_limit(ip_info['detected_ip'], 'api_generate_image')
    ip_info['has_custom_rate_limit'] = custom_limit is not None
    if custom_limit:
        ip_info['custom_rate_limit'] = custom_limit
    
    return jsonify(ip_info)

@app.route('/admin/video-proxy-monitoring')
def admin_video_proxy_monitoring():
    """Admin page for video proxy performance monitoring"""
    secret_key = request.args.get('secret')
    if not ADMIN_SECRET_KEY or secret_key != ADMIN_SECRET_KEY:
        return "Unauthorized", 401
    return render_template('admin/video_proxy_monitoring.html')

@app.route('/admin/api/video-proxy-performance', methods=['GET'])
@admin_required
def get_video_proxy_performance():
    """API endpoint to get video proxy performance statistics"""
    try:
        hours = int(request.args.get('hours', 24))
        stats = get_proxy_performance_stats(hours)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/video-proxy-logs', methods=['GET'])
@admin_required
def get_video_proxy_logs():
    """API endpoint to get recent video proxy access logs"""
    try:
        if db is None:
            return jsonify({'error': 'Database not available'}), 500
        
        # Get query parameters
        limit = int(request.args.get('limit', 100))
        hours = int(request.args.get('hours', 24))
        status_code = request.args.get('status_code')
        
        # Build query
        query = {
            'timestamp': {
                '$gte': datetime.now(timezone.utc) - timedelta(hours=hours)
            }
        }
        
        if status_code:
            query['status_code'] = int(status_code)
        
        # Get logs
        logs = list(db['video_proxy_logs'].find(
            query,
            {'_id': 0}  # Exclude MongoDB _id field
        ).sort('timestamp', -1).limit(limit))
        
        # Convert datetime objects to ISO strings for JSON serialization
        for log in logs:
            if 'timestamp' in log:
                log['timestamp'] = log['timestamp'].isoformat()
        
        return jsonify({
            'logs': logs,
            'total_count': len(logs),
            'query_hours': hours,
            'query_limit': limit
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/video-proxy-error-summary', methods=['GET'])
@admin_required
def get_video_proxy_error_summary():
    """API endpoint to get summary of video proxy errors"""
    try:
        if db is None:
            return jsonify({'error': 'Database not available'}), 500
        
        hours = int(request.args.get('hours', 24))
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Aggregate error statistics
        pipeline = [
            {'$match': {
                'timestamp': {'$gte': start_time},
                'status_code': {'$gte': 400}
            }},
            {'$group': {
                '_id': {
                    'status_code': '$status_code',
                    'error_message': '$error_message'
                },
                'count': {'$sum': 1},
                'latest_occurrence': {'$max': '$timestamp'}
            }},
            {'$sort': {'count': -1}},
            {'$limit': 20}
        ]
        
        error_summary = list(db['video_proxy_logs'].aggregate(pipeline))
        
        # Convert datetime objects to ISO strings
        for error in error_summary:
            if 'latest_occurrence' in error:
                error['latest_occurrence'] = error['latest_occurrence'].isoformat()
        
        # Get total error count
        total_errors = db['video_proxy_logs'].count_documents({
            'timestamp': {'$gte': start_time},
            'status_code': {'$gte': 400}
        })
        
        return jsonify({
            'error_summary': error_summary,
            'total_errors': total_errors,
            'hours_analyzed': hours
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/user-generations')
def admin_user_generations():
    """Admin page for user generation history management"""
    secret_key = request.args.get('secret')
    if not ADMIN_SECRET_KEY or secret_key != ADMIN_SECRET_KEY:
        return "Unauthorized", 401
    return render_template('admin/user_generations.html')

@app.route('/admin/api/user-generations', methods=['GET'])
@admin_required
def admin_get_user_generations():
    """API endpoint to get user generation history for admin"""
    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 20)), 100)  # Max 100 items
        generation_type = request.args.get('type')
        status_filter = request.args.get('status')
        
        skip = (page - 1) * limit
        
        history = UserGenerationHistory()
        
        # Build query
        query = {'is_active': True}
        if generation_type:
            query['generation_type'] = generation_type
        
        # Get generations with pagination
        cursor = history.collection.find(query).sort('created_at', -1).skip(skip).limit(limit)
        generations = []
        
        for doc in cursor:
            doc['_id'] = str(doc['_id'])
            if 'created_at' in doc:
                doc['created_at'] = doc['created_at'].isoformat()
            
            # Apply status filter if specified
            if status_filter:
                if status_filter == 'completed' and not doc.get('proxy_url'):
                    continue
                elif status_filter == 'processing' and doc.get('proxy_url'):
                    continue
                elif status_filter == 'failed':
                    # For now, we don't have explicit failed status in history
                    continue
            
            generations.append(doc)
        
        # Get total count
        total_count = history.collection.count_documents(query)
        
        # Calculate stats
        stats = calculate_generation_stats(history)
        
        return jsonify({
            'success': True,
            'generations': generations,
            'total_count': total_count,
            'page': page,
            'limit': limit,
            'stats': stats
        })
        
    except Exception as e:
        app.logger.error(f"Error retrieving admin user generations: {e}")
        return jsonify({'error': 'Failed to retrieve generation history'}), 500

def calculate_generation_stats(history):
    """Calculate statistics for admin dashboard"""
    try:
        from datetime import datetime, timezone, timedelta
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        
        # Total generations
        total = history.collection.count_documents({'is_active': True})
        
        # Today's generations
        today = history.collection.count_documents({
            'is_active': True,
            'created_at': {'$gte': today_start}
        })
        
        # Active users in last 24h (unique user_id and session_id)
        pipeline = [
            {'$match': {
                'is_active': True,
                'created_at': {'$gte': yesterday_start}
            }},
            {'$group': {
                '_id': {
                    'user_id': '$user_id',
                    'session_id': '$session_id'
                }
            }},
            {'$count': 'active_users'}
        ]
        
        active_users_result = list(history.collection.aggregate(pipeline))
        active_users = active_users_result[0]['active_users'] if active_users_result else 0
        
        # Success rate (generations with proxy_url)
        completed = history.collection.count_documents({
            'is_active': True,
            'proxy_url': {'$exists': True, '$ne': None}
        })
        
        success_rate = round((completed / total * 100), 1) if total > 0 else 0
        
        return {
            'total': total,
            'today': today,
            'active_users': active_users,
            'success_rate': success_rate
        }
        
    except Exception as e:
        app.logger.error(f"Error calculating generation stats: {e}")
        return {
            'total': 0,
            'today': 0,
            'active_users': 0,
            'success_rate': 0
        }

@app.route('/admin/api/user-generations/export', methods=['GET'])
@admin_required
def admin_export_user_generations():
    """Export user generation history as CSV"""
    try:
        import csv
        from io import StringIO
        
        history = UserGenerationHistory()
        
        # Get all generations
        cursor = history.collection.find({'is_active': True}).sort('created_at', -1)
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'ID', 'User Type', 'Generation Type', 'Prompt', 
            'Status', 'Created At', 'Has Video'
        ])
        
        # Write data
        for doc in cursor:
            writer.writerow([
                str(doc['_id']),
                'User' if doc.get('user_id') else 'Anonymous',
                doc.get('generation_type', ''),
                doc.get('prompt', ''),
                'Completed' if doc.get('proxy_url') else 'Processing',
                doc.get('created_at', '').isoformat() if doc.get('created_at') else '',
                'Yes' if doc.get('proxy_url') else 'No'
            ])
        
        # Create response
        output.seek(0)
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=user_generations.csv'}
        )
        
        return response
        
    except Exception as e:
        app.logger.error(f"Error exporting user generations: {e}")
        return jsonify({'error': 'Failed to export data'}), 500

@app.route('/admin/api/video-proxy-health', methods=['GET'])
@admin_required
def get_video_proxy_health():
    """API endpoint to check video proxy system health"""
    try:
        health_status = check_video_proxy_health()
        
        # Determine overall health status
        overall_status = 'healthy'
        if not health_status['database_connected'] or not health_status['mapping_service_available']:
            overall_status = 'unhealthy'
        elif health_status['error_rate_last_hour'] > 10:  # More than 10% error rate
            overall_status = 'degraded'
        elif health_status['avg_response_time_last_hour'] > 5000:  # More than 5 seconds
            overall_status = 'degraded'
        
        health_status['overall_status'] = overall_status
        health_status['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        # Return appropriate HTTP status code
        if overall_status == 'healthy':
            return jsonify(health_status), 200
        elif overall_status == 'degraded':
            return jsonify(health_status), 200  # Still operational but degraded
        else:
            return jsonify(health_status), 503  # Service unavailable
        
    except Exception as e:
        return jsonify({
            'overall_status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500

@app.route('/health/video-proxy', methods=['GET'])
def video_proxy_health_check():
    """Public health check endpoint for video proxy functionality"""
    try:
        health_status = check_video_proxy_health()
        
        # Return simplified health status for public endpoint
        public_health = {
            'status': 'healthy' if health_status['database_connected'] and 
                     health_status['mapping_service_available'] and
                     health_status['error_rate_last_hour'] < 20 else 'unhealthy',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return jsonify(public_health), 200 if public_health['status'] == 'healthy' else 503
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 503

@login_manager.user_loader
def load_user(user_id):
    return User.find_by_id(user_id)

@app.route('/')
def index():
    """Render the main page with the form"""
    return render_template('index.html',
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))

@app.route('/text-to-image')
def text_to_image():
    """Render the text-to-image page"""
    return render_template('text-to-image.html',
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))

@app.route('/image-to-image')
def image_to_image():
    """Render the image-to-image page"""
    return render_template('image-to-image.html',
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))

@app.route('/image-to-video')
def image_to_video_page():
    """Render the image-to-video page"""
    return render_template('image-to-video.html',
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))

@app.route('/contact')
def contact():
    """Render the contact page"""
    return render_template('contact.html',
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))

@app.route('/sitemap-page')
def sitemap_page():
    """Render the human-readable sitemap page"""
    return render_template('sitemap.html',
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))

@app.route('/sitemap.xml')
def serve_sitemap():
    """Serve the XML sitemap file for search engines"""
    return send_file('static/sitemap.xml')

@app.route('/blocked')
def blocked_page():
    """Render the blocked page with a reason"""
    reason = request.args.get('reason', 'No reason provided.')
    return render_template('blocked.html', reason=reason)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        # Check if it's a Firebase token (Google Sign-in)
        if request.json and 'idToken' in request.json:
            try:
                # Verify the token
                token = request.json['idToken']
                decoded_token = firebase_admin_auth.verify_id_token(token)
                
                # Get user info
                uid = decoded_token['uid']
                firebase_user = firebase_admin_auth.get_user(uid)
                
                # Create or update user in our database
                user_data = {
                    'uid': uid,
                    'email': firebase_user.email,
                    'displayName': firebase_user.display_name,
                    'emailVerified': firebase_user.email_verified
                }
                
                print(f"Google Sign-in for user: {firebase_user.email}")
                user_obj = User.create_or_update_from_firebase(user_data)
                
                if not user_obj:
                    print(f"Failed to create or update user for Google Sign-in: {firebase_user.email}")
                    return jsonify({'success': False, 'error': 'Failed to create user account'}), 500
                
                # Log in the user
                login_user(user_obj)
                print(f"Google user logged in successfully: {firebase_user.email}")
                return jsonify({'success': True, 'redirect': url_for('dashboard')})
            
            except Exception as e:
                print(f"Token verification error: {e}")
                return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    # For GET requests, redirect to homepage with login modal parameter
    return redirect(url_for('index', action='login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        # Check if it's a Google sign-in
        if request.json and 'idToken' in request.json:
            try:
                # Verify the token
                token = request.json['idToken']
                decoded_token = firebase_admin_auth.verify_id_token(token)
                
                # Get user info
                uid = decoded_token['uid']
                firebase_user = firebase_admin_auth.get_user(uid)
                
                print(f"Google Sign-up for user: {firebase_user.email}")
                
                # Create or update user in our database
                user_data = {
                    'uid': uid,
                    'email': firebase_user.email,
                    'displayName': firebase_user.display_name,
                    'emailVerified': firebase_user.email_verified
                }
                
                user_obj = User.create_or_update_from_firebase(user_data)
                
                if not user_obj:
                    print(f"Failed to create or update Google user in database: {firebase_user.email}")
                    return jsonify({'success': False, 'error': 'Failed to create user account in database'}), 500
                
                # Log in the user
                login_user(user_obj)
                print(f"Google user signed up and logged in successfully: {firebase_user.email}")
                return jsonify({'success': True, 'redirect': url_for('dashboard')})
            
            except Exception as e:
                print(f"Token verification error: {e}")
                return jsonify({'success': False, 'error': 'Invalid token'}), 401
    
    # For GET requests, redirect to homepage with signup modal parameter
    return redirect(url_for('index', action='signup'))

@app.route('/reset-password')
def reset_password():
    """Redirect reset-password requests to login since we only use Google auth now"""
    flash('Please use Google sign-in to access your account', 'info')
    return redirect(url_for('login'))

@app.route('/verify-email')
def verify_email():
    """Handle email verification confirmation - redirect to login for Google auth"""
    return redirect(url_for('login'))

@app.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    logout_user()
    # Return a JSON response if it's an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'redirect': url_for('login')})
    return redirect(url_for('index'))

@app.route('/check-auth-status')
def check_auth_status():
    """Check if the user is authenticated and return the status"""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': {
                'email': current_user.email if hasattr(current_user, 'email') else None,
                'name': current_user.name if hasattr(current_user, 'name') else None
            }
        })
    else:
        return jsonify({'authenticated': False})

@app.route('/get-api-token', methods=['GET', 'POST'])
def get_api_token():
    """Generate a JWT for the authenticated or anonymous user."""
    try:
        expiration = datetime.utcnow() + timedelta(hours=1)
        
        if current_user.is_authenticated:
            user_id = current_user.get_id()
            is_anonymous = False
        else:
            # For anonymous users, try to get client-provided anonymous ID first
            client_anonymous_id = None
            
            if request.method == 'POST':
                data = request.get_json()
                client_anonymous_id = data.get('anonymous_id') if data else None
            else:
                client_anonymous_id = request.args.get('anonymous_id')
            
            # Validate the client-provided ID (should be a valid UUID format)
            if client_anonymous_id:
                try:
                    # Validate UUID format
                    uuid.UUID(client_anonymous_id)
                    user_id = client_anonymous_id
                except ValueError:
                    # Invalid UUID format, generate a new one
                    user_id = str(uuid.uuid4())
            else:
                # No client ID provided, check session or generate new
                if 'anonymous_id' not in session:
                    session['anonymous_id'] = str(uuid.uuid4())
                user_id = session['anonymous_id']
            
            is_anonymous = True

        payload = {
            'user_id': user_id,
            'anonymous': is_anonymous,
            'exp': expiration,
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({'token': token, 'anonymous_id': user_id if is_anonymous else None})
    except Exception as e:
        app.logger.error(f"Error generating API token: {str(e)}")
        return jsonify({'error': 'Could not generate API token.'}), 500

@app.route('/dashboard')
@login_required
def dashboard():
    """Display user dashboard"""
    # Double check authentication - sometimes this can happen with stale sessions
    if not current_user.is_authenticated:
        print(f"Dashboard access attempted without valid auth")
        return redirect(url_for('index', action='login'))
    
    try:
        return render_template('dashboard.html', user=current_user)
    except Exception as e:
        print(f"Error loading dashboard: {str(e)}")
        # If there's an error loading the dashboard, log the user out and redirect
        logout_user()
        return redirect(url_for('index', action='login', error='session_expired'))

@app.route('/generate-txt2img-ui', methods=['POST'])
@token_required
def generate_image():
    """Generate an image based on the description provided"""

    # Turnstile verification
    turnstile_token = request.form.get('cf_turnstile_response')
    print("Received Turnstile token from client:", turnstile_token)

    client_ip = request.headers.get("CF-Connecting-IP")
    if not verify_turnstile(turnstile_token, client_ip):
        return jsonify({'error': 'The provided Turnstile token was not valid!'}), 403

    # Honeypot field check (should be empty)
    honeypot = request.form.get('website_url', '')
    if honeypot:
        app.logger.warning(f"Honeypot triggered from IP: {get_remote_address()}")
        return jsonify({'error': 'Invalid request detected.'}), 400

    # Get the image description from the form
    image_description = request.form.get('video_description')

    print(f"Received image description: {image_description}")

    # Translate the prompt to English
    image_description = translate_to_english(image_description)

    # Check if test mode is enabled
    test_mode = request.form.get('test_mode') == 'true'

    if not image_description:
        return jsonify({'error': 'Image description is required'}), 400

    # Get advanced options
    negative_prompt = request.form.get('negative_prompt', '')
    style_preset = request.form.get('style_preset', None)
    if style_preset == '':
        style_preset = None

    aspect_ratio = request.form.get('aspect_ratio', '16:9')
    output_format = request.form.get('output_format', 'png')

    # Get seed (0 means random)
    try:
        seed = int(request.form.get('seed', 0))
    except ValueError:
        seed = 0

    # Get the selected model
    selected_model = request.form.get('model', 'stable-diffusion-3.5-ultra') # Default to Stable Diffusion

    if selected_model == 'imagen-4':
        # --- Imagen 4 (GhostAPI) Generation Logic ---
        ip = get_client_ip()
        now = datetime.now()

        # Initialize IP entry if it doesn't exist
        if ip not in imagen4_request_history:
            imagen4_request_history[ip] = {
                'minute_timestamps': [],
                'day_count': 0,
                'last_day_reset': now
            }

        ip_data = imagen4_request_history[ip]

        # Clean up old minute timestamps
        ip_data['minute_timestamps'] = [
            ts for ts in ip_data['minute_timestamps'] if now - ts < IMAGEN4_MINUTE_WINDOW
        ]

        # Reset daily count if a new day has started
        if now.date() != ip_data['last_day_reset'].date():
            ip_data['day_count'] = 0
            ip_data['last_day_reset'] = now

        # Check minute limit
        if len(ip_data['minute_timestamps']) >= IMAGEN4_MINUTE_LIMIT:
            time_left = (ip_data['minute_timestamps'][0] + IMAGEN4_MINUTE_WINDOW) - now
            retry_after = int(time_left.total_seconds()) + 1 # Add 1 second buffer
            return jsonify({
                'error': f"""Rate limit exceeded for Imagen 4. You can generate up to {IMAGEN4_MINUTE_LIMIT} images per minute and at most {IMAGEN4_DAY_LIMIT} images per day using Imagen 4.
                 Please try again in {retry_after} seconds. 
                 For more usage, please visit https://api.infip.pro/docs (for Imagen 4 API), or https://chat.infip.pro/ (for UI).
                 Or, switch to Stable Diffusion 3.5 Ultra to enjoy unlimited image generation.""",
                'rate_limit_type': 'minute',
                'retry_after': retry_after
            }), 429

        # Check daily limit
        if ip_data['day_count'] >= IMAGEN4_DAY_LIMIT:
            # Calculate time until next day reset
            next_day = (now + IMAGEN4_DAY_WINDOW).replace(hour=0, minute=0, second=0, microsecond=0)
            time_left = next_day - now
            retry_after = int(time_left.total_seconds()) + 1 # Add 1 second buffer
            return jsonify({
                'error': f'Daily rate limit exceeded for Imagen 4. You can generate up to {IMAGEN4_DAY_LIMIT} images per day using Imagen 4 in AiArt. For more usage, please visit https://api.infip.pro/docs (for Imagen 4 API), or https://chat.infip.pro/ (for UI), or, switch to Stable Diffusion 3.5 Ultra.',
                'rate_limit_type': 'daily',
                'retry_after': retry_after
            }), 429

        # If limits not exceeded, record the request
        ip_data['minute_timestamps'].append(now)
        ip_data['day_count'] += 1

        ghost_api_url = "https://api.infip.pro/v1/images/generations"
        ghost_api_key = os.getenv('IMAGEN_API_KEY')

        headers = {
            "Authorization": f"Bearer {ghost_api_key}",
            "Content-Type": "application/json"
        }
        image_size = "1024x1024" # Using a common size, API docs example was 1792x1024

        payload = {
            "model": "img4", # As specified in the API docs screenshot
            "prompt": image_description,
            "response_format": "url", # Requesting a URL
            "size": image_size
        }

        try:
            print(f"Calling GhostAPI for Imagen 4: {ghost_api_url}")
            print(f"Payload: {payload}")
            response = requests.post(ghost_api_url, json=payload, headers=headers)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

            ghost_api_result = response.json()
            print(f"GhostAPI response: {ghost_api_result}")

            if ghost_api_result and 'data' in ghost_api_result and ghost_api_result['data']:
                # Assuming the API returns a list of images in 'data'
                # And each image object has a 'url' field
                image_url = ghost_api_result['data'][0].get('url')

                if image_url:
                    # For Imagen 4, we get a direct URL from the API
                    # We don't need to save it locally or use Flask's send_from_directory
                    print(f"Imagen 4 image URL received: {image_url}")
                    return jsonify({
                        'success': True,
                        'message': 'Image generated successfully by Imagen 4',
                        'image_path': image_url # Return the direct URL
                    })
                else:
                    print("GhostAPI response missing image URL in data.")
                    return jsonify({'error': 'GhostAPI response missing image URL'}), 500
            else:
                 print(f"GhostAPI response indicates failure or no data: {ghost_api_result}")
                 return jsonify({'error': ghost_api_result.get('detail', 'GhostAPI returned no image data')}), 500

        except requests.exceptions.RequestException as e:
            print(f"Error calling GhostAPI: {e}")
            return jsonify({'error': f'Error communicating with Imagen 4 API: {e}'}), 500
        except Exception as e:
            print(f"Unexpected error processing GhostAPI response: {e}")
            return jsonify({'error': f'Unexpected error processing Imagen 4 response: {e}'}), 500

    else:
        # --- Stable Diffusion 3.5 Ultra Generation Logic (Existing) ---
        try:
            # Generate the image with advanced options using the existing function
            generated_image_path = main_image_function(
                image_description=image_description,
                testMode=test_mode,
                api_key_gemini=GEMINI_API_KEY,
                negative_prompt=negative_prompt,
                aspect_ratio=aspect_ratio,
                seed=seed,
                style_preset=style_preset,
                output_format=output_format
            )

            # Extract just the filename from the path
            image_filename = os.path.basename(generated_image_path)

            # Determine which folder the image is in
            if 'test_assets' in generated_image_path:
                folder = app.config['TEST_ASSETS']
            elif 'processed_images' in generated_image_path:
                folder = app.config['PROCESSED_FOLDER']
            else:
                folder = app.config['UPLOAD_FOLDER']

            # Construct the URL using url_for for consistent URL handling
            if 'test_assets' in generated_image_path:
                image_url = url_for('serve_test_asset', filename=image_filename)
            elif 'processed_images' in generated_image_path:
                image_url = url_for('serve_processed_image', filename=image_filename)
            else:
                image_url = url_for('serve_image', filename=image_filename)

            print(f"Returning image URL to frontend: {image_url}")

            # Return the image path and success message
            return jsonify({
                'success': True,
                'message': 'Image generated successfully',
                'image_path': image_url
            })

        except Exception as e:
            print(f"Error in Stable Diffusion generation: {e}")
            return jsonify({'error': str(e)}), 500

@app.route('/api/generate', methods=['POST'])
@limiter.limit("3/minute")  # Apply rate limit: 3 requests per minute per IP
def api_generate_image():
    """API endpoint to generate an image"""
    # Get JSON data
    data = request.get_json()
    
    if not data or 'video_description' not in data:
        return jsonify({'error': 'Image description is required'}), 400
    
    image_description = data['video_description']

    print(f"Received image description from API: {image_description}")
    
    # Translate the prompt to English
    image_description = translate_to_english(image_description)
    test_mode = data.get('test_mode', False)
    
    # Get advanced options
    negative_prompt = data.get('negative_prompt', '')
    style_preset = data.get('style_preset')
    if style_preset == '':
        style_preset = None
    
    aspect_ratio = data.get('aspect_ratio', '16:9')
    output_format = data.get('output_format', 'png')
    
    # Get seed (0 means random)
    try:
        seed = int(data.get('seed', 0))
    except (ValueError, TypeError):
        seed = 0
    
    try:
        # Generate the image with advanced options
        generated_image_path = main_image_function(
            image_description=image_description,
            testMode=test_mode,
            api_key_gemini=GEMINI_API_KEY,
            negative_prompt=negative_prompt,
            aspect_ratio=aspect_ratio,
            seed=seed,
            style_preset=style_preset,
            output_format=output_format
        )
        
        # Extract just the filename from the path
        image_filename = os.path.basename(generated_image_path)
        
        # Determine which route to use based on the folder
        if 'test_assets' in generated_image_path:
            image_url = url_for('serve_test_asset', filename=image_filename, _external=True)
            folder = 'test_assets'
        elif 'processed_images' in generated_image_path:
            image_url = url_for('serve_processed_image', filename=image_filename, _external=True)
            folder = 'processed_images'
        else:
            image_url = url_for('serve_image', filename=image_filename, _external=True)
            folder = 'images'
        
        # Create a simple direct URL as a fallback
        direct_url = f"{request.host_url.rstrip('/')}/{folder}/{image_filename}"
        
        print(f"Generated URL: {image_url}")
        print(f"Direct URL: {direct_url}")
        
        # Return both formats of the URL
        return jsonify({
            'success': True,
            'message': 'Image generated successfully',
            'image_url': image_url,
            'direct_url': direct_url,
            'filename': image_filename,
            'folder': folder
        })
    
    except Exception as e:
        print(f"Error in API generate: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve generated images"""
    print(f"Serving image: {filename}")
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/test_assets/<path:filename>')
def serve_test_asset(filename):
    """Serve test assets"""
    print(f"Serving test asset: {filename}")
    return send_from_directory(app.config['TEST_ASSETS'], filename)

@app.route('/processed_images/<path:filename>')
def serve_processed_image(filename):
    """Serve processed images"""
    print(f"Serving processed image: {filename}")
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename)

@app.route('/processed_videos/<path:filename>')
def serve_processed_video(filename):
    """Serve processed videos"""
    print(f"Serving processed video: {filename}")
    return send_from_directory(app.config['PROCESSED_VIDEOS_FOLDER'], filename)

@app.route('/img2img', methods=['POST'])
@token_required
def img2img_transform():

    """Transform an image based on text prompt and uploaded image"""
    # Turnstile verification
    turnstile_token = request.form.get('cf_turnstile_response')
    print("Received Turnstile token from client:", turnstile_token)

    client_ip = request.headers.get("CF-Connecting-IP")
    if not verify_turnstile(turnstile_token, client_ip):
        return jsonify({'error': 'The provided Turnstile token was not valid!'}), 403
    
    
    # Honeypot field check (should be empty)
    honeypot = request.form.get('website', '')
    if honeypot:
        app.logger.warning(f"Honeypot triggered from IP: {get_remote_address()}")
        return jsonify({'error': 'Invalid request detected.'}), 400
    
    # IMPORTANT: Base64 images are not handled by Flask's request.files
    # They must be extracted from request.form
    
    # Get the prompt from the form
    prompt = request.form.get('video_description')

    print(f"Received prompt Image to Image: {prompt}")
    
    # Translate the prompt to English
    prompt = translate_to_english(prompt)
    
    # Get advanced options
    negative_prompt = request.form.get('negative_prompt', '')
    style_preset = request.form.get('style_preset', None)
    if style_preset == '':
        style_preset = None
    
    # Get strength (how much to transform the image)
    try:
        strength = float(request.form.get('strength', 0.75))
        # Make sure strength is between 0 and 1
        strength = max(0.1, min(1.0, strength))
    except (ValueError, TypeError):
        strength = 0.75
    
    # Get seed (0 means random)
    try:
        seed = int(request.form.get('seed', 0))
    except (ValueError, TypeError):
        seed = 0
    
    # Check if we got a base64 image string
    base64_data = request.form.get('image_data')
    
    if not base64_data and 'image_file' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    if not prompt:
        return jsonify({'error': 'Text prompt is required'}), 400
    
    try:
        # Process the image data
        if base64_data:
            # We already have the base64 data
            # But need to save it temporarily to a file
            # Remove data URL prefix if present
            if 'base64,' in base64_data:
                base64_data = base64_data.split('base64,')[1]
            
            image_data = base64.b64decode(base64_data)
            
            # Create a temporary file for the uploaded image
            temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_upload_{str(uuid.uuid4())}.png')
            
            with open(temp_image_path, 'wb') as f:
                f.write(image_data)
        else:
            # Get the uploaded file from the form
            file = request.files['image_file']
            
            # Create a temporary file for the uploaded image
            temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], f'temp_upload_{str(uuid.uuid4())}.png')
            
            # Save the file
            file.save(temp_image_path)
        
        # Now transform the saved image using img2img
        # First, get result from the img2img function
        aspect_ratio = "1:1"  # Default aspect ratio
        output_format = "png"  # Default output format
        
        transformed_image_data, result_info = img2img(
            api_key=None,  # Will get from database
            prompt=prompt,
            image_path=temp_image_path,
            negative_prompt=negative_prompt,
            strength=strength,
            seed=seed,
            style_preset=style_preset,
            aspect_ratio=aspect_ratio,
            output_format=output_format
        )
        
        # Create safe filename from prompt
        safe_prompt = ''.join(c if c.isalnum() else '_' for c in prompt)[:25]
        output_filename = f"img2img_{safe_prompt}_{result_info['seed']}.png"
        
        # Save to processed_images folder
        output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)
        
        # Save the image using save_image function
        save_image(transformed_image_data, output_path, result_info['seed'])
        
        # Clean up temp file
        try:
            os.remove(temp_image_path)
        except:
            pass
        
        # Construct the URL that will be used in the frontend
        image_url = url_for('serve_processed_image', filename=output_filename)
        
        # Return success response with image URL
        return jsonify({
            'success': True,
            'message': 'Image transformed successfully',
            'image_path': image_url,
            'seed': result_info['seed']
        })
    
    except Exception as e:
        print(f"Error processing image upload: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/img2img', methods=['POST'])
@limiter.limit("3/minute")  # Apply rate limit: 3 requests per minute per IP
def api_img2img_transform():
    """API endpoint to transform an image"""
    # Check if file was uploaded
    if 'image' not in request.files:
        return jsonify({'error': 'Image file is required'}), 400
    
    file = request.files['image']
    
    # Get JSON data from form
    prompt = request.form.get('prompt')

    print(f"Received prompt for img2img API: {prompt}")
    
    # Translate the prompt to English
    prompt = translate_to_english(prompt)
    
    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    
    negative_prompt = request.form.get('negative_prompt', '')
    strength = float(request.form.get('strength', 0.7))
    
    # Get the new parameters
    style_preset = request.form.get('style_preset', None)
    if style_preset == '':
        style_preset = None
    
    aspect_ratio = request.form.get('aspect_ratio', '1:1')
    output_format = request.form.get('output_format', 'png')
    
    # Get seed (0 means random)
    try:
        seed = int(request.form.get('seed', 0))
    except ValueError:
        seed = 0
    
    # Validate the file
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        # Save the uploaded file temporarily
        temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_' + file.filename)
        file.save(temp_image_path)
        
        try:
            # Import the img2img function and StabilityApiKey
            from img2img_stability import img2img
            from models import StabilityApiKey
            
            # Get API key from the database (oldest available key)
            api_key_obj = StabilityApiKey.find_oldest_key()
            if not api_key_obj:
                return jsonify({'error': 'No Stability AI API keys available. Please add keys to the database.'}), 500
                
            stability_api_key = api_key_obj.api_key
            
            # Perform the image transformation
            image_data, result_info = img2img(
                api_key=stability_api_key,
                prompt=prompt,
                image_path=temp_image_path,
                negative_prompt=negative_prompt,
                strength=strength,
                aspect_ratio=aspect_ratio,
                seed=seed,
                style_preset=style_preset,
                output_format=output_format
            )
            
            # Generate output filename
            safe_prompt = ''.join(c if c.isalnum() else '_' for c in prompt)[:25]
            output_filename = f"img2img_{safe_prompt}_{result_info['seed']}.{output_format}"
            output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)
            
            # Save the generated image
            save_image(image_data, output_path, result_info['seed'])
            
            # Clean up the temporary file
            os.remove(temp_image_path)
            
            # Return the image URL and success message
            return jsonify({
                'success': True,
                'message': 'Image transformed successfully',
                'image_url': url_for('serve_processed_image', filename=output_filename, _external=True),
                'seed': result_info['seed']
            })
            
        except Exception as e:
            # Clean up temporary file in case of error
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Invalid file'}), 400

@app.route('/api/enhance-prompt-ui', methods=['POST'])
@token_required
def enhance_prompt():

    """API endpoint to enhance the given image prompt with AI"""
    try:
        print("Enhance prompt endpoint called")
        print(f"Content type: {request.content_type}")
        print(f"Form data: {request.form}")
        
        # Check if the request has form data or JSON
        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json()
            if not data or 'prompt' not in data:
                return jsonify({'error': 'Prompt is required'}), 400
            user_prompt = data['prompt']
            print(f"JSON data received: {data}")
        else:
            # Handle form data
            user_prompt = request.form.get('prompt')
            if not user_prompt:
                return jsonify({'error': 'Prompt is required'}), 400
            print(f"Form data prompt: {user_prompt}")
        
        # The prompt to send to the Gemini API
        system_prompt = f"""You are an expert prompt engineer for AI image generation. Enhance the following image description to create a visually stunning AI-generated image. 
        
        User's original prompt: "{user_prompt}"
        
        Improve this prompt by:
        1. Adding specific details about visual elements
        2. Suggesting an artistic style if none is specified
        3. Including composition details (lighting, perspective, framing)
        4. Specifying mood or atmosphere
        5. Adding any relevant technical aspects (like photo-realistic, cinematic, etc.)
        
        Keep your enhanced prompt focused on the same subject/theme the user wanted, but make it much more detailed for better results.
        
        Provide only the enhanced prompt, without explanations or formatting.
        """
        
        # Call Gemini API to enhance the prompt
        from gemini_generator import generate_gemini
        print("Calling Gemini API")
        enhanced_prompt = generate_gemini(system_prompt, GEMINI_API_KEY)
        print(f"Enhanced prompt: {enhanced_prompt[:100]}...")
        
        # Return the enhanced prompt
        return jsonify({
            'success': True,
            'enhanced_prompt': enhanced_prompt
        })
    except Exception as e:
        import traceback
        print(f"Error in enhance_prompt: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/validate-token', methods=['POST'])
def validate_token():
    """Validate a Firebase ID token"""
    try:
        if not request.json:
            return jsonify({'valid': False, 'error': 'Invalid request format'}), 400
            
        # Check for token in different possible formats
        token = None
        if 'token' in request.json:
            token = request.json['token']
        elif 'idToken' in request.json:
            token = request.json['idToken']
            
        if not token:
            return jsonify({'valid': False, 'error': 'No token provided'}), 400
        
        try:
            # Try to verify the token with Firebase
            decoded_token = firebase_admin_auth.verify_id_token(token)
            
            # Token is valid, get user info
            uid = decoded_token['uid']
            
            # Check if user exists in database
            user = User.find_by_firebase_uid(uid)
            if user:
                # User exists, token is valid
                return jsonify({
                    'valid': True, 
                    'uid': uid,
                    'email': user.email if hasattr(user, 'email') else None
                })
            else:
                # Token is valid but user doesn't exist in our database
                # This is unusual but might happen if the database is out of sync
                # Let's create the user record from Firebase
                try:
                    firebase_user = firebase_admin_auth.get_user(uid)
                    
                    # Create user record
                    user_data = {
                        'uid': uid,
                        'email': firebase_user.email,
                        'displayName': firebase_user.display_name,
                        'emailVerified': firebase_user.email_verified
                    }
                    
                    user_obj = User.create_or_update_from_firebase(user_data)
                    if user_obj:
                        return jsonify({
                            'valid': True, 
                            'uid': uid,
                            'email': firebase_user.email
                        })
                    else:
                        return jsonify({'valid': False, 'error': 'Failed to create user record'}), 500
                except Exception as user_error:
                    print(f"Error creating user from token: {user_error}")
                    # Still consider the token valid even if we couldn't create the user
                    return jsonify({'valid': True, 'uid': uid})
                
        except Exception as e:
            print(f"Token validation error: {e}")
            return jsonify({'valid': False, 'error': 'Invalid token'})
    except Exception as e:
        print(f"Validate token error: {e}")
        return jsonify({'valid': False, 'error': str(e)})

@app.route('/ads.txt')
def serve_ads_txt():
    """Serve the ads.txt file"""
    return send_from_directory('static', 'ads.txt')

@app.route('/robots.txt')
def serve_robots_txt():
    """Serve the robots.txt file"""
    return send_from_directory('static', 'robots.txt')

@app.route('/test-processed-folder')
def test_processed_folder():
    """Test endpoint to check if the processed_images folder is accessible"""
    processed_dir = app.config['PROCESSED_FOLDER']
    absolute_path = os.path.abspath(processed_dir)
    
    # Create a simple test file
    test_file = "test_access.txt"
    test_path = os.path.join(processed_dir, test_file)
    
    try:
        # Write a test file
        with open(test_path, 'w') as f:
            f.write("This is a test file to check folder access")
        
        # Check if the file was created
        file_exists = os.path.exists(test_path)
        
        # List all files in the directory
        dir_contents = os.listdir(processed_dir)
        
        # Return diagnostic information
        return jsonify({
            'success': file_exists,
            'processed_dir': processed_dir,
            'absolute_path': absolute_path,
            'file_created': file_exists,
            'url_path': f'/{processed_dir}/{test_file}',
            'dir_contents': dir_contents,
            'test_access_url': url_for('serve_processed_image', filename=test_file, _external=True)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'processed_dir': processed_dir,
            'absolute_path': absolute_path
        }), 500

@app.route('/api-docs')
def api_docs():
    """Render the API documentation page"""
    return render_template('api.html', 
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))

@app.route('/donate')
def donate():
    """Render the donation page"""
    return render_template('donate.html',
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))

@app.route('/img2video-ui', methods=['POST'])
@token_required
def img2video_generate():
    """API endpoint to generate a video from an image"""
    # Turnstile verification
    turnstile_token = request.form.get('cf_turnstile_response')
    print("Received Turnstile token from client:", turnstile_token)

    client_ip = request.headers.get("CF-Connecting-IP")
    if not verify_turnstile(turnstile_token, client_ip):
        return jsonify({'error': 'The provided Turnstile token was not valid!'}), 403
        
    temp_image_path = None # Initialize temp_image_path here for cleanup in outer except

    try:
        # Check if a video generation is already in progress for this session
        active_gen_info = session.get('active_video_generation_id')
        if active_gen_info:
            # Check if the active generation is stale (e.g., older than 10 minutes)
            generation_timestamp = active_gen_info.get('timestamp')
            if generation_timestamp and (datetime.utcnow() - generation_timestamp) > timedelta(minutes=30): # Increased timeout to 30 minutes
                print("Stale video generation detected, clearing session.")
                session.pop('active_video_generation_id', None)
            else:
                return jsonify({
                    'error': 'A video is already being generated. Please wait for the current request to complete before starting a new one.',
                    'error_type': 'generation_in_progress'
                }), 409 # Conflict status code
            
        # Check if file was uploaded
        if 'image' not in request.files:
            return jsonify({'error': 'Image file is required'}), 400
        
        file = request.files['image']
        
        # Validate the file
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        # Additional file validation
        allowed_extensions = {'jpg', 'jpeg', 'png'}
        
        file_ext = ''
        if '.' in file.filename:
            file_ext = file.filename.rsplit('.', 1)[1].lower()
            
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'File format not supported. Please use JPG or PNG images. Received: {file_ext}'}), 400
        
        # Get parameters from form
        try:
            seed = int(request.form.get('seed', 0))
        except ValueError:
            seed = 0
        
        try:
            cfg_scale = float(request.form.get('cfg_scale', 1.5))
            if cfg_scale < 0 or cfg_scale > 10:
                return jsonify({'error': 'cfg_scale must be between 0 and 10'}), 400
        except ValueError:
            cfg_scale = 1.5
        
        try:
            motion_bucket_id = int(request.form.get('motion_bucket_id', 127))
            if motion_bucket_id < 1 or motion_bucket_id > 255:
                return jsonify({'error': 'motion_bucket_id must be between 1 and 255'}), 400
        except ValueError:
            motion_bucket_id = 127
        
        # Create processed_videos directory if it doesn't exist
        if not os.path.exists(app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos')):
            os.makedirs(app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos'), exist_ok=True)
        
        # Create a safe filename
        safe_filename = f"temp_{uuid.uuid4().hex}.{file_ext}"
        temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        
        # Save the file
        file.save(temp_image_path)
        
        # Validate the image can be opened
        from PIL import Image
        with Image.open(temp_image_path) as img:
            # Just checking it can be opened
            img_width, img_height = img.size
            print(f"Received image with dimensions: {img_width}x{img_height}")
        
        # Import the img2video function
        from img2video_stability import img2video, get_api_key
        
        # Get API key from the database (oldest available key)
        api_key = get_api_key()
        if not api_key:
            return jsonify({'error': 'No Stability AI API keys available. Please add keys to the database.'}), 500
        
        # Start the video generation
        generation_id, dimensions, api_key = img2video(
            api_key=api_key,
            image_path=temp_image_path,
            seed=seed,
            cfg_scale=cfg_scale,
            motion_bucket_id=motion_bucket_id
        )
        
        # Store dimensions in session for later retrieval
        session[f'img2video_dimensions_{generation_id}'] = dimensions
        # Store API key in session for later use (polling)
        session[f'img2video_api_key_{generation_id}'] = api_key
        # Set the active generation ID in session with a timestamp
        session['active_video_generation_id'] = {
            'id': generation_id,
            'timestamp': datetime.utcnow()
        }
        
        # Clean up the temporary file
        os.remove(temp_image_path)
        
        # Return the generation ID to poll for results
        return jsonify({
            'success': True,
            'id': generation_id,
            'message': f'Video generation started. Image automatically resized to {dimensions}. Poll for results using the returned ID.',
            'dimensions': dimensions
        })
            
    except Exception as e: # Main except block for the entire function
        # Clean up temporary file if it exists
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
        
        # Clear the active generation ID from session on any error
        if 'active_video_generation_id' in session:
            session.pop('active_video_generation_id', None)
        
        error_str = str(e)
        print(f"Error in image-to-video generation: {error_str}")
        if "402" in error_str and "credits" in error_str.lower():
            return jsonify({
                'error': 'Insufficient credits on all available API keys. Please add a new API key with sufficient credits.',
                'error_type': 'payment_required'
            }), 402
        else:
            return jsonify({'error': error_str}), 500


@app.route('/ui/img2video/result/<generation_id>', methods=['GET'])
@limiter.exempt
def img2video_result(generation_id):

    """API endpoint to check the status of a video generation or retrieve the result"""
    try:
        # Import necessary functions
        from img2video_stability import get_video_result, save_video, get_api_key
        
        # Try to get the API key from session (stored from previous request)
        api_key = session.get(f'img2video_api_key_{generation_id}')
        
        # If not in session, get a fresh key
        if not api_key:
            api_key = get_api_key()
            if not api_key:
                return jsonify({'error': 'No Stability AI API keys available. Please add keys to the database.'}), 500
        
        try:
            # Check the status of the generation
            result = get_video_result(api_key=api_key, generation_id=generation_id)
            
            if result['status'] == 'in-progress':
                # Return 202 Accepted status for in-progress generations
                return jsonify({
                    'status': 'in-progress',
                    'message': 'Video generation is still in progress. Try again in a few seconds.'
                }), 202
            
            # If complete, determine if we should return the video directly or save it
            # Default behavior: save the video and return its URL
            
            # Process the video for storage/return
            videos_folder = app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos')
            
            # Create folder if it doesn't exist
            if not os.path.exists(videos_folder):
                os.makedirs(videos_folder, exist_ok=True)
            
            # Try to get the dimensions from session or use a default
            dimensions = session.get(f'img2video_dimensions_{generation_id}', None)
            
            # Save the video with a prefix based on the generation ID
            video_path = save_video(
                video_data=result['video'],
                output_directory=videos_folder,
                filename_prefix=f"video_{generation_id[:8]}",
                seed=result.get('seed')
            )
            
            # Get just the filename for the URL
            video_filename = os.path.basename(video_path)
            
            # Clean up session data as we no longer need it
            if f'img2video_dimensions_{generation_id}' in session:
                session.pop(f'img2video_dimensions_{generation_id}')
            if f'img2video_api_key_{generation_id}' in session:
                session.pop(f'img2video_api_key_{generation_id}')
            
            # Clear the active generation ID from session on successful completion
            active_gen_info = session.get('active_video_generation_id')
            if isinstance(active_gen_info, dict) and active_gen_info.get('id') == generation_id:
                session.pop('active_video_generation_id')
            elif active_gen_info == generation_id: # For old format
                session.pop('active_video_generation_id')

            # Return the success response with the video URL
            return jsonify({
                'status': 'complete',
                'video_url': url_for('serve_processed_video', filename=video_filename),
                'finish_reason': result.get('finish_reason', 'SUCCESS'),
                'seed': result.get('seed', 'unknown'),
                'dimensions': dimensions
            }), 200
        except Exception as e:
            error_str = str(e)
            # Clear the active generation ID from session on any error during result retrieval
            active_gen_info = session.get('active_video_generation_id')
            if isinstance(active_gen_info, dict) and active_gen_info.get('id') == generation_id:
                session.pop('active_video_generation_id', None)
            elif active_gen_info == generation_id: # For old format
                session.pop('active_video_generation_id', None)

            if "402" in error_str and "credits" in error_str.lower():
                # Try with a new API key
                new_api_key = get_api_key()
                if new_api_key:
                    # Store new key in session
                    session[f'img2video_api_key_{generation_id}'] = new_api_key
                    return jsonify({
                        'status': 'retry',
                        'message': 'API key refreshed due to insufficient credits. Please try again.'
                    }), 200
                else:
                    return jsonify({
                        'error': 'Insufficient credits on all available API keys. Please add a new API key with sufficient credits.',
                        'error_type': 'payment_required',
                        'status': 'error'
                    }), 402
            else:
                raise e
        
    except Exception as e:
        print(f"Error checking image-to-video status: {str(e)}")
        # Clear the active generation ID from session on unexpected errors
        active_gen_info = session.get('active_video_generation_id')
        if isinstance(active_gen_info, dict) and active_gen_info.get('id') == generation_id:
            session.pop('active_video_generation_id', None)
        elif active_gen_info == generation_id: # For old format
            session.pop('active_video_generation_id', None)
        return jsonify({'error': str(e), 'status': 'error'}), 500



@app.route('/api/img2video', methods=['POST'])
@limiter.limit("500/day")  # Apply rate limit: 500 requests per day per IP for UI users
def api_img2video_generate():
    """API endpoint to generate a video from an image"""
    temp_image_path = None # Initialize temp_image_path here for cleanup in outer except

    try:
        # Check if a video generation is already in progress for this session
        active_gen_info = session.get('active_video_generation_id')
        if active_gen_info:
            # Check if the active generation is stale (e.g., older than 10 minutes)
            generation_timestamp = active_gen_info.get('timestamp')
            if generation_timestamp and (datetime.utcnow() - generation_timestamp) > timedelta(minutes=30): # Increased timeout to 30 minutes
                print("Stale video generation detected, clearing session.")
                session.pop('active_video_generation_id', None)
            else:
                return jsonify({
                    'error': 'A video is already being generated. Please wait for the current request to complete before starting a new one.',
                    'error_type': 'generation_in_progress'
                }), 409 # Conflict status code
            
        # Check if file was uploaded
        if 'image' not in request.files:
            return jsonify({'error': 'Image file is required'}), 400
        
        file = request.files['image']
        
        # Validate the file
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        
        # Additional file validation
        allowed_extensions = {'jpg', 'jpeg', 'png'}
        
        file_ext = ''
        if '.' in file.filename:
            file_ext = file.filename.rsplit('.', 1)[1].lower()
            
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'File format not supported. Please use JPG or PNG images. Received: {file_ext}'}), 400
        
        # Get parameters from form
        try:
            seed = int(request.form.get('seed', 0))
        except ValueError:
            seed = 0
        
        try:
            cfg_scale = float(request.form.get('cfg_scale', 1.5))
            if cfg_scale < 0 or cfg_scale > 10:
                return jsonify({'error': 'cfg_scale must be between 0 and 10'}), 400
        except ValueError:
            cfg_scale = 1.5
        
        try:
            motion_bucket_id = int(request.form.get('motion_bucket_id', 127))
            if motion_bucket_id < 1 or motion_bucket_id > 255:
                return jsonify({'error': 'motion_bucket_id must be between 1 and 255'}), 400
        except ValueError:
            motion_bucket_id = 127
        
        # Create processed_videos directory if it doesn't exist
        if not os.path.exists(app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos')):
            os.makedirs(app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos'), exist_ok=True)
        
        # Create a safe filename
        safe_filename = f"temp_{uuid.uuid4().hex}.{file_ext}"
        temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        
        # Save the file
        file.save(temp_image_path)
        
        # Validate the image can be opened
        from PIL import Image
        with Image.open(temp_image_path) as img:
            # Just checking it can be opened
            img_width, img_height = img.size
            print(f"Received image with dimensions: {img_width}x{img_height}")
        
        # Import the img2video function
        from img2video_stability import img2video, get_api_key
        
        # Get API key from the database (oldest available key)
        api_key = get_api_key()
        if not api_key:
            return jsonify({'error': 'No Stability AI API keys available. Please add keys to the database.'}), 500
        
        # Start the video generation
        generation_id, dimensions, api_key = img2video(
            api_key=api_key,
            image_path=temp_image_path,
            seed=seed,
            cfg_scale=cfg_scale,
            motion_bucket_id=motion_bucket_id
        )
        
        # Store dimensions in session for later retrieval
        session[f'img2video_dimensions_{generation_id}'] = dimensions
        # Store API key in session for later use (polling)
        session[f'img2video_api_key_{generation_id}'] = api_key
        # Set the active generation ID in session with a timestamp
        session['active_video_generation_id'] = {
            'id': generation_id,
            'timestamp': datetime.utcnow()
        }
        
        # Clean up the temporary file
        os.remove(temp_image_path)
        
        # Return the generation ID to poll for results
        return jsonify({
            'success': True,
            'id': generation_id,
            'message': f'Video generation started. Image automatically resized to {dimensions}. Poll for results using the returned ID.',
            'dimensions': dimensions
        })
            
    except Exception as e: # Main except block for the entire function
        # Clean up temporary file if it exists
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
        
        # Clear the active generation ID from session on any error
        if 'active_video_generation_id' in session:
            session.pop('active_video_generation_id', None)
        
        error_str = str(e)
        print(f"Unexpected error in image-to-video API: {error_str}")
        if "402" in error_str and "credits" in error_str.lower():
            return jsonify({
                'error': 'Insufficient credits on all available API keys. Please add a new API key with sufficient credits.',
                'error_type': 'payment_required'
            }), 402
        else:
            return jsonify({'error': f"An unexpected error occurred: {error_str}"}), 500

@app.route('/api/img2video/result/<generation_id>', methods=['GET'])
@limiter.exempt
def api_img2video_result(generation_id):
    """API endpoint to check the status of a video generation or retrieve the result"""
    try:
        # Import necessary functions
        from img2video_stability import get_video_result, save_video, get_api_key
        
        # Try to get the API key from session (stored from previous request)
        api_key = session.get(f'img2video_api_key_{generation_id}')
        
        # If not in session, get a fresh key
        if not api_key:
            api_key = get_api_key()
            if not api_key:
                return jsonify({'error': 'No Stability AI API keys available. Please add keys to the database.'}), 500
        
        try:
            # Check the status of the generation
            result = get_video_result(api_key=api_key, generation_id=generation_id)
            
            if result['status'] == 'in-progress':
                # Return 202 Accepted status for in-progress generations
                return jsonify({
                    'status': 'in-progress',
                    'message': 'Video generation is still in progress. Try again in a few seconds.'
                }), 202
            
            # If complete, determine if we should return the video directly or save it
            # Default behavior: save the video and return its URL
            
            # Process the video for storage/return
            videos_folder = app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos')
            
            # Create folder if it doesn't exist
            if not os.path.exists(videos_folder):
                os.makedirs(videos_folder, exist_ok=True)
            
            # Try to get the dimensions from session or use a default
            dimensions = session.get(f'img2video_dimensions_{generation_id}', None)
            
            # Save the video with a prefix based on the generation ID
            video_path = save_video(
                video_data=result['video'],
                output_directory=videos_folder,
                filename_prefix=f"video_{generation_id[:8]}",
                seed=result.get('seed')
            )
            
            # Get just the filename for the URL
            video_filename = os.path.basename(video_path)
            
            # Clean up session data as we no longer need it
            if f'img2video_dimensions_{generation_id}' in session:
                session.pop(f'img2video_dimensions_{generation_id}')
            if f'img2video_api_key_{generation_id}' in session:
                session.pop(f'img2video_api_key_{generation_id}')
            
            # Clear the active generation ID from session on successful completion
            active_gen_info = session.get('active_video_generation_id')
            if isinstance(active_gen_info, dict) and active_gen_info.get('id') == generation_id:
                session.pop('active_video_generation_id')
            elif active_gen_info == generation_id: # For old format
                session.pop('active_video_generation_id')

            # Return the success response with the video URL
            return jsonify({
                'status': 'complete',
                'video_url': url_for('serve_processed_video', filename=video_filename),
                'finish_reason': result.get('finish_reason', 'SUCCESS'),
                'seed': result.get('seed', 'unknown'),
                'dimensions': dimensions
            }), 200
        except Exception as e:
            error_str = str(e)
            if "402" in error_str and "credits" in error_str.lower():
                    # Try with a new API key
                    new_api_key = get_api_key()
                    if new_api_key:
                        # Store new key in session
                        session[f'img2video_api_key_{generation_id}'] = new_api_key
                        return jsonify({
                            'status': 'retry',
                            'message': 'API key refreshed due to insufficient credits. Please try again.'
                        }), 200
                    else:
                        # Clear the active generation ID from session on final error (402)
                        active_gen_info = session.get('active_video_generation_id')
                        if isinstance(active_gen_info, dict) and active_gen_info.get('id') == generation_id:
                            session.pop('active_video_generation_id')
                        elif active_gen_info == generation_id: # For old format
                            session.pop('active_video_generation_id')
                        return jsonify({
                            'error': 'Insufficient credits on all available API keys. Please add a new API key with sufficient credits.',
                            'error_type': 'payment_required',
                            'status': 'error'
                        }), 402
            else:
                # Clear the active generation ID from session on other errors
                active_gen_info = session.get('active_video_generation_id')
                if isinstance(active_gen_info, dict) and active_gen_info.get('id') == generation_id:
                    session.pop('active_video_generation_id')
                elif active_gen_info == generation_id: # For old format
                    session.pop('active_video_generation_id')
                raise e
        
    except Exception as e:
        print(f"Error checking image-to-video status: {str(e)}")
        # Clear the active generation ID from session on unexpected errors
        active_gen_info = session.get('active_video_generation_id')
        if isinstance(active_gen_info, dict) and active_gen_info.get('id') == generation_id:
            session.pop('active_video_generation_id')
        elif active_gen_info == generation_id: # For old format
            session.pop('active_video_generation_id')
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/text-to-video')
def qwen_video_page():
    """Render the Qwen video generation page"""
    return render_template('text-to-video.html',
                          user=current_user,
                          firebase_api_key=firebase_config.get('apiKey'),
                          firebase_auth_domain=firebase_config.get('authDomain'),
                          firebase_project_id=firebase_config.get('projectId'),
                          firebase_app_id=firebase_config.get('appId'))


def process_qwen_video_task(app, task_id):
    """
    This function runs in a background thread to generate a video.
    It will wait for an available key before processing.
    """
    with app.app_context():
        logger = app.logger
        logger.info(f"Thread for VideoTask {task_id}: Starting.")
        
        assigned_key = None
        try:
            # Loop until a key is available
            while assigned_key is None:
                assigned_key = QwenApiKey.find_available_key()
                if assigned_key is None:
                    logger.info(f"Thread for {task_id}: No available Qwen keys. Waiting...")
                    time.sleep(30) # Wait for 30 seconds before retrying

            logger.info(f"Thread for {task_id}: Key {assigned_key['_id']} acquired. Processing.")
            
            VideoTask.update(task_id, status='processing', assigned_key_id=str(assigned_key['_id']))
            
            task_doc = VideoTask.get_by_id(task_id)
            if not task_doc:
                raise ValueError("VideoTask document not found.")

            result = generate_qwen_video(prompt=task_doc['prompt'], api_key=assigned_key)

            if 'error' in result:
                 raise Exception(result['error'])

            logger.info(f"Thread for {task_id}: Video generation successful. URL: {result['video_url']}")
            
            # Create proxy mapping for the video URL
            proxy_url = None
            try:
                url_mapping = VideoUrlMapping()
                proxy_id = url_mapping.create_mapping(result['video_url'], task_id)
                proxy_url = f"/video/{proxy_id}"
                logger.info(f"Thread for {task_id}: Created proxy URL: {proxy_url}")
                
                # Update task with both original URL and proxy URL
                VideoTask.update(task_id, status='completed', result_url=result['video_url'], proxy_url=proxy_url)
            except Exception as proxy_error:
                logger.error(f"Thread for {task_id}: Failed to create proxy mapping: {proxy_error}")
                # Still mark as completed but without proxy URL
                VideoTask.update(task_id, status='completed', result_url=result['video_url'])

            # Update user generation history with result URLs
            try:
                history = UserGenerationHistory()
                history.update_generation_urls(
                    task_id=task_id,
                    result_url=result['video_url'],
                    proxy_url=proxy_url
                )
                logger.info(f"Thread for {task_id}: Updated generation history with URLs")
            except Exception as history_error:
                logger.warning(f"Thread for {task_id}: Failed to update generation history: {history_error}")

        except Exception as e:
            logger.error(f"Thread for {task_id} failed: {e}", exc_info=True)
            VideoTask.update(task_id, status='failed', error_message=str(e))
            
        finally:
            if assigned_key:
                QwenApiKey.mark_key_available(assigned_key['_id'])
                logger.info(f"Thread for {task_id}: Key {assigned_key['_id']} released.")

@app.route('/generate-text-to-video-ui', methods=['POST'])
@token_required
def generate_qwen_video_route():
    """
    API endpoint to queue a video generation task using a background thread.
    """
    data = request.get_json()
    prompt = data.get('prompt')
    turnstile_token = data.get('cf_turnstile_response')
    
    # Verify Turnstile token
    client_ip = request.headers.get("CF-Connecting-IP")
    if not verify_turnstile(turnstile_token, client_ip):
        return jsonify({'error': 'The provided Turnstile token was not valid!'}), 403

    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400

    task = VideoTask.create(prompt=prompt)
    if not task:
        return jsonify({'error': 'Failed to create video task in database.'}), 500

    # Save generation to user history
    try:
        history = UserGenerationHistory()
        user_id = None
        session_id = None
        
        # Get user identification from token
        token_data = getattr(g, 'token_data', {})
        if token_data.get('anonymous'):
            session_id = token_data.get('user_id')  # For anonymous users, user_id is actually session_id
        else:
            user_id = token_data.get('user_id')
        
        history.save_generation(
            user_id=user_id,
            session_id=session_id,
            generation_type='text-to-video',
            prompt=prompt,
            task_id=task['task_id']
        )
    except Exception as e:
        app.logger.warning(f"Failed to save generation to history: {e}")

    # Start the video generation in a background thread
    thread = threading.Thread(target=process_qwen_video_task, args=(app, task['task_id']))
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': 'Your video request has been queued. You can check the status using the task ID.',
        'task_id': task['task_id']
    }), 202

@app.route('/api/user-generations', methods=['GET'])
@token_required
def get_user_generations():
    """API endpoint to get user's generation history"""
    try:
        # Get query parameters
        generation_type = request.args.get('type', 'text-to-video')
        limit = min(int(request.args.get('limit', 20)), 50)  # Max 50 items
        skip = int(request.args.get('skip', 0))
        
        # Get user identification from token
        token_data = getattr(g, 'token_data', {})
        user_id = None
        session_id = None
        
        if token_data.get('anonymous'):
            session_id = token_data.get('user_id')  # For anonymous users
        else:
            user_id = token_data.get('user_id')
        
        if not user_id and not session_id:
            return jsonify({'error': 'User identification not found'}), 400
        
        # Get user's generation history
        history = UserGenerationHistory()
        generations = history.get_user_generations(
            user_id=user_id,
            session_id=session_id,
            generation_type=generation_type,
            limit=limit,
            skip=skip
        )
        
        # Get total count for pagination
        total_count = history.count_user_generations(
            user_id=user_id,
            session_id=session_id,
            generation_type=generation_type
        )
        
        return jsonify({
            'success': True,
            'generations': generations,
            'total_count': total_count,
            'limit': limit,
            'skip': skip,
            'has_more': (skip + limit) < total_count
        })
        
    except Exception as e:
        app.logger.error(f"Error retrieving user generations: {e}")
        return jsonify({'error': 'Failed to retrieve generation history'}), 500

@app.route('/api/user-generations/<string:generation_id>', methods=['GET'])
@token_required
def get_user_generation_by_id(generation_id):
    """API endpoint to get a specific generation by ID"""
    try:
        history = UserGenerationHistory()
        generation = history.get_generation_by_id(generation_id)
        
        if not generation:
            return jsonify({'error': 'Generation not found'}), 404
        
        # Verify ownership - check if the generation belongs to the current user
        token_data = getattr(g, 'token_data', {})
        user_id = None
        session_id = None
        
        if token_data.get('anonymous'):
            session_id = token_data.get('user_id')
        else:
            user_id = token_data.get('user_id')
        
        # Check ownership
        if (generation.get('user_id') != user_id and 
            generation.get('session_id') != session_id):
            return jsonify({'error': 'Access denied'}), 403
        
        return jsonify({
            'success': True,
            'generation': generation
        })
        
    except Exception as e:
        app.logger.error(f"Error retrieving generation by ID: {e}")
        return jsonify({'error': 'Failed to retrieve generation'}), 500

@app.route('/generate-text-to-video-ui/status/<string:task_id>', methods=['GET'])
@limiter.exempt
def get_qwen_video_status(task_id):
    """
    API endpoint to check the status of a Qwen video generation task.
    """
    task = VideoTask.get_by_id(task_id)

    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # Return proxy URL if available, otherwise fall back to result_url
    video_url = task.get('proxy_url') or task.get('result_url')
    
    response = {
        'task_id': task['task_id'],
        'status': task['status'],
        'prompt': task['prompt'],
        'created_at': task['created_at'].isoformat() if task.get('created_at') else None,
        'updated_at': task['updated_at'].isoformat() if task.get('updated_at') else None,
        'result_url': video_url,
        'error_message': task.get('error_message')
    }
    
    return jsonify(response)


def log_video_proxy_access(proxy_id, client_ip, user_agent, status_code, error_message=None, response_time_ms=None, bytes_transferred=None):
    """
    Enhanced logging for video proxy access with performance monitoring.
    Logs detailed information without exposing sensitive data.
    """
    try:
        if db is None:
            return
        
        log_entry = {
            'proxy_id': proxy_id,
            'client_ip': client_ip,
            'user_agent': user_agent,
            'status_code': status_code,
            'timestamp': datetime.now(timezone.utc),
            'endpoint': 'video_proxy'
        }
        
        # Add performance metrics if provided
        if response_time_ms is not None:
            log_entry['response_time_ms'] = response_time_ms
        
        if bytes_transferred is not None:
            log_entry['bytes_transferred'] = bytes_transferred
        
        # Add error information without exposing sensitive details
        if error_message:
            # Sanitize error message to avoid exposing Qwen service details
            sanitized_error = sanitize_error_message(error_message)
            log_entry['error_message'] = sanitized_error
        
        # Add request context for monitoring
        log_entry['referer'] = request.headers.get('Referer', 'Direct')
        log_entry['range_request'] = bool(request.headers.get('Range'))
        
        # Store in video_proxy_logs collection
        db['video_proxy_logs'].insert_one(log_entry)
        
        # Update performance metrics
        update_proxy_performance_metrics(status_code, response_time_ms, error_message is not None)
        
    except Exception as e:
        app.logger.error(f"Error logging video proxy access: {e}")


def sanitize_error_message(error_message):
    """
    Sanitize error messages to remove sensitive information while preserving useful debugging info.
    Removes Qwen-specific details and URLs while keeping error types and codes.
    """
    if not error_message:
        return error_message
    
    # List of sensitive patterns to remove or replace
    sensitive_patterns = [
        (r'https?://[^/]*qwen[^/]*[^\s]*', '[UPSTREAM_URL]'),
        (r'https?://[^/]*alibaba[^/]*[^\s]*', '[UPSTREAM_URL]'),
        (r'qwen[a-zA-Z0-9\-\.]*', '[UPSTREAM_SERVICE]'),
        (r'alibaba[a-zA-Z0-9\-\.]*', '[UPSTREAM_SERVICE]'),
        (r'X-Request-Id: [^\s]+', 'X-Request-Id: [REDACTED]'),
        (r'X-Trace-Id: [^\s]+', 'X-Trace-Id: [REDACTED]'),
        (r'auth_token[^,\s]*', 'auth_token=[REDACTED]'),
        (r'api[_-]?key[^,\s]*', 'api_key=[REDACTED]')
    ]
    
    sanitized = error_message
    for pattern, replacement in sensitive_patterns:
        import re
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    
    return sanitized


def update_proxy_performance_metrics(status_code, response_time_ms, has_error):
    """
    Update performance metrics for monitoring proxy endpoint health.
    Tracks success rates, response times, and error patterns.
    """
    try:
        if db is None:
            return
        
        current_time = datetime.now(timezone.utc)
        
        # Create or update performance metrics document
        metrics_doc = {
            'timestamp': current_time,
            'status_code': status_code,
            'response_time_ms': response_time_ms,
            'has_error': has_error,
            'success': status_code < 400
        }
        
        # Store individual metric
        db['video_proxy_metrics'].insert_one(metrics_doc)
        
        # Update aggregated metrics (hourly summary)
        hour_key = current_time.replace(minute=0, second=0, microsecond=0)
        
        # Upsert hourly aggregated metrics
        db['video_proxy_hourly_metrics'].update_one(
            {'hour': hour_key},
            {
                '$inc': {
                    'total_requests': 1,
                    'success_count': 1 if status_code < 400 else 0,
                    'error_count': 1 if status_code >= 400 else 0,
                    f'status_{status_code}_count': 1
                },
                '$push': {
                    'response_times': response_time_ms
                } if response_time_ms is not None else {},
                '$setOnInsert': {
                    'hour': hour_key
                }
            },
            upsert=True
        )
        
    except Exception as e:
        app.logger.error(f"Error updating proxy performance metrics: {e}")


def check_video_proxy_health():
    """
    Comprehensive health check for video proxy functionality.
    Returns detailed health status including database connectivity,
    mapping service availability, and performance metrics.
    """
    health_status = {
        'database_connected': False,
        'mapping_service_available': False,
        'cleanup_thread_running': False,
        'total_active_mappings': 0,
        'error_rate_last_hour': 0,
        'avg_response_time_last_hour': 0,
        'last_successful_request': None,
        'qwen_session_healthy': False,
        'recent_errors': []
    }
    
    try:
        # Check database connectivity
        if db is not None:
            # Test database connection with a simple operation
            db.command('ismaster')
            health_status['database_connected'] = True
            
            # Check mapping service availability
            try:
                mapping = VideoUrlMapping()
                stats = mapping.get_storage_usage_stats()
                health_status['mapping_service_available'] = True
                health_status['total_active_mappings'] = stats.get('active_mappings', 0)
                
                # Check cleanup thread status
                cleanup_status = VideoUrlMapping.get_cleanup_status()
                health_status['cleanup_thread_running'] = cleanup_status.get('cleanup_running', False)
                
            except Exception as e:
                health_status['mapping_service_available'] = False
                health_status['mapping_service_error'] = str(e)
            
            # Get performance metrics for the last hour
            try:
                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                
                # Calculate error rate
                total_requests = db['video_proxy_logs'].count_documents({
                    'timestamp': {'$gte': one_hour_ago}
                })
                
                error_requests = db['video_proxy_logs'].count_documents({
                    'timestamp': {'$gte': one_hour_ago},
                    'status_code': {'$gte': 400}
                })
                
                if total_requests > 0:
                    health_status['error_rate_last_hour'] = (error_requests / total_requests) * 100
                
                # Calculate average response time
                response_times = list(db['video_proxy_logs'].find({
                    'timestamp': {'$gte': one_hour_ago},
                    'response_time_ms': {'$exists': True, '$ne': None}
                }, {'response_time_ms': 1}))
                
                if response_times:
                    avg_response_time = sum(log['response_time_ms'] for log in response_times) / len(response_times)
                    health_status['avg_response_time_last_hour'] = round(avg_response_time, 2)
                
                # Get last successful request timestamp
                last_success = db['video_proxy_logs'].find_one({
                    'status_code': {'$lt': 400}
                }, sort=[('timestamp', -1)])
                
                if last_success:
                    health_status['last_successful_request'] = last_success['timestamp'].isoformat()
                
                # Get recent errors (last 10)
                recent_errors = list(db['video_proxy_logs'].find({
                    'timestamp': {'$gte': one_hour_ago},
                    'status_code': {'$gte': 400}
                }, {
                    'timestamp': 1,
                    'status_code': 1,
                    'error_message': 1,
                    'proxy_id': 1
                }).sort('timestamp', -1).limit(10))
                
                # Format recent errors for response
                health_status['recent_errors'] = [
                    {
                        'timestamp': error['timestamp'].isoformat(),
                        'status_code': error['status_code'],
                        'error_message': error.get('error_message', 'Unknown error'),
                        'proxy_id': error.get('proxy_id', 'Unknown')[:8] + '...' if error.get('proxy_id') else 'Unknown'
                    }
                    for error in recent_errors
                ]
                
            except Exception as e:
                health_status['metrics_error'] = str(e)
        
        # Check Qwen session health
        try:
            # Test if the global qwen_session is properly configured
            if qwen_session and hasattr(qwen_session, 'adapters'):
                health_status['qwen_session_healthy'] = True
            else:
                health_status['qwen_session_healthy'] = False
                health_status['qwen_session_error'] = 'Session not properly initialized'
        except Exception as e:
            health_status['qwen_session_healthy'] = False
            health_status['qwen_session_error'] = str(e)
        
        return health_status
        
    except Exception as e:
        health_status['health_check_error'] = str(e)
        return health_status


def get_proxy_performance_stats(hours=24):
    """
    Get performance statistics for the video proxy endpoint.
    Returns success rates, average response times, and error patterns.
    """
    try:
        if db is None:
            return {'error': 'Database not available'}
        
        # Calculate time range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)
        
        # Aggregate metrics from hourly summaries
        pipeline = [
            {'$match': {'hour': {'$gte': start_time, '$lte': end_time}}},
            {'$group': {
                '_id': None,
                'total_requests': {'$sum': '$total_requests'},
                'success_count': {'$sum': '$success_count'},
                'error_count': {'$sum': '$error_count'},
                'all_response_times': {'$push': '$response_times'}
            }}
        ]
        
        result = list(db['video_proxy_hourly_metrics'].aggregate(pipeline))
        
        if not result:
            return {
                'total_requests': 0,
                'success_rate': 0,
                'error_rate': 0,
                'avg_response_time_ms': 0,
                'hours_analyzed': hours
            }
        
        stats = result[0]
        total_requests = stats.get('total_requests', 0)
        success_count = stats.get('success_count', 0)
        error_count = stats.get('error_count', 0)
        
        # Calculate response time statistics
        all_response_times = []
        for response_time_list in stats.get('all_response_times', []):
            if response_time_list:
                all_response_times.extend(response_time_list)
        
        avg_response_time = sum(all_response_times) / len(all_response_times) if all_response_times else 0
        
        # Get error breakdown by status code
        error_breakdown = {}
        error_pipeline = [
            {'$match': {'hour': {'$gte': start_time, '$lte': end_time}}},
            {'$project': {
                'status_codes': {
                    '$objectToArray': {
                        '$filter': {
                            'input': {'$objectToArray': '$$ROOT'},
                            'cond': {'$regexMatch': {'input': '$$this.k', 'regex': '^status_\\d+_count$'}}
                        }
                    }
                }
            }},
            {'$unwind': '$status_codes'},
            {'$group': {
                '_id': '$status_codes.k',
                'count': {'$sum': '$status_codes.v'}
            }}
        ]
        
        error_results = list(db['video_proxy_hourly_metrics'].aggregate(error_pipeline))
        for error_result in error_results:
            status_code = error_result['_id'].replace('status_', '').replace('_count', '')
            error_breakdown[f'status_{status_code}'] = error_result['count']
        
        return {
            'total_requests': total_requests,
            'success_count': success_count,
            'error_count': error_count,
            'success_rate': (success_count / total_requests * 100) if total_requests > 0 else 0,
            'error_rate': (error_count / total_requests * 100) if total_requests > 0 else 0,
            'avg_response_time_ms': round(avg_response_time, 2),
            'error_breakdown': error_breakdown,
            'hours_analyzed': hours
        }
        
    except Exception as e:
        app.logger.error(f"Error getting proxy performance stats: {e}")
        return {'error': str(e)}

@app.route('/video/<proxy_id>', methods=['GET'])
@limiter.limit("100 per minute")  # Rate limiting for video proxy endpoint
def video_proxy(proxy_id):
    """
    Enhanced video proxy endpoint with comprehensive error handling and monitoring.
    Streams video content from Qwen to the user while hiding original URLs.
    Includes performance monitoring, retry logic, and detailed logging.
    """
    client_ip = get_client_ip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    start_time = time.time()
    bytes_transferred = 0
    
    try:
        # Initialize the VideoUrlMapping service
        url_mapping = VideoUrlMapping()
        
        # Get the original Qwen URL from the proxy ID
        qwen_url = url_mapping.get_qwen_url(proxy_id)
        
        if not qwen_url:
            # Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Log access attempt for security monitoring
            log_video_proxy_access(proxy_id, client_ip, user_agent, 404, 
                                 "Proxy ID not found or expired", response_time_ms)
            
            # Return user-friendly error page for browser requests
            if 'text/html' in request.headers.get('Accept', ''):
                return render_template('video_error.html', 
                                     error_title='Video Not Found',
                                     error_message='The video you requested could not be found.',
                                     error_code='VIDEO_NOT_FOUND',
                                     help_text='The video may have expired. Please regenerate your video to get a new link.',
                                     retry_action='regenerate'), 404
            
            # Return JSON for API requests
            return jsonify({
                'error': 'Video not found',
                'code': 'VIDEO_NOT_FOUND',
                'help_text': 'The video may have expired. Please regenerate your video to get a new link.'
            }), 404
        
        # Handle range requests for video seeking
        range_header = request.headers.get('Range')
        headers = {}
        
        if range_header:
            # Parse range header (e.g., "bytes=0-1023")
            headers['Range'] = range_header
        
        # Enhanced retry logic for transient Qwen service errors
        max_retries = 3
        retry_delay = 1  # Start with 1 second delay
        last_exception = None
        response = None
        
        for attempt in range(max_retries + 1):
            try:
                # Use connection pooling session for Qwen service requests
                response = qwen_session.get(qwen_url, headers=headers, stream=True, timeout=30)
                break  # Success, exit retry loop
                
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exception = e
                
                if attempt < max_retries:
                    # Log retry attempt
                    app.logger.warning(f"Video proxy retry {attempt + 1}/{max_retries} for proxy {proxy_id}: {type(e).__name__}")
                    
                    # Exponential backoff with jitter
                    import random
                    jitter = random.uniform(0.1, 0.5)
                    sleep_time = retry_delay * (2 ** attempt) + jitter
                    time.sleep(sleep_time)
                    continue
                else:
                    # All retries exhausted, handle the exception
                    response_time_ms = int((time.time() - start_time) * 1000)
                    
                    if isinstance(e, requests.exceptions.Timeout):
                        log_video_proxy_access(proxy_id, client_ip, user_agent, 503, 
                                             "Request timeout to upstream service", response_time_ms)
                        
                        if 'text/html' in request.headers.get('Accept', ''):
                            return render_template('video_error.html',
                                                 error_title='Request Timeout',
                                                 error_message='The video request timed out.',
                                                 error_code='SERVICE_TIMEOUT',
                                                 help_text='Please try again in a few minutes.',
                                                 retry_action='retry',
                                                 retry_after=300), 503
                        
                        return jsonify({
                            'error': 'Video temporarily unavailable. Please try again in a few minutes.',
                            'code': 'SERVICE_TIMEOUT',
                            'retry_after': 300
                        }), 503
                    
                    else:  # ConnectionError
                        log_video_proxy_access(proxy_id, client_ip, user_agent, 503, 
                                             "Connection error to upstream service", response_time_ms)
                        
                        if 'text/html' in request.headers.get('Accept', ''):
                            return render_template('video_error.html',
                                                 error_title='Connection Error',
                                                 error_message='Unable to connect to the video service.',
                                                 error_code='SERVICE_UNAVAILABLE',
                                                 help_text='Please try again in a few minutes.',
                                                 retry_action='retry',
                                                 retry_after=300), 503
                        
                        return jsonify({
                            'error': 'Video temporarily unavailable. Please try again in a few minutes.',
                            'code': 'SERVICE_UNAVAILABLE',
                            'retry_after': 300
                        }), 503
            
            except Exception as e:
                # For non-retryable exceptions, fail immediately
                response_time_ms = int((time.time() - start_time) * 1000)
                sanitized_error = sanitize_error_message(str(e))
                app.logger.error(f"Non-retryable error in video proxy for {proxy_id}: {sanitized_error}")
                log_video_proxy_access(proxy_id, client_ip, user_agent, 500, 
                                     f"Non-retryable error: {sanitized_error}", response_time_ms)
                
                if 'text/html' in request.headers.get('Accept', ''):
                    return render_template('video_error.html',
                                         error_title='Streaming Error',
                                         error_message='An error occurred while accessing the video.',
                                         error_code='STREAMING_ERROR',
                                         help_text='Please try again or regenerate your video.',
                                         retry_action='retry'), 500
                
                return jsonify({
                    'error': 'Error streaming video. Please try again or regenerate your video.',
                    'code': 'STREAMING_ERROR'
                }), 500
        
        # If we get here without a successful response, something went wrong
        if response is None:
            response_time_ms = int((time.time() - start_time) * 1000)
            log_video_proxy_access(proxy_id, client_ip, user_agent, 500, 
                                 "Failed to get response after retries", response_time_ms)
            
            if 'text/html' in request.headers.get('Accept', ''):
                return render_template('video_error.html',
                                     error_title='Service Unavailable',
                                     error_message='Unable to access the video after multiple attempts.',
                                     error_code='SERVICE_UNAVAILABLE',
                                     help_text='Please try again later.',
                                     retry_action='retry'), 503
            
            return jsonify({
                'error': 'Video temporarily unavailable. Please try again in a few minutes.',
                'code': 'SERVICE_UNAVAILABLE',
                'retry_after': 300
            }), 503
        
        # Handle different response status codes from Qwen
        response_time_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code == 404:
                log_video_proxy_access(proxy_id, client_ip, user_agent, 410, 
                                     "Upstream service returned 404", response_time_ms)
                
                # Return user-friendly error page for browser requests
                if 'text/html' in request.headers.get('Accept', ''):
                    return render_template('video_error.html',
                                         error_title='Video Expired',
                                         error_message='This video is no longer available.',
                                         error_code='VIDEO_EXPIRED',
                                         help_text='Please regenerate your video to get a new link.',
                                         retry_action='regenerate'), 410
                
                return jsonify({
                    'error': 'Video no longer available. Please regenerate your video to get a new link.',
                    'code': 'VIDEO_EXPIRED',
                    'help_text': 'Please regenerate your video to get a new link'
                }), 410
            
        if response.status_code == 403:
            log_video_proxy_access(proxy_id, client_ip, user_agent, 410, 
                                 "Upstream service returned 403", response_time_ms)
            
            # Return user-friendly error page for browser requests
            if 'text/html' in request.headers.get('Accept', ''):
                return render_template('video_error.html',
                                     error_title='Video Access Denied',
                                     error_message='Access to this video has been denied.',
                                     error_code='VIDEO_EXPIRED',
                                     help_text='Please regenerate your video to get a new link.',
                                     retry_action='regenerate'), 410
            
            return jsonify({
                'error': 'Video no longer available. Please regenerate your video to get a new link.',
                'code': 'VIDEO_EXPIRED', 
                'help_text': 'Please regenerate your video to get a new link'
            }), 410
        
        if response.status_code >= 500:
            log_video_proxy_access(proxy_id, client_ip, user_agent, 503, 
                                 f"Upstream service error: {response.status_code}", response_time_ms)
            
            # Return user-friendly error page for browser requests
            if 'text/html' in request.headers.get('Accept', ''):
                return render_template('video_error.html',
                                     error_title='Service Temporarily Unavailable',
                                     error_message='The video service is temporarily unavailable.',
                                     error_code='SERVICE_UNAVAILABLE',
                                     help_text='Please try again in a few minutes.',
                                     retry_action='retry',
                                     retry_after=300), 503
            
            return jsonify({
                'error': 'Video temporarily unavailable. Please try again in a few minutes.',
                'code': 'SERVICE_UNAVAILABLE',
                'retry_after': 300
            }), 503
        
        if not response.ok:
            log_video_proxy_access(proxy_id, client_ip, user_agent, 500, 
                                 f"Upstream response not OK: {response.status_code}", response_time_ms)
            
            # Return user-friendly error page for browser requests
            if 'text/html' in request.headers.get('Accept', ''):
                return render_template('video_error.html',
                                     error_title='Video Streaming Error',
                                     error_message='An error occurred while streaming the video.',
                                     error_code='STREAMING_ERROR',
                                     help_text='Please try again or regenerate your video.',
                                     retry_action='retry'), 500
            
            return jsonify({
                'error': 'Error streaming video. Please try again or regenerate your video.',
                'code': 'STREAMING_ERROR'
            }), 500
        
        # Prepare response headers for video streaming
        response_headers = {}
        
        # Essential headers that are safe to forward
        essential_headers = [
            'Content-Type', 'Content-Length', 'Accept-Ranges', 
            'Content-Range', 'Last-Modified', 'ETag'
        ]
        
        # Qwen-specific headers to filter out (maintain white-label appearance)
        qwen_specific_headers = [
            'Server', 'X-Powered-By', 'X-Qwen-*', 'X-Request-Id',
            'X-Trace-Id', 'X-Service-*', 'Via', 'X-Cache',
            'X-Served-By', 'X-Timer', 'X-Fastly-*', 'CF-*',
            'X-Amz-*', 'X-Alibaba-*', 'Ali-*'
        ]
        
        # Copy essential headers while filtering out Qwen-specific ones
        for header in essential_headers:
            if header in response.headers:
                response_headers[header] = response.headers[header]
        
        # Filter out any Qwen-specific headers that might leak service details
        for header_name in response.headers:
            # Skip if it's already in essential headers
            if header_name in essential_headers:
                continue
                
            # Check if header matches any Qwen-specific patterns
            is_qwen_header = False
            for pattern in qwen_specific_headers:
                if pattern.endswith('*'):
                    if header_name.startswith(pattern[:-1]):
                        is_qwen_header = True
                        break
                elif header_name.lower() == pattern.lower():
                    is_qwen_header = True
                    break
            
            # Skip Qwen-specific headers
            if is_qwen_header:
                continue
        
        # Set default content type if not provided
        if 'Content-Type' not in response_headers:
            response_headers['Content-Type'] = 'video/mp4'
        
        # Add caching headers for better performance
        response_headers['Cache-Control'] = 'public, max-age=3600'
        
        # Ensure Accept-Ranges is set for video seeking
        if 'Accept-Ranges' not in response_headers:
            response_headers['Accept-Ranges'] = 'bytes'
        
        # Create enhanced streaming response with byte tracking
        def generate():
            nonlocal bytes_transferred
            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        bytes_transferred += len(chunk)
                        yield chunk
            except Exception as e:
                # Log streaming error without exposing sensitive details
                sanitized_error = f"Streaming interrupted: {type(e).__name__}"
                app.logger.error(f"Error streaming video chunk for proxy {proxy_id}: {sanitized_error}")
                # Connection was likely closed by client
                return
        
        # Return streaming response with appropriate status code
        status_code = response.status_code if response.status_code in [200, 206] else 200
        
        # Create the response
        streaming_response = Response(
            stream_with_context(generate()),
            status=status_code,
            headers=response_headers
        )
        
        # Log successful access with performance metrics
        response_time_ms = int((time.time() - start_time) * 1000)
        log_video_proxy_access(proxy_id, client_ip, user_agent, status_code, 
                             None, response_time_ms, bytes_transferred)
        
        return streaming_response
            
    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        sanitized_error = sanitize_error_message(str(e))
        app.logger.error(f"Error in video proxy endpoint for {proxy_id}: {sanitized_error}")
        log_video_proxy_access(proxy_id, client_ip, user_agent, 500, 
                             f"Proxy endpoint error: {sanitized_error}", response_time_ms)
        
        # Return user-friendly error page for browser requests
        if 'text/html' in request.headers.get('Accept', ''):
            return render_template('video_error.html',
                                 error_title='Video Proxy Error',
                                 error_message='An error occurred in the video proxy service.',
                                 error_code='PROXY_ERROR',
                                 help_text='Please try again or regenerate your video.',
                                 retry_action='retry'), 500
        
        return jsonify({
            'error': 'Error streaming video. Please try again or regenerate your video.',
            'code': 'PROXY_ERROR'
        }), 500


if __name__ == '__main__':
    # Reset any keys that were stuck in 'generating' state on server restart
    with app.app_context():
        reset_count = QwenApiKey.reset_all_generating_to_available()
        app.logger.info(f"Startup Check: Reset {reset_count} stuck Qwen API keys to 'available'.")

    if ADMIN_SECRET_KEY:
        print("="*60)
        print("Admin Dashboard URL:")
        print(f"http://127.0.0.1:5000/admin?secret={ADMIN_SECRET_KEY}")
        print("="*60)
    else:
        print("="*60)
        print("WARNING: ADMIN_SECRET_KEY not set. Admin dashboard is disabled.")
        print("="*60)
    # Configure logging
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
    
    file_handler = RotatingFileHandler(os.path.join(LOGS_DIR, 'app.log'), maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('AI Art startup')
    
    app.logger.info('Visitor logging initialized')
    
    # Print debugging information about image paths
    print("=" * 50)
    print("IMAGE FOLDER CONFIGURATION:")
    print(f"Upload Folder: {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    print(f"Test Assets: {os.path.abspath(app.config['TEST_ASSETS'])}")
    print(f"Processed Folder: {os.path.abspath(app.config['PROCESSED_FOLDER'])}")
    print(f"Processed Videos Folder: {os.path.abspath(app.config['PROCESSED_VIDEOS_FOLDER'])}")
    print(f"App directory: {app_dir}")
    print("=" * 50)
    
    # Start the app in debug mode (development only)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
