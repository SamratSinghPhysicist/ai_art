document.addEventListener('DOMContentLoaded', function() {
    const structuredData = {
      "@context": "https://schema.org",
      "@type": "WebApplication",
      "name": "AI Art Generator",
      "url": "https://aiart-zroo.onrender.com/",
      "description": "A free, unlimited AI image generator that creates stunning images from text or photos. No signup required.",
      "applicationCategory": "DesignApplication",
      "operatingSystem": "Any",
      "offers": {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "USD"
      },
      "featureList": [
        "Text to Image Generation",
        "Image to Image Transformation",
        "Image to Video Animation",
        "Free and Unlimited Usage",
        "No Signup Required"
      ],
      "screenshot": "https://aiart-zroo.onrender.com/static/images/og-image.svg",
      "creator": {
        "@type": "Organization",
        "name": "AI Art"
      }
    };

    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.text = JSON.stringify(structuredData);
    document.head.appendChild(script);
});
