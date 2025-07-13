from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash, g
import os
import uuid
from image_generator import main_image_function
from prompt_translate import translate_to_english
from models import User, db, request_logs_collection, QwenApiKey
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
from datetime import datetime, timedelta
import os
import requests
from turnstile_utils import verify_turnstile

# Load environment variables
load_dotenv()

app = Flask(__name__)

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
        'api_img2video_result'
    ]
    if request.endpoint in endpoints_to_log_and_check:
        log_request(ip, request.endpoint)

def get_rate_limit():
    ip = get_client_ip()
    endpoint = request.endpoint
    custom_limit = get_custom_rate_limit(ip, endpoint)
    if custom_limit:
        return custom_limit.get('limit_string', get_remote_address)
    return get_remote_address

# Initialize Limiter with stricter limits
limiter = Limiter(
    get_rate_limit, 
    app=app,
    default_limits=["1440 per day", "60 per hour"], # Stricter default limits
    storage_uri="memory://",  # Use memory for storage, consider Redis for production
    strategy="moving-window" # Moving window for better abuse prevention
)

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
                # Use a simple in-memory dictionary for rate limiting anonymous users
                if 'anonymous_requests' not in app.config:
                    app.config['anonymous_requests'] = {}
                
                now = datetime.utcnow()
                if user_id not in app.config['anonymous_requests']:
                    app.config['anonymous_requests'][user_id] = []
                
                # Clean up old requests
                app.config['anonymous_requests'][user_id] = [t for t in app.config['anonymous_requests'][user_id] if now - t < timedelta(days=1)]
                
                # Enforce a limit (e.g., 20 requests per day for anonymous users)
                if len(app.config['anonymous_requests'][user_id]) >= 20: # Increased limit to 20 for free generations
                    return jsonify({'error': 'Free generation limit reached. Please log in to continue or try again tomorrow'}), 429 # Too Many Requests
                                            
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
            endpoints = ['generate_image', 'api_generate_image', 'img2img_transform', 'api_img2img_transform', 'img2video_generate', 'api_img2video_generate']
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
        key.save()
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

@app.route('/get-api-token', methods=['GET'])
def get_api_token():
    """Generate a JWT for the authenticated or anonymous user."""
    try:
        expiration = datetime.utcnow() + timedelta(hours=1)
        
        if current_user.is_authenticated:
            user_id = current_user.get_id()
            is_anonymous = False
        else:
            # For anonymous users, use a session-based ID
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
        
        return jsonify({'token': token})
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

@app.route('/google4732be05fe4d2482.html')
def google_verification():
    """Serve the Google verification file"""
    return render_template('google4732be05fe4d2482.html')

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

if __name__ == '__main__':
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
