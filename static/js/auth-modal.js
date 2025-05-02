// Auth Modal Functionality
// Global variables for UI functions
let updateUIForLoggedInUser;
let updateUIForLoggedOutUser;

document.addEventListener('DOMContentLoaded', function() {
    console.log("Auth modal script loaded");
    
    // Initialize Firebase
    try {
        console.log("Firebase initialization attempt");
        console.log("Firebase object available:", typeof firebase !== 'undefined');
        console.log("firebaseConfig available:", typeof firebaseConfig !== 'undefined');
        // Check if Firebase is already initialized
        if (typeof firebase === 'undefined') {
            console.error("Firebase SDK not found! Make sure Firebase scripts are loaded first.");
        } else if (!firebase.apps || !firebase.apps.length) {
            // If firebaseConfig is defined globally (from your templates), use it
            if (typeof firebaseConfig !== 'undefined') {
                console.log("Initializing Firebase with config:", firebaseConfig);
                firebase.initializeApp(firebaseConfig);
                
                // Try to restore auth state from localStorage if user is not signed in
                const storedToken = localStorage.getItem('authToken');
                if (storedToken) {
                    console.log("Found token in localStorage, attempting to sign in");
                    // We don't try to signInWithCustomToken anymore as it might fail
                    // Just set the auth state based on localStorage presence
                    firebase.auth().onAuthStateChanged(function(user) {
                        if (!user) {
                            console.log("No Firebase user despite having token - forcing UI update for logged in user");
                            // Force UI update as if user is logged in
                            updateUIForLoggedInUser({ email: "user@example.com" });
                        }
                    });
                }
            } else {
                console.error("Firebase config not found!");
            }
        } else {
            console.log("Firebase already initialized");
        }
    } catch (error) {
        console.error("Firebase initialization error:", error);
    }
    
    // Listen for auth state changes
    if (typeof firebase !== 'undefined') {
        console.log("Setting up auth state listener");
        firebase.auth().onAuthStateChanged((user) => {
            if (user) {
                console.log('[Auth Modal] User is signed in:', user.email);
                console.log('[Auth Modal] User object:', user);
                
                // Store token in localStorage for persistence across pages
                user.getIdToken().then((idToken) => {
                    localStorage.setItem('authToken', idToken);
                    console.log('[Auth Modal] Token stored in localStorage');
                    
                    // Immediately update UI without waiting for page refresh
                    updateUIForLoggedInUser(user);
                });
            } else {
                console.log('[Auth Modal] No user is signed in');
                
                // Check if we have a token in localStorage despite Firebase saying no user
                // This helps with cross-page auth state synchronization
                const storedToken = localStorage.getItem('authToken');
                if (storedToken) {
                    console.log('[Auth Modal] Token found in localStorage but Firebase has no user');
                    // Validate token with server
                    fetch('/validate-token', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ token: storedToken })
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.valid) {
                            console.log('[Auth Modal] Token is valid, updating UI as logged in');
                            updateUIForLoggedInUser({ email: data.email || "user@example.com" });
                        } else {
                            console.log('[Auth Modal] Token is invalid, removing from localStorage');
                            localStorage.removeItem('authToken');
                            updateUIForLoggedOutUser();
                        }
                    })
                    .catch(error => {
                        console.error('[Auth Modal] Error validating token:', error);
                        localStorage.removeItem('authToken');
                        updateUIForLoggedOutUser();
                    });
                } else {
                    // No token in localStorage, definitely logged out
                    localStorage.removeItem('authToken');
                    updateUIForLoggedOutUser();
                }
            }
        });
    }
    
    // Create modal if it doesn't exist
    if (!document.getElementById('authModal')) {
        console.log("Creating auth modal");
        createAuthModal();
    } else {
        console.log("Auth modal already exists");
    }
    
    // DOM Elements - find these after ensuring the modal exists
    const authModal = document.getElementById('authModal');
    const closeAuthModal = document.getElementById('closeAuthModal');
    const authModalTitle = document.getElementById('authModalTitle');
    const authModalSubtitle = document.getElementById('authModalSubtitle');
    const googleAuthBtn = document.getElementById('googleAuthBtn');
    const googleBtnText = document.getElementById('googleBtnText');
    const authSwitchText = document.getElementById('authSwitchText');
    
    // Find all open auth modal buttons throughout the document
    const openAuthModalBtns = document.querySelectorAll('.open-auth-modal');
    
    // Current auth mode (login or signup)
    let currentAuthMode = 'login';
    
    // Open modal with specific mode - making it globally available
    window.openAuthModal = function(mode) {
        if (!authModal) {
            console.error("Auth modal not found!");
            return;
        }
        
        currentAuthMode = mode || 'login';
        updateAuthModalContent();
        authModal.classList.add('active');
        document.body.style.overflow = 'hidden'; // Prevent scrolling when modal is open
    };
    
    // Close modal - making it globally available
    window.closeAuthModal = function() {
        if (!authModal) {
            console.error("Auth modal not found!");
            return;
        }
        
        authModal.classList.remove('active');
        document.body.style.overflow = ''; // Restore scrolling
    };
    
    // Update modal content based on mode
    function updateAuthModalContent() {
        if (!authModalTitle || !authModalSubtitle || !googleBtnText || !authSwitchText) {
            console.error("Auth modal elements not found!");
            return;
        }
        
        if (currentAuthMode === 'login') {
            authModalTitle.textContent = 'Welcome Back';
            authModalSubtitle.textContent = 'Sign in to continue your creative journey';
            googleBtnText.textContent = 'Sign in with Google';
            authSwitchText.innerHTML = 'Don\'t have an account? <a href="#" class="auth-footer-link" id="authSwitchBtn">Sign up</a>';
        } else {
            authModalTitle.textContent = 'Create Account';
            authModalSubtitle.textContent = 'Get started with your free AI Art account';
            googleBtnText.textContent = 'Sign up with Google';
            authSwitchText.innerHTML = 'Already have an account? <a href="#" class="auth-footer-link" id="authSwitchBtn">Login</a>';
        }
        // Re-attach event listener to the switch button after changing innerHTML
        const authSwitchBtn = document.getElementById('authSwitchBtn');
        if (authSwitchBtn) {
            authSwitchBtn.addEventListener('click', switchAuthMode);
        }
    }
    
    // Switch between login and signup modes
    function switchAuthMode(e) {
        e.preventDefault();
        currentAuthMode = currentAuthMode === 'login' ? 'signup' : 'login';
        updateAuthModalContent();
    }
    
    // UI update functions shared with other scripts
    updateUIForLoggedInUser = function(user) {
        console.log('[Auth Modal] Updating UI for logged in user:', user.email);
        
        // Force update navbar if available
        if (typeof window.forceUpdateNavbar === 'function') {
            window.forceUpdateNavbar(true);
        }
        
        // Close modal if it's open
        if (authModal && authModal.classList.contains('active')) {
            closeAuthModal();
        }
    };
    
    updateUIForLoggedOutUser = function() {
        console.log('[Auth Modal] Updating UI for logged out user');
        
        // Force update navbar if available
        if (typeof window.forceUpdateNavbar === 'function') {
            window.forceUpdateNavbar(false);
        }
    };
    
    // Event Listeners - Only add these if we found the elements
    function setupEventListeners() {
        // Find all open modal buttons
        const openAuthModalBtns = document.querySelectorAll('.open-auth-modal');
        
        if (openAuthModalBtns.length > 0) {
            openAuthModalBtns.forEach(btn => {
                // Remove any existing listeners to avoid duplicates
                const newBtn = btn.cloneNode(true);
                if (btn.parentNode) {
                    btn.parentNode.replaceChild(newBtn, btn);
                }
                
                // Add fresh listener
                newBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    console.log("Auth modal button clicked");
                    const mode = this.getAttribute('data-mode') || 'login';
                    openAuthModal(mode);
                });
            });
        } else {
            console.warn("No auth modal buttons found on page");
        }
        
        if (closeAuthModal) {
            closeAuthModal.addEventListener('click', function() {
                window.closeAuthModal();
            });
        }
        
        // Close modal when clicking outside the modal content
        if (authModal) {
            authModal.addEventListener('click', (e) => {
                if (e.target === authModal) {
                    window.closeAuthModal();
                }
            });
        }
        
        // Handle Google auth
        if (googleAuthBtn) {
            googleAuthBtn.addEventListener('click', handleGoogleAuth);
        } else {
            console.warn("Google auth button not found");
        }
    }
    
    // Setup event listeners
    setupEventListeners();
    
    // Close modal when pressing Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && authModal && authModal.classList.contains('active')) {
            window.closeAuthModal();
        }
    });
    
    // Check URL for login/signup parameters
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('action')) {
        const action = urlParams.get('action');
        if (action === 'login' || action === 'signup') {
            openAuthModal(action);
        }
    }
    
    // Redirect handling for direct access to login/signup URLs
    if (window.location.pathname === '/login') {
        // Redirect to home with login modal
        window.history.replaceState({}, document.title, '/?action=login');
        openAuthModal('login');
    }
    else if (window.location.pathname === '/signup') {
        // Redirect to home with signup modal
        window.history.replaceState({}, document.title, '/?action=signup');
        openAuthModal('signup');
    }
    
    // Handle Google authentication
    function handleGoogleAuth() {
        if (typeof firebase === 'undefined' || !firebase.auth) {
            console.error("Firebase auth not available!");
            alert("Authentication system is not available. Please refresh the page and try again.");
            return;
        }
        
        const provider = new firebase.auth.GoogleAuthProvider();
        firebase.auth().signInWithPopup(provider)
            .then((result) => {
                // Get ID token
                return result.user.getIdToken();
            })
            .then((idToken) => {
                // Store token in localStorage for persistence across pages
                localStorage.setItem('authToken', idToken);
                
                // Send token to server
                // The endpoint is different based on the auth mode
                const endpoint = currentAuthMode === 'login' ? '/login' : '/signup';
                return fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    body: JSON.stringify({ idToken: idToken })
                });
            })
            .then((response) => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then((data) => {
                if (data.success) {
                    // Close the modal first
                    window.closeAuthModal();
                    
                    // Force update UI immediately before redirecting
                    updateUIForLoggedInUser({ email: "user@example.com" });
                    
                    // Small delay to ensure UI updates before redirect
                    setTimeout(() => {
                        window.location.href = data.redirect;
                    }, 300);
                } else {
                    console.error(data.error);
                    alert('Authentication error: ' + data.error);
                }
            })
            .catch((error) => {
                console.error('Authentication error:', error);
                alert('Authentication error: ' + error.message);
            });
    }
    
    // Function to create the modal if it doesn't exist
    function createAuthModal() {
        const modalHTML = `
        <div class="auth-modal-overlay" id="authModal">
            <div class="auth-modal">
                <button class="auth-modal-close" id="closeAuthModal">×</button>
                
                <div class="auth-modal-left">
                    <div class="auth-modal-logo">
                        <span class="auth-modal-logo-text">AI Art</span>
                    </div>
                    
                    <h2 class="auth-modal-title" id="authModalTitle">Get Started</h2>
                    <p class="auth-modal-subtitle" id="authModalSubtitle">Sign in to continue your creative journey</p>
                    
                    <button id="googleAuthBtn" class="auth-provider-button">
                        <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google logo" class="auth-provider-icon">
                        <span class="auth-provider-text" id="googleBtnText">Continue with Google</span>
                    </button>
                    
                    <!-- Future auth providers would go here -->
                    <div class="auth-provider-button" style="opacity: 0.6; cursor: not-allowed;">
                        <svg class="auth-provider-icon" viewBox="0 0 24 24" fill="#000000"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/></svg>
                        <span class="auth-provider-text">More options coming soon</span>
                    </div>
                    
                    <div class="auth-modal-footer">
                        <p id="authSwitchText">Don't have an account? <a href="#" class="auth-footer-link" id="authSwitchBtn">Sign up</a></p>
                    </div>
                </div>
                
                <div class="auth-modal-right">
                    <div class="auth-decorations">
                        <div class="auth-decoration auth-deco-1"></div>
                        <div class="auth-decoration auth-deco-2"></div>
                        <div class="floating-icon icon-1">✨</div>
                        <div class="floating-icon icon-2">🎨</div>
                        <div class="floating-icon icon-3">🖌️</div>
                    </div>
                    
                    <div class="auth-right-content">
                        <img src="https://images.unsplash.com/photo-1581591524425-c7e0978865fc?ixlib=rb-4.0.3&auto=format&fit=crop&w=500&q=80" alt="AI generated art" class="auth-right-image">
                        <h3 class="auth-right-title">Unleash Your Creativity</h3>
                        <p class="auth-right-description">Join our community and start creating stunning AI-generated artwork today.</p>
                    </div>
                </div>
            </div>
        </div>`;
        
        const modalStylesHTML = `
        <style>
            /* Auth Modal Styles */
            .auth-modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.5);
                backdrop-filter: blur(5px);
                display: none;
                justify-content: center;
                align-items: center;
                z-index: 1000;
                opacity: 0;
                transition: opacity 0.3s ease;
            }
            
            .auth-modal-overlay.active {
                display: flex;
                opacity: 1;
            }
            
            .auth-modal {
                background-color: white;
                border-radius: 16px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                width: 90%;
                max-width: 900px;
                overflow: hidden;
                display: flex;
                position: relative;
                opacity: 0;
                transform: translateY(20px);
                transition: opacity 0.3s ease, transform 0.3s ease;
            }
            
            .auth-modal-overlay.active .auth-modal {
                opacity: 1;
                transform: translateY(0);
            }
            
            .auth-modal-left {
                flex: 1;
                padding: 40px;
                display: flex;
                flex-direction: column;
            }
            
            .auth-modal-right {
                flex: 1;
                background: linear-gradient(135deg, var(--gradient-end), var(--gradient-start));
                position: relative;
                overflow: hidden;
                display: none;
            }
            
            .auth-modal-logo {
                margin-bottom: 10px;
                display: inline-flex;
                align-items: center;
            }
            
            .auth-modal-logo-text {
                background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
                -webkit-background-clip: text;
                background-clip: text;
                -webkit-text-fill-color: transparent;
                font-size: 1.4rem;
                font-weight: 700;
                margin-left: 8px;
            }
            
            .auth-modal-close {
                position: absolute;
                top: 20px;
                right: 20px;
                background: none;
                border: none;
                font-size: 1.5rem;
                cursor: pointer;
                color: #666;
                z-index: 10;
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 50%;
                transition: all 0.2s;
            }
            
            .auth-modal-close:hover {
                background-color: rgba(0, 0, 0, 0.05);
                color: #333;
            }
            
            .auth-modal-title {
                font-size: 1.8rem;
                font-weight: 700;
                margin-bottom: 8px;
                color: var(--text);
            }
            
            .auth-modal-subtitle {
                color: var(--text-light);
                margin-bottom: 32px;
            }
            
            .auth-provider-button {
                display: flex;
                align-items: center;
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 16px;
                border: 1px solid var(--border);
                background-color: white;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
                position: relative;
                overflow: hidden;
            }
            
            .auth-provider-button::after {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(135deg, var(--gradient-start), var(--gradient-end));
                opacity: 0;
                transition: opacity 0.3s;
                z-index: 1;
            }
            
            .auth-provider-button:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(91, 143, 249, 0.2);
                border-color: transparent;
            }
            
            .auth-provider-button:hover::after {
                opacity: 1;
            }
            
            .auth-provider-button:hover .auth-provider-text {
                color: white;
                position: relative;
                z-index: 2;
            }
            
            .auth-provider-button:hover .auth-provider-icon {
                position: relative;
                z-index: 2;
            }
            
            .auth-provider-button:hover img {
                filter: brightness(10);
            }
            
            .auth-provider-icon {
                width: 24px;
                height: 24px;
                margin-right: 12px;
            }
            
            .auth-provider-text {
                font-weight: 500;
                color: var(--text);
                flex-grow: 1;
                text-align: center;
            }
            
            .auth-modal-footer {
                margin-top: auto;
                text-align: center;
                color: var(--text-light);
                font-size: 0.9rem;
            }
            
            .auth-footer-link {
                color: var(--primary);
                text-decoration: none;
                font-weight: 500;
            }
            
            .auth-footer-link:hover {
                text-decoration: underline;
            }
            
            .auth-right-content {
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100%;
                padding: 40px;
                position: relative;
                z-index: 2;
                color: white;
                text-align: center;
            }
            
            .auth-right-title {
                font-size: 2rem;
                font-weight: 700;
                margin-bottom: 20px;
            }
            
            .auth-right-description {
                font-size: 1.1rem;
                opacity: 0.9;
                line-height: 1.6;
                margin-bottom: 30px;
            }
            
            .auth-right-bg {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                opacity: 0.1;
            }
            
            .auth-modal-divider {
                display: flex;
                align-items: center;
                margin: 20px 0;
                color: var(--text-light);
            }
            
            .auth-modal-divider::before,
            .auth-modal-divider::after {
                content: "";
                flex: 1;
                height: 1px;
                background-color: var(--border);
                margin: 0 10px;
            }
            
            .auth-decorations {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
            }
            
            .auth-decoration {
                position: absolute;
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 50%;
            }
            
            .auth-deco-1 {
                width: 300px;
                height: 300px;
                top: -150px;
                right: -100px;
                animation: float 20s infinite alternate ease-in-out;
            }
            
            .auth-deco-2 {
                width: 200px;
                height: 200px;
                bottom: -100px;
                left: -50px;
                animation: float 15s infinite alternate-reverse ease-in-out;
            }
            
            .auth-modal-footer {
                margin-top: auto;
                text-align: center;
                color: var(--text-light);
                font-size: 0.9rem;
            }
            
            .auth-footer-link {
                color: var(--primary);
                text-decoration: none;
                font-weight: 500;
            }
            
            .auth-footer-link:hover {
                text-decoration: underline;
            }
            
            .auth-right-image {
                width: 80%;
                max-width: 300px;
                margin-bottom: 30px;
                border-radius: 10px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            }
            
            .floating-icon {
                position: absolute;
                z-index: 3;
                color: white;
                font-size: 2rem;
                filter: drop-shadow(0 4px 6px rgba(0,0,0,0.1));
                opacity: 0.7;
                animation-duration: 15s;
                animation-iteration-count: infinite;
                animation-timing-function: ease-in-out;
            }
            
            .icon-1 {
                top: 20%;
                left: 15%;
                animation-name: floatIcon1;
            }
            
            .icon-2 {
                top: 60%;
                left: 60%;
                animation-name: floatIcon2;
            }
            
            .icon-3 {
                top: 30%;
                left: 70%;
                animation-name: floatIcon3;
            }
            
            @keyframes floatIcon1 {
                0%, 100% { transform: translate(0, 0) rotate(0deg); }
                25% { transform: translate(15px, 15px) rotate(5deg); }
                50% { transform: translate(0, 30px) rotate(0deg); }
                75% { transform: translate(-15px, 15px) rotate(-5deg); }
            }
            
            @keyframes floatIcon2 {
                0%, 100% { transform: translate(0, 0) rotate(0deg); }
                25% { transform: translate(-15px, -10px) rotate(-5deg); }
                50% { transform: translate(0, -20px) rotate(0deg); }
                75% { transform: translate(15px, -10px) rotate(5deg); }
            }
            
            @keyframes floatIcon3 {
                0%, 100% { transform: translate(0, 0) rotate(0deg); }
                25% { transform: translate(10px, -15px) rotate(5deg); }
                50% { transform: translate(20px, 0) rotate(0deg); }
                75% { transform: translate(10px, 15px) rotate(-5deg); }
            }
            
            @keyframes float {
                0%, 100% { transform: translate(0, 0) rotate(0deg); }
                50% { transform: translate(-20px, 20px) rotate(5deg); }
            }
            
            @media (min-width: 768px) {
                .auth-modal-right {
                    display: block;
                }
            }
        </style>`;
        
        // Add styles to head
        document.head.insertAdjacentHTML('beforeend', modalStylesHTML);
        
        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }
}); 