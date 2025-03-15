import os
import cv2
import numpy as np
from PIL import Image
import colorsys
from collections import Counter
import math
from scipy.stats import entropy
from skimage.feature import graycomatrix, graycoprops
from skimage.measure import shannon_entropy

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
        
        # NEW: Analyze texture
        texture = analyze_texture(img_rgb)
        
        # NEW: Detect objects
        objects = detect_objects(img)
        
        # NEW: Classify scene
        scene = classify_scene(img_rgb)
        
        # NEW: Analyze color harmony
        color_harmony = analyze_color_harmony(dominant_colors)
        
        # NEW: Get AI-powered analysis using Pollinations Vision API
        ai_insights = {}
        try:
            # Import dynamically to avoid circular imports
            from pollinations_vision import analyze_image_with_pollinations, extract_ai_insights
            
            # Get AI analysis of the image
            ai_analysis = analyze_image_with_pollinations(image_path)
            
            # Extract structured insights from the AI analysis
            if ai_analysis:
                ai_insights = extract_ai_insights(ai_analysis)
                print(f"Successfully obtained AI insights for image: {image_path}")
                
                # Pass AI-detected objects to the object detection function
                if 'ai_detected_objects' in ai_insights and ai_insights['ai_detected_objects']:
                    objects = detect_objects(img, ai_insights['ai_detected_objects'])
                
                # Pass AI style description to the style analysis function
                if 'ai_style_description' in ai_insights and ai_insights['ai_style_description']:
                    # Make sure style is updated as a dictionary, not a string
                    style_result = analyze_style(img_rgb, brightness, contrast, dominant_colors, ai_insights['ai_style_description'])
                    if isinstance(style_result, dict):
                        style = style_result
        except Exception as ai_err:
            print(f"Error getting AI insights (continuing with traditional analysis): {ai_err}")
        
        # Compile results
        analysis_results = {
            'dimensions': {'width': width, 'height': height},
            'dominant_colors': dominant_colors,
            'composition': composition,
            'brightness': brightness,
            'contrast': contrast,
            'has_faces': has_faces,
            'face_count': face_count,
            'style': style,
            'texture': texture,
            'objects': objects,
            'scene': scene,
            'color_harmony': color_harmony,
            'ai_insights': ai_insights
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
        
    # Calculate brightness histogram for more detailed analysis
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist.flatten() / hist.sum()  # Normalize
    
    # Calculate high-key and low-key metrics
    high_key = np.sum(hist[192:]) / np.sum(hist)  # Proportion of bright pixels
    low_key = np.sum(hist[:64]) / np.sum(hist)    # Proportion of dark pixels
    mid_tones = 1 - high_key - low_key            # Proportion of mid-tones
    
    return {
        'value': brightness_level,
        'category': brightness_category,
        'high_key': float(high_key),
        'low_key': float(low_key),
        'mid_tones': float(mid_tones)
    }, {
        'value': contrast_level,
        'category': contrast_category
    }

def classify_scene(img_rgb):
    """
    Classify the scene type in the image.
    
    Args:
        img_rgb (numpy.ndarray): RGB image array
        
    Returns:
        dict: Scene classification results
    """
    # Convert to HSV for better color analysis
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
    
    # Calculate color histograms
    h_hist = cv2.calcHist([hsv], [0], None, [180], [0, 180])
    s_hist = cv2.calcHist([hsv], [1], None, [256], [0, 256])
    v_hist = cv2.calcHist([hsv], [2], None, [256], [0, 256])
    
    # Normalize histograms
    h_hist = h_hist.flatten() / h_hist.sum()
    s_hist = s_hist.flatten() / s_hist.sum()
    v_hist = v_hist.flatten() / v_hist.sum()
    
    # Color range definitions
    # Hue ranges for common colors
    blue_range = (90, 130)   # Sky, water
    green_range = (35, 85)   # Vegetation, nature
    red_range = (0, 10)      # Red objects, sunset
    red_range2 = (170, 180)  # Red objects (wrapping around)
    
    # Calculate color proportions
    blue_prop = np.sum(h_hist[blue_range[0]:blue_range[1]])
    green_prop = np.sum(h_hist[green_range[0]:green_range[1]])
    red_prop = np.sum(h_hist[red_range[0]:red_range[1]]) + np.sum(h_hist[red_range2[0]:red_range2[1]])
    
    # Calculate saturation and value properties
    high_sat = np.sum(s_hist[128:]) / np.sum(s_hist)  # High saturation proportion
    low_sat = np.sum(s_hist[:64]) / np.sum(s_hist)    # Low saturation proportion
    high_val = np.sum(v_hist[192:]) / np.sum(v_hist)  # High value proportion
    low_val = np.sum(v_hist[:64]) / np.sum(v_hist)    # Low value proportion
    
    # Scene classification logic
    scene_type = "unknown"
    scene_confidence = 0.5  # Default confidence
    scene_attributes = []
    
    # Outdoor natural scene detection
    if green_prop > 0.2 and blue_prop > 0.15:
        scene_type = "outdoor_nature"
        scene_confidence = min(green_prop + blue_prop, 0.9)
        scene_attributes.append("natural")
        if green_prop > 0.3:
            scene_attributes.append("vegetation_rich")
        if blue_prop > 0.3:
            scene_attributes.append("sky_visible")
    
    # Urban scene detection
    elif blue_prop < 0.15 and green_prop < 0.15 and high_sat < 0.3:
        scene_type = "urban"
        scene_confidence = 0.6 + (low_sat * 0.3)
        scene_attributes.append("man_made")
        if low_val > 0.3:
            scene_attributes.append("dark_urban")
    
    # Indoor scene detection
    elif low_sat > 0.4 and blue_prop < 0.1 and green_prop < 0.1:
        scene_type = "indoor"
        scene_confidence = 0.5 + (low_sat * 0.4)
        scene_attributes.append("interior")
        if high_val > 0.4:
            scene_attributes.append("well_lit")
        else:
            scene_attributes.append("dimly_lit")
    
    # Sunset/sunrise detection
    elif red_prop > 0.15 and blue_prop > 0.1 and high_sat > 0.3:
        scene_type = "sunset_sunrise"
        scene_confidence = 0.5 + (red_prop * 0.5)
        scene_attributes.append("dramatic_sky")
        scene_attributes.append("warm_tones")
    
    # Night scene detection
    elif low_val > 0.5 and low_sat > 0.3:
        scene_type = "night"
        scene_confidence = 0.5 + (low_val * 0.4)
        scene_attributes.append("dark")
        if high_sat > 0.2:
            scene_attributes.append("artificial_lighting")
    
    # Beach/water scene detection
    elif blue_prop > 0.3 and high_val > 0.4 and high_sat < 0.4:
        scene_type = "water"
        scene_confidence = 0.5 + (blue_prop * 0.4)
        scene_attributes.append("bright")
        scene_attributes.append("open")
    
    # Studio/portrait scene detection
    elif low_sat > 0.5 and high_val > 0.3:
        scene_type = "studio"
        scene_confidence = 0.5 + (low_sat * 0.3)
        scene_attributes.append("controlled_lighting")
        scene_attributes.append("neutral_background")
    
    return {
        'type': scene_type,
        'confidence': float(scene_confidence),
        'attributes': scene_attributes,
        'color_distribution': {
            'blue': float(blue_prop),
            'green': float(green_prop),
            'red': float(red_prop),
            'high_saturation': float(high_sat),
            'low_saturation': float(low_sat),
            'high_value': float(high_val),
            'low_value': float(low_val)
        }
    }

def analyze_texture(img_rgb):
    """
    Analyze the texture characteristics of the image.
    
    Args:
        img_rgb (numpy.ndarray): RGB image array
        
    Returns:
        dict: Texture analysis results with enhanced texture features
    """
    # Convert to grayscale for texture analysis
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    
    # Resize for faster processing if needed
    max_dim = 512
    h, w = gray.shape
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)))
    
    # Calculate texture entropy (measure of randomness)
    texture_entropy = shannon_entropy(gray)
    
    # Calculate GLCM (Gray-Level Co-occurrence Matrix) properties
    distances = [1, 3, 5]  # Pixel distances
    angles = [0, np.pi/4, np.pi/2, 3*np.pi/4]  # Angles (0, 45, 90, 135 degrees)
    
    # Normalize gray levels to reduce computation
    gray_norm = (gray / 16).astype(np.uint8)
    
    # Calculate GLCM
    glcm = graycomatrix(gray_norm, distances, angles, 16, symmetric=True, normed=True)
    
    # Calculate GLCM properties
    contrast = graycoprops(glcm, 'contrast').mean()
    dissimilarity = graycoprops(glcm, 'dissimilarity').mean()
    homogeneity = graycoprops(glcm, 'homogeneity').mean()
    energy = graycoprops(glcm, 'energy').mean()
    correlation = graycoprops(glcm, 'correlation').mean()
    
    # Calculate edge density using Canny edge detector with multiple thresholds
    edges_low = cv2.Canny(gray, 30, 100)
    edges_high = cv2.Canny(gray, 100, 200)
    edge_density_low = np.sum(edges_low > 0) / (gray.shape[0] * gray.shape[1])
    edge_density_high = np.sum(edges_high > 0) / (gray.shape[0] * gray.shape[1])
    edge_density = np.sum(cv2.Canny(gray, 50, 150) > 0) / (gray.shape[0] * gray.shape[1])
    
    # Calculate gradient magnitude for texture strength
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)
    texture_strength = np.mean(gradient_magnitude)
    
    # Calculate local binary pattern for texture pattern analysis
    from skimage.feature import local_binary_pattern
    radius = 3
    n_points = 8 * radius
    lbp = local_binary_pattern(gray, n_points, radius, method='uniform')
    lbp_hist, _ = np.histogram(lbp, bins=n_points+2, range=(0, n_points+2), density=True)
    lbp_uniformity = np.sum(lbp_hist**2)  # Higher value means more uniform texture
    
    # Calculate frequency domain features using FFT
    f_transform = np.fft.fft2(gray)
    f_shift = np.fft.fftshift(f_transform)
    magnitude_spectrum = 20 * np.log(np.abs(f_shift) + 1)
    
    # Analyze high vs low frequency content
    h, w = magnitude_spectrum.shape
    center_y, center_x = h//2, w//2
    radius = min(center_y, center_x) // 2
    
    # Create masks for low and high frequencies
    y, x = np.ogrid[:h, :w]
    low_freq_mask = ((x - center_x)**2 + (y - center_y)**2) <= radius**2
    high_freq_mask = ((x - center_x)**2 + (y - center_y)**2) > (radius*2)**2
    
    # Calculate energy in different frequency bands
    low_freq_energy = np.sum(magnitude_spectrum * low_freq_mask) / np.sum(low_freq_mask)
    high_freq_energy = np.sum(magnitude_spectrum * high_freq_mask) / np.sum(high_freq_mask)
    freq_ratio = high_freq_energy / low_freq_energy if low_freq_energy > 0 else 0
    
    # Enhanced texture type classification
    if edge_density_high > 0.15 and contrast > 5 and high_freq_energy > low_freq_energy:
        texture_type = "highly_detailed"
    elif edge_density > 0.1 and contrast > 5:
        texture_type = "detailed"
    elif homogeneity > 0.9 and energy > 0.2 and low_freq_energy > high_freq_energy:
        texture_type = "smooth"
    elif correlation > 0.9 and homogeneity < 0.7 and lbp_uniformity > 0.1:
        texture_type = "patterned"
    elif edge_density > 0.05 and energy < 0.1:
        texture_type = "textured"
    elif contrast < 2 and homogeneity > 0.8:
        texture_type = "flat"
    elif texture_entropy > 7.0 and edge_density > 0.08:
        texture_type = "complex"
    elif freq_ratio > 1.5:
        texture_type = "grainy"
    elif lbp_uniformity > 0.2 and edge_density < 0.05:
        texture_type = "uniform"
    else:
        texture_type = "mixed"
    
    # Calculate texture scale (fine vs coarse)
    if high_freq_energy > low_freq_energy * 1.5:
        texture_scale = "fine"
    elif low_freq_energy > high_freq_energy * 1.5:
        texture_scale = "coarse"
    else:
        texture_scale = "medium"
    
    return {
        'type': texture_type,
        'scale': texture_scale,
        'entropy': float(texture_entropy),
        'contrast': float(contrast),
        'homogeneity': float(homogeneity),
        'energy': float(energy),
        'correlation': float(correlation),
        'edge_density': float(edge_density),
        'dissimilarity': float(dissimilarity),
        'texture_strength': float(texture_strength),
        'pattern_uniformity': float(lbp_uniformity),
        'frequency_ratio': float(freq_ratio),
        'high_frequency_energy': float(high_freq_energy),
        'low_frequency_energy': float(low_freq_energy)
    }

def detect_objects(img, ai_detected_objects=None):
    """
    Detect common objects in the image using pre-trained models and AI insights.
    
    Args:
        img (numpy.ndarray): Image array
        ai_detected_objects (list, optional): List of objects detected by AI vision API
        
    Returns:
        dict: Object detection results
    """
    # Initialize results
    objects = {
        'person_likely': False,
        'face_likely': False,
        'text_likely': False,
        'nature_likely': False,
        'building_likely': False,
        'vehicle_likely': False,
        'detected_objects': []
    }
    
    # Detect faces using Haar Cascade
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    
    if len(faces) > 0:
        objects['face_likely'] = True
        objects['person_likely'] = True
        objects['detected_objects'].append('face')
    
    # Detect text using EAST text detector or simple edge-based heuristics
    # For simplicity, we'll use edge detection and contour analysis
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Text often has many small contours close together
    small_contours = [c for c in contours if 10 < cv2.contourArea(c) < 300]
    if len(small_contours) > 50:  # Arbitrary threshold
        objects['text_likely'] = True
        objects['detected_objects'].append('text')
    
    # Color-based detection for nature (green dominant) and sky (blue dominant)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Green detection (for nature/vegetation)
    lower_green = np.array([35, 50, 50])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)
    green_ratio = np.sum(green_mask > 0) / (img.shape[0] * img.shape[1])
    
    if green_ratio > 0.15:  # If more than 15% of the image is green
        objects['nature_likely'] = True
        objects['detected_objects'].append('vegetation')
    
    # Blue detection (for sky)
    lower_blue = np.array([90, 50, 50])
    upper_blue = np.array([130, 255, 255])
    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
    blue_ratio = np.sum(blue_mask > 0) / (img.shape[0] * img.shape[1])
    
    if blue_ratio > 0.15:  # If more than 15% of the image is blue
        objects['detected_objects'].append('sky')
    
    # Detect straight lines for buildings
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=100, maxLineGap=10)
    if lines is not None and len(lines) > 5:
        # Count vertical and horizontal lines
        vertical_lines = 0
        horizontal_lines = 0
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
            if angle < 10 or angle > 170:  # Horizontal
                horizontal_lines += 1
            elif 80 < angle < 100:  # Vertical
                vertical_lines += 1
        
        if vertical_lines > 3 and horizontal_lines > 3:
            objects['building_likely'] = True
            objects['detected_objects'].append('building')
    
    # Incorporate AI-detected objects if available
    if ai_detected_objects:
        # Add AI-detected objects to our list
        for obj in ai_detected_objects:
            if obj.lower() not in [o.lower() for o in objects['detected_objects']]:
                objects['detected_objects'].append(obj.lower())
                
            # Update likelihood flags based on AI detections
            if any(person_term in obj.lower() for person_term in ['person', 'people', 'human', 'man', 'woman', 'child']):
                objects['person_likely'] = True
                
            if any(face_term in obj.lower() for face_term in ['face', 'portrait', 'selfie']):
                objects['face_likely'] = True
                
            if any(text_term in obj.lower() for text_term in ['text', 'writing', 'letter', 'word', 'sign']):
                objects['text_likely'] = True
                
            if any(nature_term in obj.lower() for nature_term in ['tree', 'plant', 'flower', 'grass', 'forest', 'garden', 'nature']):
                objects['nature_likely'] = True
                
            if any(building_term in obj.lower() for building_term in ['building', 'house', 'architecture', 'structure', 'skyscraper']):
                objects['building_likely'] = True
                
            if any(vehicle_term in obj.lower() for vehicle_term in ['car', 'vehicle', 'truck', 'bus', 'motorcycle', 'bicycle']):
                objects['vehicle_likely'] = True
    
    return objects

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

def analyze_color_harmony(dominant_colors):
    """
    Analyze the color harmony of the dominant colors in the image.
    
    Args:
        dominant_colors (list): List of dominant colors in hex format
        
    Returns:
        dict: Color harmony analysis results
    """
    # Convert hex colors to HSV for better analysis
    hsv_colors = []
    for color in dominant_colors[:5]:  # Analyze top 5 colors
        # Convert hex to RGB
        r = int(color[1:3], 16) / 255.0
        g = int(color[3:5], 16) / 255.0
        b = int(color[5:7], 16) / 255.0
        # Convert RGB to HSV
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        hsv_colors.append((h, s, v))
    
    # Calculate average hue, saturation, and value
    avg_h = sum(h for h, _, _ in hsv_colors) / len(hsv_colors) if hsv_colors else 0
    avg_s = sum(s for _, s, _ in hsv_colors) / len(hsv_colors) if hsv_colors else 0
    avg_v = sum(v for _, _, v in hsv_colors) / len(hsv_colors) if hsv_colors else 0
    
    # Determine color temperature
    # Warm colors: red, orange, yellow (hue 0-60 degrees in HSV)
    # Cool colors: green, blue, purple (hue 120-270 degrees in HSV)
    # Convert HSV hue (0-1) to degrees (0-360)
    avg_hue_deg = avg_h * 360
    
    if 0 <= avg_hue_deg <= 30 or 330 <= avg_hue_deg <= 360:
        temperature = "warm"
    elif 180 <= avg_hue_deg <= 270:
        temperature = "cool"
    elif 30 < avg_hue_deg < 60 or 270 < avg_hue_deg < 330:
        temperature = "mixed"
    else:
        temperature = "neutral"
    
    # Analyze color harmony type
    # Collect all hues and find their distribution on the color wheel
    hues = [h for h, _, _ in hsv_colors]
    
    # Convert hues to degrees and sort
    hue_degrees = sorted([h * 360 for h in hues])
    
    # Calculate hue differences (considering the circular nature of the color wheel)
    hue_diffs = []
    for i in range(len(hue_degrees)):
        for j in range(i+1, len(hue_degrees)):
            diff = min(abs(hue_degrees[i] - hue_degrees[j]), 360 - abs(hue_degrees[i] - hue_degrees[j]))
            hue_diffs.append(diff)
    
    # Determine harmony type based on hue differences
    if len(set([int(h * 10) for h in hues])) <= 2:  # Very similar hues
        harmony_type = "monochromatic"
    elif any(abs(diff - 180) < 15 for diff in hue_diffs):  # Complementary (opposite colors)
        harmony_type = "complementary"
    elif any(abs(diff - 120) < 15 for diff in hue_diffs):  # Triadic (three colors equidistant)
        harmony_type = "triadic"
    elif any(abs(diff - 90) < 15 for diff in hue_diffs) or any(abs(diff - 270) < 15 for diff in hue_diffs):  # Square/Tetradic
        harmony_type = "tetradic"
    elif any(abs(diff - 30) < 10 for diff in hue_diffs) or any(abs(diff - 60) < 10 for diff in hue_diffs):  # Analogous
        harmony_type = "analogous"
    else:
        harmony_type = "discordant"
    
    # Calculate harmony score (higher is more harmonious)
    harmony_score = 0.0
    
    if harmony_type == "monochromatic":
        harmony_score = 0.9
    elif harmony_type == "analogous":
        harmony_score = 0.8
    elif harmony_type == "complementary":
        harmony_score = 0.7
    elif harmony_type == "triadic":
        harmony_score = 0.6
    elif harmony_type == "tetradic":
        harmony_score = 0.5
    else:  # discordant
        harmony_score = 0.3
    
    # Adjust score based on saturation and value consistency
    s_std = np.std([s for _, s, _ in hsv_colors])
    v_std = np.std([v for _, _, v in hsv_colors])
    
    # Lower standard deviation means more consistency
    consistency_factor = 1.0 - (s_std + v_std) / 2.0
    harmony_score = harmony_score * 0.7 + consistency_factor * 0.3
    
    return {
        'type': harmony_type,
        'score': float(harmony_score),
        'temperature': temperature,
        'avg_saturation': float(avg_s),
        'avg_value': float(avg_v),
        'consistency': float(consistency_factor)
    }

def analyze_style(img_rgb, brightness, contrast, dominant_colors, ai_style_description=None):
    """
    Analyze the overall style of the image, incorporating AI insights if available.
    
    Args:
        img_rgb (numpy.ndarray): RGB image array
        brightness (dict): Brightness analysis results
        contrast (dict): Contrast analysis results
        dominant_colors (list): List of dominant colors
        ai_style_description (str, optional): Style description from AI vision API
        
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
    
    # Calculate color diversity
    color_diversity = len(set([color[:4] for color in dominant_colors[:5]])) / 5.0
    
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
    elif saturation > 0.6 and color_diversity > 0.8:
        style = "colorful"
    elif brightness['category'] == "dark" and saturation > 0.7:
        style = "rich"
    elif contrast['category'] == "high" and brightness['category'] == "bright":
        style = "bold"
    else:
        style = "mixed"
    
    # Incorporate AI style insights if available
    ai_style_keywords = []
    if ai_style_description:
        # Extract style keywords from AI description
        style_keywords = [
            "photorealistic", "cinematic", "artistic", "abstract", "vintage", 
            "modern", "surreal", "minimalist", "dramatic", "vibrant", "muted", 
            "high-contrast", "low-contrast", "noir", "pastel", "saturated", 
            "desaturated", "moody", "bright", "dark", "warm", "cool", "neutral",
            "professional", "casual", "elegant", "rustic", "futuristic", "retro"
        ]
        
        # Find matching style keywords in AI description
        for keyword in style_keywords:
            if keyword in ai_style_description.lower():
                ai_style_keywords.append(keyword)
        
        # If AI detected a specific style that our algorithm didn't, use it
        if ai_style_keywords and style == "mixed":
            # Use the first detected style keyword as the primary style
            style = ai_style_keywords[0]
    
    return {
        'style': style,
        'saturation': float(saturation),
        'vibrant': vibrant,
        'monochromatic': monochromatic,
        'color_diversity': float(color_diversity),
        'ai_detected_styles': ai_style_keywords
    }