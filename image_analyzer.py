import os
import cv2
import numpy as np
from PIL import Image
import colorsys

def analyze_reference_image(image_path):
    """
    Analyzes a reference image to extract key visual features that can be used
    to guide the image generation process.
    
    Args:
        image_path (str): Path to the reference image file
        
    Returns:
        dict: Dictionary containing extracted features and analysis results
    """
    if not image_path or not os.path.exists(image_path):
        print(f"Reference image not found or not provided: {image_path}")
        return None
        
    try:
        # Read the image using OpenCV
        img = cv2.imread(image_path)
        if img is None:
            print(f"Error: Could not read image {image_path}")
            return None
            
        # Convert to RGB for better color analysis (OpenCV uses BGR)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Get image dimensions
        height, width = img.shape[:2]
        
        # Extract dominant colors
        dominant_colors = extract_dominant_colors(img_rgb)
        
        # Analyze composition
        composition = analyze_composition(img)
        
        # Analyze brightness and contrast
        brightness, contrast = analyze_brightness_contrast(img_rgb)
        
        # Detect if image contains faces
        has_faces, face_count = detect_faces(img)
        
        # Analyze overall style
        style = analyze_style(img_rgb, brightness, contrast, dominant_colors)
        
        # Compile results
        analysis_results = {
            'dimensions': {'width': width, 'height': height},
            'dominant_colors': dominant_colors,
            'composition': composition,
            'brightness': brightness,
            'contrast': contrast,
            'has_faces': has_faces,
            'face_count': face_count,
            'style': style
        }
        
        print(f"Successfully analyzed reference image: {image_path}")
        return analysis_results
        
    except Exception as e:
        print(f"Error analyzing reference image: {e}")
        return None

def extract_dominant_colors(img_rgb, num_colors=5):
    """
    Extract the dominant colors from an image.
    
    Args:
        img_rgb (numpy.ndarray): RGB image array
        num_colors (int): Number of dominant colors to extract
        
    Returns:
        list: List of dominant colors in hex format
    """
    # Reshape the image to be a list of pixels
    pixels = img_rgb.reshape(-1, 3)
    
    # Convert to float for k-means
    pixels = np.float32(pixels)
    
    # Define criteria and apply kmeans
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
    _, labels, centers = cv2.kmeans(pixels, num_colors, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
    
    # Convert back to uint8
    centers = np.uint8(centers)
    
    # Count occurrences of each label
    counts = np.bincount(labels.flatten())
    
    # Sort colors by frequency
    sorted_indices = np.argsort(counts)[::-1]
    sorted_centers = centers[sorted_indices]
    
    # Convert to hex colors
    hex_colors = []
    for color in sorted_centers:
        hex_color = '#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2])
        hex_colors.append(hex_color)
    
    return hex_colors

def analyze_composition(img):
    """
    Analyze the composition of the image (rule of thirds, centered, etc.)
    
    Args:
        img (numpy.ndarray): Image array
        
    Returns:
        dict: Composition analysis results
    """
    height, width = img.shape[:2]
    
    # Convert to grayscale for edge detection
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Detect edges
    edges = cv2.Canny(blurred, 50, 150)
    
    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Find the largest contour (likely the main subject)
    if contours:
        largest_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(largest_contour)
        
        # Calculate center of the main subject
        subject_center_x = x + w/2
        subject_center_y = y + h/2
        
        # Calculate relative position (0-1)
        rel_x = subject_center_x / width
        rel_y = subject_center_y / height
        
        # Determine composition type
        if 0.3 <= rel_x <= 0.7 and 0.3 <= rel_y <= 0.7:
            composition_type = "centered"
        elif (abs(rel_x - 1/3) < 0.1 or abs(rel_x - 2/3) < 0.1) and \
             (abs(rel_y - 1/3) < 0.1 or abs(rel_y - 2/3) < 0.1):
            composition_type = "rule_of_thirds"
        else:
            composition_type = "other"
            
        return {
            'type': composition_type,
            'subject_position': {'x': rel_x, 'y': rel_y}
        }
    else:
        return {'type': 'unknown', 'subject_position': None}

def analyze_brightness_contrast(img_rgb):
    """
    Analyze the brightness and contrast of the image.
    
    Args:
        img_rgb (numpy.ndarray): RGB image array
        
    Returns:
        tuple: (brightness_level, contrast_level)
    """
    # Convert to grayscale for brightness analysis
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    
    # Calculate mean brightness (0-255)
    mean_brightness = np.mean(gray)
    
    # Normalize to 0-1 range
    brightness_level = mean_brightness / 255.0
    
    # Calculate standard deviation for contrast
    std_dev = np.std(gray)
    
    # Normalize contrast (max possible std dev is 127.5 for a grayscale image)
    contrast_level = std_dev / 127.5
    
    # Categorize brightness
    if brightness_level < 0.3:
        brightness_category = "dark"
    elif brightness_level < 0.7:
        brightness_category = "medium"
    else:
        brightness_category = "bright"
        
    # Categorize contrast
    if contrast_level < 0.3:
        contrast_category = "low"
    elif contrast_level < 0.6:
        contrast_category = "medium"
    else:
        contrast_category = "high"
    
    return {
        'value': brightness_level,
        'category': brightness_category
    }, {
        'value': contrast_level,
        'category': contrast_category
    }

def detect_faces(img):
    """
    Detect faces in the image.
    
    Args:
        img (numpy.ndarray): Image array
        
    Returns:
        tuple: (has_faces, face_count)
    """
    # Load the pre-trained face detector
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    # Convert to grayscale for face detection
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Detect faces
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    
    face_count = len(faces)
    has_faces = face_count > 0
    
    return has_faces, face_count

def analyze_style(img_rgb, brightness, contrast, dominant_colors):
    """
    Analyze the overall style of the image.
    
    Args:
        img_rgb (numpy.ndarray): RGB image array
        brightness (dict): Brightness analysis results
        contrast (dict): Contrast analysis results
        dominant_colors (list): List of dominant colors
        
    Returns:
        dict: Style analysis results
    """
    # Calculate color saturation
    hsv_img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    saturation = np.mean(hsv_img[:, :, 1]) / 255.0
    
    # Determine if colors are vibrant
    vibrant = saturation > 0.5 and contrast['value'] > 0.4
    
    # Determine if image is monochromatic
    # Convert dominant colors to HSV for better hue comparison
    hsv_colors = []
    for color in dominant_colors[:3]:  # Check top 3 colors
        # Convert hex to RGB
        r = int(color[1:3], 16) / 255.0
        g = int(color[3:5], 16) / 255.0
        b = int(color[5:7], 16) / 255.0
        # Convert RGB to HSV
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        hsv_colors.append((h, s, v))
    
    # Check if hues are similar
    hue_diffs = []
    for i in range(len(hsv_colors)):
        for j in range(i+1, len(hsv_colors)):
            # Calculate the smallest difference between hues (considering the circular nature of hue)
            diff = min(abs(hsv_colors[i][0] - hsv_colors[j][0]), 
                       1 - abs(hsv_colors[i][0] - hsv_colors[j][0]))
            hue_diffs.append(diff)
    
    monochromatic = all(diff < 0.1 for diff in hue_diffs) if hue_diffs else False
    
    # Determine style based on analysis
    if vibrant and contrast['category'] == "high":
        style = "vibrant"
    elif brightness['category'] == "dark" and contrast['category'] == "high":
        style = "dramatic"
    elif monochromatic:
        style = "monochromatic"
    elif brightness['category'] == "bright" and saturation < 0.3:
        style = "minimalist"
    elif brightness['category'] == "medium" and contrast['category'] == "medium":
        style = "balanced"
    else:
        style = "mixed"
    
    return {
        'style': style,
        'saturation': saturation,
        'vibrant': vibrant,
        'monochromatic': monochromatic
    }