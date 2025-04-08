"""
USES PHOT.AI API TO CREATE IMAGES FROM IMAGES USING PHOT.AI API
Visit https://docs.phot.ai/ for documentation.
"""

import time
import requests

 
phot_api_key = "67f563b055c8422c2d6a4fa5_f16b7eeb2aa1b3533560_apyhitools"


def get_order_id(phot_api_key, image_mode, source_url, prompt, guidance_scale, aspect_ratio, num_outputs=1, style_id="hyperrealistic"):

    """
    Send a POST request to the Phot.ai API to create an image. 
    Returns the order_id for the image that is generated.
    """

    headers = {
      'x-api-key': phot_api_key,
      'Content-Type': 'application/json'
    }
    
    url = 'https://prodapi.phot.ai/external/api/v3/user_activity/create-art'

    # image_mode = "OpenPose"
    # source_url = "https://ai-image-editor-wasabi-bucket.apyhi.com/assets/obj_replacer/obj_replacer_6.png"
    # prompt = "A beautiful girl"
    # guidance_scale = 7.5
    # aspect_ratio = "1:1"

    # style_id = "anime"     #Optional
    
    data = {
      'prompt': prompt,
      'image_mode': image_mode,
      'source_url': source_url,
      'guidance_scale': guidance_scale,
      'aspect_ratio': aspect_ratio,
      'num_outputs': num_outputs  # Add outputs parameter with integer value
    }
    
    if style_id:
        studio_options = {"style": [style_id]}
        data['studio_options'] = studio_options
    
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200:
        print(response.json())

        print('='*50)
        print(f"The order id is: {response.json()['data']['order_id']}")
        return response.json()['data']['order_id']
    else:
        print(f"Error: {response.status_code} - {response.text}")
        # Return None or raise an exception when the request fails
        raise Exception(f"Failed to create image: {response.text}")

def get_img_url(phot_api_key, order_id):
    """
    Send a GET request to the Phot.ai API to get the image URL.
    Returns the image URL if the order is ready, else, returns None."""

    
    # order_id = "e2365748-0e71-465f-8199-7527d4bea41e"
    
    url = f"https://prodapi.phot.ai/external/api/v1/user_activity/order-status?order_id={order_id}"
    
    payload={}
    headers = {'x-api-key': phot_api_key}
    
    response = requests.get(url=url, headers=headers, data=payload)

    if response.status_code == 200:
        print(response.json())
    else:
        print(f"Error: {response.status_code} - {response.text}")

    #If 'order_status' == "order_complete", return the image URL
    if response.json()['order_status'] == "order_complete":
        print('='*50)
        print(f"The image url is: {response.json()['output_urls'][0]}")

        return response.json()['output_urls'][0]
    else:
        print('='*50)
        print(f"The image order ({order_id}) is not ready yet. Please try again later.")
        return None

def main_img2img(phot_api_key, image_mode, source_url, prompt, guidance_scale, aspect_ratio, num_outputs,style_id=None):
    """
    Main function to create an image, and get the image URL.
    Returns the image URL.
    """

    try:
        order_id = get_order_id(phot_api_key, image_mode, source_url, prompt, guidance_scale, aspect_ratio, num_outputs,style_id)

        img_url = get_img_url(phot_api_key, order_id)

        #Wait until the image is ready
        for i in range(20):
            if img_url == None:
                time.sleep(5)
                img_url = get_img_url(phot_api_key, order_id)
            else:
                break
        
        return img_url
    except Exception as e:
        print(f"Error in main_img2img: {e}")
        return None


main_img2img(phot_api_key, image_mode = "OpenPose", source_url = "https://www.pbs.org/wnet/nature/files/2014/10/Monkey-Main.jpg", prompt = "Make the monkey eat banana", guidance_scale = 7, aspect_ratio="16:9", num_outputs=1 ,style_id="hyperrealistic")