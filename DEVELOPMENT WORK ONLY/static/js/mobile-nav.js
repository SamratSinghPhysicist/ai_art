document.addEventListener('DOMContentLoaded', function() {
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const navLinks = document.querySelector('.nav-links');

    if (mobileMenuBtn && navLinks) {
        mobileMenuBtn.addEventListener('click', function() {
            navLinks.classList.toggle('active');
            // Close any open dropdowns when the main menu is toggled
            document.querySelectorAll('.dropdown-menu.active').forEach(menu => {
                menu.classList.remove('active');
            });
        });
    }

    const dropdownToggles = document.querySelectorAll('.dropdown-toggle');
    dropdownToggles.forEach(toggle => {
        toggle.addEventListener('click', function(e) {
            // Only handle dropdown toggle click in mobile view
            if (window.innerWidth <= 768) {
                e.preventDefault(); // Prevent default link behavior
                e.stopPropagation(); // Stop event from bubbling up to document

                const dropdownMenu = this.nextElementSibling;

                // Close other dropdowns if open
                document.querySelectorAll('.dropdown-menu.active').forEach(menu => {
                    if (menu !== dropdownMenu) {
                        menu.classList.remove('active');
                    }
                });

                // Toggle current dropdown
                dropdownMenu.classList.toggle('active');
            }
        });
    });

    // Close mobile menu and dropdowns when a nav-link (not a dropdown-toggle) is clicked
    document.querySelectorAll('.nav-links .nav-link:not(.dropdown-toggle)').forEach(link => {
        link.addEventListener('click', function() {
            if (window.innerWidth <= 768) {
                navLinks.classList.remove('active');
                document.querySelectorAll('.dropdown-menu.active').forEach(menu => {
                    menu.classList.remove('active');
                });
            }
        });
    });

    // Close dropdowns when clicking outside on mobile
    document.addEventListener('click', function(e) {
        if (window.innerWidth <= 768) {
            dropdownToggles.forEach(toggle => {
                const dropdownMenu = toggle.nextElementSibling;
                if (!toggle.contains(e.target) && !dropdownMenu.contains(e.target)) {
                    dropdownMenu.classList.remove('active');
                }
            });
        }
    });
});