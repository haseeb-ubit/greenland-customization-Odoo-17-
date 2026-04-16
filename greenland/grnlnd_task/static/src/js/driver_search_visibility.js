/** @odoo-module **/

import { registry } from "@web/core/registry";
import { onMounted } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

// Function to hide search bar for driver users
function hideSearchBarForDrivers() {
    onMounted(async () => {
        try {
            // Call the controller to check if user is in driver group
            const result = await rpc('/grnlnd_task/is_driver_user', {});
            
            if (result.is_driver) {
                // Add a CSS class to the body for driver users
                document.body.classList.add('driver-user');
                document.body.setAttribute('data-driver-user', 'true');
                
                // Also directly hide search bars
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
registry.category("views").add("hide_search_for_drivers", hideSearchBarForDrivers); 