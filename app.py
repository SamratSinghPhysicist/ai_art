from image_generator import main_image_function

GEMINI_API_KEY = "AIzaSyA0RYI9KRrNLi6KaX4g49UJD4G5YBEb6II"

def main(video_description, testMode, GEMINI_API_KEY):
    print("Generating Image...")
    print("This may take upto 1 minute...")
    print("Please wait...")
    generated_image_path = main_image_function(video_description, testMode, GEMINI_API_KEY)
    print("=" * 50)
    print("Image Generated Successfully! \n")

    print(f"Generated image is saved in: {generated_image_path}")

if __name__ == '__main__':
    video_description = input("Enter a consise video description or thumbnail details to generate a thumbnail for your youtube video: ")
    main(video_description, False, GEMINI_API_KEY)