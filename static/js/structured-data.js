/**
 * Structured Data Generator
 * This script dynamically generates structured data (JSON-LD) 
 * for rich search results in Google and other search engines.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Base structured data for the WebApplication
    const baseStructuredData = {
        "@context": "https://schema.org",
        "@type": "WebApplication",
        "name": "AI Art Thumbnail Generator",
        "url": "https://aiart-zroo.onrender.com",
        "description": "AI-powered tool for creating professional YouTube thumbnails instantly",
        "applicationCategory": "DesignApplication",
        "offers": {
            "@type": "Offer",
            "price": "0",
            "priceCurrency": "USD"
        },
        "operatingSystem": "Web Browser",
        "featureList": [
            "AI-generated thumbnails",
            "Custom style references",
            "High-resolution downloads",
            "API integration"
        ]
    };
    
    // Check if we're on a page with generated content
    const generatedThumbnail = document.querySelector('.generated-thumbnail img');
    
    if (generatedThumbnail) {
        // Add CreativeWork data for the generated thumbnail
        const thumbnailData = {
            "@context": "https://schema.org",
            "@type": "ImageObject",
            "contentUrl": generatedThumbnail.src,
            "name": "AI-Generated Thumbnail",
            "description": document.querySelector('#video-description') ? document.querySelector('#video-description').value : "AI-Generated Thumbnail",
            "creator": {
                "@type": "Organization",
                "name": "AI Art Thumbnail Generator",
                "url": "https://aiart-zroo.onrender.com"
            },
            "dateCreated": new Date().toISOString()
        };
        
        // Add the structured data to the page
        addStructuredData(thumbnailData);
    }
    
    // Add structured data for sample thumbnails
    const sampleThumbnails = document.querySelectorAll('.gallery-grid .thumbnail-card img');
    if (sampleThumbnails && sampleThumbnails.length > 0) {
        const imageGalleryData = {
            "@context": "https://schema.org",
            "@type": "ImageGallery",
            "name": "AI Art Thumbnail Examples",
            "description": "Gallery of YouTube thumbnails created with our AI thumbnail generator",
            "image": Array.from(sampleThumbnails).map(img => ({
                "@type": "ImageObject",
                "contentUrl": "https://aiart-zroo.onrender.com" + img.getAttribute('src'),
                "name": img.getAttribute('alt'),
                "description": img.getAttribute('alt'),
                "encodingFormat": "image/jpeg"
            }))
        };
        
        // Add the structured data to the page
        addStructuredData(imageGalleryData);
    }
    
    // Always add the base structured data
    addStructuredData(baseStructuredData);
    
    /**
     * Adds structured data to the page
     * @param {Object} data - The structured data object
     */
    function addStructuredData(data) {
        const script = document.createElement('script');
        script.type = 'application/ld+json';
        script.text = JSON.stringify(data);
        document.head.appendChild(script);
    }
}); 