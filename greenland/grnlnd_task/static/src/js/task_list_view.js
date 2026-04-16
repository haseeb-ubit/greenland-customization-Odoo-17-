/** @odoo-module */

import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useEffect } from "@odoo/owl";

export class TaskListController extends ListController {
    setup() {
        super.setup();

        useEffect(
            () => {
                const selection = this.model.root.selection;
                // Target the button using the custom class we will add
                const btn = document.querySelector(".o_btn_link_invoice");

                if (btn) {
                    // Show button for tickets without a valid posted invoice.
                    // This includes truly unlinked tickets AND tickets with stale
                    // references (cancelled/reversed invoices) which can be re-linked.
                    const hasNotInvoiced = selection.some(rec => rec.data.invoice_state === 'not');

                    if (hasNotInvoiced) {
                        btn.classList.remove("d-none");
                    } else {
                        btn.classList.add("d-none");
                    }
                }
            },
            () => [this.model.root.selection]
        );
    }
}

export const taskListView = {
    ...listView,
    Controller: TaskListController,
};

registry.category("views").add("task_list_invoice_link", taskListView);
