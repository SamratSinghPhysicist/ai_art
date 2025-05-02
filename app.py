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

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure the upload folder for storing generated images
app_dir = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(app_dir, 'images')
app.config['TEST_ASSETS'] = os.path.join(app_dir, 'test_assets')
app.config['PROCESSED_FOLDER'] = os.path.join(app_dir, 'processed_images')

# URL path prefixes for images (not file system paths)
app.config['IMAGES_URL_PATH'] = 'images'
app.config['TEST_ASSETS_URL_PATH'] = 'test_assets'
app.config['PROCESSED_URL_PATH'] = 'processed_images'

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

# Also fix the logs directory path
LOGS_DIR = os.path.join(app_dir, 'logs')

@login_manager.user_loader
def load_user(user_id):
    return User.find_by_id(user_id)

@app.route('/')
def index():
    """Render the main page with the form"""
    return render_template('index.html',
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

@app.route('/sitemap-page')
def sitemap_page():
    """Render the human-readable sitemap page"""
    return render_template('sitemap.html')

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
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Display user's saved images"""
    images = current_user.get_thumbnails()
    return render_template('dashboard.html', user=current_user, thumbnails=images)

@app.route('/image/<image_id>/delete', methods=['POST'])
@login_required
def delete_image(image_id):
    """Delete a user's image"""
    try:
        # Convert string ID to ObjectId
        from bson.objectid import ObjectId
        image_id = ObjectId(image_id)
        
        # Find the image before deleting it (to check if it has image_data)
        image = db['images'].find_one({'_id': image_id, 'user_id': current_user._id})
        
        if not image:
            return jsonify({'success': False, 'error': 'Image not found or you do not have permission to delete it'}), 404
        
        # Delete the image from the database
        result = db['images'].delete_one({'_id': image_id, 'user_id': current_user._id})
        
        if result.deleted_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Image not found or you do not have permission to delete it'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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
        
        # Save the image to the user's collection if logged in
        if current_user.is_authenticated:
            current_user.save_thumbnail(f'/{folder}/{image_filename}', image_description)
        
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
    """Transform an uploaded image based on the prompt provided"""
    # Check if file and prompt are provided
    if 'image' not in request.files or not request.form.get('prompt'):
        return jsonify({'error': 'Both image and prompt are required'}), 400
    
    file = request.files['image']
    prompt = request.form.get('prompt')
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
            # Import the img2img function and StabilityApiKey from models
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
            
            # Generate output filename based on prompt
            safe_prompt = ''.join(c if c.isalnum() else '_' for c in prompt)[:25]
            output_filename = f"img2img_{safe_prompt}_{result_info['seed']}.{output_format}"
            output_path = os.path.join(app.config['PROCESSED_FOLDER'], output_filename)
            
            # Save the generated image
            with open(output_path, 'wb') as f:
                f.write(image_data)
            
            # Check if file was saved successfully and log info
            if os.path.exists(output_path):
                print(f"Image saved successfully at: {output_path}")
                print(f"File size: {os.path.getsize(output_path)} bytes")
            else:
                print(f"WARNING: File was not saved at: {output_path}")
            
            # Print current working directory and absolute path
            print(f"Current working directory: {os.getcwd()}")
            print(f"Absolute path to saved image: {os.path.abspath(output_path)}")
            
            # Clean up the temporary file
            os.remove(temp_image_path)
            
            # Save the image to the user's collection if logged in
            if current_user.is_authenticated:
                current_user.save_thumbnail(f'/{app.config["PROCESSED_FOLDER"]}/{output_filename}', prompt)
            
            # Construct the URL that will be used in the frontend
            image_url = url_for('serve_processed_image', filename=output_filename)
            print(f"Returning image URL to frontend: {image_url}")
            
            # Return success response
            return jsonify({
                'success': True,
                'message': 'Image transformed successfully',
                'image_path': image_url,
                'seed': result_info['seed']
            })
            
        except Exception as e:
            print(f"Error in img2img_transform: {str(e)}")
            # Clean up temporary file in case of error
            if os.path.exists(temp_image_path):
                os.remove(temp_image_path)
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'Invalid file'}), 400

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
            with open(output_path, 'wb') as f:
                f.write(image_data)
            
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
    print(f"App directory: {app_dir}")
    print("=" * 50)
    
    # Start the app in debug mode (development only)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
