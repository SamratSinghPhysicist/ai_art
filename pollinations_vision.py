import requests
import base64
import os
from PIL import Image
import io
import json
import re

def analyze_image_with_pollinations(image_path, detailed_analysis=True):
    """
    Analyzes an image using Pollinations.ai Vision API to extract advanced features
    and insights that can enhance the reference image analysis.
    
    Args:
        image_path (str): Path to the image file to analyze
        detailed_analysis (bool): Whether to request a detailed analysis or a basic one
        
    Returns:
        dict: Dictionary containing AI-powered analysis results
    """
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return None
        
    try:
        # Read the image and encode it as base64
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
        
        # Create a more detailed prompt for comprehensive analysis
        if detailed_analysis:
            analysis_prompt = (
                "Analyze this image in detail as if you were a professional thumbnail designer and provide the following information:\n"
                "1. Main subject: Describe the main subject and focal point in detail\n"
                "2. Visual elements: List all key visual elements, objects, and their arrangement\n"
                "3. Color analysis: Analyze the color palette, dominant colors, color harmony, and emotional impact of colors\n"
                "4. Lighting: Describe the lighting direction, quality, mood, and any special lighting effects\n"
                "5. Composition: Analyze the composition technique, balance, focal points, and visual flow\n"
                "6. Style and techniques: Identify the artistic style, photographic/design techniques used\n"
                "7. Emotional impact: Describe the mood, atmosphere, and emotional response the image evokes\n"
                "8. Thumbnail effectiveness: Assess how effective this would be as a YouTube thumbnail and why\n"
                "9. Improvement suggestions: Suggest specific ways to make this image more engaging as a thumbnail\n"
                "10. Keywords: List 10-15 specific keywords that best describe this image\n\n"
                "Format your response as a structured JSON with these categories. Be extremely detailed and specific."
            )
        else:
            # Basic analysis for faster processing
            analysis_prompt = (
                "Describe this image concisely, focusing on:\n"
                "1. Main subject\n"
                "2. Key visual elements\n"
                "3. Color palette and mood\n"
                "4. Overall style\n"
                "Format your response as a structured JSON."
            )
            
        # Prepare the API request to Pollinations.ai Vision API using the OpenAI-compatible endpoint
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
            "model": "openai-large"  # Using openai-large model which supports vision capabilities
        })
        
        # Process the response
        if response.status_code == 200:
            result = response.json()
            ai_analysis = result['choices'][0]['message']['content']
            
            # Try to parse the JSON response if it's in JSON format
            try:
                # Extract JSON from the response if it's embedded in text
                json_match = re.search(r'```json\n(.+?)\n```', ai_analysis, re.DOTALL)
                if json_match:
                    ai_analysis = json_match.group(1)
                    print("Extracted JSON from code block")
                
                # Try to find JSON in the text even if not properly formatted with code blocks
                if not json_match:
                    json_match = re.search(r'\{.*\}', ai_analysis, re.DOTALL)
                    if json_match:
                        ai_analysis = json_match.group(0)
                        print("Extracted JSON from text")
                
                # Clean up any potential issues in the JSON string
                ai_analysis = ai_analysis.replace('\\n', ' ').replace('\\', '')
                
                # Try to parse the JSON
                analysis_dict = json.loads(ai_analysis)
                print("Successfully parsed JSON response")
                return analysis_dict
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {e}")
                # If not valid JSON, return the raw text analysis
                return {"raw_analysis": ai_analysis}
        else:
            print(f"Error from Pollinations API: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error analyzing image with Pollinations Vision API: {e}")
        return None

def extract_ai_insights(ai_analysis):
    """
    Extracts structured insights from the AI analysis to enhance the reference image analysis.
    
    Args:
        ai_analysis (dict): The raw AI analysis from Pollinations Vision API
        
    Returns:
        dict: Structured insights that can be integrated with the existing analysis
    """
    if not ai_analysis:
        return {}
        
    # Initialize the insights dictionary with more comprehensive fields
    insights = {
        'ai_subject_description': '',
        'ai_detected_objects': [],
        'ai_style_description': '',
        'ai_color_analysis': '',
        'ai_composition_insights': '',
        'ai_mood': '',
        'ai_lighting': '',
        'ai_thumbnail_effectiveness': '',
        'ai_improvement_suggestions': '',
        'ai_keywords': [],
        'ai_emotional_impact': ''
    }
    
    # If we have raw analysis text instead of structured data
    if 'raw_analysis' in ai_analysis:
        raw_text = ai_analysis['raw_analysis']
        
        # Extract insights using text parsing
        if 'subject' in raw_text.lower():
            insights['ai_subject_description'] = extract_section(raw_text, 'subject')
            
        if 'object' in raw_text.lower() or 'element' in raw_text.lower():
            objects_text = extract_section(raw_text, 'object') or extract_section(raw_text, 'element')
            if objects_text:
                insights['ai_detected_objects'] = [obj.strip() for obj in objects_text.split(',')]
            
        if 'style' in raw_text.lower() or 'technique' in raw_text.lower():
            insights['ai_style_description'] = extract_section(raw_text, 'style') or extract_section(raw_text, 'technique')
            
        if 'color' in raw_text.lower():
            insights['ai_color_analysis'] = extract_section(raw_text, 'color')
            
        if 'composition' in raw_text.lower():
            insights['ai_composition_insights'] = extract_section(raw_text, 'composition')
            
        if 'mood' in raw_text.lower() or 'emotion' in raw_text.lower():
            insights['ai_mood'] = extract_section(raw_text, 'mood') or extract_section(raw_text, 'emotion')
            
        if 'lighting' in raw_text.lower() or 'light' in raw_text.lower():
            insights['ai_lighting'] = extract_section(raw_text, 'lighting') or extract_section(raw_text, 'light')
            
        if 'thumbnail' in raw_text.lower() or 'effectiveness' in raw_text.lower():
            insights['ai_thumbnail_effectiveness'] = extract_section(raw_text, 'thumbnail') or extract_section(raw_text, 'effectiveness')
            
        if 'improvement' in raw_text.lower() or 'suggestion' in raw_text.lower():
            insights['ai_improvement_suggestions'] = extract_section(raw_text, 'improvement') or extract_section(raw_text, 'suggestion')
            
        if 'keyword' in raw_text.lower():
            keywords_text = extract_section(raw_text, 'keyword')
            if keywords_text:
                insights['ai_keywords'] = [kw.strip() for kw in keywords_text.split(',')]
                
        if 'emotional' in raw_text.lower() or 'impact' in raw_text.lower():
            insights['ai_emotional_impact'] = extract_section(raw_text, 'emotional') or extract_section(raw_text, 'impact')
    else:
        # Process structured JSON response
        # Map the AI analysis fields to our insights structure
        field_mappings = {
            'main_subject': 'ai_subject_description',
            'visual_elements': 'ai_detected_objects',
            'style_and_techniques': 'ai_style_description',
            'style': 'ai_style_description',
            'color_analysis': 'ai_color_analysis',
            'color_palette': 'ai_color_analysis',
            'composition': 'ai_composition_insights',
            'mood': 'ai_mood',
            'emotional_impact': 'ai_emotional_impact',
            'lighting': 'ai_lighting',
            'thumbnail_effectiveness': 'ai_thumbnail_effectiveness',
            'improvement_suggestions': 'ai_improvement_suggestions',
            'keywords': 'ai_keywords'
        }
        
        # Process each field in the AI analysis
        for source_field, target_field in field_mappings.items():
            if source_field in ai_analysis:
                insights[target_field] = ai_analysis[source_field]
    
    return insights

def extract_section(text, keyword):
    """
    Helper function to extract a section from unstructured text based on a keyword.
    
    Args:
        text (str): The text to search in
        keyword (str): The keyword to search for
        
    Returns:
        str: The extracted section
    """
    import re
    pattern = re.compile(f".*{keyword}.*?[:\-]\s*(.*?)(?:\n\n|\n[A-Z]|$)", re.IGNORECASE | re.DOTALL)
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return ""