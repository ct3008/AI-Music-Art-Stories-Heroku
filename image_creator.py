import os
import requests
import replicate

# Load the API token
api_token = os.getenv("LAB_DISCO_API_KEY")
api = replicate.Client(api_token=api_token)

# Define textures, imageries, and styles
textures = [
    'painting', 'calligraphy brush ink stroke', 'pastel watercolor on canvas',
    'charcoal drawing', 'pencil drawing', 'impasto palette knife painting',
    'mosaic', 'jagged, irregular', 'rubbed graphite on paper', 'digital glitch',
    'splattered paint', 'graffiti', 'ink blots'
]

imageries = [
    'blossoming flower', 'chaotic intertwining lines', 'flowing waves',
    'starry night', 'curvilinear intertwined circles', 'whirling lines',
    'vibrant kaleidoscope of colors', 'interstellar light trails',
    'abstract fractal patterns', 'dissolving geometric shards',
    'diffused cosmic mists', 'translucent ripple effects'
]


# Define the target imageries for specific combinations
selected_combinations = {
    "chaotic intertwining lines": [ 'jagged, irregular', 'splattered paint', 'digital glitch'],
    "flowing waves": ['mosaic', 'impasto palette knife painting', 'rubbed graphite on paper', 'pastel watercolor on canvas', 'graffiti'],
    "curvilinear intertwined circles": ['mosaic', 'charcoal drawing', 'impasto palette knife painting', 'jagged,irregular', 'pastel watercolor on canvas'],
    "whirling lines": ['painting', 'digital glitch', 'ink blots', 'graffiti', 'pencil drawing'],
    "interstellar light trails": ['painting', 'jagged,irregular', 'digital glitch', 'calligraphy brush ink stroke', 'ink blots'],
    "abstract fractal patterns": ['impasto palette knife painting', 'mosaic', 'charcoal drawing', 'splattered paint', 'rubbed graphite on paper'],
    "dissolving geometric shards": ['painting', 'graffiti', 'digital glitch', 'jagged,irregular', 'pencil drawing'],
    "translucent ripple effects": ['mosaic', 'charcoal drawing', 'ink blots', 'impasto palette knife painting', 'digital glitch']
}

# Function to run prompts and save outputs
def generate_images(api, combinations):
    for imagery, textures in combinations.items():
        for texture in textures:
            prompt = f"simple, aesthetic, abstract {imagery} in {texture} texture"
            print(f"Running prompt: {prompt}")

            # Run the replicate API
            try:
                output = api.run(
                    "stability-ai/stable-diffusion-3.5-large",
                    input={"prompt": prompt}
                )
                print("generated image: ", output)

                # Save each image with a dynamic name
                for index, item in enumerate(output):
                    response = requests.get(item)
                    if response.status_code == 200:
                        filename = f"./images/{imagery.replace(' ', '_')}_{texture.replace(' ', '_')}_output_{index}.webp"
                        with open(filename, "wb") as file:
                            file.write(response.content)
                        print(f"Image saved: {filename}")
                    else:
                        print(f"Failed to download image at {item}")

            except Exception as e:
                print(f"Error generating image for prompt '{prompt}': {e}")

# Run the function
generate_images(api, selected_combinations)
