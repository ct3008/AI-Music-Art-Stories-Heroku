import warnings
import os
import librosa
import numpy as np
import tempfile
from flask import Flask, jsonify, request, render_template, session, send_file, request
import replicate
from dotenv import load_dotenv
import requests
from tasks import long_running_task, generate_image_task, download_prompt #for Heroku, "forking", reason we have redis
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

#------------------- Basic set-up -------------------
load_dotenv()
app = Flask(__name__, template_folder='./templates', static_folder='./static')
CORS(app)

# Let Cloudinary set-up (image storage)
cloudinary.config(
    cloudinary_url=os.getenv("CLOUDINARY_URL"),
    secure=True
)
conf = cloudinary.config()


# API key storage (many variations because of synchronicity issues)
api_key_storage = ''

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
            # print("DISCO KEYWORD: ", api_key)
        else:
            # Store the API key (you can replace this with database/file storage)
            api_key_storage = api_key
            # print("API KEY: ", api_key_storage)
            # print("Stored in environ after: ", os.getenv("LAB_DISCO_API_KEY"))
            redis_conn.set("api_key", api_key)
            # print("Stored in redis: ", redis_conn.get("api_key").decode('utf-8'))

        return jsonify({'message': 'API Key saved successfully!'}), 200
    except Exception as e:
        return jsonify({'message': f'Error: {str(e)}'}), 500

# Basic API routes
@app.route('/')
def homepage():
    return render_template('waveform.html')

@app.route('/quick_start')
def quick_start():
    return render_template('quick_start.html')

#------------------- Audio File -------------------
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


#------------------- Upload/Generate Image -------------------

# Upload your own image
@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file_to_upload = request.files['image']

    # Upload the image to Cloudinary
    result = cloudinary.uploader.upload(file_to_upload)

    # Return the static URL
    return jsonify({"url": result['secure_url']})

# Fills in "Previously Generated Images" Container
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
    
# Generate Image using replicate model
@app.route('/generate_initial', methods=['POST'])
def generate_initial():
    data = request.get_json()
    prompt = data.get('prompt', '')
    api_key = api_key_storage
    if api_key and os.getenv("LAB_DISCO_API_KEY") and redis_conn.get("api_key"):
        data['api_key'] = api_key
    elif redis_conn.get("api_key"):
        data['api_key'] = redis_conn.get("api_key").decode('utf-8')
    else:
        data['api_key'] = os.getenv("LAB_DISCO_API_KEY")

    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400

    # Enqueue the task and return the job ID
    try:
        job = queue.enqueue(generate_image_task, data, job_timeout=300)  # Set a job timeout (e.g., 60 seconds)
        return jsonify({'job_id': job.get_id(), 'status': 'queued'}), 202
    except Exception as e:
        return jsonify({'error': str(e)}), 500


#------------------- Video Creation -------------------
@app.route("/process-data", methods=["POST"])
def process_data():
    data = request.json

    api_key = api_key_storage
    if api_key and os.getenv("LAB_DISCO_API_KEY") and redis_conn.get("api_key"):
        # print("input box chosen process")
        data['api_key'] = api_key
    elif redis_conn.get("api_key"):
        # print("redis chosen process")
        data['api_key'] = redis_conn.get("api_key").decode('utf-8')
    else:
        # print("os env chosen process")
        data['api_key'] = os.getenv("LAB_DISCO_API_KEY")
    print("ABOUT TO ENQUEUE. Key used: ", data['api_key'])
    job = queue.enqueue(long_running_task, data,job_timeout=3000)
    print(job)
    print("done enqueueing")
    
    # Respond immediately with the job ID
    return jsonify({"job_id": job.get_id(), "status": "queued"}), 202

#------------------- Download and Adjust Video -------------------

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

#------------------- Helpers -------------------

# Calls helper functions to get queue length -> length (1)
@app.route('/get_queue_length', methods=['GET'])
def queue_length():
    queue_length = get_queue_length()
    return jsonify({"queue_length": queue_length}), 200

#Gets total number of jobs (started + in queue) -> length (2)
def get_queue_length():
    queue_key = f"rq:queue:{queue.name}"
    num_queue_key = redis_conn.llen(queue_key)
    num_started_key = get_started_task_count()
    print("queue items, in progress items: ", num_queue_key, num_started_key)

    return num_queue_key + num_started_key

# Count number of jobs -> length (3)
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

# Check job status
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

# Download Prompt
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