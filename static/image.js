
const dropArea = document.getElementById("drop-area");
const inputFile = document.getElementById("input-file");
const imageView = document.getElementById("img-view");

let draggedElement = null;

// Upload image when a file is selected
inputFile.addEventListener("change", uploadImage);

async function uploadImage() {
    const file = inputFile.files[0];
    if (!file) {
        console.error("No file selected!");
        return;
    }

    try {
        // Create a FormData object to send the file
        const formData = new FormData();
        formData.append("image", file);

        // Send the file to your backend's upload endpoint
        const response = await fetch("/upload_image", {
            method: "POST",
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`Failed to upload image: ${response.statusText}`);
        }

        // Parse the response to get the Cloudinary URL
        const data = await response.json();
        const imgLink = data.url; // This assumes your backend sends the Cloudinary `secure_url`

        console.log("Uploaded image URL:", imgLink);
        setImage(imgLink);
    } catch (error) {
        console.error("Error uploading image:", error);
    }
}

// Handles dragging an image from file or image elements
dropArea.addEventListener("dragover", (e) => {
    e.preventDefault();
});

dropArea.addEventListener("drop", (e) => {
    e.preventDefault();

    // Check if the dropped item is a file or an <img> element
    const dataTransfer = e.dataTransfer;

    if (dataTransfer.files.length > 0) {
        // If files are being dropped, handle file upload
        inputFile.files = dataTransfer.files;
        uploadImage();
    } else {
        // If an image element is being dragged
        let imgSrc = e.dataTransfer.getData("text/uri-list");
        if (!imgSrc) {
            // Fallback in case "uri-list" is not supported
            imgSrc = e.dataTransfer.getData("text/html");
            const imgElement = new DOMParser().parseFromString(imgSrc, "text/html").querySelector("img");
            if (imgElement) {
                imgSrc = imgElement.src;
            }
        }

        if (imgSrc) {
            console.log("Image link from drag:", imgSrc);
            setImage(imgSrc);
        }
    }

    // Reset dragging state
    if (draggedElement) {
        draggedElement.classList.remove("dragging");
        draggedElement = null;
    }
});

// Add drag event listeners to the draggable element
document.addEventListener("dragstart", (e) => {
    if (e.target.tagName === "IMG") {
        draggedElement = e.target;
        e.target.classList.add("dragging");
    }
});

document.addEventListener("dragend", (e) => {
    if (draggedElement) {
        draggedElement.classList.remove("dragging");
        draggedElement = null;
    }
});

// Helper function to set the background image
function setImage(imgLink) {
    imageView.style.backgroundImage = `url(${imgLink})`;
    imageView.textContent = "";
    imageView.style.border = 0;
}
