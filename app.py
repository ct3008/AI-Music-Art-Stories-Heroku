import warnings
import os
# import openai
# from openai import OpenAI
import librosa
import numpy as np
import tempfile
from flask import Flask, jsonify, request, render_template, session, send_file, request
import replicate
from dotenv import load_dotenv
import requests
from tasks import long_running_task, process_audio, generate_image_task, download_prompt
from queue_config import queue, redis_conn
from flask_cors import CORS
from datetime import datetime
import cloudinary
import cloudinary.uploader
import uuid
import subprocess
from moviepy.editor import VideoFileClip, AudioFileClip
# import logging
# logging.basicConfig(level=logging.DEBUG)


warnings.simplefilter("ignore", UserWarning)  # For PySoundFile warning
warnings.simplefilter("ignore", FutureWarning)  # For FutureWarning

# CLOUDINARY_URL = 'cloudinary://218577541897493:mtt6DbXehKwIm5dbOnBQbHU4XJ0@hnkke5f4a'
# cloudinary.config(
#     # cloud_name=os.environ['CLOUDINARY_URL'].split('@')[1],
#     # api_key=os.environ['CLOUDINARY_URL'].split(':')[1][2:],
#     # api_secret=os.environ['CLOUDINARY_URL'].split(':')[2].split('@')[0],
#     cloud_name=CLOUDINARY_URL.split('@')[1],
#     api_key=CLOUDINARY_URL.split(':')[1][2:],
#     api_secret=CLOUDINARY_URL.split(':')[2].split('@')[0],
# )

load_dotenv()
app = Flask(__name__, template_folder='./templates', static_folder='./static')
CORS(app)

# Let Cloudinary parse the full URL
cloudinary.config(
    cloudinary_url=os.getenv("CLOUDINARY_URL")
)
print("Cloud name:", cloudinary.config().cloud_name)
print("API key:", cloudinary.config().api_key)
print("API secret:", cloudinary.config().api_secret)
print("Cloudinary URL:", os.getenv("CLOUDINARY_URL"))


# api_key = os.getenv("OPENAI_DISCO_API_KEY")
# client = OpenAI(api_key=api_key)

# Get the API key from environment variables
# REPLICATE_API_TOKEN = os.getenv("LAB_DISCO_API_KEY")
api_key_storage = ''
# Initialize Replicate client
# if REPLICATE_API_TOKEN:
#     api = replicate.Client(api_token=REPLICATE_API_TOKEN)
# else:
#     raise ValueError("Replicate API key is not set. Please check your environment variables.")

@app.route('/save_api_key', methods=['POST'])
def save_api_key():
    global api_key_storage
    try:
        data = request.get_json()
        api_key = data.get('api_key')        

        if not api_key:
            return jsonify({'message': 'API Key is missing!'}), 400
        
        if "disco" == api_key.lower().strip():
            api_key = os.getenv("LAB_DISCO_API_KEY")
            api_key_storage = api_key
            redis_conn.set("api_key", api_key)
            print("DISCO KEYWORD: ", api_key)
        else:
            # Store the API key (you can replace this with database/file storage)
            api_key_storage = api_key
            print("API KEY: ", api_key_storage)
            # print("Stored in environ before: ", os.getenv("LAB_DISCO_API_KEY"))
            # os.environ["LAB_DISCO_API_KEY"] = api_key_storage
            print("Stored in environ after: ", os.getenv("LAB_DISCO_API_KEY"))
            redis_conn.set("api_key", api_key)
            print("Stored in redis: ", redis_conn.get("api_key").decode('utf-8'))


        return jsonify({'message': 'API Key saved successfully!'}), 200
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file_to_upload = request.files['image']

    # Upload the image to Cloudinary
    result = cloudinary.uploader.upload(file_to_upload)

    # Return the static URL
    return jsonify({"url": result['secure_url']})

@app.route("/get_recent_images", methods=["GET"])
def get_recent_images():
    try:
        # Get the 5 most recent image URLs from Redis
        image_keys = redis_conn.keys("image:*")  # Assuming keys are like "image:<timestamp>"
        sorted_image_keys = sorted(image_keys, key=lambda k: float(k.decode().split(":")[1].split('.')[0]), reverse=True)
        recent_images = []

        # Fetch details for the 5 most recent images
        for key in sorted_image_keys[:10]:
            # print("key: ", key.decode())
            image_url = redis_conn.get(key).decode("utf-8")
            image_metadata = redis_conn.hgetall(f"image_metadata:{key.decode().split('.')[-1]}")
            prompt = image_metadata.get(b'prompt', b'No prompt').decode('utf-8')
            recent_images.append({'url': image_url, 'prompt': prompt})

        return jsonify({'status': 'success', 'images': recent_images})

    except Exception as e:
        print(f"Error fetching recent images: {str(e)}")
        return jsonify({'status': 'error', 'error': str(e)})

# motion_magnitudes = {
#     "zoom_in": {"none": 1.00, "weak": 1.02, "normal": 1.04, "strong": 10, "vstrong": 20},
#     "zoom_out": {"none": 1.00, "weak": -0.5, "normal": -1.04, "strong": -10, "vstrong": -20},
#     "rotate_up": {"none": 0, "weak": 0.5, "normal": 1, "strong": 10, "vstrong": 20},
#     "rotate_down": {"none": 0, "weak": -0.5, "normal": -1, "strong": -10, "vstrong": -20},
#     "rotate_right": {"none": 0, "weak": 0.5, "normal": 1, "strong": 10, "vstrong": 20},
#     "rotate_left": {"none": 0, "weak": -0.5, "normal": -1, "strong": -10, "vstrong": -20},
#     "rotate_cw": {"none": 0, "weak": 0.5, "normal": 1, "strong": 10, "vstrong": 20},
#     "rotate_ccw": {"none": 0, "weak": -0.5, "normal": -1, "strong": -10, "vstrong": -20},
#     "spin_cw": {"none": 0, "weak": 0.5, "normal": 1, "strong": 10, "vstrong": 20},
#     "spin_ccw": {"none": 0, "weak": -0.5, "normal": -1, "strong": -10, "vstrong": -20},
#     "pan_up": {"none": 0, "weak": 0.5, "normal": 1, "strong": 10, "vstrong": 20},
#     "pan_down": {"none": 0, "weak": -0.5, "normal": -1, "strong": -10, "vstrong": -20},
#     "pan_right": {"none": 0, "weak": 0.5, "normal": 1, "strong": 10, "vstrong": 20},
#     "pan_left": {"none": 0, "weak": -0.5, "normal": -1, "strong": -10, "vstrong": -20}
# }

# API Route

@app.route('/')
def homepage():
    return render_template('waveform.html')

@app.route('/quick_start')
def quick_start():
    return render_template('quick_start.html')

AUDIO_FOLDER = 'uploads/audioclip'
app.config['AUDIO_FOLDER'] = AUDIO_FOLDER

# Make sure the upload folder exists
if not os.path.exists(AUDIO_FOLDER):
    os.makedirs(AUDIO_FOLDER)

@app.route('/upload-file', methods=['POST'])
def upload_file():
    if 'audioFile' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['audioFile']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file:
        # Save the file to the upload folder
        file_path = os.path.join(app.config['AUDIO_FOLDER'], file.filename)
        file.save(file_path)
        return jsonify({'message': 'File uploaded successfully!', 'filename': file.filename}), 200


@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    file = request.files['audioFile']
    print("FILE: ")
    print(file)
    if file:
        file_path = os.path.join('.', file.filename)
        file.save(file_path)

        # Load the audio file using librosa
        y, sr = librosa.load(file_path, sr=None)

        # Calculate RMS energy
        rms = librosa.feature.rms(y=y)[0]

        # Smooth RMS energy to remove minor fluctuations
        smoothed_rms = np.convolve(rms, np.ones(10)/10, mode='same')

        # Perform onset detection with adjusted parameters
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        smoothed_onset_env = np.convolve(onset_env, np.ones(5)/5, mode='same')
        onset_frames = librosa.onset.onset_detect(onset_envelope=smoothed_onset_env, sr=sr, hop_length=512, backtrack=True)
        
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)

        # Perform beat detection
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times2 = librosa.frames_to_time(beat_frames, sr=sr)
        beat_times = [{'time': beat} for beat in beat_times2]

        onset_strengths = [onset_env[int(frame)] for frame in onset_frames if int(frame) < len(onset_env)]
        onset_strength_pairs = list(zip(onset_times, onset_strengths))

        # Sort by strength, largest to smallest
        sorted_onsets = sorted(onset_strength_pairs, key=lambda x: x[1], reverse=True)
        top_onset_times = sorted_onsets  # Keep both time and strength pairs

        # Align onsets with closest beats while keeping strength information
        aligned_onsets = [
            {
                'time': min(beat_times2, key=lambda x: abs(x - time)),
                'strength': float(strength),  # Convert to float
            }
            for time, strength in top_onset_times
        ]

        # Find low-energy periods
        threshold = np.percentile(smoothed_rms, 10)
        low_energy_before_onset = []
        for i in range(1, len(onset_frames)):
            start = onset_frames[i-1]
            end = onset_frames[i]
            
            # Ensure the segment is valid and non-empty
            if start < end and end <= len(smoothed_rms):
                rms_segment = smoothed_rms[start:end]
                if len(rms_segment) > 0:  # Ensure the segment is non-empty
                    min_rms = np.min(rms_segment)
                    if min_rms < threshold:
                        low_energy_before_onset.append({
                            'time': float(librosa.frames_to_time(start, sr=sr)),  # Convert to float
                            'strength': float(min_rms)  # Convert to float
                        })

        duration = librosa.get_duration(y=y, sr=sr)
        # print("BEATS: ", beat_times[0:5])  # Change to beat_times2 for accurate print
        # print("ALIGNED: ", aligned_onsets[0:15])

        return jsonify({
            "success": True,
            "low_energy_timestamps": low_energy_before_onset,
            "top_onset_times": beat_times,
            "aligned_onsets": aligned_onsets, 
            "duration": float(duration)
        })
    return jsonify({"success": False, "error": "No file provided"}), 400


@app.route('/upload_audio_large', methods=['POST'])
def upload_audio_large():
    file = request.files['audioFile']
    if file:
        # Save the audio file temporarily
        file_path = os.path.join('.', file.filename)
        file.save(file_path)

        # Load the audio file using librosa
        y, sr = librosa.load(file_path, sr=None)

        # Calculate RMS energy
        rms = librosa.feature.rms(y=y)[0]

        # Smooth RMS energy to remove minor fluctuations
        smoothed_rms = np.convolve(rms, np.ones(10)/10, mode='same')

        # Perform onset detection
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)

        # Map onset frames to onset strengths
        onset_strengths = [onset_env[int(frame)] for frame in onset_frames if int(frame) < len(onset_env)]

        # Pair onset times with their strengths
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)
        onset_strength_pairs = list(zip(onset_times, onset_strengths))

        # Sort by strength, largest to smallest
        sorted_onsets = sorted(onset_strength_pairs, key=lambda x: x[1], reverse=True)

        # Keep only the top 30 values
        top_onsets = sorted_onsets[:30]

        # Extract times from sorted onsets
        top_onset_times = [time for time, strength in top_onsets]

        # Determine a threshold for major dips
        threshold = np.percentile(smoothed_rms, 10)  # 10th percentile as threshold

        # Find major low-energy periods before onsets
        low_energy_before_onset = []
        for i in range(1, len(onset_frames)):
            start = onset_frames[i-1]
            end = onset_frames[i]
            rms_segment = smoothed_rms[start:end]
            if np.min(rms_segment) < threshold:
                low_energy_before_onset.append(librosa.frames_to_time(start, sr=sr))

        duration = librosa.get_duration(y=y, sr=sr)

        os.remove(file_path)  # Clean up the audio file
        return jsonify({"success": True, "low_energy_timestamps": low_energy_before_onset, "top_onset_times": top_onset_times, "duration": duration})
    return jsonify({"success": False, "error": "No file provided"}), 400

    
# @app.route('/generate_initial', methods=['POST'])
# def generate_initial():
#     data = request.get_json()
#     prompt = data.get('prompt', '')
#     api_key = api_key_storage
#     print("API TOKEN?: ", api_key)
#     api = replicate.Client(api_token=api_key)

#     if not prompt:
#         return jsonify({'error': 'No prompt provided'}), 400

#     try:
#         output = api.run(
#             "lucataco/open-dalle-v1.1:1c7d4c8dec39c7306df7794b28419078cb9d18b9213ab1c21fdc46a1deca0144",
#             input={
#                 "width": 768,
#                 "height": 768,
#                 "prompt": prompt,
#                 "scheduler": "KarrasDPM",
#                 "num_outputs": 1,
#                 "guidance_scale": 7.5,
#                 "apply_watermark": True,
#                 "negative_prompt": "worst quality, low quality",
#                 "prompt_strength": 0.8,
#                 "num_inference_steps": 40
#             },
#             timeout=180
#         )
#         # Assuming the output is a list of FileOutput objects, extract the URL
#         if output and isinstance(output, list):
#             image_url = str(output[0])  # Convert FileOutput to string to extract the URL
#             print("Initial Image OUTPUT", image_url)
#             return jsonify({'output': image_url})

#         return jsonify({'error': 'Unexpected output format'}), 500

#     except Exception as e:
#         print("Error:", str(e))  # Log the actual error to the console
#         return jsonify({'error': str(e)}), 500

# @app.route('/check_job_status_generate/<job_id>', methods=['GET'])
# def check_job_status_generate(job_id):
#     job = queue.fetch_job(job_id)
    
#     if job is None:
#         return jsonify({'status': 'failed', 'error': 'Job not found'}), 404

#     print("Status Generate: ", job.get_status())
#     if job.is_finished:
#         result = job.result
#         print("Job result: ", result)
#         if result and isinstance(result, dict):
#             # Check for error or output
#             if 'output' in result:
#                 return jsonify({'status': 'finished', 'output': result['output']})
#             elif 'error' in result:
#                 return jsonify({'status': 'failed', 'error': result['error']}), 500
#         return jsonify({'status': 'failed', 'error': 'Unexpected output format'}), 500
    
#     if job.is_failed:
#         return jsonify({'status': 'failed', 'error': 'Job failed due to timeout or other error'}), 500
    
#     # Job is still processing
#     return jsonify({'status': job.get_status()}), 200

def get_started_task_count():
    worker_keys = redis_conn.smembers("rq:workers")
    
    started_count = 0
    for worker_key in worker_keys:
        # print("worker key: %s" % worker_key.decode('utf-8'))
        # each worker key (e.g., "worker:<worker_name>") has a hash key "current_job"
        worker_data = redis_conn.hgetall(f"{worker_key.decode('utf-8')}")
        # If worker is processing a job, it will have a "current_job" field
        if worker_data.get(b'current_job'):
            started_count += 1

    return started_count

def get_queue_length():
    queue_key = f"rq:queue:{queue.name}"
    num_queue_key = redis_conn.llen(queue_key)
    num_started_key = get_started_task_count()
    print("queue items, in progress items: ", num_queue_key, num_started_key)

    return num_queue_key + num_started_key
    # return queue.count()

@app.route('/get_queue_length', methods=['GET'])
def queue_length():
    queue_length = get_queue_length()
    return jsonify({"queue_length": queue_length}), 200

@app.route('/generate_initial', methods=['POST'])
def generate_initial():
    data = request.get_json()
    prompt = data.get('prompt', '')
    api_key = api_key_storage
    if api_key and os.getenv("LAB_DISCO_API_KEY") and redis_conn.get("api_key"):
        print("input box chosen")
        data['api_key'] = api_key
    elif redis_conn.get("api_key"):
        print("redis chosen")
        data['api_key'] = redis_conn.get("api_key").decode('utf-8')
    else:
        print("os env chosen")
        data['api_key'] = os.getenv("LAB_DISCO_API_KEY")
    print("API TOKEN? api_key,", api_key,". environ: ",  os.getenv("LAB_DISCO_API_KEY"), ". redis: ", redis_conn.get("api_key").decode('utf-8'))
    print("API KEY ACTUALLY PASSED? ", data['api_key'])
    

    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400

    # Enqueue the task and return the job ID
    try:
        job = queue.enqueue(generate_image_task, data, job_timeout=300)  # Set a job timeout (e.g., 60 seconds)
        return jsonify({'job_id': job.get_id(), 'status': 'queued'}), 202
    except Exception as e:
        return jsonify({'error': str(e)}), 500



def split_and_pair_values(data):
    motions = data['motion'].strip().split(',')
    strengths = data['strength'].strip().split(',')
    speeds = ['normal']
    # speeds = data['speed'].strip().split(',')
    return list(zip(motions, strengths, speeds))

# def get_motion_data(form_data, trans_data, time_intervals):
#     motion_data = []

#     for i in range(len(time_intervals) - 1):
#         start = float(time_intervals[i])
#         end = float(time_intervals[i + 1])
#         if (time_intervals[i] >= time_intervals[i + 1]):
#             break
#         segment_motion_data = []

#         # Check for transitions
#         for interval, data in trans_data.items():
#             interval_start, interval_end = map(float, interval.split('-'))
#             if start <= interval_start < end or start < interval_end <= end:
#                 segment_motion_data.extend(split_and_pair_values(data))
#                 break  # Only take the transition motion

#         # If no transition, default to closest form_data motion
#         if not segment_motion_data:
#             closest_form_data = get_closest_form_data(start, form_data)
#             if closest_form_data:
#                 segment_motion_data.extend(split_and_pair_values(closest_form_data))

#         motion_data.append(segment_motion_data)

#     return motion_data


# def get_closest_form_data(time, form_data):
#     closest_time = min((float(t) for t in form_data.keys() if float(t) >= time), default=None)
#     if closest_time is not None:
#         # print(closest_time)
#         # print(form_data)
#         return form_data[f"{closest_time:.2f}"]
#     else:
#         closest_time = min((float(t) for t in form_data.keys() if float(t) <= time), default=None)
#         return form_data[f"{closest_time:.2f}"]



# def get_motion_and_speed(time, form_data):
#     motion_options = ["zoom_in", "zoom_out", "pan_right", "pan_left", "pan_up", "pan_down", "spin_cw", "spin_ccw", 
#                       "rotate_up", "rotate_down", "rotate_right", "rotate_left", "rotate_cw", "rotate_ccw", "none"]
#     speed_options = ["vslow", "slow", "normal", "fast", "vfast"]
#     strength_options = ["weak", "normal", "strong", "vstrong"]

#     form_entry = form_data.get(time, {})
#     motion = form_entry.get('motion', 'none')
#     speed = form_entry.get('speed', 'normal')
#     strength = form_entry.get('strength', 'normal')

#     if motion not in motion_options:
#         print(f"Invalid motion option for time {time}. Using default 'none'.")
#         motion = 'none'

#     motions = [(motion, speed, strength)]
#     return motions

def get_motion_data(form_data, trans_data, time_intervals):
    motion_data = []

    for i in range(len(time_intervals) - 1):
        start = float(time_intervals[i])
        end = float(time_intervals[i + 1])
        if start >= end:
            break

        segment_motion_data = []

        # Check for transitions
        for interval, data in trans_data.items():
            interval_start, interval_end = map(float, interval.split('-'))
            if start <= interval_start < end or start < interval_end <= end:
                segment_motion_data.extend(split_and_pair_values(data))
                break  # Only take the transition motion

        # If no transition, default to closest form_data motion
        if not segment_motion_data:
            closest_form_data = get_closest_form_data(start, form_data)
            if closest_form_data:
                segment_motion_data.extend(split_and_pair_values(closest_form_data))

        motion_data.append(segment_motion_data)

    return motion_data


def get_closest_form_data(time, form_data):
    closest_time = min((float(t) for t in form_data.keys() if float(t) >= time), default=None)
    if closest_time is not None:
        return form_data[f"{closest_time:.2f}"]
    else:
        closest_time = min((float(t) for t in form_data.keys() if float(t) <= time), default=None)
        return form_data[f"{closest_time:.2f}"]


def split_and_pair_values(data):
    """
    Splits motion and strength values and pairs them correctly.
    """
    motions = data['motion'].split(',')
    strengths = data['strength'].split(',')

    # Ensure the number of motions and strengths match
    if len(motions) != len(strengths):
        raise ValueError(f"Mismatch between motions ({len(motions)}) and strengths ({len(strengths)}).")

    # Create pairs of motion and strength
    paired_values = []
    for motion, strength in zip(motions, strengths):
        paired_values.append({'motion': motion.strip(), 'strength': strength.strip()})

    return paired_values


def get_motion_and_speed(time, form_data):
    motion_options = [
        "zoom_in", "zoom_out", "pan_right", "pan_left", "pan_up", "pan_down", 
        "spin_cw", "spin_ccw", "rotate_up", "rotate_down", "rotate_right", 
        "rotate_left", "rotate_cw", "rotate_ccw", "none"
    ]
    speed_options = ["vslow", "slow", "normal", "fast", "vfast"]
    strength_options = ["weak", "normal", "strong", "vstrong"]

    form_entry = form_data.get(time, {})
    motion = form_entry.get('motion', 'none')
    speed = form_entry.get('speed', 'normal')
    strength = form_entry.get('strength', 'normal')

    # Split motion and strength if they are comma-separated
    motion_list = motion.split(',')
    strength_list = strength.split(',')

    # Validate and pair motion and strength
    motions = []
    for motion, strength in zip(motion_list, strength_list):
        print("Motion, strength: ", motion, strength)
        if motion not in motion_options:
            print(f"Invalid motion option '{motion}' for time {time}. Using default 'none'.")
            motion = 'none'
        # if strength not in strength_options and not is_valid_strength_expression(strength):
        # if strength not in strength_options:
            print(f"Invalid strength option '{strength}' for time {time}. Using default 'normal'.")
            strength = 'normal'
        motions.append({'motion': motion.strip(), 'strength': strength.strip(), 'speed': speed.strip()})

    return motions


# def is_valid_strength_expression(expression):
#     """
#     Validates if a strength expression is a mathematical function like 10*sin(2*3.14*t/10).
#     """
#     try:
#         # Replace `t` with 1 for validation, as it's a placeholder for time
#         eval(expression.replace('t', '1'), {"sin": __import__('math').sin, "cos": __import__('math').cos})
#         return True
#     except Exception:
#         return False
def is_valid_strength_expression(expression):
    """
    Validates if a strength expression is in the format:
    [coefficient]*[sin|cos|tan](a*t/b)
    Example: 10*sin(2*3.14*t/10)
    """
    # Define the regex pattern
    pattern = r"^\d*(\.\d+)?\s*[\*]?\s*(sin|cos|tan)\(\s*\d+(\.\d+)?\s*\*\s*t\s*/\s*\d+(\.\d+)?\s*\)$"

    # Check if the expression matches the pattern
    if not re.match(pattern, expression):
        print("FAILED MATCH")
        return False

    # Attempt to evaluate the expression with t = 1
    try:
        eval(expression.replace('t', '1'), {"sin": math.sin, "cos": math.cos, "tan": math.tan})
        return True
    except Exception:
        return False

# def merge_intervals(interval_strings, motion_data, scene_change_times):
#     merged_intervals = []
    
#     # Loop through intervals
#     i = 0
#     while i < len(interval_strings) - 1:
#         current_interval = interval_strings[i]
#         next_interval = interval_strings[i + 1]
        
#         current_motions = motion_data[i]
#         next_motions = motion_data[i + 1]
        
#         # Extract start and end times from the intervals
#         current_start_time, current_end_time = current_interval.split("-")
#         next_start_time, next_end_time = next_interval.split("-")
        
#         # Compare the end time of the current interval and start time of the next
#         if current_end_time == next_start_time and current_motions == next_motions:
#             # Merge intervals and combine motion data
#             merged_interval = f"{current_start_time}-{next_end_time}"
#             merged_motions = current_motions  # Since both motions are the same, use one
            
#             # Add the merged interval and motion data
#             merged_intervals.append((merged_interval, merged_motions))
            
#             # Skip the next interval, as it's already merged
#             i += 2
#         else:
#             # Add the current interval and motion data as is
#             merged_intervals.append((current_interval, current_motions))
#             i += 1
    
#     # Handle the last interval if it wasn't merged
#     if i < len(interval_strings):
#         merged_intervals.append((interval_strings[i], motion_data[i]))
    
#     return merged_intervals


def parse_input_data(form_data, trans_data, song_duration):
    trans_data = {k: v for k, v in trans_data.items() if v.get('transition', True)}
    scene_change_times = sorted(list(map(float, form_data.keys())))
    print("scene times and trans app.py", scene_change_times, trans_data)
    
    # Create the combined list of transition times
    transition_times = list(map(float, [time.split('-')[0] for time in trans_data.keys()] + 
                                  [time.split('-')[1] for time in trans_data.keys()] + list(form_data.keys())))
    time_intervals = sorted(set(scene_change_times + transition_times))
    
    # Add 0 at the beginning and the song's duration at the end
    time_intervals = [0] + [float(i) for i in time_intervals] + [float(round(song_duration, 2))]
    time_intervals = sorted(set(time_intervals))  # Remove duplicates and sort
    
    # Create the interval strings based on time intervals
    interval_strings = [f"{time_intervals[i]}-{time_intervals[i+1]}" for i in range(len(time_intervals) - 1)]
    
    # Get the motion data
    motion_data = get_motion_data(form_data, trans_data, time_intervals)
    og_motion_data = motion_data
    # Print the intervals and motions before merging
    for interval, motions in zip(interval_strings, motion_data):
        print(f"Interval: {interval}, Motions: {motions}")

    # Merge intervals with identical motion data
    # merged_intervals = merge_intervals(interval_strings, motion_data, scene_change_times)

    # # Print the merged intervals
    # for interval, motions in merged_intervals:
    #     print(f"MERGED Interval: {interval}, Motions: {motions}")

    # print("merged: ", merged_intervals)

    # Replace the old interval_strings and motion_data with the merged values
    # interval_strings = [interval for interval, motions in merged_intervals]
    # motion_data = [motions for interval, motions in merged_intervals]

    # Add time intervals from form_data and trans_data
    for key, value in form_data.items():
        time_intervals.append(float(key))
    
    for key in trans_data.keys():
        start, end = map(float, key.split('-'))
        time_intervals.extend([start, end])
    
    time_intervals = sorted(set(time_intervals))
    time_intervals = [str(i) for i in time_intervals]
    
    # Return the updated values
    return song_duration, scene_change_times, transition_times, time_intervals, interval_strings, motion_data, og_motion_data


# def calculate_frames(scene_change_times, time_intervals, motion_data, total_song_len, final_anim_frames):
#     frame_data = {
#         "zoom": [],
#         "translation_x": [],
#         "translation_y": [],
#         "angle": [],
#         "rotation_3d_x": [],
#         "rotation_3d_y": [],
#         "rotation_3d_z": []
#     }
#     tmp_times = scene_change_times.copy()

#     speed_multiplier = {"vslow": 0.25, "slow": 0.5, "normal": 1, "fast": 2.5, "vfast": 6}
#     frame_rate = 15

#     current_frame = 0
#     animation_prompts = []
#     # print("INTERVAL: ", time_intervals)
#     for interval, motions in zip(time_intervals, motion_data):
#         _, strength, speed = motions[0]
#         start_time, end_time = map(float, interval.split('-'))
        
#         # print("TMP TIME: ", tmp_times)
#         if tmp_times != [] and int(tmp_times[0]) <= end_time and int(tmp_times[0]) >= start_time:
#             new_frame = round(current_frame + ((tmp_times[0]) - start_time) * 15 * speed_multiplier[speed])
#             # print("----------------END FRAME:---------------", new_frame)
#             if new_frame not in final_anim_frames:
				
#                 final_anim_frames.append(new_frame)
#             tmp_times.pop(0)
#         duration = (end_time - start_time) * frame_rate
#         adjusted_duration = round(duration * speed_multiplier[speed])
#         end_frame = current_frame + adjusted_duration
#         for motion, strength, speed in motions:
#             animation_prompts.append((start_time, end_time, current_frame, end_frame))
            
#             def get_motion_value(motion, strength):
#                 return motion_magnitudes.get(motion, {}).get(strength, strength)

#             motion_value = get_motion_value(motion, strength)
#             print("motion value: ", motion_value)
#             if motion == "zoom_in":
#                 frame_data["zoom"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "zoom_out":
#                 frame_data["zoom"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "pan_right":
#                 frame_data["translation_x"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "pan_left":
#                 frame_data["translation_x"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "pan_up":
#                 frame_data["translation_y"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "pan_down":
#                 frame_data["translation_y"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "spin_cw":
#                 frame_data["angle"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "spin_ccw":
#                 frame_data["angle"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "rotate_up":
#                 frame_data["rotation_3d_x"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "rotate_down":
#                 frame_data["rotation_3d_x"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "rotate_right":
#                 frame_data["rotation_3d_y"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "rotate_left":
#                 frame_data["rotation_3d_y"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "rotate_cw":
#                 frame_data["rotation_3d_z"].append((current_frame, end_frame, adjusted_duration, motion_value))
#             elif motion == "rotate_ccw":
#                 frame_data["rotation_3d_z"].append((current_frame, end_frame, adjusted_duration, motion_value))


#         current_frame = end_frame

#         if str(end_time) == str(total_song_len) and end_frame not in final_anim_frames and (end_frame - 1) not in final_anim_frames:
#             final_anim_frames.append(end_frame)
        

#     return frame_data, animation_prompts
def calculate_frames(scene_change_times, time_intervals, motion_data, total_song_len, final_anim_frames):
    frame_data = {
        "zoom": [],
        "translation_x": [],
        "translation_y": [],
        "angle": [],
        "rotation_3d_x": [],
        "rotation_3d_y": [],
        "rotation_3d_z": []
    }
    tmp_times = scene_change_times.copy()

    speed_multiplier = {"vslow": 0.25, "slow": 0.5, "normal": 1, "fast": 2.5, "vfast": 6}
    frame_rate = 15

    current_frame = 0
    animation_prompts = []
    adjustments = []

    for interval, motions in zip(time_intervals, motion_data):
        start_time, end_time = map(float, interval.split('-'))

        # Handle scene change times
        if tmp_times and start_time <= tmp_times[0] <= end_time:
            new_frame = round(current_frame + ((tmp_times[0] - start_time) * frame_rate * speed_multiplier['normal']))
            if new_frame not in final_anim_frames:
                final_anim_frames.append(new_frame)
            tmp_times.pop(0)

        # Calculate duration for the interval
        duration = (end_time - start_time) * frame_rate
        adjusted_duration = math.ceil(duration * speed_multiplier['normal'])
        end_frame = current_frame + adjusted_duration
        speed_factor = duration / adjusted_duration
        adjustments.append({
            "start_frame": current_frame,
            "end_frame": end_frame,
            "speed_factor": speed_factor,
            "start_time": start_time,
            "end_time": end_time
        })

        # Process all motions for this interval
        for motion_entry in motions:
            motion = motion_entry['motion']
            strength = motion_entry['strength']
            

            def get_motion_value(motion, strength):
                print("for motion: ", motion, " and strength: ", strength, " motion value: ",motion_magnitudes.get(motion, {}).get(strength, strength))
                return motion_magnitudes.get(motion, {}).get(strength, strength)

            motion_value = get_motion_value(motion, strength)

            # Add motion-specific frame data
            if motion == "zoom_in":
                frame_data["zoom"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "zoom_out":
                frame_data["zoom"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "pan_right":
                frame_data["translation_x"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "pan_left":
                frame_data["translation_x"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "pan_up":
                frame_data["translation_y"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "pan_down":
                frame_data["translation_y"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "spin_cw":
                frame_data["angle"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "spin_ccw":
                frame_data["angle"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "rotate_up":
                frame_data["rotation_3d_x"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "rotate_down":
                frame_data["rotation_3d_x"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "rotate_right":
                frame_data["rotation_3d_y"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "rotate_left":
                frame_data["rotation_3d_y"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "rotate_cw":
                frame_data["rotation_3d_z"].append((current_frame, end_frame, adjusted_duration, motion_value))
            elif motion == "rotate_ccw":
                frame_data["rotation_3d_z"].append((current_frame, end_frame, adjusted_duration, motion_value))

            # Add animation prompts
            animation_prompts.append((start_time, end_time, current_frame, end_frame, motion, strength))

        # Update the current frame
        current_frame = end_frame

        # Handle the final frame at the end of the song
        if str(end_time) == str(total_song_len) and end_frame not in final_anim_frames and (end_frame - 1) not in final_anim_frames:
            final_anim_frames.append(end_frame)

    return frame_data, animation_prompts, adjustments


# def build_transition_strings(frame_data):
#     motion_defaults = {
#         "zoom": 1.0,
#         "translation_x": 0,
#         "translation_y": 0,
#         "angle": 0,
#         "rotation_3d_x": 0,
#         "rotation_3d_y": 0,
#         "rotation_3d_z": 0
#     }
#     motion_strings = {motion: [] for motion in frame_data}
#     print("FRAME DATA: ", frame_data)

#     for motion, frames in frame_data.items():
#         previous_end_frame = None
#         for (start_frame, end_frame, duration, value) in frames:
#             print("START: ", start_frame)
#             print("END: ", end_frame)
#             print("VALUE: ", value)
#             pre_frame = start_frame - 1
#             post_frame = end_frame + 1
#             #Checks if the current motion immediately follows the previous motion 
#             # (i.e., the end frame of the previous motion is the same as the start 
#             # frame of the current motion). If so, it increments the start_frame by 
#             # 2 to avoid overlapping frames.
#             if previous_end_frame is not None and previous_end_frame == start_frame:
#                 start_frame = start_frame + 2
#             else:
#                 #If the current motion doesn’t immediately follow the previous one, it 
#                 # adds a motion entry for the pre_frame with the default motion value.
#                 if pre_frame >= 0:
#                     motion_strings[motion].append(f"{pre_frame}:({motion_defaults[motion]})")
                    
#             motion_strings[motion].append(f"{start_frame}:({value})")
#             motion_strings[motion].append(f"{end_frame}:({value})")
#             #start and end frame have same motion
#             if post_frame >= 0:
#                 #adds a motion entry for post_frame with the default motion value
#                 motion_strings[motion].append(f"{post_frame}:({motion_defaults[motion]})")
                
#             previous_end_frame = end_frame

#     for motion in motion_strings:
#         if not any(s.startswith('0:') for s in motion_strings[motion]):
#             motion_strings[motion].insert(0, f"0:({motion_defaults[motion]})")

#     print("motion strings: ", motion_strings)

#     return motion_strings

def build_transition_strings(frame_data):
    motion_defaults = {
        "zoom": 1.0,
        "translation_x": 0,
        "translation_y": 0,
        "angle": 0,
        "rotation_3d_x": 0,
        "rotation_3d_y": 0,
        "rotation_3d_z": 0
    }
    motion_strings = {motion: [] for motion in frame_data}
    print("FRAME DATA: ", frame_data)

    for motion, frames in frame_data.items():
        previous_end_frame = None
        for idx, (start_frame, end_frame, duration, value) in enumerate(frames):
            
            pre_frame = start_frame - 1
            post_frame = end_frame + 1
            #Checks if the current motion immediately follows the previous motion 
            # (i.e., the end frame of the previous motion is the same as the start 
            # frame of the current motion). If so, it increments the start_frame by 
            # 2 to avoid overlapping frames.
            if previous_end_frame is not None and previous_end_frame == start_frame:
                start_frame = start_frame + 2
            else:
                #If the current motion doesn’t immediately follow the previous one, it 
                # adds a motion entry for the pre_frame with the default motion value.
                if pre_frame >= 0:
                    print(f"pre-frame {pre_frame}:({motion_defaults[motion]})")
                    motion_strings[motion].append(f"{pre_frame}:({motion_defaults[motion]})")
                    
            motion_strings[motion].append(f"{start_frame}:({value})")
            motion_strings[motion].append(f"{end_frame}:({value})")
            #start and end frame have same motion
            try:
                #if next seq of same motion type exists, check if start val matches current seq end frame
                # if exists and is true, append the same value to post frame
                next_start, next_end, _, next_value = frames[idx+1]
                if next_start == end_frame:
                    motion_strings[motion].append(f"{post_frame}:({value})")
                else:
                    # Reset value to default to indicate changing motion
                    motion_strings[motion].append(f"{post_frame}:({motion_defaults[motion]})")
            except:
                motion_strings[motion].append(f"{post_frame}:({motion_defaults[motion]})")
            # if post_frame >= 0:
            #     print(f"post-frame {post_frame}:({motion_defaults[motion]})")
            #     #adds a motion entry for post_frame with the default motion value
            #     motion_strings[motion].append(f"{post_frame}:({motion_defaults[motion]})")
                
            previous_end_frame = end_frame

    for motion in motion_strings:
        if not any(s.startswith('0:') for s in motion_strings[motion]):
            motion_strings[motion].insert(0, f"0:({motion_defaults[motion]})")

    print("motion strings: ", motion_strings)

    return motion_strings

def create_prompt(data):
    vibe = data.get('vibe', '')
    imagery = data.get('imagery', '')
    texture = data.get('texture', '')
    style = data.get('style', '')
    color = data.get('color', '')

    prompt = (
        f"{color}, {style} in {texture} texture, simple abstract, beautiful, 4k, motion. "
        f"{imagery}. Evoking a feeling of a {vibe} undertone."
    )
    return prompt

def generate_image_prompts(form_data, final_anim_frames):
    prompts = []

    # Define a dictionary to map short descriptions to more detailed descriptions
    detail_dict = {
        "aggressive": "intense and powerful energy, creating a sense of urgency and dynamism",
        "epic": "grand and majestic energy, evoking a sense of awe and excitement",
        "happy": "bright and cheerful energy, evoking a sense of joy and positivity",
        "chill": "calm and relaxed energy, creating a sense of tranquility and peace",
        "sad": "melancholic and somber energy, evoking a sense of sorrow and introspection",
        "romantic": "loving and tender energy, evoking a sense of affection and intimacy",
        "uplifting": "encouraging and inspiring energy, evoking a sense of hope and motivation",
        "starry night": "starry night sky with delicate splotches resembling stars",
        "curvilinear intertwined circles": "intricate abstract recursive line art",
        "flowing waves": "flowing waves, merging and separating gracefully",
        "blossoming flower": "delicate flower petals dancing in the wind, spiraling and intertwining gracefully",
        "chaotic intertwining lines": "dynamic abstract line art with intersecting, intertwined, jagged edges, evoking a sense of chaos and dissonance",
        "painting": "beautiful, 4k",
        "black/white": "Black and white",
        "full color": "Vibrant, full color"
    }
    # print("GENERATE PROMPTS")
    # Generate prompts
    for timestamp, data in form_data.items():
        prompt_parts = [
            detail_dict.get(data['color'], data['color']),
            detail_dict.get(data['style'], data['style']),
            detail_dict.get(data['texture'], data['texture']),
            detail_dict.get(data['imagery'], data['imagery']),
            detail_dict.get(data['vibe'], data['vibe'])
        ]
        # print(data)
        
        prompt = f"{prompt_parts[0]} color scheme, {prompt_parts[1]} style in {prompt_parts[2]} texture, beautiful, simple abstract, 4k. {prompt_parts[3]} imagery evoking the feeling of {prompt_parts[4]} vibe."
        prompts.append(prompt)
    # print("ALL PROMPTS")
    # print(prompts)

    # print("final anim frames: ",final_anim_frames)
    # print("prompts: ",prompts)
    combined_prompts = " | ".join([f"{final_anim_frames[i]}: {prompts[i]}" for i in range(len(prompts))])
    # print("combo: ", combined_prompts)
    # combined_prompts += " | ".join([f"{final_anim_frames[i]}"])

    return combined_prompts
    # def create_prompt(data):
    #     prompt_parts = [
    #         f"Vibe: {data.get('vibe', '')}",
    #         f"Imagery: {data.get('imagery', '')}",
    #         f"Texture: {data.get('texture', '')}",
    #         f"Style: {data.get('style', '')}",
    #         f"Color: {data.get('color', '')}"
    #     ]
    #     return ", ".join(part for part in prompt_parts if part.split(": ")[1])

    # prompts = []
    # for data in form_data.values():
    #     prompt = create_prompt(data)
    #     prompts.append(prompt)

    # return prompts

def generate_prompt_completion(client, prompt):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    return completion.choices[0].message['content']


@app.route("/check-job-status/<job_id>", methods=["GET"])
def check_job_status(job_id):
    # Get the job from the queue
    job = queue.fetch_job(job_id)
    
    # If the job doesn't exist, return an error message
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    # Get the job's status
    status = job.get_status()
    if status == "started":
       print("Job Status: in progress")
    else: 
        print("Job Status: ", status)
    
    if status == 'failed':
        error_message = job.meta.get('error', 'An unknown error occurred.')
        return jsonify({"job_id": job_id, "status": "failed", "error": error_message}), 400
    # Check if the job is finished
    elif status == 'finished':
        # Optionally, you can return the result of the job
        return jsonify({"job_id": job_id, "status": "finished", "result": job.result}), 200
    else:
        # Return the current status if the job is still running
        return jsonify({"job_id": job_id, "status": status}), 200


    # def combine_audio_video(audio_filename, video_url, output_filename="./downloaded_videos/output_combined.mp4"):
    #     try:
    #         audio_path = f"./{audio_filename}"  # Adjust path based on where you save files
    #         audio_clip = AudioFileClip(audio_path)
    #         video_clip = VideoFileClip(video_url)

    #         # Combine audio and video
    #         final_clip = video_clip.set_audio(audio_clip)

    #         # Save the final output
    #         final_clip.write_videofile(output_filename, codec="libx264", audio_codec="aac")
    #         print(f"Combined video saved to {output_filename}")
            

    #     except Exception as e:
    #         print(f"Error during processing: {e}")
    #     finally:
    #         # Properly close MoviePy resources
    #         if 'audio_clip' in locals():
    #             audio_clip.close()
    #         if 'video_clip' in locals():
    #             video_clip.close()
    #         if 'final_clip' in locals():
    #             final_clip.close()

    # @app.route('/get_video/<filename>', methods=["GET"])
    # def get_video(filename):
    #     print("Downloading video?")
        
    #     # Get the video_url from the query parameters
    #     video_url = request.args.get('video_url')  # This retrieves the 'video_url' parameter
    #     if not video_url:
    #         return jsonify({"error": "video_url parameter is missing."}), 400

    #     # Assuming the filename is valid, prepare the output filename
    #     output_filename = "./downloaded_videos/output_combined.mp4"
        
    #     # Call the function to combine audio and video
    #     try:
    #         combine_audio_video(filename, video_url, output_filename)
    #     except Exception as e:
    #         return jsonify({"error": str(e)}), 500
        
    #     # Return the combined video file
    #     return send_file(output_filename, as_attachment=True, download_name="output_combined.mp4")

    # def combine_audio_video(audio_filename, video_url, output_filename="./downloaded_videos/output_combined.mp4"):
    #     try:
    #         # Assuming you are downloading the video from the URL and combining it with the audio file
    #         # Download the video file from `video_url`
    #         # Then use MoviePy or any other method to combine video and audio

    #         audio_path = f"./{audio_filename}"  # Adjust path based on where you save audio files
    #         video_clip = VideoFileClip(video_url)  # Assuming video_url is directly usable
            
    #         # Process video and audio combining (not full code for brevity)
    #         # Example with MoviePy:
    #         audio_clip = AudioFileClip(audio_path)
    #         final_clip = video_clip.set_audio(audio_clip)

    #         final_clip.write_videofile(output_filename, codec="libx264", audio_codec="aac")
    #         print(f"Combined video saved to {output_filename}")

    #     except Exception as e:
    #         print(f"Error during processing: {e}")
    #         raise e  # Re-raise error so it can be handled in the route
    #     finally:
    #         # Ensure all resources are properly closed
    #         if 'audio_clip' in locals():
    #             audio_clip.close()
    #         if 'video_clip' in locals():
    #             video_clip.close()
    #         if 'final_clip' in locals():
    #             final_clip.close()

# @app.route('/get_video/<filename>', methods=["POST"])  # Change method to POST
# def get_video(filename):
#     print("Downloading video?")
    
#     # Get the video_url from the JSON body
#     data = request.get_json()  # Parse JSON body
#     video_url = data.get('video_url')  # Extract video_url from the JSON
#     if not video_url:
#         return jsonify({"error": "video_url parameter is missing."}), 400

#     # Prepare the output filename
#     output_filename = "./downloaded_videos/output_combined.mp4"
    
#     # Call the function to combine audio and video
#     try:
#         combine_audio_video(filename, video_url, output_filename)
#     except Exception as e:
#         return jsonify({"error": str(e)}), 500
    
#     # Return the combined video file as an attachment
#     return send_file(output_filename, as_attachment=True, download_name="output_combined.mp4")


# def combine_audio_video(audio_filename, video_url, output_filename="./downloaded_videos/output_combined.mp4"):
#     try:
#         # Process video and audio combining using MoviePy
#         audio_path = f"./{audio_filename}"  # Adjust path based on where you save audio files
#         video_clip = VideoFileClip(video_url)  # Assuming video_url is directly usable
        
#         # Combine audio and video
#         audio_clip = AudioFileClip(audio_path)
#         final_clip = video_clip.set_audio(audio_clip)

#         final_clip.write_videofile(output_filename, codec="libx264", audio_codec="aac")
#         print(f"Combined video saved to {output_filename}")

#     except Exception as e:
#         print(f"Error during processing: {e}")
#         raise e  # Re-raise error so it can be handled in the route
#     finally:
#         # Ensure all resources are properly closed
#         if 'audio_clip' in locals():
#             audio_clip.close()
#         if 'video_clip' in locals():
#             video_clip.close()
#         if 'final_clip' in locals():
#             final_clip.close()

@app.route('/get_video/<filename>', methods=["POST"])
def get_video(filename):
    print("Downloading video?")

    # Get the video_url and adjustments from the JSON body
    data = request.get_json()
    video_url = data.get('video_url')
    adjustments = data.get('adjustments')

    if not video_url:
        return jsonify({"error": "video_url parameter is missing."}), 400

    if not adjustments:
        return jsonify({"error": "adjustments parameter is missing."}), 400

    # Prepare the output filename
    output_filename = f"./{filename}_output_combined.mp4"

    # Call the function to process the video with speed adjustments
    try:
        process_video_with_speed_adjustments(video_url, adjustments, filename, output_filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Return the combined video file as an attachment
    return send_file(output_filename, as_attachment=True, download_name=f"{filename}_output_combined.mp4")


def process_video_with_speed_adjustments(video_url, adjustments, audio_filename, output_filename):
    # Step 1: Download the video
    video_file = "downloaded_video.mp4"
    download_video(video_url, video_file)

    # # Step 2: Adjust the playback speed of intervals
    adjusted_video_file = "adjusted_video.mp4"
    adjust_video_speed(video_file, adjustments, adjusted_video_file)

    # Step 3: Combine the adjusted video with the audio
    # combine_audio_video(audio_filename, video_file, output_filename)
    combine_audio_video(audio_filename, adjusted_video_file, output_filename)

    # Cleanup temporary files
    if os.path.exists(video_file):
        os.remove(video_file)
    if os.path.exists(adjusted_video_file):
        os.remove(adjusted_video_file)


def download_video(api_url, save_path):
    print("Downloading video...")
    response = requests.get(api_url, stream=True, verify=False)
    print(f"Response code: {response.status_code}")
    if response.status_code == 200:
        # print("Downloading video started.")
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        # files = os.listdir('.')
        # print(f"Files in current directory: {files}")
    else:
        raise Exception(f"Failed to download video: {response.status_code}")

def adjust_video_speed(input_video, adjustments, output_video):
    print("adjusting video speed")
    segments = []
    for i, adj in enumerate(adjustments):
        start_frame = adj["start_frame"]
        end_frame = adj["end_frame"]
        speed_factor = adj["speed_factor"]

        # Calculate start and end times
        start_time = start_frame / 15  # Assuming 15 fps
        end_time = end_frame / 15

        # Extract segment
        segment_file = f"segment_{i}.mp4"
        subprocess.run([
            "ffmpeg", "-i", input_video,
            "-vf", f"select='between(n,{start_frame},{end_frame})'",
            "-vsync", "vfr",
            "-c:v", "libx264",
            segment_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Adjust playback speed
        adjusted_segment = f"adjusted_segment_{i}.mp4"
        subprocess.run([
            "ffmpeg", "-i", segment_file,
            "-filter:v", f"setpts=PTS/{speed_factor}",
            "-filter:a", f"atempo={min(speed_factor, 2.0)}",  # atempo must be between 0.5 and 2.0, limit accordingly
            adjusted_segment
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        segments.append(adjusted_segment)

    # Merge all segments
    with open("file_list.txt", "w") as f:
        for segment in segments:
            f.write(f"file '{segment}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "file_list.txt", "-c", "copy", output_video
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Cleanup temporary files
    for segment in segments + [f"segment_{i}.mp4" for i in range(len(adjustments))]:
        os.remove(segment)
    os.remove("file_list.txt")

    temp_files = [f"segment_{i}.mp4" for i in range(100)] + \
             [f"adjusted_segment_{i}.mp4" for i in range(100)] + ["file_list.txt"]

    for temp_file in temp_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)

# def adjust_video_speed(input_video, adjustments, output_video):
#     print("adjusting video speed")

#     # Build filter graph
#     filter_graph = ""
#     for i, adj in enumerate(adjustments):
#         start_time = adj["start_frame"] / 15  # Assuming 15 fps
#         end_time = adj["end_frame"] / 15
#         speed_factor = adj["speed_factor"]

#         # Trim, setpts for video, and atempo for audio
#         filter_graph += (
#             f"[0:v]trim=start={start_time}:end={end_time},setpts=PTS/{speed_factor}[v{i}];"
#             f"[0:a]atrim=start={start_time}:end={end_time},asetpts=PTS-STARTPTS,atempo={min(speed_factor, 2.0)}[a{i}];"
#         )

#     # Concatenate all segments
#     video_inputs = "".join(f"[v{i}]" for i in range(len(adjustments)))
#     audio_inputs = "".join(f"[a{i}]" for i in range(len(adjustments)))
#     filter_graph += f"{video_inputs}concat=n={len(adjustments)}:v=1:a=0[v];"
#     filter_graph += f"{audio_inputs}concat=n={len(adjustments)}:v=0:a=1[a]"

#     # Run FFmpeg
#     subprocess.run([
#         "ffmpeg", "-i", input_video, "-filter_complex", filter_graph,
#         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac", output_video
#     ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

#     print(f"Output saved to {output_video}")



def combine_audio_video(audio_filename, video_file, output_filename):
    try:
        audio_path = f"./{audio_filename}"
        video_clip = VideoFileClip(video_file)
        audio_clip = AudioFileClip(audio_path)
        # print("COMBINE AUDIO VIDEO")
        print(audio_path)
        print(video_clip)
        print(audio_clip)

        final_clip = video_clip.set_audio(audio_clip)
        final_clip.write_videofile(output_filename, codec="libx264", audio_codec="aac")
        print(f"Combined video saved to {output_filename}")

    except Exception as e:
        print(f"Error during processing: {e}")
        raise e
    finally:
        # Ensure all resources are properly closed
        if 'audio_clip' in locals():
            audio_clip.close()
        if 'video_clip' in locals():
            video_clip.close()
        if 'final_clip' in locals():
            final_clip.close()


@app.route("/process-data", methods=["POST"])
def process_data():
    # Enqueue the task and pass the request data
    # files = os.listdir('.')
    # print("Files in current directory:", files)
    data = request.json

    
    # files['audioFile']
    print("PROCESS DATA")
    api_key = api_key_storage
    # print("API TOKEN? api key, ", api_key,". os:", os.getenv("LAB_DISCO_API_KEY"))
    # data['api_key'] = os.getenv("LAB_DISCO_API_KEY")
    if api_key and os.getenv("LAB_DISCO_API_KEY") and redis_conn.get("api_key"):
        print("input box chosen process")
        data['api_key'] = api_key
    elif redis_conn.get("api_key"):
        print("redis chosen process")
        data['api_key'] = redis_conn.get("api_key").decode('utf-8')
    else:
        print("os env chosen process")
        data['api_key'] = os.getenv("LAB_DISCO_API_KEY")
    print("PROCESS API TOKEN? api_key,", api_key,". environ: ",  os.getenv("LAB_DISCO_API_KEY"), ". redis: ", redis_conn.get("api_key").decode('utf-8'))
    print("PROCESS API KEY ACTUALLY PASSED? ", data['api_key'])
    # data['enqueue_time'] = datetime.now()
    # api = replicate.Client(api_token=api_key)
    print("ABOUT TO ENQUEUE")
    job = queue.enqueue(long_running_task, data,job_timeout=3000)
    print(job)
    print("done enqueue")
    
    # Respond immediately with the job ID
    return jsonify({"job_id": job.get_id(), "status": "queued"}), 202

@app.route("/download_prompt", methods=["POST"])
def download_prompt_caller():
    # Enqueue the task and pass the request data
    data = request.json
    
    prompt = download_prompt(data)
    
    print("prompt: ", prompt)
    
    # Respond immediately with the job ID
    return jsonify({"prompt": prompt}), 202


if __name__ == "__main__":
    # app.run(debug=True)
    port = int(os.environ.get("PORT", 5004))
    app.run(host="0.0.0.0", port=port)