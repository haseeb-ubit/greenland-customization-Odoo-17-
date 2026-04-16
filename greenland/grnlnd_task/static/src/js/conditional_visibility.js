/** @odoo-module **/

import { registry } from "@web/core/registry";
import { onMounted, onWillUpdateProps, useState } from "@odoo/owl";

function setupFieldVisibility(formView) {
    const state = useState({ showFields: true });

    // Initial visibility setup on component mount
    onMounted(() => {
        updateVisibility();
    });

    // Update visibility whenever props change (i.e., when sale_contract_id changes)
    onWillUpdateProps((newProps) => {
        if (newProps.record.data.sale_contract_id !== formView.props.record.data.sale_contract_id) {
            updateVisibility();
        }
    });

    function updateVisibility() {
        const contractType = formView.props.record.data.sale_contract_id?.contract_type;
        state.showFields = contractType !== "Non Hazardous";
        formView.updateFieldProperties("disposal_facility_delivery_note", { visible: state.showFields });
        formView.updateFieldProperties("disposal_facility_name", { visible: state.showFields });
    }
}

// Register the form view setup function
registry.category("views").add("project.task", setupFieldVisibility);
