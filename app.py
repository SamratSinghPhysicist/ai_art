from flask import Flask, request, jsonify, render_template, send_from_directory, redirect, url_for, session, flash
import os
from image_generator import main_image_function
from image_editor import process_image
from models import User, db
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

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
    
    try:
        # Generate the image
        generated_image_path = main_image_function(video_description, test_mode, GEMINI_API_KEY)
        
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
    
    try:
        # Generate the image
        generated_image_path = main_image_function(video_description, test_mode, GEMINI_API_KEY)
        
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
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)




