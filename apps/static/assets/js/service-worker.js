self.addEventListener('push', function(event) {
    const data = event.data.json();
    const browser = getBrowserType();
    const options = {
        body: data.body,
        icon: '/static/assets/img/logo-256x256.jpg',
        badge: '/static/assets/img/logo-256x256.jpg',
        // add actions if browser is chrome only
        actions: browser == "Chrome" ?  [
            { action: 'open', title: 'Open Reminder', icon: 'https://cdn4.iconfinder.com/data/icons/ionicons/512/icon-ios7-bell-512.png'},
            { action: 'completed', title: 'Completed', icon: 'https://cdn4.iconfinder.com/data/icons/ionicons/512/icon-ios7-checkmark-512.png' }
        ] : "" ,
        data: {
            url: data.url,
            reminderId: data.reminderId
        }
    };
    event.waitUntil(
        // if browser is chrome, add options to show notification
        // if safari, options will be ignored
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const action = event.action;
    const reminderId = event.notification.data.reminderId;

    switch (action) {
        case 'completed':
            completeReminder(reminderId);
            break;
        case 'open':
            // Open a specific URL where the user can choose more options
            event.waitUntil(clients.openWindow(event.notification.data.url));
            break;
        default:
            // If no action is specified, open the main page
            event.waitUntil(clients.openWindow(event.notification.data.url));
            break;
    }
});

function completeReminder(reminderId) {
    fetch(`/complete_reminder/${reminderId}`, { method: 'POST' });
}

function getBrowserType() {
    const userAgent = navigator.userAgent;

    if (userAgent.includes("Firefox")) {
        return "Firefox";
    } else if (userAgent.includes("Chrome") && userAgent.includes("Edg/")) {
        return "Edge (Chromium)";
    } else if (userAgent.includes("Chrome")) {
        return "Chrome";
    } else if (userAgent.includes("Safari") && !userAgent.includes("Chrome")) {
        return "Safari";
    } else if (userAgent.includes("Opera") || userAgent.includes("OPR")) {
        return "Opera";
    } else if (userAgent.includes("MSIE") || userAgent.includes("Trident/")) {
        return "Internet Explorer";
    } else {
        return "Unknown";
    }
}
