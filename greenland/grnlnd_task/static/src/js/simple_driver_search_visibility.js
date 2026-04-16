/** @odoo-module **/

import { registry } from "@web/core/registry";
import { onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// Function to hide search bar for driver users
function hideSearchBarForDrivers() {
    const userService = useService("user");
    
    onMounted(async () => {
        try {
            // Get current user info
            const user = await userService.load();
            
            // Check if user has the driver group
            // We'll check if the user has the specific group by looking at the groups_id
            const isDriver = user.groups_id && user.groups_id.some(groupId => {
                // This is a simplified check - you might need to adjust based on how groups are stored
                return groupId === 'grnlnd_task.group_driver_access';
            });
            
            if (isDriver) {
                // Add CSS class to body for driver users
                document.body.classList.add('driver-user');
                document.body.setAttribute('data-driver-user', 'true');
                
                // Hide search bars
                const searchBars = document.querySelectorAll('.o_cp_searchview.d-flex.input-group');
                searchBars.forEach(searchBar => {
                    searchBar.style.display = 'none';
                });
                
                // Listen for dynamic content changes
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        if (mutation.type === 'childList') {
                            const newSearchBars = document.querySelectorAll('.o_cp_searchview.d-flex.input-group');
                            newSearchBars.forEach(searchBar => {
                                searchBar.style.display = 'none';
                            });
                        }
                    });
                });
                
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
            }
        } catch (error) {
            console.error('Error checking driver group:', error);
        }
    });
}

// Register the function to run on all views
registry.category("views").add("simple_hide_search_for_drivers", hideSearchBarForDrivers); 