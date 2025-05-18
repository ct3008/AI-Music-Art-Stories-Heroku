# Main code for running tasks (generate image + video)
import time  # Simulating long tasks
import datetime
from redis import Redis
import cloudinary
import cloudinary.uploader
import json
from queue_config import queue, redis_conn
import os
from flask import jsonify, send_file, Flask
from rq import get_current_job
from rq.timeouts import JobTimeoutException
import replicate
import librosa
import numpy as np
from time import sleep
import requests
from helpers import ( #helper functions
    parse_input_data,
    calculate_frames,
    build_transition_strings,
    generate_image_prompts,
    create_deforum_prompt
)

#------------------- Upload/Generate Image -------------------
# Main task being called to generate images
def generate_image_task(data):
    global init_image
    job = get_current_job
    print("Generating image")
    try:
        prompt = data.get('prompt', '')
        api_key = data.get('api_key', '')
        # print(f"USED API KEY GEN: {api_key}")
        api = replicate.Client(api_token=api_key)

        if not prompt:
            return {'error': 'No prompt provided'}  # Return as a dictionary, no jsonify

        # output = api.run(
        #     "lucataco/open-dalle-v1.1:1c7d4c8dec39c7306df7794b28419078cb9d18b9213ab1c21fdc46a1deca0144",
        #     input={
        #         "width": 768,
        #         "height": 768,
        #         "prompt": prompt,
        #         "scheduler": "KarrasDPM",
        #         "num_outputs": 1,
        #         "guidance_scale": 7.5,
        #         "apply_watermark": True,
        #         "negative_prompt": "worst quality, low quality",
        #         "prompt_strength": 0.8,
        #         "num_inference_steps": 40
        #     },
        #     timeout=600
        # )

        # output = api.run(
        #     "stability-ai/stable-diffusion-3.5-large",
        #     input={
        #         "prompt": prompt,
        #         "width": 768,
        #         "height": 768,
        #         "num_outputs": 1,
        #         "guidance_scale": 7.5,
        #         "apply_watermark": True,
        #         "negative_prompt": "worst quality, low quality",
        #         "prompt_strength": 0.8,
        #         "num_inference_steps": 40
        #     }
        # )
        
        output = api.run(
            "black-forest-labs/flux-schnell",
            input={
                "prompt": prompt,
                "go_fast": True,
                "megapixels": "1",
                "num_outputs": 1,
                "aspect_ratio": "1:1",
                "output_format": "webp",
                "output_quality": 80,
                "num_inference_steps": 4
            }
        )
        # Simulate a long-running process, like calling an API
        # output = ["https://png.pngtree.com/png-clipart/20230512/original/pngtree-isolated-front-view-cat-on-white-background-png-image_9158426.png"]
        print("output done: ", output)
        # Simulating a timeout with sleep
        time.sleep(3)  # Adjust this based on your expected task duration

        if output and isinstance(output, list):
            image_url = str(output[0])
            init_image = image_url
            cloudinary_response = cloudinary.uploader.upload(image_url)
            cloudinary_image_url = cloudinary_response.get('secure_url')

            # Save the Cloudinary URL to Redis for later retrieval
            timestamp = time.time()
            public_id = cloudinary_response.get('public_id')
            redis_conn.set(f'image:{timestamp}.{public_id}', cloudinary_image_url)
            redis_conn.hset(f'image_metadata:{public_id}', 'prompt', prompt)
            redis_conn.hset(f'image_metadata:{public_id}', 'timestamp', timestamp)
            print("saving under timestamp: ", timestamp, public_id)

            print('Image uploaded to Cloudinary:', cloudinary_image_url, public_id)
            return {'status': "success", 'output': cloudinary_image_url}

        return {"status": "error", 'error': 'Unexpected output format'}  # Return error message as dict
    except TimeoutError:
        # Handle the timeout error
        print("Task timed out")
        return {"status": "error", 'error': 'Job timeout occurred'}  # Timeout error message
    except Exception as e:
        # Log the actual error and return it as a dictionary
        print(f"Error: {str(e)}")
        return {"status": "error", 'error': str(e)}  # Return error data


def long_running_task(data):
    global init_image
    try:
        job = get_current_job()
        
        print("Long running running")
        api_key = data['api_key']
        print(f"USED API KEY: {api_key}")
        api = replicate.Client(api_token=api_key)
        
        timestamps_scenes = data['timestamps_scenes']
        form_data = data['form_data']
        transitions_data = data['transitions_data']
        song_len = data['song_len']
        motion_mode = data['motion_mode']
        seed = data['seed']
        input_image_url = data.get('input_image_url',"https://raw.githubusercontent.com/ct3008/ct3008.github.io/main/images/isee1.jpeg")

        # Processing the data
        # song_duration, scene_change_times, transition_times, time_intervals, interval_strings, motion_data = parse_input_data(form_data, transitions_data, song_len)
        song_duration, scene_change_times, transition_times, time_intervals, interval_strings, motion_data, og_motion_data= parse_input_data(form_data, transitions_data, song_len)
        final_anim_frames = [0]
        if round(song_len, 2) not in scene_change_times:
            scene_change_times.append(round(song_len, 2))
        
        frame_data, animation_prompts, adjustments = calculate_frames(scene_change_times, interval_strings, motion_data, song_duration, final_anim_frames)
        motion_strings = build_transition_strings(frame_data)
        prompts = generate_image_prompts(form_data, final_anim_frames)

        # Create the Deforum prompt
        if not input_image_url or str(input_image_url).lower() == "none":
            print("No valid input image URL specified. Using default.")
            input_image_url = "https://raw.githubusercontent.com/ct3008/ct3008.github.io/main/images/isee1.jpeg"
        deforum_prompt = create_deforum_prompt(motion_strings, final_anim_frames, motion_mode, prompts, seed, input_image_url)
        
        # Run the API
        output = api.run(
            "deforum-art/deforum-stable-diffusion:1a98303504c7d866d2b198bae0b03237eab82edc1491a5306895d12b0021d6f6",
            input=deforum_prompt
        )
        # output = "https://replicate.delivery/yhqm/fw9VUo7kexv1fowRmtpZyEwCa8HNUef4uWpDsoQuNbW8EHHhC/out.mp4"
        # video_path = download_video_from_url(output)
        filename = data['filename']
        if not filename or not output:
            return jsonify({"error": "Missing audio filename or video URL"}), 40
        
        
        print("output: ", output)
        # time.sleep(12)
        # Compile the response
        if isinstance(output, str):  # It's a URL
            final_output = output
        elif hasattr(output, "url"):  # It's a FileOutput object with a URL
            final_output = output.url
        else:
            raise ValueError(f"Unexpected output type: {type(output)}")
                
        try:
            str_output = str(output)
        except:
            str_output = ""
        response = {
            'timestamps_scenes': timestamps_scenes,
            'form_data': form_data,
            'transitions_data': transitions_data,
            'song_len': song_len,
            'animation_prompts': animation_prompts,
            'motion_prompts': motion_strings,
            'prompts': prompts,
            'output_url': final_output,
            'original_output': str_output,
            'input_image_url': input_image_url,
            'filename': filename,
            'adjustments': adjustments
        }
        
        print("response: ", response)
        for key in ['timestamps_scenes', 'form_data', 'transitions_data']:
            response[key] = response.get(key, None)
            if isinstance(response[key], (list, dict)):
                continue
            elif isinstance(response[key], (np.ndarray, set)):
                response[key] = list(response[key])  # Convert arrays or sets to lists
            elif isinstance(response[key], datetime):
                response[key] = response[key].isoformat()  # Convert datetime to string
            else:
                response[key] = str(response[key])  # Fallback: Convert to string
        print("response after 'fix': ", response)
        return {"status": "success", "output": response}
    except JobTimeoutException:
        # Log or handle the timeout exception here
        return {"status": "error", "error": "Task exceeded maximum timeout value"}
    except Exception as e:
        # because we continue calling
        # Log the error and store the error message in the job metadata
        current_job = get_current_job()
        if current_job:
            current_job.set_status('failed')
            current_job.meta['error'] = str(e)
            current_job.save_meta()
        raise
    # Perform task
    return {"result": "Task completed"}

#------------------- Download and Adjust Video -------------------

def download_video_from_url(video_url, save_path="./downloaded_videos/replicate_video.mp4"):
    response = requests.get(video_url, stream=True)
    if response.status_code == 200:
        with open(save_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        print(f"Video downloaded successfully to {save_path}")
    else:
        raise Exception(f"Failed to download video. Status code: {response.status_code}")
    return save_path

#------------------- Helpers -------------------
def download_prompt(data):
    print("run download_prompt")

    timestamps_scenes = data['timestamps_scenes']
    form_data = data['form_data']
    transitions_data = data['transitions_data']
    song_len = data['song_len']
    motion_mode = data['motion_mode']
    seed = data['seed']
    input_image_url = data.get('input_image_url',"https://raw.githubusercontent.com/ct3008/ct3008.github.io/main/images/isee1.jpeg")

    # Processing the data
    # song_duration, scene_change_times, transition_times, time_intervals, interval_strings, motion_data = parse_input_data(form_data, transitions_data, song_len)
    song_duration, scene_change_times, transition_times, time_intervals, interval_strings, motion_data, og_motion_data= parse_input_data(form_data, transitions_data, song_len)
    final_anim_frames = [0]
    if round(song_len, 2) not in scene_change_times:
        scene_change_times.append(round(song_len, 2))
    
    frame_data, animation_prompts,_ = calculate_frames(scene_change_times, interval_strings, motion_data, song_duration, final_anim_frames)
    motion_strings = build_transition_strings(frame_data)
    prompts = generate_image_prompts(form_data, final_anim_frames)

    # Create the Deforum prompt
    if not input_image_url or str(input_image_url).lower() == "none":
        print("No valid input image URL specified. Using default.")
        input_image_url = "https://raw.githubusercontent.com/ct3008/ct3008.github.io/main/images/isee1.jpeg"
    deforum_prompt = create_deforum_prompt(motion_strings, final_anim_frames, motion_mode, prompts, seed, input_image_url)
    print("deforum prompt: ", deforum_prompt)
    return deforum_prompt