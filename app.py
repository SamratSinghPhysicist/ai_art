from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash
import os
from image_generator import main_image_function
from image_editor import process_image
from models import User, db
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from flask import send_file
import requests

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure the upload folder for storing generated images
app.config['UPLOAD_FOLDER'] = 'images'
app.config['TEST_ASSETS'] = 'test_assets'
app.config['PROCESSED_FOLDER'] = 'processed_images'


# Configure Flask-Login
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# API key
GEMINI_API_KEY = "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II"
# Shrinkearn API key
SHRINKEARN_API_KEY = os.getenv('SHRINKEARN_API_KEY', '229cd899f7265729506ef7abd124f781bddf2b64')

# Ensure the images directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return User.find_by_id(user_id)

@app.route('/')
def index():
    """Render the main page with the form"""
    return render_template('index.html')

@app.route('/blog')
def blog():
    """Render the blog page with SEO-focused content"""
    return render_template('blog.html')

@app.route('/blog-ai-image-generation')
def blog_ai_image_generation():
    """Render the AI image generation blog page"""
    return render_template('blog-ai-image-generation.html')

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
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.find_by_email(email)
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid email or password')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handle user registration"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user already exists
        existing_user = User.find_by_email(email)
        if existing_user:
            return render_template('signup.html', error='Email already registered')
        
        # Create new user
        user = User(email=email, password=password, name=name)
        user.save()
        
        # Log in the new user
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    """Handle user logout"""
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Display user's saved images"""
    images = current_user.get_thumbnails()
    
    # Generate shortened URLs for each image if they don't have image_data
    for image in images:
        if not image.get('image_data') and image.get('image_path'):
            full_url = request.host_url.rstrip('/') + image['image_path']
            image['shortened_url'] = shorten_url(full_url)
    
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

def shorten_url(long_url):
    """Shorten a URL using the Shrinkearn API"""
    try:
        # If API key is not set, return the original URL
        if not SHRINKEARN_API_KEY:
            print("Shrinkearn API key not set, using original URL")
            return long_url
            
        # API endpoint for Shrinkearn
        api_url = 'https://shrinkearn.com/api'
        
        # Parameters for the API request
        params = {
            'api': SHRINKEARN_API_KEY,
            'url': long_url
        }
        
        # Make the API request - Shrinkearn uses GET method
        print(f"Sending request to Shrinkearn API for URL: {long_url}")
        response = requests.get(api_url, params=params, timeout=10)
        response_text = response.text
        print(f"Shrinkearn API response: {response_text}")
        
        try:
            data = response.json()
            
            # Check if the request was successful
            if data.get('status') == 'success':
                shortened_url = data.get('shortenedUrl')
                # Remove any escape characters from the URL - Shrinkearn returns URL with escaped quotes and slashes
                if shortened_url:
                    # Remove extra quotes and escape characters
                    shortened_url = shortened_url.replace('"', '').replace('\\/', '/')
                    print(f"URL shortened successfully: {shortened_url}")
                    return shortened_url
                else:
                    print("Shortened URL not found in response")
                    return long_url
            else:
                # Log the error and return the original URL
                error_msg = data.get('message', 'Unknown error')
                print(f"URL shortening failed: {error_msg}")
                return long_url
        except ValueError:
            # If the response is not valid JSON
            print(f"Invalid JSON response from Shrinkearn: {response_text}")
            return long_url
            
    except requests.exceptions.RequestException as e:
        # Log the exception and return the original URL
        print(f"Error making request to Shrinkearn: {str(e)}")
        return long_url
    except Exception as e:
        # Log the exception and return the original URL
        print(f"Unexpected error shortening URL: {str(e)}")
        return long_url

@app.route('/generate', methods=['POST'])
def generate_image():
    """Generate an image based on the description provided"""
    # Get the image description from the form
    image_description = request.form.get('video_description')
    
    # Check if test mode is enabled
    test_mode = request.form.get('test_mode') == 'true'
    
    if not image_description:
        return jsonify({'error': 'Image description is required'}), 400
    
    try:
        # Generate the image
        generated_image_path = main_image_function(image_description, test_mode, GEMINI_API_KEY)
        
        # Process the image to remove the watermark if it's not a test asset
        generated_image_path = process_image(generated_image_path)
        
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
        
        # Generate the full download URL
        download_url = request.host_url.rstrip('/') + f'/{folder}/{image_filename}'
        
        # Shorten the download URL using Shrinkearn
        shortened_url = shorten_url(download_url)
        
        # Return the image path, shortened URL, and success message
        return jsonify({
            'success': True,
            'message': 'Image generated successfully',
            'image_path': f'/{folder}/{image_filename}',
            'download_url': shortened_url
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
    # No reference image handling in API endpoint
    
    try:
        # Generate the image
        generated_image_path = main_image_function(image_description, test_mode, GEMINI_API_KEY)
        
        # Process the image to remove the watermark if it's not a test asset
        generated_image_path = process_image(generated_image_path)
        
        # Extract just the filename from the path
        image_filename = os.path.basename(generated_image_path)
        
        # Determine which folder the image is in
        if 'test_assets' in generated_image_path:
            folder = app.config['TEST_ASSETS']
        elif 'processed_images' in generated_image_path:
            folder = app.config['PROCESSED_FOLDER']
        else:
            folder = app.config['UPLOAD_FOLDER']
        
        # Generate the full download URL
        download_url = request.host_url.rstrip('/') + f'/{folder}/{image_filename}'
        
        # Shorten the download URL using Shrinkearn
        shortened_url = shorten_url(download_url)
        
        # Return the image URL, shortened URL, and success message
        return jsonify({
            'success': True,
            'message': 'Image generated successfully',
            'image_url': f'{request.host_url}{folder}/{image_filename}',
            'download_url': shortened_url
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/images/<filename>')
def serve_image(filename):
    """Serve the generated images"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/test_assets/<filename>')
def serve_test_asset(filename):
    """Serve the test assets"""
    return send_from_directory(app.config['TEST_ASSETS'], filename)

@app.route('/processed_images/<filename>')
def serve_processed_image(filename):
    """Serve the processed images"""
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename)

@app.route('/download/<path:folder>/<filename>')
def download_image(folder, filename):
    """Handle image downloads - either redirect to shortened URL or force download"""
    # Build the original image URL
    original_url = f"/{folder}/{filename}"
    full_url = request.host_url.rstrip('/') + original_url
    
    # Check if we should use URL shortening
    use_shortening = request.args.get('monetize', 'true').lower() == 'true'
    
    if use_shortening and SHRINKEARN_API_KEY:
        # Shorten the URL and redirect to it
        shortened_url = shorten_url(full_url)
        if shortened_url != full_url:  # Only redirect if shortening was successful
            return redirect(shortened_url)
    
    # If shortening is disabled or failed, serve the file with download headers
    if folder == app.config['UPLOAD_FOLDER']:
        return send_from_directory(
            app.config['UPLOAD_FOLDER'], 
            filename, 
            as_attachment=True,
            download_name=f"ai-image-{filename}"
        )
    elif folder == app.config['PROCESSED_FOLDER']:
        return send_from_directory(
            app.config['PROCESSED_FOLDER'],
            filename,
            as_attachment=True,
            download_name=f"ai-image-{filename}"
        )
    elif folder == app.config['TEST_ASSETS']:
        return send_from_directory(
            app.config['TEST_ASSETS'],
            filename,
            as_attachment=True,
            download_name=f"ai-image-{filename}"
        )
    else:
        return jsonify({'error': 'Invalid folder path'}), 400

@app.route('/api/enhance-prompt', methods=['POST'])
def enhance_prompt():
    """API endpoint to enhance the given image prompt with AI"""
    # Get the prompt from the request
    data = request.get_json()
    
    if not data or 'prompt' not in data:
        return jsonify({'error': 'Prompt is required'}), 400
    
    user_prompt = data['prompt']
    
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
    
    try:
        # Call Gemini API to enhance the prompt
        from gemini_generator import generate_gemini
        enhanced_prompt = generate_gemini(system_prompt, GEMINI_API_KEY)
        
        # Return the enhanced prompt
        return jsonify({
            'success': True,
            'enhanced_prompt': enhanced_prompt
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/google4732be05fe4d2482.html')
def google_verification():
    """Serve the Google verification file"""
    return render_template('google4732be05fe4d2482.html')

if __name__ == '__main__':
    # Configure logging
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    file_handler = RotatingFileHandler('logs/app.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('AI Art startup')
    
    # Start the app in debug mode (development only)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)




