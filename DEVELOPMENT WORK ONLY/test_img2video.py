import argparse
import os
import time
from img2video_stability import generate_video_from_image


def main():
    """
    Test the image-to-video generation functionality using the Stability API.
    """
    parser = argparse.ArgumentParser(description="Test Image-to-Video generation with Stability AI")
    parser.add_argument("--image", required=True, help="Path to the input image")
    parser.add_argument("--output", default="./processed_videos", help="Output directory for the video")
    parser.add_argument("--seed", type=int, default=0, help="Seed for generation (0 = random)")
    parser.add_argument("--cfg_scale", type=float, default=1.5, help="How strongly the video adheres to the image (0-10)")
    parser.add_argument("--motion", type=int, default=127, help="Amount of motion (1-255)")
    parser.add_argument("--timeout", type=int, default=600, help="Maximum time to wait for generation in seconds")
    
    args = parser.parse_args()
    
    # Ensure the image file exists
    if not os.path.exists(args.image):
        print(f"Error: Image file '{args.image}' not found")
        return 1
    
    print(f"Starting image-to-video generation with Stability AI")
    print(f"Input image: {args.image}")
    print(f"Output directory: {args.output}")
    print(f"Parameters:")
    print(f"  - Seed: {args.seed} (0 means random)")
    print(f"  - CFG Scale: {args.cfg_scale}")
    print(f"  - Motion Bucket ID: {args.motion}")
    print(f"  - Timeout: {args.timeout} seconds")
    print("-" * 50)
    
    # Start timing
    start_time = time.time()
    
    # Run the generation
    video_path, generation_id = generate_video_from_image(
        image_path=args.image,
        output_directory=args.output,
        seed=args.seed,
        cfg_scale=args.cfg_scale,
        motion_bucket_id=args.motion,
        timeout=args.timeout
    )
    
    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    
    if video_path:
        print(f"\nSuccess! Video generated in {elapsed_time:.2f} seconds")
        print(f"Video saved to: {video_path}")
        print(f"Generation ID: {generation_id}")
        return 0
    else:
        print(f"\nError: Video generation failed after {elapsed_time:.2f} seconds")
        if generation_id:
            print(f"Generation ID: {generation_id}")
            print("You may check the status manually later using this ID")
        return 1


if __name__ == "__main__":
    exit(main()) 