
import requests
import time
import json
import uuid
from models import QwenApiKey



def find_video_url_in_response(data):
    """Finds the video URL in the Qwen API response."""
    try:
        # Primary location: The 'content' field of the success response.
        if data.get('task_status') == 'success' and isinstance(data.get('content'), str) and data['content'].startswith('http'):
            return data['content']

        # The URL is also often in the `output` field of the `task` dictionary
        if data.get('task') and data['task'].get('output') and data['task']['output'].get('video_url'):
            return data['task']['output']['video_url']
        
        # Fallback for other possible structures
        if data.get('data') and data['data'].get('video_url'):
            return data['data']['video_url']

    except (KeyError, TypeError):
        pass # Ignore errors if keys don't exist

    return None

def generate_qwen_video(prompt, api_key):
    """
    Generates a video using the Qwen API.
    """
    keys = api_key

    BASE_URL = "https://chat.qwen.ai"
    AUTH_TOKEN = keys.get("auth_token")
    CHAT_ID = keys.get("chat_id")
    FID = keys.get("fid")
    CHILDREN_IDS = keys.get("children_ids")
    X_REQUEST_ID = keys.get("x_request_id")

    if not all([AUTH_TOKEN, CHAT_ID, FID, CHILDREN_IDS, X_REQUEST_ID]):
        return {"error": "One or more required Qwen keys are missing from the database."}

    headers = {
        "authorization": f"Bearer {AUTH_TOKEN}",
        "content-type": "application/json",
        "origin": BASE_URL,
        "referer": f"{BASE_URL}/c/{CHAT_ID}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "x-request-id": X_REQUEST_ID
    }

    payload = {
        "stream": False,
        "incremental_output": True,
        "chat_id": CHAT_ID,
        "chat_mode": "normal",
        "model": "qwen3-235b-a22b",
        "parent_id": None,
        "messages": [{
            "fid": str(FID),
            "parentId": None,
            "childrenIds": CHILDREN_IDS,
            "role": "user",
            "content": prompt,
            "user_action": "recommendation",
            "files": [],
            "timestamp": int(time.time()),
            "models": ["qwen3-235b-a22b"],
            "chat_type": "t2v",
            "feature_config": {
                "thinking_enabled": False,
                "output_schema": "phase"
            },
            "extra": {
                "meta": {
                    "subChatType": "t2v"
                }
            },
            "sub_chat_type": "t2v",
            "parent_id": None
        }],
        "timestamp": int(time.time()) + 3,
        "size": "16:9"
    }

    # 1. Initial video generation request
    try:
        print("Initiating Qwen video generation...")
        url = f"{BASE_URL}/api/v2/chat/completions?chat_id={CHAT_ID}"
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        init_response = response.json()
        print("Qwen video generation initiated successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Qwen initial request failed: {e}")
        return {"error": f"Failed to initiate video generation: {e}"}

    # 2. Extract task ID
    try:
        task_id = init_response['data']['messages'][0]['extra']['wanx']['task_id']
        print(f"Extracted task ID: {task_id}")
    except KeyError:
        print(f"Could not extract task_id from response: {init_response}")
        return {"error": "Could not get task ID from Qwen API."}

    # 3. Poll for task status
    print("Polling for video generation status...")
    status_url = f"{BASE_URL}/api/v1/tasks/status/{task_id}"
    max_attempts = 100
    interval = 5

    for attempt in range(max_attempts):
        try:
            time.sleep(interval)
            print(f"Polling attempt {attempt + 1}/{max_attempts}...")
            response = requests.get(status_url, headers=headers)
            response.raise_for_status()
            status_data = response.json()
            print(f"Polling response: {status_data}")

            task_status = status_data.get('task_status')
            if task_status in ['completed', 'success']:
                print("Video generation completed. Parsing final response...")
                video_url = find_video_url_in_response(status_data)

                if video_url:
                    print(f"Successfully extracted video URL: {video_url}")
                    return {"video_url": video_url}
                else:
                    print("Failed to extract video URL from the final response.")
                    return {"error": "Video generation completed, but no video URL found."}
            elif task_status in ['failed', 'error']:
                return {"error": f"Video generation failed: {status_data.get('message', 'Unknown error')}"}

        except requests.exceptions.RequestException as e:
            print(f"Polling request failed: {e}")
            # Continue polling even if one request fails

    return {"error": "Video generation timed out."}

