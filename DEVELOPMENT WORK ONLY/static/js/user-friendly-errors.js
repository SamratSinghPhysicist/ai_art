/**
 * User-Friendly Error Handling for Frontend
 * 
 * This module provides utilities for displaying user-friendly error messages
 * and handling various error scenarios with encouraging messaging and donation prompts.
 */

class UserFriendlyErrorHandler {
    constructor() {
        this.donationLink = '/donate';
        this.registerLink = '/signup';
        this.loginLink = '/login';
    }

    /**
     * Display a user-friendly error message in the UI
     * @param {Object} errorData - Error response from the server
     * @param {string} containerId - ID of the container to display the error in
     */
    displayError(errorData, containerId = 'error-message') {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Error container with ID '${containerId}' not found`);
            return;
        }

        // Clear any existing content
        container.innerHTML = '';
        container.style.display = 'block';

        // Create error content
        const errorContent = this.createErrorContent(errorData);
        container.appendChild(errorContent);

        // Auto-hide success messages after 5 seconds
        if (errorData.success) {
            setTimeout(() => {
                container.style.display = 'none';
            }, 5000);
        }

        // Scroll to error message
        container.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    /**
     * Create HTML content for error display
     * @param {Object} errorData - Error response data
     * @returns {HTMLElement} - DOM element with error content
     */
    createErrorContent(errorData) {
        const wrapper = document.createElement('div');
        wrapper.className = this.getErrorClass(errorData.error_type || 'info');

        // Title
        if (errorData.title) {
            const title = document.createElement('h3');
            title.className = 'error-title';
            title.textContent = errorData.title;
            wrapper.appendChild(title);
        }

        // Main message
        const message = document.createElement('p');
        message.className = 'error-message';
        message.textContent = errorData.message || 'An unexpected error occurred.';
        wrapper.appendChild(message);

        // Action message
        if (errorData.action_message) {
            const actionMsg = document.createElement('p');
            actionMsg.className = 'error-action';
            actionMsg.innerHTML = `<strong>What to do:</strong> ${errorData.action_message}`;
            wrapper.appendChild(actionMsg);
        }

        // Wait time countdown
        if (errorData.wait_time && errorData.wait_time > 0) {
            const countdown = this.createCountdown(errorData.wait_time);
            wrapper.appendChild(countdown);
        }

        // Donation prompt
        if (errorData.show_donation_prompt && errorData.donation_message) {
            const donationPrompt = this.createDonationPrompt(
                errorData.donation_message,
                errorData.donation_link || this.donationLink
            );
            wrapper.appendChild(donationPrompt);
        }

        // Upgrade message
        if (errorData.upgrade_available && errorData.upgrade_message) {
            const upgradePrompt = this.createUpgradePrompt(errorData.upgrade_message);
            wrapper.appendChild(upgradePrompt);
        }

        // Alternative actions
        if (errorData.alternatives && errorData.alternatives.length > 0) {
            const alternatives = this.createAlternativesList(errorData.alternatives);
            wrapper.appendChild(alternatives);
        }

        // Retry button for certain error types
        if (this.shouldShowRetryButton(errorData)) {
            const retryButton = this.createRetryButton(errorData);
            wrapper.appendChild(retryButton);
        }

        return wrapper;
    }

    /**
     * Get CSS class for error type
     * @param {string} errorType - Type of error
     * @returns {string} - CSS class name
     */
    getErrorClass(errorType) {
        const baseClass = 'user-friendly-error';
        
        switch (errorType) {
            case 'rate_limit':
                return `${baseClass} rate-limit-error`;
            case 'server_busy':
                return `${baseClass} server-busy-error`;
            case 'queue_full':
                return `${baseClass} queue-full-error`;
            case 'api_error':
                return `${baseClass} api-error`;
            case 'validation_error':
                return `${baseClass} validation-error`;
            case 'auth_error':
                return `${baseClass} auth-error`;
            case 'generation_failed':
                return `${baseClass} generation-failed-error`;
            case 'timeout_error':
                return `${baseClass} timeout-error`;
            default:
                return `${baseClass} general-error`;
        }
    }

    /**
     * Create countdown timer for wait times
     * @param {number} waitTime - Wait time in seconds
     * @returns {HTMLElement} - Countdown element
     */
    createCountdown(waitTime) {
        const countdownWrapper = document.createElement('div');
        countdownWrapper.className = 'countdown-wrapper';

        const countdownText = document.createElement('p');
        countdownText.className = 'countdown-text';
        countdownWrapper.appendChild(countdownText);

        const progressBar = document.createElement('div');
        progressBar.className = 'countdown-progress';
        const progressFill = document.createElement('div');
        progressFill.className = 'countdown-progress-fill';
        progressBar.appendChild(progressFill);
        countdownWrapper.appendChild(progressBar);

        // Start countdown
        let remaining = waitTime;
        const updateCountdown = () => {
            if (remaining <= 0) {
                countdownText.textContent = '✅ You can try again now!';
                progressFill.style.width = '100%';
                progressFill.style.backgroundColor = '#10b981';
                return;
            }

            const minutes = Math.floor(remaining / 60);
            const seconds = remaining % 60;
            
            if (minutes > 0) {
                countdownText.textContent = `⏰ ${minutes}m ${seconds}s remaining`;
            } else {
                countdownText.textContent = `⏰ ${seconds}s remaining`;
            }

            const progress = ((waitTime - remaining) / waitTime) * 100;
            progressFill.style.width = `${progress}%`;

            remaining--;
        };

        updateCountdown();
        const interval = setInterval(() => {
            updateCountdown();
            if (remaining < 0) {
                clearInterval(interval);
            }
        }, 1000);

        return countdownWrapper;
    }

    /**
     * Create donation prompt element
     * @param {string} message - Donation message
     * @param {string} link - Donation link
     * @returns {HTMLElement} - Donation prompt element
     */
    createDonationPrompt(message, link) {
        const donationDiv = document.createElement('div');
        donationDiv.className = 'donation-prompt';

        const donationMessage = document.createElement('p');
        donationMessage.textContent = message;
        donationDiv.appendChild(donationMessage);

        const donationButton = document.createElement('a');
        donationButton.href = link;
        donationButton.className = 'donation-button';
        donationButton.textContent = '❤️ Support Us';
        donationButton.target = '_blank';
        donationDiv.appendChild(donationButton);

        return donationDiv;
    }

    /**
     * Create upgrade prompt element
     * @param {string} message - Upgrade message
     * @returns {HTMLElement} - Upgrade prompt element
     */
    createUpgradePrompt(message) {
        const upgradeDiv = document.createElement('div');
        upgradeDiv.className = 'upgrade-prompt';

        const upgradeMessage = document.createElement('p');
        upgradeMessage.textContent = message;
        upgradeDiv.appendChild(upgradeMessage);

        const upgradeButton = document.createElement('a');
        upgradeButton.href = this.registerLink;
        upgradeButton.className = 'upgrade-button';
        upgradeButton.textContent = '⭐ Upgrade Account';
        upgradeDiv.appendChild(upgradeButton);

        return upgradeDiv;
    }

    /**
     * Create alternatives list
     * @param {Array} alternatives - List of alternative actions
     * @returns {HTMLElement} - Alternatives list element
     */
    createAlternativesList(alternatives) {
        const alternativesDiv = document.createElement('div');
        alternativesDiv.className = 'alternatives-section';

        const title = document.createElement('h4');
        title.textContent = '💡 Meanwhile, you can:';
        alternativesDiv.appendChild(title);

        const list = document.createElement('ul');
        list.className = 'alternatives-list';

        alternatives.forEach(alternative => {
            const listItem = document.createElement('li');
            listItem.textContent = alternative;
            list.appendChild(listItem);
        });

        alternativesDiv.appendChild(list);
        return alternativesDiv;
    }

    /**
     * Check if retry button should be shown
     * @param {Object} errorData - Error data
     * @returns {boolean} - Whether to show retry button
     */
    shouldShowRetryButton(errorData) {
        const retryableTypes = [
            'api_error',
            'generation_failed',
            'timeout_error',
            'server_busy'
        ];
        return retryableTypes.includes(errorData.error_type);
    }

    /**
     * Create retry button
     * @param {Object} errorData - Error data
     * @returns {HTMLElement} - Retry button element
     */
    createRetryButton(errorData) {
        const buttonWrapper = document.createElement('div');
        buttonWrapper.className = 'retry-button-wrapper';

        const retryButton = document.createElement('button');
        retryButton.className = 'retry-button';
        retryButton.textContent = '🔄 Try Again';
        
        // Disable button during wait time
        if (errorData.wait_time && errorData.wait_time > 0) {
            retryButton.disabled = true;
            setTimeout(() => {
                retryButton.disabled = false;
                retryButton.textContent = '✅ Try Again Now';
            }, errorData.wait_time * 1000);
        }

        retryButton.addEventListener('click', () => {
            this.handleRetry(errorData);
        });

        buttonWrapper.appendChild(retryButton);
        return buttonWrapper;
    }

    /**
     * Handle retry button click
     * @param {Object} errorData - Error data
     */
    handleRetry(errorData) {
        // Hide error message
        const container = document.getElementById('error-message');
        if (container) {
            container.style.display = 'none';
        }

        // Trigger retry based on context
        if (typeof window.retryLastRequest === 'function') {
            window.retryLastRequest();
        } else {
            // Fallback: reload the page or trigger form submission
            const generateButton = document.querySelector('[id*="generate"], [class*="generate"]');
            if (generateButton && !generateButton.disabled) {
                generateButton.click();
            }
        }
    }

    /**
     * Handle API response and display appropriate message
     * @param {Response} response - Fetch response object
     * @param {string} containerId - Container ID for error display
     * @returns {Promise<Object|null>} - Parsed response data or null if error
     */
    async handleApiResponse(response, containerId = 'error-message') {
        try {
            const data = await response.json();

            if (!response.ok || !data.success) {
                // Display user-friendly error
                this.displayError(data, containerId);
                return null;
            }

            // Success - hide any existing errors
            const container = document.getElementById(containerId);
            if (container) {
                container.style.display = 'none';
            }

            return data;
        } catch (error) {
            // Handle JSON parsing errors
            const fallbackError = {
                error_type: 'api_error',
                title: 'Communication Error',
                message: '🔧 We had trouble communicating with our servers. Please try again in a moment.',
                action_message: 'Check your internet connection and try again',
                show_donation_prompt: true,
                donation_message: '❤️ Your support helps us maintain reliable service!',
                alternatives: [
                    'Check your internet connection',
                    'Try refreshing the page',
                    'Try again in a few minutes',
                    'Contact support if this persists'
                ]
            };

            this.displayError(fallbackError, containerId);
            return null;
        }
    }

    /**
     * Show success message
     * @param {string} message - Success message
     * @param {string} containerId - Container ID
     */
    showSuccess(message, containerId = 'error-message') {
        const successData = {
            success: true,
            error_type: 'success',
            title: '✅ Success!',
            message: message
        };

        this.displayError(successData, containerId);
    }

    /**
     * Show loading state with user-friendly message
     * @param {string} message - Loading message
     * @param {string} containerId - Container ID
     */
    showLoading(message = '🎨 Creating your masterpiece...', containerId = 'error-message') {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.innerHTML = `
            <div class="loading-message">
                <div class="loading-spinner"></div>
                <p>${message}</p>
            </div>
        `;
        container.style.display = 'block';
    }

    /**
     * Hide error/message container
     * @param {string} containerId - Container ID
     */
    hideMessage(containerId = 'error-message') {
        const container = document.getElementById(containerId);
        if (container) {
            container.style.display = 'none';
        }
    }
}

// Global instance
window.userFriendlyErrorHandler = new UserFriendlyErrorHandler();

// Convenience functions
window.showUserFriendlyError = (errorData, containerId) => {
    window.userFriendlyErrorHandler.displayError(errorData, containerId);
};

window.handleApiResponse = (response, containerId) => {
    return window.userFriendlyErrorHandler.handleApiResponse(response, containerId);
};

window.showSuccess = (message, containerId) => {
    window.userFriendlyErrorHandler.showSuccess(message, containerId);
};

window.showLoading = (message, containerId) => {
    window.userFriendlyErrorHandler.showLoading(message, containerId);
};

window.hideMessage = (containerId) => {
    window.userFriendlyErrorHandler.hideMessage(containerId);
};