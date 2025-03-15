import os
import argparse
from pollinations_vision import analyze_image_with_pollinations, extract_ai_insights
from image_generator import generate_image_pollinations_ai, image_generate_prompt_pollinations
from image_analyzer import analyze_reference_image
from image_editor import process_image
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get API key from environment or use default
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II")

def generate_thumbnail_from_reference(reference_image_path, video_description, output_path=None, detailed_analysis=True):
    """
    Generate a thumbnail based on a reference image using Pollinations.ai vision capabilities.
    
    Args:
        reference_image_path (str): Path to the reference image
        video_description (str): Description of the video content
        output_path (str, optional): Path to save the generated thumbnail
        detailed_analysis (bool): Whether to perform detailed analysis of the reference image
        
    Returns:
        str: Path to the generated thumbnail
    """
    if not os.path.exists(reference_image_path):
        print(f"Reference image not found: {reference_image_path}")
        return None
    
    print(f"Analyzing reference image: {reference_image_path}")
    
    # Step 1: Get AI-powered analysis of the reference image using Pollinations Vision API
    ai_analysis = analyze_image_with_pollinations(reference_image_path, detailed_analysis)
    
    if not ai_analysis:
        print("Failed to analyze reference image with Pollinations Vision API. Falling back to basic analysis.")
        # Fall back to traditional image analysis
        reference_image_analysis = analyze_reference_image(reference_image_path)
    else:
        print("Successfully analyzed reference image with Pollinations Vision API.")
        # Extract structured insights from the AI analysis
        ai_insights = extract_ai_insights(ai_analysis)
        
        # Get traditional image analysis
        reference_image_analysis = analyze_reference_image(reference_image_path)
        
        # Integrate AI insights with traditional analysis
        if reference_image_analysis and ai_insights:
            reference_image_analysis['ai_insights'] = ai_insights
            
            # Print some key insights from the analysis
            print("\nKey insights from reference image analysis:")
            if ai_insights.get('ai_subject_description'):
                print(f"Subject: {ai_insights['ai_subject_description'][:100]}...")
            if ai_insights.get('ai_style_description'):
                print(f"Style: {ai_insights['ai_style_description'][:100]}...")
            if ai_insights.get('ai_color_analysis'):
                print(f"Colors: {ai_insights['ai_color_analysis'][:100]}...")
            if ai_insights.get('ai_thumbnail_effectiveness'):
                print(f"Thumbnail effectiveness: {ai_insights['ai_thumbnail_effectiveness'][:100]}...")
    
    # Step 2: Generate an enhanced prompt for the image generation
    print("\nGenerating enhanced prompt based on reference image analysis...")
    enhanced_prompt = image_generate_prompt_pollinations(video_description, GEMINI_API_KEY, reference_image_analysis)
    
    print(f"\nEnhanced prompt: {enhanced_prompt[:150]}...")
    
    # Step 3: Generate the image using Pollinations.ai
    print("\nGenerating thumbnail image...")
    generated_image_path = generate_image_pollinations_ai(enhanced_prompt, False)
    
    # Step 4: Process the image (remove watermark, etc.)
    processed_image_path = process_image(generated_image_path)
    
    # Step 5: Save to output path if specified
    if output_path:
        from shutil import copyfile
        copyfile(processed_image_path, output_path)
        print(f"\nThumbnail saved to: {output_path}")
        return output_path
    
    print(f"\nThumbnail generated at: {processed_image_path}")
    return processed_image_path

def main():
    parser = argparse.ArgumentParser(description='Generate a thumbnail based on a reference image using Pollinations.ai')
    parser.add_argument('reference_image', help='Path to the reference image')
    parser.add_argument('video_description', help='Description of the video content')
    parser.add_argument('--output', '-o', help='Path to save the generated thumbnail')
    parser.add_argument('--basic', '-b', action='store_true', help='Use basic analysis instead of detailed analysis')
    
    args = parser.parse_args()
    
    generate_thumbnail_from_reference(
        args.reference_image,
        args.video_description,
        args.output,
        not args.basic
    )

if __name__ == "__main__":
    main()