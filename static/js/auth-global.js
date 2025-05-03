/**
 * Global Authentication Handler
 * Runs immediately on page load to ensure consistent auth state across all pages
 */

// IMMEDIATELY run this code before DOM is fully loaded
(function() {
    console.log('Global auth handler executing immediately');
    
    // Flag to track if we've completed initial auth check
    window.authCheckComplete = false;
    
    // Add a loading class to body until auth is determined - IMPORTANT: this hides the navbar
    document.documentElement.classList.add('auth-initializing');
    
    // Set initial UI state as logged out
    document.documentElement.classList.add('auth-logged-out');
    
    // Check if user has a valid auth token
    const authToken = localStorage.getItem('authToken');
    
    // Helper function to update navbar UI (works before DOM is fully loaded)
    function updateNavbarAuthState(isLoggedIn) {
        console.log('Updating navbar auth state, isLoggedIn:', isLoggedIn);
        
        // Don't update UI if state hasn't changed and initial check is complete
        if (window.authCheckComplete && window.currentAuthState === isLoggedIn) {
            console.log('Auth state unchanged, skipping UI update');
            return;
        }
        
        // Store current auth state
        window.currentAuthState = isLoggedIn;
        
        // Update auth state classes on document
        if (isLoggedIn) {
            document.documentElement.classList.remove('auth-logged-out');
            document.documentElement.classList.add('auth-logged-in');
        } else {
            document.documentElement.classList.remove('auth-logged-in');
            document.documentElement.classList.add('auth-logged-out');
        }
        
        // Only update DOM elements once it's safe to show the navbar
        function attemptDomUpdate() {
            const navLinksContainer = document.querySelector('.nav-links');
            if (!navLinksContainer) {
                return false;
            }
            
            // Target all possible login/signup link selectors to ensure we find them
            const loginLink = 
                navLinksContainer.querySelector('a[data-mode="login"], a.open-auth-modal[data-mode="login"], a[href="/login"], a[href="#"][class*="login"]');
            const signupLink = 
                navLinksContainer.querySelector('a[data-mode="signup"], a.open-auth-modal[data-mode="signup"], a[href="/signup"], a[href="#"][class*="signup"], a[href="#"][class*="sign-up"]');
            const myImagesLink = 
                navLinksContainer.querySelector('a[href="/dashboard"]');
            const logoutLink = 
                navLinksContainer.querySelector('a[href="/logout"]');
            
            if (isLoggedIn) {
                // User is logged in, show Dashboard and Logout
                
                // Handle Login → Dashboard
                if (loginLink && !myImagesLink) {
                    const newMyImagesLink = document.createElement('a');
                    newMyImagesLink.href = '/dashboard';
                    newMyImagesLink.className = loginLink.className.replace('open-auth-modal', '');
                    newMyImagesLink.textContent = 'Dashboard';
                    loginLink.parentNode.replaceChild(newMyImagesLink, loginLink);
                }
                
                // Handle Signup → Logout
                if (signupLink && !logoutLink) {
                    const newLogoutLink = document.createElement('a');
                    newLogoutLink.href = '/logout';
                    newLogoutLink.className = signupLink.className.replace('open-auth-modal', '');
                    newLogoutLink.textContent = 'Logout';
                    
                    // Add logout handler
                    newLogoutLink.addEventListener('click', function(e) {
                        e.preventDefault();
                        localStorage.setItem('logout_in_progress', 'true');
                        localStorage.removeItem('authToken');
                        window.location.href = '/logout';
                    });
                    
                    signupLink.parentNode.replaceChild(newLogoutLink, signupLink);
                }
            } else {
                // User is logged out, show Login and Signup
                
                // Handle Dashboard → Login
                if (myImagesLink && !loginLink) {
                    const newLoginLink = document.createElement('a');
                    newLoginLink.href = '#';
                    newLoginLink.className = 'nav-link open-auth-modal';
                    newLoginLink.setAttribute('data-mode', 'login');
                    newLoginLink.textContent = 'Login';
                    
                    // Add click handler for modal
                    newLoginLink.addEventListener('click', function(e) {
                        e.preventDefault();
                        if (typeof openAuthModal === 'function') {
                            openAuthModal('login');
                        } else {
                            // Fallback if function not available yet
                            window.location.href = '/?action=login';
                        }
                    });
                    
                    myImagesLink.parentNode.replaceChild(newLoginLink, myImagesLink);
                }
                
                // Handle Logout → Signup
                if (logoutLink && !signupLink) {
                    const newSignupLink = document.createElement('a');
                    newSignupLink.href = '#';
                    newSignupLink.className = 'nav-link open-auth-modal';
                    newSignupLink.setAttribute('data-mode', 'signup');
                    newSignupLink.textContent = 'Sign Up';
                    
                    // Add click handler for modal
                    newSignupLink.addEventListener('click', function(e) {
                        e.preventDefault();
                        if (typeof openAuthModal === 'function') {
                            openAuthModal('signup');
                        } else {
                            // Fallback if function not available yet
                            window.location.href = '/?action=signup';
                        }
                    });
                    
                    logoutLink.parentNode.replaceChild(newSignupLink, logoutLink);
                }
            }
            
            return true;
        }
        
        // First try immediate DOM update
        const updated = attemptDomUpdate();
        
        // Then remove loading state once all updates are ready
        function finalizeUIState() {
            // Remove initializing class to show navbar with correct state
            document.documentElement.classList.remove('auth-initializing');
            console.log('Auth initialization complete, navbar visible now');
        }
        
        // If we couldn't update DOM immediately, set up retry logic
        if (!updated) {
            let attempts = 0;
            const maxAttempts = 5;
            
            function retryDomUpdate() {
                if (attemptDomUpdate()) {
                    finalizeUIState();
                    return;
                }
                
                attempts++;
                if (attempts < maxAttempts) {
                    setTimeout(retryDomUpdate, 200);
                } else {
                    // Even if DOM update failed, still show navbar after max attempts
                    finalizeUIState();
                }
            }
            
            // Start retry process
            setTimeout(retryDomUpdate, 100);
        } else {
            // DOM updated successfully, finalize UI state
            finalizeUIState();
        }
    }
    
    // Function to validate token with the server
    function validateAuthToken(token) {
        console.log('Validating token with server');
        return fetch('/validate-token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ token: token })
        })
        .then(response => {
            if (!response.ok) {
                console.error(`Token validation server response not OK: ${response.status}`);
                throw new Error('Token validation failed');
            }
            return response.json();
        })
        .then(data => {
            if (!data.valid) {
                console.error('Server explicitly reported token as invalid');
                throw new Error('Invalid token');
            }
            console.log('Token successfully validated with server');
            return data;
        });
    }
    
    // Set a global flag we can check later
    window.globalAuthInitialized = true;
    
    // IMPORTANT: Only validate if we have a token, otherwise assume logged out immediately
    if (authToken) {
        console.log('Auth token found, validating with server...');
        
        // Validate with server - this will update the UI after validation
        validateAuthToken(authToken)
            .then(data => {
                console.log('Auth token validated successfully, updating UI');
                window.userEmail = data.email || "user@example.com";
                updateNavbarAuthState(true);
                window.authCheckComplete = true;
            })
            .catch(err => {
                console.error('Auth token validation failed:', err);
                console.log('Removing invalid token from localStorage');
                localStorage.removeItem('authToken');
                updateNavbarAuthState(false);
                window.authCheckComplete = true;
            });
    } else {
        // No token, immediately set UI to logged out state
        console.log('No auth token found, setting UI to logged out state');
        updateNavbarAuthState(false);
        window.authCheckComplete = true;
    }
    
    // Make the openAuthModal function globally available
    window.openAuthModal = function(mode) {
        // First try passing to auth-modal.js if it's loaded
        if (typeof document.querySelector('.auth-modal-overlay') !== 'undefined') {
            const authModal = document.querySelector('.auth-modal-overlay');
            if (authModal) {
                // Update mode in the modal
                if (mode === 'login' || mode === 'signup') {
                    const loginTab = document.getElementById('loginTab');
                    const signupTab = document.getElementById('signupTab');
                    if (loginTab && signupTab) {
                        if (mode === 'login') {
                            loginTab.classList.add('active');
                            signupTab.classList.remove('active');
                        } else {
                            loginTab.classList.remove('active');
                            signupTab.classList.add('active');
                        }
                    }
                }
                
                // Show the modal
                authModal.classList.add('active');
                document.body.style.overflow = 'hidden';
                return;
            }
        }
        
        // Fallback: redirect to homepage with action parameter
        window.location.href = `/?action=${mode}`;
    };
    
    // Fix for Google Auth on all pages
    window.addEventListener('DOMContentLoaded', function() {
        // Double-check auth state after DOM is fully loaded
        if (!window.authCheckComplete) {
            checkAuthStateAndUpdateUI();
        }
        
        // Set up modal trigger event listeners
        setupAuthButtonHandlers();
        
        // Fix Google Auth button functionality
        function setupGoogleAuthButton() {
            const googleAuthBtn = document.getElementById('googleAuthBtn');
            if (!googleAuthBtn) return false;
            
            // Remove existing listeners
            const newBtn = googleAuthBtn.cloneNode(true);
            googleAuthBtn.parentNode.replaceChild(newBtn, googleAuthBtn);
            
            // Add fresh click handler
            newBtn.addEventListener('click', function() {
                console.log('Google auth button clicked');
                
                if (typeof firebase === 'undefined' || !firebase.auth) {
                    console.error('Firebase auth not available!');
                    alert('Authentication system is not fully loaded. Please try again in a moment.');
                    return;
                }
                
                // Get current auth mode
                let currentMode = 'login';
                const modalTitle = document.getElementById('authModalTitle');
                if (modalTitle && modalTitle.textContent.includes('Sign Up')) {
                    currentMode = 'signup';
                }
                
                const provider = new firebase.auth.GoogleAuthProvider();
                firebase.auth().signInWithPopup(provider)
                    .then((result) => {
                        return result.user.getIdToken();
                    })
                    .then((idToken) => {
                        // Store token in localStorage for persistence
                        localStorage.setItem('authToken', idToken);
                        
                        // Determine endpoint based on current mode
                        const endpoint = currentMode === 'login' ? '/login' : '/signup';
                        
                        return fetch(endpoint, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'Accept': 'application/json'
                            },
                            body: JSON.stringify({ idToken: idToken })
                        });
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            // Immediately update UI
                            updateNavbarAuthState(true);
                            
                            // Close modal if it exists
                            const modal = document.getElementById('authModal');
                            if (modal) {
                                modal.classList.remove('active');
                                document.body.style.overflow = '';
                            }
                            
                            // Redirect after a short delay to ensure UI updates
                            setTimeout(() => {
                                window.location.href = data.redirect || '/dashboard';
                            }, 300);
                        } else {
                            console.error(data.error);
                            alert('Authentication error: ' + data.error);
                        }
                    })
                    .catch(error => {
                        console.error('Authentication error:', error);
                        alert('Authentication error: ' + error.message);
                    });
            });
            
            return true;
        }
        
        // Try to setup the button immediately
        if (!setupGoogleAuthButton()) {
            // If not available yet, observe DOM changes
            const observer = new MutationObserver(function() {
                if (setupGoogleAuthButton()) {
                    observer.disconnect();
                }
            });
            
            observer.observe(document, {
                childList: true, 
                subtree: true
            });
        }
    });
    
    // Function to set up auth button handlers
    function setupAuthButtonHandlers() {
        // Find all login/signup buttons and attach event handlers
        document.querySelectorAll('.open-auth-modal').forEach(button => {
            // Clone and replace to remove old listeners
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);
            
            // Add fresh handler
            newButton.addEventListener('click', function(e) {
                e.preventDefault();
                const mode = this.getAttribute('data-mode') || 'login';
                window.openAuthModal(mode);
            });
        });
    }
    
    // Function to check auth state and update UI accordingly
    function checkAuthStateAndUpdateUI() {
        const authToken = localStorage.getItem('authToken');
        
        if (authToken) {
            // We have a token, validate it
            validateAuthToken(authToken)
                .then(data => {
                    console.log('Auth token is valid, updating UI to logged in state');
                    updateNavbarAuthState(true);
                    window.authCheckComplete = true;
                })
                .catch(err => {
                    console.error('Auth token validation failed in checkAuthStateAndUpdateUI:', err);
                    localStorage.removeItem('authToken');
                    updateNavbarAuthState(false);
                    window.authCheckComplete = true;
                });
        } else {
            // No token, we're definitely logged out
            console.log('No auth token found, ensuring UI shows logged out state');
            updateNavbarAuthState(false);
            window.authCheckComplete = true;
        }
    }
    
    // Handle auth state changes from Firebase directly
    if (typeof firebase !== 'undefined' && firebase.auth) {
        firebase.auth().onAuthStateChanged(function(user) {
            console.log('Firebase auth state changed, user:', user ? 'signed in' : 'signed out');
            
            if (user) {
                console.log('Firebase auth state changed: User is signed in');
                
                // If user is signed in but we don't have a token, get one
                if (!localStorage.getItem('authToken')) {
                    user.getIdToken().then(function(token) {
                        console.log('Got token from Firebase, storing and updating UI');
                        localStorage.setItem('authToken', token);
                        
                        // Validate with server before updating UI
                        validateAuthToken(token)
                            .then(() => {
                                updateNavbarAuthState(true);
                            })
                            .catch(error => {
                                console.error('Server rejected token from Firebase:', error);
                                localStorage.removeItem('authToken');
                                updateNavbarAuthState(false);
                            });
                    }).catch(function(error) {
                        console.error('Error getting token from Firebase:', error);
                    });
                } else {
                    // Already have a token, validate it
                    checkAuthStateAndUpdateUI();
                }
            } else {
                console.log('Firebase auth state changed: User is signed out');
                
                // Clear token and update UI
                if (localStorage.getItem('authToken')) {
                    console.log('Clearing auth token due to Firebase signout');
                    localStorage.removeItem('authToken');
                }
                updateNavbarAuthState(false);
            }
        });
    } else {
        console.warn('Firebase auth not available, relying on server-side validation only');
    }
    
    // Listen for storage events to sync auth state across tabs
    window.addEventListener('storage', function(event) {
        if (event.key === 'authToken') {
            console.log('Auth token changed in another tab');
            checkAuthStateAndUpdateUI();
        }
    });
    
    // Periodically check auth status with server to catch any session mismatches
    function checkServerAuthStatus() {
        // Only run if there's an auth token in localStorage
        const authToken = localStorage.getItem('authToken');
        if (!authToken) {
            // No token, we are definitely logged out, no need to check
            console.log('No auth token, skipping server auth check');
            return;
        }
        
        console.log('Performing server auth status check');
        fetch('/check-auth-status')
            .then(response => response.json())
            .then(data => {
                const hasToken = !!localStorage.getItem('authToken');
                const serverIsAuth = data.authenticated;
                
                // Fix mismatch: Client thinks logged in (has token) but server says not authenticated
                if (hasToken && !serverIsAuth) {
                    console.warn('Auth mismatch: client has token but server says not authenticated');
                    localStorage.removeItem('authToken');
                    updateNavbarAuthState(false);
                }
                
                // Fix mismatch: Client thinks logged out (no token) but server says authenticated
                if (!hasToken && serverIsAuth) {
                    console.warn('Auth mismatch: client has no token but server says authenticated');
                    // This shouldn't happen, but let's force a server-side logout to be safe
                    fetch('/logout').catch(() => {});
                }
            })
            .catch(error => {
                console.error('Error checking server auth status:', error);
            });
    }
    
    // Check server auth status after a short delay to let page load first
    setTimeout(checkServerAuthStatus, 2000);
    
    // Also check periodically (every 5 minutes)
    setInterval(checkServerAuthStatus, 5 * 60 * 1000);
})(); 