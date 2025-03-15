import os
import json
import requests
import base64
import re

def test_pollinations_vision_api(image_path):
    """
    Test the Pollinations Vision API directly to diagnose any issues
    """
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return None
        
    try:
        # Read the image and encode it as base64
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Create a prompt for analysis
        analysis_prompt = (
            "Analyze this image in detail and provide the following information:\n"
            "1. Main subject: Describe the main subject\n"
            "2. Visual elements: List key visual elements\n"
            "3. Color analysis: Analyze the color palette\n"
            "4. Style: Identify the artistic style\n"
            "Format your response as a structured JSON."
        )
            
        # Prepare the API request to Pollinations.ai Vision API
        print("Sending request to Pollinations Vision API...")
        response = requests.post('https://text.pollinations.ai/openai', json={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": analysis_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            "model": "openai-large"  # Using openai-large model which supports vision
        })
        
        # Print response status and headers for debugging
        print(f"Response status code: {response.status_code}")
        print(f"Response headers: {response.headers}")
        
        # Process the response
        if response.status_code == 200:
            result = response.json()
            print("Raw API response:")
            print(json.dumps(result, indent=2))
            
            ai_analysis = result['choices'][0]['message']['content']
            print("\nAI Analysis content:")
            print(ai_analysis)
            
            # Try to parse the JSON response if it's in JSON format
            try:
                # Extract JSON from the response if it's embedded in text
                json_match = re.search(r'```json\n(.+?)\n```', ai_analysis, re.DOTALL)
                if json_match:
                    ai_analysis = json_match.group(1)
                    print("\nExtracted JSON from code block:")
                    print(ai_analysis)
                
                # Try to find JSON in the text even if not properly formatted with code blocks
                if not json_match:
                    json_match = re.search(r'\{.*\}', ai_analysis, re.DOTALL)
                    if json_match:
                        ai_analysis = json_match.group(0)
                        print("\nExtracted JSON from text:")
                        print(ai_analysis)
                    
                analysis_dict = json.loads(ai_analysis)
                print("\nSuccessfully parsed JSON:")
                print(json.dumps(analysis_dict, indent=2))
                return analysis_dict
            except json.JSONDecodeError as e:
                print(f"\nJSON parsing error: {e}")
                # If not valid JSON, return the raw text analysis
                return {"raw_analysis": ai_analysis}
        else:
            print(f"Error from Pollinations API: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error analyzing image with Pollinations Vision API: {e}")
        return None

# Test with a sample image
if __name__ == "__main__":
    # Use a sample image from the reference_images folder
    sample_image = "reference_images/8016c7b2-d491-4530-9fbd-dc6d28989df1_sample1.jpg"
    print(f"Testing with image: {sample_image}")
    result = test_pollinations_vision_api(sample_image)
    
    if result:
        print("\nTest successful! API is working.")
    else:
        print("\nTest failed. API is not working properly.")