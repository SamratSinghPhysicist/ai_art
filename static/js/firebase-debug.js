// Firebase debug script
console.log('Firebase debug script loaded');

document.addEventListener('DOMContentLoaded', function() {
    // Check if Firebase SDK is loaded
    if (typeof firebase === 'undefined') {
        console.error('Firebase SDK not found. Check if the Firebase scripts are properly loaded.');
        
        // Add Firebase scripts dynamically as a fallback
        const addScript = (src) => {
            return new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = src;
                script.onload = resolve;
                script.onerror = reject;
                document.head.appendChild(script);
            });
        };
        
        Promise.all([
            addScript('https://www.gstatic.com/firebasejs/9.6.10/firebase-app-compat.js'),
            addScript('https://www.gstatic.com/firebasejs/9.6.10/firebase-auth-compat.js')
        ]).then(() => {
            console.log('Firebase SDK loaded dynamically');
            initFirebase();
        }).catch(error => {
            console.error('Failed to load Firebase SDK dynamically:', error);
        });
    } else {
        console.log('Firebase SDK already loaded');
        initFirebase();
    }
    
    function initFirebase() {
        try {
            // Check if Firebase config is available
            if (typeof firebaseConfig === 'undefined') {
                console.error('Firebase config not found. Make sure it is defined before initializing Firebase.');
                return;
            }
            
            console.log('Firebase config found:', firebaseConfig);
            
            // Check if Firebase is already initialized
            if (!firebase.apps || !firebase.apps.length) {
                console.log('Initializing Firebase with config');
                firebase.initializeApp(firebaseConfig);
                console.log('Firebase initialized successfully');
            } else {
                console.log('Firebase already initialized');
            }
            
            // Verify auth is working
            console.log('Firebase auth available:', typeof firebase.auth !== 'undefined');
            
            // Add a click event on login button for debugging
            const loginButtons = document.querySelectorAll('.open-auth-modal');
            if (loginButtons.length > 0) {
                console.log(`Found ${loginButtons.length} login/signup buttons`);
                loginButtons.forEach(btn => {
                    btn.addEventListener('click', function(e) {
                        console.log('Auth button clicked:', this.getAttribute('data-mode'));
                    });
                });
            } else {
                console.error('No login/signup buttons found with class .open-auth-modal');
            }
        } catch (error) {
            console.error('Firebase initialization error:', error);
        }
    }
}); 