/**
 * Script to fix authentication issues across pages
 * This specifically addresses the error "Authentication error: Unexpected token '<', '<!DOCTYPE "...' is not valid JSON"
 */

// Immediately check if user is logged in - this runs before DOMContentLoaded
(function immediateAuthCheck() {
    // Check for auth token in localStorage
    const authToken = localStorage.getItem('authToken');
    if (authToken) {
        console.log('Auth token found in localStorage - user should be logged in');
        
        // This will be fixed when DOM is loaded
        // Just mark it for later checks
        window.hasAuthToken = true;
    }
})();

document.addEventListener('DOMContentLoaded', function() {
    console.log('Auth-fix script loaded');
    
    // Check if logout was initiated on another page
    if (localStorage.getItem('logout_in_progress') === 'true') {
        console.log('Detected logout in progress from another page');
        // Continue logout process on this page
        ensureCompleteLogout();
        return; // Stop further execution of this script
    }
    
    // Fix for "Unexpected token" error when attempting authentication
    // This happens when the server returns HTML instead of JSON
    // We'll intercept fetch requests to login and signup endpoints
    const originalFetch = window.fetch;
    window.fetch = function(url, options) {
        // Only intercept login and signup requests
        if (typeof url === 'string' && (url.includes('/login') || url.includes('/signup'))) {
            if (!options) options = {};
            if (!options.headers) options.headers = {};
            
            // Ensure proper headers
            options.headers['Content-Type'] = 'application/json';
            options.headers['Accept'] = 'application/json';
            
            // Additional error handling
            return originalFetch(url, options)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Server responded with status: ${response.status}`);
                    }
                    return response;
                })
                .catch(error => {
                    console.error('Authentication request error:', error);
                    // Remove any existing session data on error
                    localStorage.removeItem('authToken');
                    throw error;
                });
        }
        
        // Intercept logout requests to ensure complete logout
        if (typeof url === 'string' && url.includes('/logout')) {
            // Ensure we clear all auth state before proceeding with the actual logout
            ensureCompleteLogout();
            
            // Then proceed with the original fetch
            return originalFetch(url, options);
        }
        
        // Call original fetch for all other requests
        return originalFetch(url, options);
    };
    
    // Function to ensure complete logout across all pages
    window.ensureCompleteLogout = function() {
        console.log('Performing complete logout across all pages');
        
        // Set a flag indicating logout in progress to avoid navigation before complete
        localStorage.setItem('logout_in_progress', 'true');
        
        // Clear all auth-related localStorage items immediately
        localStorage.removeItem('authToken');
        
        // Try to clear all Firebase-related localStorage
        try {
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && 
                    (key.includes('firebase') || 
                     key.includes('firebaseui') || 
                     key.includes('auth') || 
                     key.includes('token'))) {
                    console.log('Removing localStorage item:', key);
                    localStorage.removeItem(key);
                }
            }
        } catch (e) {
            console.error('Error clearing localStorage:', e);
        }
        
        // Clear all session cookies related to authentication
        document.cookie.split(';').forEach(function(c) {
            document.cookie = c.trim().split('=')[0] + '=;' + 'expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        });
        
        // First, call the server-side logout endpoint
        console.log('Calling server-side logout endpoint');
        
        // Promise for server logout
        const serverLogoutPromise = fetch('/logout', {
            method: 'GET',
            credentials: 'same-origin'
        })
        .then(response => {
            console.log('Server-side logout response:', response.status);
            return response;
        })
        .catch(error => {
            console.error('Server-side logout error:', error);
            // Continue with client-side logout even if server logout fails
        });
        
        // Firebase signout promise
        const firebaseLogoutPromise = new Promise((resolve) => {
            if (typeof firebase !== 'undefined' && firebase.auth) {
                console.log('Starting Firebase signOut');
                firebase.auth().signOut()
                    .then(() => {
                        console.log('Firebase signOut successful');
                        resolve();
                    })
                    .catch(error => {
                        console.error('Firebase signOut error:', error);
                        resolve(); // Resolve anyway to continue logout process
                    });
            } else {
                console.log('Firebase auth not available');
                resolve();
            }
        });
        
        // Wait for both logout processes to complete or fail
        Promise.all([serverLogoutPromise, firebaseLogoutPromise])
            .then(() => {
                console.log('All logout processes completed');
                
                // Final cleanup
                localStorage.removeItem('logout_in_progress');
                
                // Force reload from server (not from cache) to ensure fresh state
                console.log('Redirecting to home page with forced reload');
                window.location.href = '/?nocache=' + new Date().getTime();
            })
            .catch(error => {
                console.error('Error during logout process:', error);
                
                // Still redirect even if there was an error
                localStorage.removeItem('logout_in_progress');
                window.location.href = '/?nocache=' + new Date().getTime();
            });
    };
    
    // Attach the logout function to all logout links
    document.querySelectorAll('a[href="/logout"]').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            ensureCompleteLogout();
        });
    });
    
    // Fix for maintaining authentication across pages
    if (typeof firebase !== 'undefined') {
        const authToken = localStorage.getItem('authToken');
        
        if (authToken) {
            console.log('Found auth token in localStorage, syncing with server...');
            
            // Force immediate UI update based on token presence
            if (typeof window.hasAuthToken !== 'undefined' && window.hasAuthToken) {
                forceUpdateNavbar(true);
            }
            
            // We need to validate the token with our server
            // This ensures the session is recognized on both client and server
            fetch('/validate-token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ token: authToken })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Token validation failed');
                }
                return response.json();
            })
            .then(data => {
                if (!data.valid) {
                    throw new Error('Invalid token');
                }
                console.log('Token validated successfully');
                
                // Force update navbar UI
                forceUpdateNavbar(true);
                
                // Check if auth-modal.js has loaded and expose functions to it
                if (typeof updateUIForLoggedInUser === 'function') {
                    // Force update UI for logged in user
                    console.log('Calling updateUIForLoggedInUser from auth-fix.js');
                    updateUIForLoggedInUser({ email: data.email || "user@example.com" });
                } else {
                    console.log('updateUIForLoggedInUser not available yet, setting up observer');
                    // Set up a MutationObserver to detect when auth-modal.js loads
                    let scriptObserver = new MutationObserver(function(mutations) {
                        if (typeof updateUIForLoggedInUser === 'function') {
                            console.log('updateUIForLoggedInUser now available, calling it');
                            updateUIForLoggedInUser({ email: data.email || "user@example.com" });
                            // Disconnect observer after function is found
                            scriptObserver.disconnect();
                        }
                    });
                    
                    // Start observing document for script additions
                    scriptObserver.observe(document.documentElement, {
                        childList: true,
                        subtree: true
                    });
                    
                    // Also try directly after a delay as a fallback
                    setTimeout(function() {
                        if (typeof updateUIForLoggedInUser === 'function') {
                            console.log('updateUIForLoggedInUser now available after timeout');
                            updateUIForLoggedInUser({ email: data.email || "user@example.com" });
                            scriptObserver.disconnect();
                        } else {
                            console.log('updateUIForLoggedInUser still not available, fixing UI manually');
                            // Manual UI update as fallback
                            forceUpdateNavbar(true);
                        }
                    }, 1000);
                }
            })
            .catch(error => {
                console.error('Error validating token:', error);
                localStorage.removeItem('authToken');
                
                // Check if auth-modal.js has loaded
                if (typeof updateUIForLoggedOutUser === 'function') {
                    console.log('Calling updateUIForLoggedOutUser after validation error');
                    updateUIForLoggedOutUser();
                } else {
                    console.log('updateUIForLoggedOutUser not available, fixing UI manually');
                    forceUpdateNavbar(false);
                }
            });
        } else {
            console.log('No auth token found, ensuring logged out UI');
            // No token, definitely logged out
            if (typeof updateUIForLoggedOutUser === 'function') {
                updateUIForLoggedOutUser();
            } else {
                forceUpdateNavbar(false);
            }
        }
    }
    
    // Force update navbar function - works independently of auth-modal.js
    function forceUpdateNavbar(isLoggedIn) {
        console.log('Manually fixing navbar, isLoggedIn:', isLoggedIn);
        const navLinksContainer = document.querySelector('.nav-links');
        if (!navLinksContainer) {
            console.error("Could not find .nav-links container");
            return;
        }
        
        // Find existing auth links
        const existingLoginLink = navLinksContainer.querySelector('a.nav-link[data-mode="login"], a.nav-link.open-auth-modal');
        const existingSignupLink = navLinksContainer.querySelector('a.nav-link[data-mode="signup"]') || 
                                  (existingLoginLink ? Array.from(navLinksContainer.querySelectorAll('a.nav-link.open-auth-modal'))
                                   .find(link => link !== existingLoginLink) : null);
        const existingMyImagesLink = navLinksContainer.querySelector('a.nav-link[href="/dashboard"]');
        const existingLogoutLink = navLinksContainer.querySelector('a.nav-link[href="/logout"]');
        
        if (isLoggedIn) {
            // User is logged in, show My Images & Logout
            if (existingLoginLink && !existingMyImagesLink) {
                const myImagesLink = document.createElement('a');
                myImagesLink.textContent = 'My Images';
                myImagesLink.href = '/dashboard';
                myImagesLink.className = 'nav-link';
                existingLoginLink.parentNode.replaceChild(myImagesLink, existingLoginLink);
            }
            
            if (existingSignupLink && !existingLogoutLink) {
                const logoutLink = document.createElement('a');
                logoutLink.textContent = 'Logout';
                logoutLink.href = '/logout';
                logoutLink.className = 'nav-link';
                // Add click handler
                logoutLink.addEventListener('click', function(e) {
                    e.preventDefault();
                    if (typeof window.ensureCompleteLogout === 'function') {
                        window.ensureCompleteLogout();
                    } else {
                        localStorage.setItem('logout_in_progress', 'true');
                        window.location.href = '/logout';
                    }
                });
                existingSignupLink.parentNode.replaceChild(logoutLink, existingSignupLink);
            }
        } else {
            // User is logged out, show Login & Signup
            if (existingMyImagesLink && !existingLoginLink) {
                const loginLink = document.createElement('a');
                loginLink.textContent = 'Login';
                loginLink.href = '#';
                loginLink.className = 'nav-link open-auth-modal';
                loginLink.setAttribute('data-mode', 'login');
                existingMyImagesLink.parentNode.replaceChild(loginLink, existingMyImagesLink);
            }
            
            if (existingLogoutLink && !existingSignupLink) {
                const signupLink = document.createElement('a');
                signupLink.textContent = 'Sign Up';
                signupLink.href = '#';
                signupLink.className = 'nav-link open-auth-modal';
                signupLink.setAttribute('data-mode', 'signup');
                existingLogoutLink.parentNode.replaceChild(signupLink, existingLogoutLink);
            }
        }
    }
}); 