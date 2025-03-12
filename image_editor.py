import os
import cv2
import numpy as np
from PIL import Image
from pathlib import Path

def remove_watermark(image_path):
    """
    Removes the 'pollinations.ai' watermark from the bottom right corner of an image.
    Uses multiple techniques to ensure complete watermark removal.
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        str: Path to the processed image without watermark
    """
    try:
        # Check if the file exists
        if not os.path.exists(image_path):
            print(f"Error: Image file {image_path} not found.")
            return image_path
            
        # Create output directory if it doesn't exist
        output_dir = Path("processed_images")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate output filename
        filename = os.path.basename(image_path)
        output_path = str(output_dir / filename)
        
        # Open the image using OpenCV (which is better for pixel manipulation)
        img = cv2.imread(image_path)
        if img is None:
            print(f"Error: Could not read image {image_path}")
            return image_path
            
        # Get image dimensions
        height, width = img.shape[:2]
        
        # Define the region of interest (bottom right corner where watermark is located)
        # Increase the ROI size to ensure we capture the entire watermark
        roi_height = int(height * 0.12)  # Increased from 8% to 12% of image height
        roi_width = int(width * 0.35)    # Increased from 25% to 35% of image width
        
        # Extract the region of interest
        roi = img[height-roi_height:height, width-roi_width:width]
        
        # Create a mask for the watermark area
        mask = np.zeros(roi.shape[:2], dtype=np.uint8)
        
        # Convert ROI to grayscale for processing
        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # Apply multiple techniques to detect the watermark
        
        # 1. Adaptive thresholding for better text detection in varying backgrounds
        adaptive_thresh = cv2.adaptiveThreshold(
            roi_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # 2. Edge detection to find text boundaries
        edges = cv2.Canny(roi_gray, 100, 200)
        
        # 3. Standard thresholding with multiple values to catch different brightness levels
        _, thresh1 = cv2.threshold(roi_gray, 180, 255, cv2.THRESH_BINARY)
        _, thresh2 = cv2.threshold(roi_gray, 200, 255, cv2.THRESH_BINARY)
        _, thresh3 = cv2.threshold(roi_gray, 220, 255, cv2.THRESH_BINARY)
        
        # Combine the different masks
        combined_mask = cv2.bitwise_or(adaptive_thresh, edges)
        combined_mask = cv2.bitwise_or(combined_mask, thresh1)
        combined_mask = cv2.bitwise_or(combined_mask, thresh2)
        combined_mask = cv2.bitwise_or(combined_mask, thresh3)
        
        # Find contours in the combined mask
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter contours by size and shape to find text-like shapes
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 5:  # Reduced minimum area threshold to catch smaller parts of the watermark
                # Calculate aspect ratio to identify text-like shapes
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = float(w) / h if h > 0 else 0
                
                # Text typically has aspect ratios between 0.1 and 10
                if 0.1 < aspect_ratio < 10:
                    cv2.drawContours(mask, [contour], -1, 255, -1)
        
        # Apply morphological operations to ensure complete coverage
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=3)  # Increased iterations
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)  # Close gaps
        
        # Create a full-size mask for the entire image
        full_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        full_mask[height-roi_height:height, width-roi_width:width] = mask
        
        # Use inpainting with a larger radius for better blending
        result = cv2.inpaint(img, full_mask, 5, cv2.INPAINT_TELEA)
        
        # Additional step: blend the inpainted area with surrounding pixels for smoother transition
        blended = result.copy()
        blur_region = cv2.GaussianBlur(result[height-roi_height:height, width-roi_width:width], (5, 5), 0)
        alpha = 0.7  # Blending factor
        blended[height-roi_height:height, width-roi_width:width] = \
            cv2.addWeighted(result[height-roi_height:height, width-roi_width:width], 
                           alpha, blur_region, 1-alpha, 0)
        
        # Save the processed image
        cv2.imwrite(output_path, blended)
        
        print(f"Watermark removed successfully. Saved to {output_path}")
        return output_path
        
    except Exception as e:
        print(f"Error removing watermark: {e}")
        return image_path  # Return original path if processing fails


def process_image(image_path):
    """
    Main function to process an image by removing the watermark.
    This is the function that should be called from other modules.
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        str: Path to the processed image
    """
    if not image_path or 'placeholder' in image_path:
        # Don't process placeholder images
        return image_path
        
    return remove_watermark(image_path)
