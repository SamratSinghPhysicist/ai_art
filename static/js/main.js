// Initialize drag and drop for image upload
function initDragAndDrop() {
    const dropArea = document.getElementById('drop-area');
    const fileInput = document.getElementById('image-upload');
    const previewContainer = document.getElementById('preview-container');
    const imagePreview = document.getElementById('image-preview');
    const browseBtn = document.querySelector('.browse-btn');
    
    if (!dropArea || !fileInput) return;
    
    // Click browse button to trigger file input
    if (browseBtn) {
        browseBtn.addEventListener('click', () => {
            fileInput.click();
        });
    }
    
    // Prevent default behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    // Highlight drop area when item is dragged over it
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, unhighlight, false);
    });
    
    function highlight() {
        dropArea.classList.add('highlight');
    }
    
    function unhighlight() {
        dropArea.classList.remove('highlight');
    }
    
    // Handle dropped files
    dropArea.addEventListener('drop', handleDrop, false);
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        
        if (files.length) {
            fileInput.files = files;
            updateFilePreview(files[0]);
        }
    }
    
    // Handle file input change
    fileInput.addEventListener('change', function() {
        if (this.files.length) {
            updateFilePreview(this.files[0]);
        }
    });
    
    // Update preview image
    function updateFilePreview(file) {
        if (!file.type.match('image.*')) {
            alert('Please select an image file');
            return;
        }
        
        if (file.size > 5 * 1024 * 1024) {
            alert('File size exceeds 5MB limit');
            return;
        }
        
        const reader = new FileReader();
        reader.onload = function(e) {
            imagePreview.src = e.target.result;
            previewContainer.classList.remove('hidden');
        };
        reader.readAsDataURL(file);
    }
}

// Call this function when the DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initTabs();
    initStyleSelector();
    initEnhancePrompt();
    initDragAndDrop();
    handleFormSubmission();
}); 