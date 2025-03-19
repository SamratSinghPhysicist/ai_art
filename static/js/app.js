// app.js - General application functionality

// Initialize any global application functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('App initialized');
    
    // Ensure all externally linked images have error fallbacks
    const images = document.querySelectorAll('img');
    images.forEach(img => {
        if (!img.hasAttribute('onerror') && !img.src.startsWith('data:')) {
            img.onerror = function() {
                // If image fails to load, replace with placeholder
                this.src = '/test_assets/placeholder.jpg';
                return true;
            };
        }
    });
});

// Add custom analytics tracking function (if needed)
function trackEvent(category, action, label) {
    console.log(`Event tracked: ${category} - ${action} - ${label}`);
    // Implement actual analytics tracking here if needed
} 