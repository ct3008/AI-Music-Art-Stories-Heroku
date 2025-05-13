function show_brainstorming() {
    const brainstormingBox = document.getElementById("brainstormingBox")

    brainstormingBox.style.display = "block";
}

$(document).ready(function () {
    fetchRecentImages();

    // Function to fetch recent images from the backend
    function fetchRecentImages() {
        $.ajax({
            url: '/get_recent_images',
            type: 'GET',
            success: function (response) {
                if (response.status === 'success') {
                    const imagesContainer = $('#recent-images-container');
                    imagesContainer.empty(); // Clear any existing images

                    response.images.forEach(image => {
                        
                        const imageElement = $('<div class="img-wrapper"></div>');
                        const img = $('<img src="' + image.url + '" alt="Generated Image" class="img">');
                        const prompt = $('<p class="image-prompt">Prompt: ' + image.prompt + '</p>');

                        // When clicking on the image, show the prompt
                        img.on('click', function () {
                            alert('Prompt: ' + image.prompt); // You can display it differently, like in a modal
                        });

                        // Make the image draggable
                        img.on('mousedown', function (event) {
                            const $image = $(this);
                            let offsetX = event.clientX - $image.position().left;
                            let offsetY = event.clientY - $image.position().top;

                            $(document).on('mousemove.draggable', function (event) {
                                $image.css({
                                    left: event.clientX - offsetX,
                                    top: event.clientY - offsetY
                                });
                            });

                            $(document).on('mouseup.draggable', function () {
                                $(document).off('.draggable');
                            });
                        });

                        imageElement.append(img);
                        imageElement.append(prompt);
                        imagesContainer.append(imageElement);
                    });
                } else {
                    console.error('Failed to load recent images');
                }
            },
            error: function (xhr, status, error) {
                console.error('Error fetching recent images:', error);
            }
        });
    }



    $('#image-form').on('submit', function (event) {
        event.preventDefault();
        let prompt = $('#prompt').val();

        // Show loading indicator and hide generated image
        $('#loading-indicator').show();
        $('#generated-image').hide();

        $.ajax({
            url: '/generate_initial',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ prompt: prompt }),
            success: function (response) {
                // Hide loading indicator and handle job response
                // $('#loading-indicator').hide();

                if (response.job_id) {
                    // If job_id is returned, check job status every 2 seconds
                    checkJobStatus(response.job_id);
                } else {
                    alert('Error: Job ID not returned');
                }
            },
            error: function (xhr, status, error) {
                console.error('Error:', error);
                $('#loading-indicator').hide();
            }
        });
    });

    // Function to check job status
    function checkJobStatus(jobId) {
        $.ajax({
            url: `/check-job-status/${jobId}`,
            type: 'GET',
            success: function (response) {
                if(response.status == "started"){
                    console.log("Generate Image Status: in progress");
                    let responseTmp = response;
                    responseTmp.status = "in progress"
                    console.log("Job Details: ", responseTmp)

                } else{
                    console.log("Generate Image Status: ", response.status)
                    console.log("Job Details: ", response)
                }
                
                if (response.status === 'finished') {
                    if (response.result.error) {
                        $('#loading-indicator').hide();
                        console.log("error: ", response.result.error);
                        alert(`Error: ${response.result.error}. Check API dashboard and try again.`);
                        return; // Exit the function to prevent further processing
                    }else{
                        $('#loading-indicator').hide();
                        // Job completed, show the generated image
                        $('#generated-image').attr('src', response.result.output).show();
                    }

                } else if (response.status === 'failed') {
                    // Job failed, show error message
                    alert(`Error: ${response.result.error || 'An error occurred while processing the image'}`);
                } else {
                    // Job still processing, check again in 2 seconds
                    setTimeout(function () {
                        checkJobStatus(jobId);
                    }, 3000);
                }
            },
            error: function (xhr, status, error) {
                console.error('Error checking job status:', error);
                $('#loading-indicator').hide();
            }
        });
    }

    // Make the image draggable
    $('#output-container').on('mousedown', '#generated-image', function (event) {
        let $image = $(this);
        let offsetX = event.clientX - $image.position().left;
        let offsetY = event.clientY - $image.position().top;

        $(document).on('mousemove.draggable', function (event) {
            $image.css({
                left: event.clientX - offsetX,
                top: event.clientY - offsetY
            });
        });

        $(document).on('mouseup.draggable', function () {
            $(document).off('.draggable');
        });
    });
});
