/**
 * Mobile Navigation Handler
 * Controls the mobile menu toggle functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const navLinks = document.querySelector('.nav-links');
    
    // Ensure navbar starts hidden on mobile
    if (window.innerWidth <= 768) {
        if (navLinks) {
            navLinks.classList.remove('active');
        }
    }
    
    if (mobileMenuBtn && navLinks) {
        // Toggle mobile menu
        mobileMenuBtn.addEventListener('click', function(e) {
            e.preventDefault();
            navLinks.classList.toggle('active');
            
            // Accessibility
            const expanded = navLinks.classList.contains('active');
            mobileMenuBtn.setAttribute('aria-expanded', expanded);
        });
        
        // Mobile dropdown toggle - Handle with capturing to ensure it's processed before any link clicks
        const dropdownToggles = document.querySelectorAll('.dropdown-toggle');
        dropdownToggles.forEach(toggle => {
            toggle.addEventListener('click', function(e) {
                // Only handle dropdown toggle click in mobile view
                if (window.innerWidth <= 768) {
                    // Prevent any default actions or propagation
                    e.preventDefault();
                    e.stopPropagation();
                    
                    const dropdownMenu = this.nextElementSibling;
                    const dropdownArrow = this.querySelector('.dropdown-arrow');
                    
                    // Close all other dropdowns first
                    document.querySelectorAll('.dropdown-menu').forEach(menu => {
                        if (menu !== dropdownMenu && menu.classList.contains('active')) {
                            menu.classList.remove('active');
                            const arrow = menu.previousElementSibling.querySelector('.dropdown-arrow');
                            if (arrow) arrow.style.transform = '';
                        }
                    });
                    
                    // Toggle this dropdown
                    dropdownMenu.classList.toggle('active');
                    
                    // Toggle arrow direction
                    if (dropdownArrow) {
                        dropdownArrow.style.transform = dropdownMenu.classList.contains('active') 
                            ? 'rotate(180deg)' 
                            : '';
                    }
                    
                    // Prevent this click from navigating
                    return false;
                }
            }, true); // Use capturing phase to ensure this runs before other handlers
        });
        
        // Close menu when clicking on a dropdown item link
        const dropdownItems = document.querySelectorAll('.dropdown-item');
        dropdownItems.forEach(item => {
            item.addEventListener('click', function() {
                if (window.innerWidth <= 768) {
                    // Keep the navigation menu open but close the dropdown
                    const parentDropdown = this.closest('.dropdown-menu');
                    if (parentDropdown) {
                        parentDropdown.classList.remove('active');
                    }
                    
                    // Don't close the mobile menu when clicking a dropdown item
                    // This allows navigation while keeping the mobile menu open
                }
            });
        });
        
        // Close menu when clicking on a direct nav link (non-dropdown)
        const directNavLinks = Array.from(navLinks.querySelectorAll('.nav-link')).filter(
            link => !link.classList.contains('dropdown-toggle')
        );
        
        directNavLinks.forEach(link => {
            link.addEventListener('click', function() {
                if (window.innerWidth <= 768) {
                    navLinks.classList.remove('active');
                    mobileMenuBtn.setAttribute('aria-expanded', 'false');
                    
                    // Also close any open dropdowns
                    document.querySelectorAll('.dropdown-menu').forEach(menu => {
                        menu.classList.remove('active');
                    });
                }
            });
        });
        
        // Handle window resize events
        window.addEventListener('resize', function() {
            if (window.innerWidth <= 768) {
                // On mobile view, keep the menu collapsed unless clicked
                if (!navLinks.classList.contains('active')) {
                    navLinks.style.display = 'none';
                }
            } else {
                // On desktop view, remove inline styles to let CSS handle display
                navLinks.style.display = '';
            }
        });
        
        // Initialize ARIA attributes
        mobileMenuBtn.setAttribute('aria-controls', 'mobile-menu');
        mobileMenuBtn.setAttribute('aria-expanded', 'false');
        mobileMenuBtn.setAttribute('aria-label', 'Toggle menu');
        navLinks.id = 'mobile-menu';
    }
}); 