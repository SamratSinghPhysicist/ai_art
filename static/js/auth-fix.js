/**
 * Script to fix authentication issues across pages
 * This specifically addresses the error "Authentication error: Unexpected token '<', '<!DOCTYPE "...' is not valid JSON"
 */

// Immediately check if user is logged in - this runs before DOMContentLoaded
(function immediateAuthCheck() {
    // Check for auth token in localStorage
    const authToken = localStorage.getItem('authToken');
    if (authToken) {
        // This will be fixed when DOM is loaded
        // Just mark it for later checks
        window.hasAuthToken = true;
    }
})();

document.addEventListener('DOMContentLoaded', function() {
    // Check if logout was initiated on another page
    if (localStorage.getItem('logout_in_progress') === 'true') {
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
        // Set a flag indicating logout in progress to avoid navigation before complete
        localStorage.setItem('logout_in_progress', 'true');
        
        // Immediately update UI to logged out state
        if (typeof forceUpdateNavbar === 'function') {
            forceUpdateNavbar(false);
        }
        
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
                    localStorage.removeItem(key);
                }
            }
        } catch (e) {
        }
        
        // Clear all session cookies related to authentication
        document.cookie.split(';').forEach(function(c) {
            document.cookie = c.trim().split('=')[0] + '=;' + 'expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
        });
        
        // First, call the server-side logout endpoint
        // Promise for server logout
        const serverLogoutPromise = fetch('/logout', {
            method: 'GET',
            credentials: 'same-origin',
            headers: {
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
        })
        .then(response => {
            return response;
        })
        .catch(error => {
            // Continue with client-side logout even if server logout fails
        });
        
        // Firebase signout promise
        const firebaseLogoutPromise = new Promise((resolve) => {
            if (typeof firebase !== 'undefined' && firebase.auth) {
                firebase.auth().signOut()
                    .then(() => {
                        resolve();
                    })
                    .catch(error => {
                        resolve(); // Resolve anyway to continue logout process
                    });
            } else {
                resolve();
            }
        });
        
        // Wait for both logout processes to complete or fail
        Promise.all([serverLogoutPromise, firebaseLogoutPromise])
            .then(() => {
                // Final cleanup
                localStorage.removeItem('logout_in_progress');
                
                // Force reload from server (not from cache) to ensure fresh state
                // Specify a full cache-busting reload
                const reloadUrl = '/?nocache=' + new Date().getTime();
                
                // Reset auth-related data one last time before reload
                localStorage.removeItem('authToken');
                sessionStorage.clear();
                
                // Use different reload method based on browser support
                if (navigator.userAgent.indexOf('MSIE') !== -1 || navigator.appVersion.indexOf('Trident/') > -1) {
                    // IE-specific reload
                    document.execCommand('ClearAuthenticationCache');
                    window.location.href = reloadUrl;
                } else {
                    // Modern browser - use location.replace for cleaner history
                    window.location.replace(reloadUrl);
                }
            })
            .catch(error => {
                // Still redirect even if there was an error
                localStorage.removeItem('logout_in_progress');
                localStorage.removeItem('authToken');
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
                    throw new Error('Token validation failed with status: ' + response.status);
                }
                return response.json();
            })
            .then(data => {
                if (!data.valid) {
                    throw new Error('Invalid token');
                }
                
                // Force update navbar UI - ONLY after server confirms the token is valid
                forceUpdateNavbar(true);
                
                // Check if auth-modal.js has loaded and expose functions to it
                if (typeof updateUIForLoggedInUser === 'function') {
                    // Force update UI for logged in user
                    updateUIForLoggedInUser({ email: data.email || "user@example.com" });
                } else {
                    // Set up a MutationObserver to detect when auth-modal.js loads
                    let scriptObserver = new MutationObserver(function(mutations) {
                        if (typeof updateUIForLoggedInUser === 'function') {
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
                            updateUIForLoggedInUser({ email: data.email || "user@example.com" });
                            scriptObserver.disconnect();
                        } else {
                            // Manual UI update as fallback
                            forceUpdateNavbar(true);
                        }
                    }, 1000);
                }
            })
            .catch(error => {
                // Token is invalid, remove it
                localStorage.removeItem('authToken');
                
                // Update UI to logged out state
                forceUpdateNavbar(false);
                
                // Check if auth-modal.js has loaded
                if (typeof updateUIForLoggedOutUser === 'function') {
                    updateUIForLoggedOutUser();
                }
            });
        } else {
            forceUpdateNavbar(false);
        }
    }
    
    // Helper function to forcibly update the navbar (used when other methods don't work)
    window.forceUpdateNavbar = function forceUpdateNavbar(isLoggedIn) {
        // First update document classes to reflect auth state
        if (isLoggedIn) {
            document.documentElement.classList.remove('auth-logged-out');
            document.documentElement.classList.add('auth-logged-in');
        } else {
            document.documentElement.classList.remove('auth-logged-in');
            document.documentElement.classList.add('auth-logged-out');
        }
        
        // Make sure initializing state is removed to show the navbar
        document.documentElement.classList.remove('auth-initializing');
        
        const navLinksContainer = document.querySelector('.nav-links');
        
        if (!navLinksContainer) {
            setTimeout(() => forceUpdateNavbar(isLoggedIn), 200);
            return;
        }
        
        // Target all possible login/signup link selectors to find them reliably
        const loginLinks = [
            ...navLinksContainer.querySelectorAll('a[data-mode="login"]'),
            ...navLinksContainer.querySelectorAll('a.open-auth-modal[data-mode="login"]'),
            ...navLinksContainer.querySelectorAll('a[href="/login"]'),
            ...navLinksContainer.querySelectorAll('a[href="#"][class*="login"]')
        ];
        
        const signupLinks = [
            ...navLinksContainer.querySelectorAll('a[data-mode="signup"]'),
            ...navLinksContainer.querySelectorAll('a.open-auth-modal[data-mode="signup"]'),
            ...navLinksContainer.querySelectorAll('a[href="/signup"]'),
            ...navLinksContainer.querySelectorAll('a[href="#"][class*="signup"]'),
            ...navLinksContainer.querySelectorAll('a[href="#"][class*="sign-up"]')
        ];
        
        const myImagesLinks = [...navLinksContainer.querySelectorAll('a[href="/dashboard"]')];
        const logoutLinks = [...navLinksContainer.querySelectorAll('a[href="/logout"]')];
        
        const loginLink = loginLinks.length > 0 ? loginLinks[0] : null;
        const signupLink = signupLinks.length > 0 ? signupLinks[0] : null;
        const myImagesLink = myImagesLinks.length > 0 ? myImagesLinks[0] : null;
        const logoutLink = logoutLinks.length > 0 ? logoutLinks[0] : null;
        
        if (isLoggedIn) {
            // User is logged in, show Dashboard and Logout
            if (loginLink && !myImagesLink) {
                const newMyImagesLink = document.createElement('a');
                newMyImagesLink.href = '/dashboard';
                newMyImagesLink.className = 'nav-link';
                newMyImagesLink.textContent = 'Dashboard';
                loginLink.parentNode.replaceChild(newMyImagesLink, loginLink);
            }
            
            if (signupLink && !logoutLink) {
                const newLogoutLink = document.createElement('a');
                newLogoutLink.href = '/logout';
                newLogoutLink.className = 'nav-link';
                newLogoutLink.textContent = 'Logout';
                
                // Add logout handler
                newLogoutLink.addEventListener('click', function(e) {
                    e.preventDefault();
                    window.ensureCompleteLogout();
                });
                
                signupLink.parentNode.replaceChild(newLogoutLink, signupLink);
            }
        } else {
            // User is logged out, show Login and Signup
            if (myImagesLink && !loginLink) {
                const newLoginLink = document.createElement('a');
                newLoginLink.href = '#';
                newLoginLink.className = 'nav-link open-auth-modal';
                newLoginLink.setAttribute('data-mode', 'login');
                newLoginLink.textContent = 'Login';
                
                // Add click handler
                newLoginLink.addEventListener('click', function(e) {
                    e.preventDefault();
                    if (typeof window.openAuthModal === 'function') {
                        window.openAuthModal('login');
                    } else {
                        window.location.href = '/?action=login';
                    }
                });
                
                myImagesLink.parentNode.replaceChild(newLoginLink, myImagesLink);
            }
            
            if (logoutLink && !signupLink) {
                const newSignupLink = document.createElement('a');
                newSignupLink.href = '#';
                newSignupLink.className = 'nav-link open-auth-modal';
                newSignupLink.setAttribute('data-mode', 'signup');
                newSignupLink.textContent = 'Sign Up';
                
                // Add click handler
                newSignupLink.addEventListener('click', function(e) {
                    e.preventDefault();
                    if (typeof window.openAuthModal === 'function') {
                        window.openAuthModal('signup');
                    } else {
                        window.location.href = '/?action=signup';
                    }
                });
                
                logoutLink.parentNode.replaceChild(newSignupLink, logoutLink);
            }
        }
        
        // Make sure navbar is visible after update
        navLinksContainer.style.visibility = 'visible';
        navLinksContainer.style.opacity = '1';
    };
    
    // Last resort check - if the auth state doesn't match after 2 seconds
    setTimeout(() => {
        const hasToken = !!localStorage.getItem('authToken');
        const hasMyImagesLink = !!document.querySelector('.nav-links a[href="/dashboard"]');
        const hasLogoutLink = !!document.querySelector('.nav-links a[href="/logout"]');
        
        // If logged in but no dashboard/logout links, force update
        if (hasToken && (!hasMyImagesLink || !hasLogoutLink)) {
            forceUpdateNavbar(true);
        }
        
        // If not logged in but has dashboard/logout links, force update
        if (!hasToken && (hasMyImagesLink || hasLogoutLink)) {
            forceUpdateNavbar(false);
        }
    }, 2000);
});
