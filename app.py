from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash
import os
from image_generator import main_image_function
from models import User, db
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

# Load environment variables
load_dotenv()

app = Flask(__name__)

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

@app.route('/generate', methods=['POST'])
def generate_image():
    """Generate an image based on the description provided"""
    # Get the image description from the form
    image_description = request.form.get('video_description')
    
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
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def api_generate_image():
    """API endpoint to generate an image"""
    # Get JSON data
    data = request.get_json()
    
    if not data or 'video_description' not in data:
        return jsonify({'error': 'Image description is required'}), 400
    
    image_description = data['video_description']
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

@app.route('/img2img', methods=['POST'])
def img2img_transform():
    """Transform an image based on text prompt and uploaded image"""
    # IMPORTANT: Base64 images are not handled by Flask's request.files
    # They must be extracted from request.form
    
    # Get the prompt from the form
    prompt = request.form.get('video_description')
    
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
def api_img2img_transform():
    """API endpoint to transform an image"""
    # Check if file was uploaded
    if 'image' not in request.files:
        return jsonify({'error': 'Image file is required'}), 400
    
    file = request.files['image']
    
    # Get JSON data from form
    prompt = request.form.get('prompt')
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

@app.route('/api/enhance-prompt', methods=['POST'])
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

@app.route('/api/img2video', methods=['POST'])
def api_img2video_generate():
    """API endpoint to generate a video from an image"""
    try:
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
        
        if file:
            # Create processed_videos directory if it doesn't exist
            if not os.path.exists(app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos')):
                os.makedirs(app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos'), exist_ok=True)
            
            # Create a safe filename
            safe_filename = f"temp_{uuid.uuid4().hex}.{file_ext}"
            temp_image_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
            
            try:
                # Save the file
                file.save(temp_image_path)
                
                # Validate the image can be opened
                try:
                    from PIL import Image
                    with Image.open(temp_image_path) as img:
                        # Just checking it can be opened
                        img_width, img_height = img.size
                        print(f"Received image with dimensions: {img_width}x{img_height}")
                except Exception as img_error:
                    raise ValueError(f"Invalid image file: {str(img_error)}")
                
                # Import the img2video function
                from img2video_stability import img2video, get_api_key
                
                # Get API key from the database (oldest available key)
                api_key = get_api_key()
                if not api_key:
                    return jsonify({'error': 'No Stability AI API keys available. Please add keys to the database.'}), 500
                
                try:
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
                    
                    # Clean up the temporary file
                    os.remove(temp_image_path)
                    
                    # Return the generation ID to poll for results
                    return jsonify({
                        'success': True,
                        'id': generation_id,
                        'message': f'Video generation started. Image automatically resized to {dimensions}. Poll for results using the returned ID.',
                        'dimensions': dimensions
                    })
                except Exception as e:
                    error_str = str(e)
                    if "402" in error_str and "credits" in error_str.lower():
                        # Special handling for payment required errors
                        return jsonify({
                            'error': 'Insufficient credits on all available API keys. Please add a new API key with sufficient credits.',
                            'error_type': 'payment_required'
                        }), 402
                    else:
                        raise e
                
            except Exception as e:
                # Clean up temporary file if it exists
                if os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                
                print(f"Error in image-to-video generation: {str(e)}")
                return jsonify({'error': str(e)}), 500
    except Exception as e:
        print(f"Unexpected error in image-to-video API: {str(e)}")
        return jsonify({'error': f"An unexpected error occurred: {str(e)}"}), 500

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
                    return jsonify({
                        'error': 'Insufficient credits on all available API keys. Please add a new API key with sufficient credits.',
                        'error_type': 'payment_required',
                        'status': 'error'
                    }), 402
            else:
                raise e
        
    except Exception as e:
        print(f"Error checking image-to-video status: {str(e)}")
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/processed_videos/<path:filename>')
def serve_processed_video(filename):
    """Serve a processed video file"""
    videos_folder = app.config.get('PROCESSED_VIDEOS_FOLDER', 'processed_videos')
    return send_from_directory(videos_folder, filename)

if __name__ == '__main__':
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
    
    # Initialize visitor logger to track IP addresses and locations
    visitor_logger = VisitorLogger(app, LOGS_DIR)
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
