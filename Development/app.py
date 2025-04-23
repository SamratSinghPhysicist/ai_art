from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash
import os
from image_generator import main_image_function
from models import User, db
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
from flask import send_file

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure the upload folder for storing generated images
app_dir = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(app_dir, 'images')
app.config['TEST_ASSETS'] = os.path.join(app_dir, 'test_assets')
app.config['PROCESSED_FOLDER'] = os.path.join(app_dir, 'processed_images')

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
    
    try:
        # Generate the image
        generated_image_path = main_image_function(image_description, test_mode, GEMINI_API_KEY)
        
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
    # No reference image handling in API endpoint
    
    try:
        # Generate the image
        generated_image_path = main_image_function(image_description, test_mode, GEMINI_API_KEY)
        
        
        # Extract just the filename from the path
        image_filename = os.path.basename(generated_image_path)
        
        # Determine which folder the image is in
        if 'test_assets' in generated_image_path:
            folder = app.config['TEST_ASSETS']
        elif 'processed_images' in generated_image_path:
            folder = app.config['PROCESSED_FOLDER']
        else:
            folder = app.config['UPLOAD_FOLDER']
        
        # Return the image URL and success message
        return jsonify({
            'success': True,
            'message': 'Image generated successfully',
            'image_url': f'{request.host_url}{folder}/{image_filename}'
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
    
    # Start the app in debug mode (development only)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
