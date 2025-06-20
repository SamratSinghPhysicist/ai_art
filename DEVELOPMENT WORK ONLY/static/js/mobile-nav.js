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
    
    // Dropdown functionality for desktop and mobile
    const dropdowns = document.querySelectorAll('.dropdown');
    
    dropdowns.forEach(dropdown => {
        const toggle = dropdown.querySelector('.dropdown-toggle');
        const menu = dropdown.querySelector('.dropdown-menu');
        const arrow = dropdown.querySelector('.dropdown-arrow');
        
        // Handle dropdown toggle on click (for both mobile and desktop)
        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            // Close all other dropdowns
            dropdowns.forEach(otherDropdown => {
                if (otherDropdown !== dropdown) {
                    otherDropdown.querySelector('.dropdown-menu').classList.remove('active');
                    const otherArrow = otherDropdown.querySelector('.dropdown-arrow');
                    if (otherArrow) {
                        otherArrow.style.transform = 'rotate(0deg)';
                    }
                }
            });
            
            // Toggle current dropdown
            menu.classList.toggle('active');
            
            // Rotate arrow
            if (arrow) {
                arrow.style.transform = menu.classList.contains('active') 
                    ? 'rotate(180deg)' 
                    : 'rotate(0deg)';
            }
        });
        
        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!dropdown.contains(e.target)) {
                menu.classList.remove('active');
                if (arrow) {
                    arrow.style.transform = 'rotate(0deg)';
                }
            }
        });
    });
    
    // Improve accessibility with keyboard navigation
    dropdowns.forEach(dropdown => {
        const toggle = dropdown.querySelector('.dropdown-toggle');
        const menu = dropdown.querySelector('.dropdown-menu');
        const items = dropdown.querySelectorAll('.dropdown-item');
        
        // Handle keyboard navigation
        toggle.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                menu.classList.toggle('active');
            } else if (e.key === 'ArrowDown' && menu.classList.contains('active')) {
                e.preventDefault();
                items[0].focus();
            } else if (e.key === 'Escape') {
                menu.classList.remove('active');
            }
        });
        
        // Add arrow key navigation between dropdown items
        items.forEach((item, index) => {
            item.addEventListener('keydown', function(e) {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    items[index + 1 < items.length ? index + 1 : 0].focus();
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    items[index - 1 >= 0 ? index - 1 : items.length - 1].focus();
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    toggle.focus();
                    menu.classList.remove('active');
                }
            });
        });
    });
    
    // Add aria attributes for accessibility
    dropdowns.forEach(dropdown => {
        const toggle = dropdown.querySelector('.dropdown-toggle');
        const menu = dropdown.querySelector('.dropdown-menu');
        
        // Set aria attributes
        toggle.setAttribute('aria-haspopup', 'true');
        toggle.setAttribute('aria-expanded', 'false');
        menu.setAttribute('role', 'menu');
        
        // Update aria-expanded when dropdown state changes
        toggle.addEventListener('click', function() {
            const expanded = menu.classList.contains('active');
            toggle.setAttribute('aria-expanded', expanded);
        });
        
        // Set attributes for dropdown items
        const items = dropdown.querySelectorAll('.dropdown-item');
        items.forEach(item => {
            item.setAttribute('role', 'menuitem');
            item.setAttribute('tabindex', '-1');
        });
    });
    
    // FAQ Accordion functionality
    const faqItems = document.querySelectorAll('.faq-item');
    
    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');
        const answer = item.querySelector('.faq-answer');
        
        // Initialize FAQ items - ensure they start closed
        if (answer) {
            answer.style.maxHeight = null;
        }
        
        if (question) {
            question.addEventListener('click', () => {
                // Close other FAQ items
                faqItems.forEach(otherItem => {
                    if (otherItem !== item && otherItem.classList.contains('active')) {
                        otherItem.classList.remove('active');
                        const otherAnswer = otherItem.querySelector('.faq-answer');
                        if (otherAnswer) {
                            otherAnswer.style.maxHeight = null;
                        }
                    }
                });
                
                // Toggle current FAQ item
                item.classList.toggle('active');
                
                if (item.classList.contains('active')) {
                    answer.style.maxHeight = answer.scrollHeight + 'px';
                } else {
                    answer.style.maxHeight = null;
                }
            });
            
            // Add keyboard support for accessibility
            question.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    question.click();
                }
            });
            
            // Set appropriate ARIA attributes
            question.setAttribute('aria-expanded', 'false');
            question.setAttribute('role', 'button');
            question.setAttribute('tabindex', '0');
            
            const questionHeading = question.querySelector('h3');
            if (questionHeading) {
                const id = 'faq-' + questionHeading.textContent.trim().toLowerCase().replace(/\s+/g, '-');
                answer.id = id;
                question.setAttribute('aria-controls', id);
            }
        }
    });
}); 