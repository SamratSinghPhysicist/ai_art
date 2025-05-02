/**
 * Global Authentication Handler
 * Runs immediately on page load to ensure consistent auth state across all pages
 */

// IMMEDIATELY run this code before DOM is fully loaded
(function() {
    console.log('Global auth handler executing immediately');
    
    // Check if user has a valid auth token
    const authToken = localStorage.getItem('authToken');
    
    // Helper function to update navbar UI (works before DOM is fully loaded)
    function updateNavbarAuthState(isLoggedIn) {
        console.log('Updating navbar auth state, isLoggedIn:', isLoggedIn);
        
        // Function to modify navbar once it's available
        function modifyNavbar() {
            const navLinksContainer = document.querySelector('.nav-links');
            if (!navLinksContainer) {
                console.warn('Nav links container not found yet, will retry');
                return false;
            }
            
            // Find auth-related links
            const loginLink = navLinksContainer.querySelector('a[data-mode="login"], a.open-auth-modal[data-mode="login"]');
            const signupLink = navLinksContainer.querySelector('a[data-mode="signup"], a.open-auth-modal[data-mode="signup"]');
            const myImagesLink = navLinksContainer.querySelector('a[href="/dashboard"]');
            const logoutLink = navLinksContainer.querySelector('a[href="/logout"]');
            
            if (isLoggedIn) {
                // User is logged in, show My Images and Logout
                
                // Handle Login → My Images
                if (loginLink && !myImagesLink) {
                    const newMyImagesLink = document.createElement('a');
                    newMyImagesLink.href = '/dashboard';
                    newMyImagesLink.className = loginLink.className.replace('open-auth-modal', '');
                    newMyImagesLink.textContent = 'My Images';
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
                
                // Handle My Images → Login
                if (myImagesLink && !loginLink) {
                    const newLoginLink = document.createElement('a');
                    newLoginLink.href = '#';
                    newLoginLink.className = 'nav-link open-auth-modal';
                    newLoginLink.setAttribute('data-mode', 'login');
                    newLoginLink.textContent = 'Login';
                    myImagesLink.parentNode.replaceChild(newLoginLink, myImagesLink);
                }
                
                // Handle Logout → Signup
                if (logoutLink && !signupLink) {
                    const newSignupLink = document.createElement('a');
                    newSignupLink.href = '#';
                    newSignupLink.className = 'nav-link open-auth-modal';
                    newSignupLink.setAttribute('data-mode', 'signup');
                    newSignupLink.textContent = 'Sign Up';
                    logoutLink.parentNode.replaceChild(newSignupLink, logoutLink);
                }
            }
            
            return true;
        }
        
        // Try immediately
        if (!modifyNavbar()) {
            // If navbar isn't ready, set up a MutationObserver to wait for it
            const observer = new MutationObserver(function(mutations) {
                if (modifyNavbar()) {
                    observer.disconnect();
                }
            });
            
            // Start observing document for DOM changes
            observer.observe(document, {
                childList: true,
                subtree: true
            });
            
            // Also try again after a short delay
            setTimeout(function() {
                if (modifyNavbar()) {
                    observer.disconnect();
                }
            }, 100);
        }
    }
    
    // Function to validate token with the server
    function validateAuthToken(token) {
        return fetch('/validate-token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ token: token })
        })
        .then(response => {
            if (!response.ok) throw new Error('Token validation failed');
            return response.json();
        })
        .then(data => {
            if (!data.valid) throw new Error('Invalid token');
            return data;
        });
    }
    
    // Set a global flag we can check later
    window.globalAuthInitialized = true;
    
    // Initial UI update based on token presence
    if (authToken) {
        // Immediately update UI (don't wait for validation)
        updateNavbarAuthState(true);
        
        // Then validate with server
        validateAuthToken(authToken)
            .then(data => {
                console.log('Auth token validated successfully');
                // Token is valid, ensure UI is updated
                updateNavbarAuthState(true);
                window.userEmail = data.email || "user@example.com";
            })
            .catch(err => {
                console.error('Auth token validation failed:', err);
                // Token is invalid, remove it and update UI
                localStorage.removeItem('authToken');
                updateNavbarAuthState(false);
            });
    } else {
        // No token, ensure UI shows logged out state
        updateNavbarAuthState(false);
    }
    
    // Fix for Google Auth on all pages
    window.addEventListener('DOMContentLoaded', function() {
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
            
            // Also try after a delay
            setTimeout(function() {
                setupGoogleAuthButton();
                observer.disconnect();
            }, 1000);
        }
    });
})(); 