// Small progressive enhancements; every feature also works without JavaScript.
document.addEventListener('DOMContentLoaded', () => {
    // Product page: expand/collapse the specifications accordion.
    document.querySelectorAll('.accordion-title').forEach((title) => {
        title.addEventListener('click', () => {
            title.closest('.accordion-item').classList.toggle('active');
        });
    });

    // Flash messages fade out after a few seconds (errors stay until dismissed by reload).
    document.querySelectorAll('.message:not(.message--error)').forEach((message) => {
        setTimeout(() => {
            message.style.transition = 'opacity .4s';
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 400);
        }, 5000);
    });
});
