"""
Backend API separation module for AiArt optimization.
This module extracts existing Flask routes into separate API endpoints with /api/v1/ prefix.
"""

from flask import Blueprint, request, jsonify, current_app, g
from flask_cors import CORS
import os
import time
from datetime import datetime
from functools import wraps
import logging

# Import existing modules
from adaptive_rate_limiter import should_allow_request as adaptive_should_allow_request, get_rate_limit_message
from ip_utils import get_client_ip
from models import User, QwenApiKey, StabilityApiKey, VideoTask
from image_generator import main_image_function
from img2img_stability import img2img, save_image
from img2video_stability import img2video, get_video_result, save_video, get_api_key
from qwen_generator import generate_qwen_video
from prompt_translate import translate_to_english
from gemini_generator import generate_gemini
import uuid
import base64

# Create API blueprint
api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

# Configure CORS for the API blueprint
CORS(api_v1, 
     origins=['https://aiart-zroo.onrender.com', 'http://localhost:3000', 'http://localhost:5000', 'http://localhost:8000'],
     methods=['GET', 'POST', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With', 'x-access-token'],
     supports_credentials=True)

# Logger setup
logger = logging.getLogger(__name__)

def api_error_handler(f):
    """Decorator to handle API errors consistently"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"API Error in {f.__name__}: {str(e)}")
            return jsonify({
                'success': False,
                'error': 'Internal server error',
                'message': str(e)
            }), 500
    return decorated_function

def require_api_token(f):
    """Decorator to require API token for protected endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        if 'x-access-token' in request.headers:
            token = request.headers['x-access-token']
        elif 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]

        if not token:
            return jsonify({
                'success': False,
                'error': 'Authentication required',
                'message': 'API token is missing'
            }), 401

        # Store token in request context for use by other decorators
        g.api_token = token
        return f(*args, **kwargs)
    return decorated_function

def adaptive_rate_limit_api(f):
    """API version of adaptive rate limiting decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get user information
        user_id = None
        is_authenticated = False
        is_donor = False
        
        # Try to get user info from token if available
        if hasattr(g, 'api_token'):
            # Here you would decode the token to get user info
            # For now, we'll use basic IP-based limiting
            pass
        
        # Get client IP
        ip = get_client_ip()
        
        # Get resource monitor from app context
        resource_monitor = getattr(current_app, 'resource_monitor', None)
        
        # Check if request should be allowed using adaptive rate limiter
        allowed, info = adaptive_should_allow_request(
            user_id=user_id,
            ip=ip,
            is_authenticated=is_authenticated,
            is_donor=is_donor,
            resource_monitor=resource_monitor
        )
        
        if not allowed:
            # Generate user-friendly message using new error handling system
            message_info = get_rate_limit_message(allowed, info)
            
            # Return comprehensive user-friendly response
            response_data = {
                'success': False,
                'error_type': 'rate_limit',
                'title': message_info.get('title', 'Rate Limit Reached'),
                'message': message_info['message'],
                'action_message': message_info.get('action_message', 'Please wait and try again'),
                'wait_time': message_info.get('wait_time', 60),
                'retry_after': message_info.get('wait_time', 60),
                'tier': info.get('tier', 'anonymous'),
                'server_load': info.get('server_load', 0.0),
                'show_donation_prompt': message_info.get('donation_link') is not None,
                'donation_message': message_info.get('donation_message', ''),
                'donation_link': message_info.get('donation_link', '/donate'),
                'upgrade_available': message_info.get('upgrade_available', False),
                'upgrade_message': message_info.get('upgrade_message', ''),
                'alternatives': message_info.get('alternatives', [])
            }
            
            return jsonify(response_data), 429
        
        # Request is allowed, proceed with the original function
        return f(*args, **kwargs)
    
    return decorated_function

# Health check endpoint
@api_v1.route('/health', methods=['GET'])
@api_error_handler
def health_check():
    """Health check endpoint with load and queue metrics"""
    try:
        # Get resource monitor from app context
        resource_monitor = getattr(current_app, 'resource_monitor', None)
        queue_manager = getattr(current_app, 'queue_manager', None)
        
        # Basic health status
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0',
            'service': 'aiart-backend'
        }
        
        # Add resource metrics if available
        if resource_monitor:
            try:
                from resource_monitor import get_system_status
                system_status = get_system_status()
                health_status.update({
                    'cpu_usage': system_status.get('cpu_usage', 0),
                    'memory_usage': system_status.get('memory_usage', 0),
                    'load_percentage': system_status.get('load_percentage', 0),
                    'is_hibernating': system_status.get('is_hibernating', False)
                })
            except Exception as e:
                logger.warning(f"Could not get resource status: {e}")
                health_status['resource_monitor'] = 'unavailable'
        
        # Add queue metrics if available
        if queue_manager:
            try:
                queue_metrics = queue_manager.get_queue_metrics()
                health_status.update({
                    'queue_length': queue_metrics.get('total_queued', 0),
                    'active_requests': queue_metrics.get('active_requests', 0),
                    'processed_requests': queue_metrics.get('total_completed', 0)
                })
            except Exception as e:
                logger.warning(f"Could not get queue metrics: {e}")
                health_status['queue_manager'] = 'unavailable'
        
        # Check database connectivity
        try:
            from models import db
            if db is not None:
                # Simple database check
                db.list_collection_names()
                health_status['database'] = 'connected'
            else:
                health_status['database'] = 'disconnected'
        except Exception as e:
            logger.warning(f"Database check failed: {e}")
            health_status['database'] = 'error'
        
        # Determine overall status
        if (health_status.get('cpu_usage', 0) > 90 or 
            health_status.get('memory_usage', 0) > 95 or
            health_status.get('database') == 'error'):
            health_status['status'] = 'degraded'
        
        return jsonify(health_status)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }), 503

# Text-to-Image Generation API
@api_v1.route('/generate/text-to-image', methods=['POST'])
@require_api_token
@adaptive_rate_limit_api
@api_error_handler
def generate_text_to_image():
    """API endpoint for text-to-image generation"""
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'error': 'Invalid request',
            'message': 'JSON data required'
        }), 400
    
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({
            'success': False,
            'error': 'Missing prompt',
            'message': 'Prompt is required'
        }), 400
    
    if len(prompt) > 1000:
        return jsonify({
            'success': False,
            'error': 'Prompt too long',
            'message': 'Prompt must be 1000 characters or less'
        }), 400
    
    # Translate prompt to English
    prompt = translate_to_english(prompt)
    
    # Get optional parameters
    negative_prompt = data.get('negative_prompt', '')
    style_preset = data.get('style_preset')
    aspect_ratio = data.get('aspect_ratio', '1:1')
    seed = data.get('seed', 0)
    
    try:
        # Generate image using existing function
        result = main_image_function(
            prompt=prompt,
            negative_prompt=negative_prompt,
            style_preset=style_preset,
            aspect_ratio=aspect_ratio,
            seed=seed
        )
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Image generated successfully',
                'image_url': result.get('image_url'),
                'seed': result.get('seed'),
                'prompt_used': prompt
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Generation failed',
                'message': result.get('error', 'Unknown error occurred')
            }), 500
            
    except Exception as e:
        logger.error(f"Text-to-image generation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Generation failed',
            'message': str(e)
        }), 500

# Image-to-Image Transformation API
@api_v1.route('/generate/image-to-image', methods=['POST'])
@require_api_token
@adaptive_rate_limit_api
@api_error_handler
def generate_image_to_image():
    """API endpoint for image-to-image transformation"""
    # Check if image file was uploaded
    if 'image' not in request.files:
        return jsonify({
            'success': False,
            'error': 'Missing image',
            'message': 'Image file is required'
        }), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({
            'success': False,
            'error': 'No file selected',
            'message': 'Please select an image file'
        }), 400
    
    # Get parameters
    prompt = request.form.get('prompt', '').strip()
    if not prompt:
        return jsonify({
            'success': False,
            'error': 'Missing prompt',
            'message': 'Prompt is required'
        }), 400
    
    # Translate prompt to English
    prompt = translate_to_english(prompt)
    
    negative_prompt = request.form.get('negative_prompt', '')
    strength = float(request.form.get('strength', 0.7))
    style_preset = request.form.get('style_preset')
    aspect_ratio = request.form.get('aspect_ratio', '1:1')
    output_format = request.form.get('output_format', 'png')
    seed = int(request.form.get('seed', 0))
    
    # Save uploaded file temporarily
    temp_image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], f'temp_{uuid.uuid4().hex}.png')
    file.save(temp_image_path)
    
    try:
        # Get API key
        api_key_obj = StabilityApiKey.find_oldest_key()
        if not api_key_obj:
            return jsonify({
                'success': False,
                'error': 'Service unavailable',
                'message': 'No API keys available'
            }), 503
        
        # Perform transformation
        image_data, result_info = img2img(
            api_key=api_key_obj.api_key,
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
        output_path = os.path.join(current_app.config['PROCESSED_FOLDER'], output_filename)
        
        # Save the generated image
        save_image(image_data, output_path, result_info['seed'])
        
        # Clean up temporary file
        os.remove(temp_image_path)
        
        # Return success response
        return jsonify({
            'success': True,
            'message': 'Image transformed successfully',
            'image_url': f"/processed_images/{output_filename}",
            'seed': result_info['seed'],
            'prompt_used': prompt
        })
        
    except Exception as e:
        # Clean up temporary file
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)
        
        logger.error(f"Image-to-image transformation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Transformation failed',
            'message': str(e)
        }), 500

# Text-to-Video Generation API
@api_v1.route('/generate/text-to-video', methods=['POST'])
@require_api_token
@adaptive_rate_limit_api
@api_error_handler
def generate_text_to_video():
    """API endpoint for text-to-video generation"""
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'error': 'Invalid request',
            'message': 'JSON data required'
        }), 400
    
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({
            'success': False,
            'error': 'Missing prompt',
            'message': 'Prompt is required'
        }), 400
    
    if len(prompt) > 500:
        return jsonify({
            'success': False,
            'error': 'Prompt too long',
            'message': 'Prompt must be 500 characters or less'
        }), 400
    
    # Get Qwen API key
    qwen_keys = QwenApiKey.get_all()
    if not qwen_keys:
        return jsonify({
            'success': False,
            'error': 'Service unavailable',
            'message': 'Video generation service temporarily unavailable'
        }), 503
    
    import random
    selected_key = random.choice(qwen_keys)
    
    # Create video task
    video_task = VideoTask.create(prompt)
    if not video_task:
        return jsonify({
            'success': False,
            'error': 'Task creation failed',
            'message': 'Failed to create video generation task'
        }), 500
    
    task_id = video_task['task_id']
    
    # Return task ID for polling
    return jsonify({
        'success': True,
        'message': 'Video generation started',
        'task_id': task_id,
        'status_url': f"/api/v1/generate/text-to-video/status/{task_id}"
    }), 202

# Text-to-Video Status API
@api_v1.route('/generate/text-to-video/status/<task_id>', methods=['GET'])
@api_error_handler
def get_text_to_video_status(task_id):
    """API endpoint to check text-to-video generation status"""
    try:
        video_task = VideoTask.get_by_task_id(task_id)
        if not video_task:
            return jsonify({
                'success': False,
                'error': 'Task not found',
                'message': 'Invalid task ID'
            }), 404
        
        status = video_task.get('status', 'pending')
        
        response_data = {
            'success': True,
            'task_id': task_id,
            'status': status,
            'created_at': video_task.get('created_at'),
            'updated_at': video_task.get('updated_at')
        }
        
        if status == 'completed':
            response_data.update({
                'video_url': video_task.get('video_url'),
                'proxy_url': video_task.get('proxy_url')
            })
        elif status == 'failed':
            response_data['error_message'] = video_task.get('error_message')
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error checking video status: {e}")
        return jsonify({
            'success': False,
            'error': 'Status check failed',
            'message': str(e)
        }), 500

# Image-to-Video Generation API
@api_v1.route('/generate/image-to-video', methods=['POST'])
@require_api_token
@adaptive_rate_limit_api
@api_error_handler
def generate_image_to_video():
    """API endpoint for image-to-video generation"""
    # Check if image file was uploaded
    if 'image' not in request.files:
        return jsonify({
            'success': False,
            'error': 'Missing image',
            'message': 'Image file is required'
        }), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({
            'success': False,
            'error': 'No file selected',
            'message': 'Please select an image file'
        }), 400
    
    # Validate file extension
    allowed_extensions = {'jpg', 'jpeg', 'png'}
    file_ext = ''
    if '.' in file.filename:
        file_ext = file.filename.rsplit('.', 1)[1].lower()
    
    if file_ext not in allowed_extensions:
        return jsonify({
            'success': False,
            'error': 'Invalid file format',
            'message': f'File format not supported. Please use JPG or PNG images. Received: {file_ext}'
        }), 400
    
    # Get parameters
    seed = int(request.form.get('seed', 0))
    cfg_scale = float(request.form.get('cfg_scale', 1.5))
    motion_bucket_id = int(request.form.get('motion_bucket_id', 127))
    
    # Validate parameters
    if cfg_scale < 0 or cfg_scale > 10:
        return jsonify({
            'success': False,
            'error': 'Invalid parameter',
            'message': 'cfg_scale must be between 0 and 10'
        }), 400
    
    if motion_bucket_id < 1 or motion_bucket_id > 255:
        return jsonify({
            'success': False,
            'error': 'Invalid parameter',
            'message': 'motion_bucket_id must be between 1 and 255'
        }), 400
    
    # Save uploaded file temporarily
    safe_filename = f"temp_{uuid.uuid4().hex}.{file_ext}"
    temp_image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_filename)
    file.save(temp_image_path)
    
    try:
        # Validate image can be opened
        from PIL import Image
        with Image.open(temp_image_path) as img:
            img_width, img_height = img.size
        
        # Get API key
        api_key = get_api_key()
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'Service unavailable',
                'message': 'No API keys available'
            }), 503
        
        # Start video generation
        generation_id, dimensions, api_key = img2video(
            api_key=api_key,
            image_path=temp_image_path,
            seed=seed,
            cfg_scale=cfg_scale,
            motion_bucket_id=motion_bucket_id
        )
        
        # Clean up temporary file
        os.remove(temp_image_path)
        
        return jsonify({
            'success': True,
            'message': 'Video generation started',
            'generation_id': generation_id,
            'dimensions': dimensions,
            'status_url': f"/api/v1/generate/image-to-video/status/{generation_id}"
        }), 202
        
    except Exception as e:
        # Clean up temporary file
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)
        
        logger.error(f"Image-to-video generation error: {e}")
        return jsonify({
            'success': False,
            'error': 'Generation failed',
            'message': str(e)
        }), 500

# Image-to-Video Status API
@api_v1.route('/generate/image-to-video/status/<generation_id>', methods=['GET'])
@api_error_handler
def get_image_to_video_status(generation_id):
    """API endpoint to check image-to-video generation status"""
    try:
        # Get API key (you might want to store this with the generation)
        api_key = get_api_key()
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'Service unavailable',
                'message': 'No API keys available'
            }), 503
        
        # Check generation status
        result = get_video_result(api_key=api_key, generation_id=generation_id)
        
        if result['status'] == 'in-progress':
            return jsonify({
                'success': True,
                'generation_id': generation_id,
                'status': 'in-progress',
                'message': 'Video generation is still in progress'
            }), 202
        
        # If complete, save video and return URL
        videos_folder = current_app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos')
        os.makedirs(videos_folder, exist_ok=True)
        
        video_path = save_video(
            video_data=result['video'],
            output_directory=videos_folder,
            filename_prefix=f"video_{generation_id[:8]}",
            seed=result.get('seed')
        )
        
        video_filename = os.path.basename(video_path)
        
        return jsonify({
            'success': True,
            'generation_id': generation_id,
            'status': 'complete',
            'video_url': f"/processed_videos/{video_filename}",
            'finish_reason': result.get('finish_reason', 'SUCCESS'),
            'seed': result.get('seed', 'unknown')
        })
        
    except Exception as e:
        logger.error(f"Error checking image-to-video status: {e}")
        return jsonify({
            'success': False,
            'error': 'Status check failed',
            'message': str(e)
        }), 500

# User Authentication API
@api_v1.route('/auth/validate-token', methods=['POST'])
@api_error_handler
def validate_auth_token():
    """API endpoint to validate authentication tokens"""
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'error': 'Invalid request',
            'message': 'JSON data required'
        }), 400
    
    token = data.get('token') or data.get('idToken')
    if not token:
        return jsonify({
            'success': False,
            'error': 'Missing token',
            'message': 'Authentication token is required'
        }), 400
    
    try:
        from firebase_admin import auth as firebase_admin_auth
        
        # Verify token with Firebase
        decoded_token = firebase_admin_auth.verify_id_token(token)
        uid = decoded_token['uid']
        
        # Check if user exists in database
        user = User.find_by_firebase_uid(uid)
        
        return jsonify({
            'success': True,
            'valid': True,
            'uid': uid,
            'email': user.email if user and hasattr(user, 'email') else None,
            'user_exists': user is not None
        })
        
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        return jsonify({
            'success': False,
            'valid': False,
            'error': 'Invalid token',
            'message': str(e)
        }), 401

# Prompt Enhancement API
@api_v1.route('/enhance-prompt', methods=['POST'])
@require_api_token
@api_error_handler
def enhance_prompt():
    """API endpoint to enhance image generation prompts"""
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'error': 'Invalid request',
            'message': 'JSON data required'
        }), 400
    
    user_prompt = data.get('prompt', '').strip()
    if not user_prompt:
        return jsonify({
            'success': False,
            'error': 'Missing prompt',
            'message': 'Prompt is required'
        }), 400
    
    try:
        # System prompt for enhancement
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
        
        # Get Gemini API key from environment
        GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II')
        
        # Call Gemini API
        enhanced_prompt = generate_gemini(system_prompt, GEMINI_API_KEY)
        
        return jsonify({
            'success': True,
            'original_prompt': user_prompt,
            'enhanced_prompt': enhanced_prompt
        })
        
    except Exception as e:
        logger.error(f"Prompt enhancement error: {e}")
        return jsonify({
            'success': False,
            'error': 'Enhancement failed',
            'message': str(e)
        }), 500