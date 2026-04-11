document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Menu Toggle
    const mobileMenuBtn = document.querySelector('.mobile-menu-btn');
    const navLinks = document.querySelector('.nav-links');
    const navItems = document.querySelectorAll('.nav-links a');

    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', () => {
            navLinks.classList.toggle('active');
            // Toggle icon from bars to times
            const icon = mobileMenuBtn.querySelector('i');
            if (navLinks.classList.contains('active')) {
                icon.classList.remove('fa-bars');
                icon.classList.add('fa-times');
            } else {
                icon.classList.remove('fa-times');
                icon.classList.add('fa-bars');
            }
        });
    }

    // Close mobile menu when a link is clicked
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            if (navLinks.classList.contains('active')) {
                navLinks.classList.remove('active');
                const icon = mobileMenuBtn.querySelector('i');
                icon.classList.remove('fa-times');
                icon.classList.add('fa-bars');
            }
        });
    });

    // 2. Header Box Shadow on Scroll
    const header = document.getElementById('header');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            header.style.boxShadow = '0 5px 20px rgba(0, 0, 0, 0.05)';
            header.style.padding = '10px 0';
        } else {
            header.style.boxShadow = '0 1px 0 rgba(0, 0, 0, 0.05)';
            header.style.padding = '15px 0';
        }
    });

    // 3. Scroll Reveal Animations (Intersection Observer)
    const revealElements = document.querySelectorAll('.reveal');
    
    const revealObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('active');
                observer.unobserve(entry.target); // Only animate once
            }
        });
    }, {
        root: null,
        threshold: 0.15, // Trigger when 15% visible
        rootMargin: '0px 0px -50px 0px'
    });

    revealElements.forEach(el => {
        revealObserver.observe(el);
    });

    // 4. Google Ads Conversion Tracking para Botões do WhatsApp
    const whatsappLinks = document.querySelectorAll('a[href*="wa.me"]');
    whatsappLinks.forEach(link => {
        link.addEventListener('click', (event) => {
            const href = link.href;
            const openInNewTab = (link.getAttribute('target') || '').toLowerCase() === '_blank';

            if (typeof fbq === 'function') {
                fbq('track', 'Contact');
            }

            if (typeof gtag === 'function') {
                if (!openInNewTab) {
                    event.preventDefault();
                }

                gtag('event', 'conversion', {
                    send_to: 'AW-16663688962/0lmZCJaEmY4cEILu7ok-',
                    event_callback: () => {
                        if (!openInNewTab) {
                            window.location.href = href;
                        }
                    },
                    event_timeout: 1500
                });

                if (!openInNewTab) {
                    window.setTimeout(() => {
                        window.location.href = href;
                    }, 1700);
                }
            }
        });
    });
});
