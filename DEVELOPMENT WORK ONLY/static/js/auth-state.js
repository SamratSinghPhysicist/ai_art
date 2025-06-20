// This script manages the global authentication state of the user

// Function to be called when the user is logged in
function onLogin(user) {
    // Add 'logged-in' class to body
    document.body.classList.add('logged-in');
    document.body.classList.remove('logged-out');
    
    // Update navbar links
    updateNavbarForLoggedInUser();
}

// Function to be called when the user is logged out
function onLogout() {
    // Add 'logged-out' class to body
    document.body.classList.add('logged-out');
    document.body.classList.remove('logged-in');
    
    // Update navbar links
    updateNavbarForLoggedOutUser();
}

// Update navbar for logged-in user
function updateNavbarForLoggedInUser() {
    const navLinks = document.querySelector('.nav-links');
    if (navLinks) {
        // Replace Login/Sign Up with My Images/Logout
        const loginLink = navLinks.querySelector('a[href="/login"]');
        const signupLink = navLinks.querySelector('a[href="/signup"]');
        
        if (loginLink) {
            loginLink.textContent = 'My Images';
            loginLink.href = '/dashboard';
        }
        
        if (signupLink) {
            signupLink.textContent = 'Logout';
            signupLink.href = '/logout';
            // Add event listener for logout
            signupLink.addEventListener('click', function(e) {
                e.preventDefault();
                firebase.auth().signOut();
            });
        }
    }
}

// Update navbar for logged-out user
function updateNavbarForLoggedOutUser() {
    const navLinks = document.querySelector('.nav-links');
    if (navLinks) {
        // Replace My Images/Logout with Login/Sign Up
        const myImagesLink = navLinks.querySelector('a[href="/dashboard"]');
        const logoutLink = navLinks.querySelector('a[href="/logout"]');
        
        if (myImagesLink) {
            myImagesLink.textContent = 'Login';
            myImagesLink.href = '/login';
        }
        
        if (logoutLink) {
            logoutLink.textContent = 'Sign Up';
            logoutLink.href = '/signup';
            // Remove logout event listener if any
            logoutLink.replaceWith(logoutLink.cloneNode(true));
        }
    }
}

// Listen for Firebase auth state changes
document.addEventListener('DOMContentLoaded', function() {
    if (typeof firebase !== 'undefined') {
        firebase.auth().onAuthStateChanged(function(user) {
            if (user) {
                // User is signed in.
                onLogin(user);
            } else {
                // User is signed out.
                onLogout();
            }
        });
    } else {
        // Fallback to logged-out state if Firebase is not available
        onLogout();
    }
});
