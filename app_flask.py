from flask import Flask, request, jsonify, render_template, send_from_directory
import os
from image_generator import main_image_function

app = Flask(__name__)

# Configure the upload folder for storing generated images
app.config['UPLOAD_FOLDER'] = 'images'
app.config['TEST_ASSETS'] = 'test_assets'

# API key
GEMINI_API_KEY = "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II"

# Ensure the images directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    """Render the main page with the form"""
    return render_template('index.html')

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
        
        # Extract just the filename from the path
        image_filename = os.path.basename(generated_image_path)
        
        # Determine which folder the image is in
        if 'test_assets' in generated_image_path:
            folder = app.config['TEST_ASSETS']
        else:
            folder = app.config['UPLOAD_FOLDER']
        
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
        
        # Extract just the filename from the path
        image_filename = os.path.basename(generated_image_path)
        
        # Determine which folder the image is in
        if 'test_assets' in generated_image_path:
            folder = app.config['TEST_ASSETS']
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

if __name__ == '__main__':
    app.run(debug=True)
