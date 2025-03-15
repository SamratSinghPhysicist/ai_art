from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash
import os
from image_generator import main_image_function
from image_editor import process_image
from models import User, db
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure the upload folder for storing generated images
app.config['UPLOAD_FOLDER'] = 'images'
app.config['TEST_ASSETS'] = 'test_assets'
app.config['PROCESSED_FOLDER'] = 'processed_images'
app.config['REFERENCE_IMAGES'] = 'reference_images'

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
os.makedirs(app.config['REFERENCE_IMAGES'], exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return User.find_by_id(user_id)

@app.route('/')
def index():
    """Render the main page with the form"""
    return render_template('index.html')

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
    """Display user's saved thumbnails"""
    thumbnails = current_user.get_thumbnails()
    return render_template('dashboard.html', user=current_user, thumbnails=thumbnails)

@app.route('/thumbnail/<thumbnail_id>/delete', methods=['POST'])
@login_required
def delete_thumbnail(thumbnail_id):
    """Delete a user's thumbnail"""
    try:
        # Convert string ID to ObjectId
        from bson.objectid import ObjectId
        thumbnail_id = ObjectId(thumbnail_id)
        
        # Find the thumbnail before deleting it (to check if it has image_data)
        thumbnail = db['thumbnails'].find_one({'_id': thumbnail_id, 'user_id': current_user._id})
        
        if not thumbnail:
            return jsonify({'success': False, 'error': 'Thumbnail not found or you do not have permission to delete it'}), 404
        
        # Delete the thumbnail from the database
        result = db['thumbnails'].delete_one({'_id': thumbnail_id, 'user_id': current_user._id})
        
        if result.deleted_count > 0:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Thumbnail not found or you do not have permission to delete it'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/generate', methods=['POST'])
def generate_thumbnail():
    """Generate a thumbnail based on the description provided"""
    # Get the video description from the form
    video_description = request.form.get('video_description')
    
    # Check if test mode is enabled
    test_mode = request.form.get('test_mode') == 'true'
    
    if not video_description:
        return jsonify({'error': 'Video description is required'}), 400
    
    # Handle reference image upload if provided
    reference_image_path = None
    if 'reference_image' in request.files:
        reference_image = request.files['reference_image']
        if reference_image and reference_image.filename != '':
            # Secure the filename to prevent any security issues
            from werkzeug.utils import secure_filename
            filename = secure_filename(reference_image.filename)
            # Create a unique filename to avoid overwriting
            import uuid
            unique_filename = f"{uuid.uuid4()}_{filename}"
            # Save the file
            reference_image_path = os.path.join(app.config['REFERENCE_IMAGES'], unique_filename)
            reference_image.save(reference_image_path)
    
    try:
        # Generate the image with optional reference image
        generated_image_path = main_image_function(video_description, test_mode, GEMINI_API_KEY, reference_image_path)
        
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
        
        # Save the thumbnail to the user's collection if logged in
        if current_user.is_authenticated:
            current_user.save_thumbnail(f'/{folder}/{image_filename}', video_description)
        
        # Return the image path and success message
        return jsonify({
            'success': True,
            'message': 'Thumbnail generated successfully',
            'image_path': f'/{folder}/{image_filename}'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate', methods=['POST'])
def api_generate_thumbnail():
    """API endpoint to generate a thumbnail"""
    # Get JSON data
    data = request.get_json()
    
    if not data or 'video_description' not in data:
        return jsonify({'error': 'Video description is required'}), 400
    
    video_description = data['video_description']
    test_mode = data.get('test_mode', False)
    reference_image_path = data.get('reference_image_path', None)
    
    try:
        # Generate the image with optional reference image
        generated_image_path = main_image_function(video_description, test_mode, GEMINI_API_KEY, reference_image_path)
        
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
        
        # Return the image URL and success message
        return jsonify({
            'success': True,
            'message': 'Thumbnail generated successfully',
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

@app.route('/reference_images/<filename>')
def serve_reference_image(filename):
    """Serve the reference images"""
    return send_from_directory(app.config['REFERENCE_IMAGES'], filename)

@app.route('/api/analyze-reference-image', methods=['POST'])
def analyze_reference_image_api():
    """API endpoint to analyze a reference image using Pollinations Vision API"""
    # Check if a file was uploaded
    if 'reference_image' not in request.files:
        return jsonify({'error': 'No reference image provided'}), 400
        
    reference_image = request.files['reference_image']
    if reference_image.filename == '':
        return jsonify({'error': 'No reference image selected'}), 400
        
    try:
        # Save the uploaded image temporarily
        from werkzeug.utils import secure_filename
        import uuid
        
        filename = secure_filename(reference_image.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        reference_image_path = os.path.join(app.config['REFERENCE_IMAGES'], unique_filename)
        reference_image.save(reference_image_path)
        
        # Import the Pollinations Vision API functions
        from pollinations_vision import analyze_image_with_pollinations, extract_ai_insights
        
        # Get detailed analysis from Pollinations Vision API
        detailed_analysis = request.form.get('detailed_analysis', 'true').lower() == 'true'
        ai_analysis = analyze_image_with_pollinations(reference_image_path, detailed_analysis)
        
        if not ai_analysis:
            return jsonify({'error': 'Failed to analyze image with Pollinations Vision API'}), 500
            
        # Extract structured insights from the AI analysis
        ai_insights = extract_ai_insights(ai_analysis)
        
        # Return the analysis results
        return jsonify({
            'success': True,
            'message': 'Reference image analyzed successfully',
            'image_path': f'/reference_images/{unique_filename}',
            'analysis': ai_analysis,
            'insights': ai_insights
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/enhance-prompt', methods=['POST'])
def enhance_prompt():
    """API endpoint to enhance a prompt using Gemini"""
    # Get JSON data
    data = request.get_json()
    
    if not data or 'prompt' not in data:
        return jsonify({'error': 'Prompt is required'}), 400
    
    original_prompt = data['prompt']
    
    try:
        # Create a meta-prompt for enhancing the user's prompt
        meta_prompt = f"""You are an expert YouTube thumbnail designer. Enhance the following basic prompt to create a more detailed, 
        vivid, and engaging description for a YouTube thumbnail. Make it more specific, visual, and compelling, 
        but keep it concise (maximum 2-3 sentences):
        
        "{original_prompt}"
        
        Provide only the enhanced prompt text without any explanations or additional formatting."""
        
        # Use the generate_gemini function to enhance the prompt
        from gemini_generator import generate_gemini
        enhanced_prompt = generate_gemini(meta_prompt, GEMINI_API_KEY)
        
        # Return the enhanced prompt
        return jsonify({
            'success': True,
            'original_prompt': original_prompt,
            'enhanced_prompt': enhanced_prompt
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Configure logging for production
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/thumbnail_generator.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Thumbnail generator startup')
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)




