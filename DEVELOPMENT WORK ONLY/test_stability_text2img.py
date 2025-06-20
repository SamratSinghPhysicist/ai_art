import os
import argparse
from text2img_stability import generate_image_stability
from PIL import Image

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Test Stability AI text-to-image generation")
    parser.add_argument("--prompt", default="A beautiful sunset over mountains", help="Text prompt for image generation")
    parser.add_argument("--test-mode", action="store_true", help="Use test mode (returns placeholder image)")
    parser.add_argument("--negative-prompt", default="", help="Negative prompt to exclude concepts from the image")
    parser.add_argument("--aspect-ratio", default="16:9", choices=["16:9", "1:1", "21:9", "2:3", "3:2", "4:5", "5:4", "9:16", "9:21"], help="Aspect ratio of the output image")
    parser.add_argument("--seed", type=int, default=0, help="Seed for reproducible results (0 means random)")
    parser.add_argument("--style-preset", choices=["3d-model", "analog-film", "anime", "cinematic", "comic-book", 
                                                  "digital-art", "enhance", "fantasy-art", "isometric", "line-art", 
                                                  "low-poly", "modeling-compound", "neon-punk", "origami", 
                                                  "photographic", "pixel-art", "tile-texture"], 
                         help="Style preset to guide the image model")
    parser.add_argument("--output-format", default="png", choices=["png", "jpeg", "webp"], help="Format of the output image")
    parser.add_argument("--display", action="store_true", help="Display the generated image")
    
    args = parser.parse_args()
    
    print(f"Generating image with prompt: '{args.prompt}'")
    print(f"Test mode: {args.test_mode}")
    
    # Generate the image
    generated_image_path = generate_image_stability(
        prompt=args.prompt,
        testMode=args.test_mode,
        negative_prompt=args.negative_prompt,
        aspect_ratio=args.aspect_ratio,
        seed=args.seed,
        style_preset=args.style_preset,
        output_format=args.output_format
    )
    
    print(f"Image generated and saved to: {generated_image_path}")
    
    # Display the image if requested
    if args.display:
        try:
            img = Image.open(generated_image_path)
            img.show()
        except Exception as e:
            print(f"Failed to display image: {e}")

if __name__ == "__main__":
    main() 