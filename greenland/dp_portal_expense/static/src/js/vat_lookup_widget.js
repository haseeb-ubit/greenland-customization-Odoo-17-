/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useService } from "@web/core/utils/hooks";
import { useState, onWillUpdateProps, useEffect } from "@odoo/owl";

export class VatLookupField extends CharField {
    static template = "dp_portal_expense.VatLookupField";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = useState({
            suggestions: [],
            showDropdown: false,
            loading: false,
            selectedIndex: -1,
            inputValue: this.props.record.data[this.props.name] || '',
        });
        this.debounceTimer = null;

        // Sync local state if record changes externally (using useEffect for robust dependency tracking)
        useEffect(() => {
            const nextValue = this.props.record.data[this.props.name] || '';
            if (nextValue !== this.state.inputValue) {
                this.state.inputValue = nextValue;
            }
        }, () => [this.props.record.data[this.props.name]]);
    }

    async onInput(ev) {
        const value = ev.target.value;
        this.state.inputValue = value; // Update UI immediately

        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        if (value && value.length >= 1) {
            this.state.loading = true;
            this.debounceTimer = setTimeout(async () => {
                await this.searchVendors(value);
            }, 250);
        } else {
            this.state.suggestions = [];
            this.state.showDropdown = false;
            this.state.loading = false;
        }
    }

    onChange(ev) {
        // Commit to model only when done typing
        this.props.record.update({ [this.props.name]: ev.target.value });
    }
    async searchVendors(vat) {
        try {
            const vendors = await this.orm.searchRead(
                "res.partner",
                [
                    "&",
                    ["x_studio_contact_type", "=", "Vendor"],
                    ["is_company", "=", true],
                    "|",
                    ["vat", "ilike", vat],
                    ["vat", "ilike", vat.replace(/\s+/g, '')]
                ],
                ["id", "name", "vat", "phone"],
                { limit: 500 }
            );

            this.state.suggestions = vendors;
            this.state.showDropdown = vendors.length > 0;
            this.state.selectedIndex = vendors.length > 0 ? 0 : -1;
            // Auto-select on exact match
            const exactMatch = vendors.find(v => v.vat === vat);
            if (exactMatch) {
                this.selectVendor(exactMatch);
            }
        } catch (error) {
            console.error("VatLookup error:", error);
        }
        this.state.loading = false;
    }

    selectVendor(vendor) {
        this.state.inputValue = vendor.vat; // Update UI immediately
        this.props.record.update({
            vendor_id: [vendor.id, vendor.name],
            [this.props.name]: vendor.vat
        });
        this.state.showDropdown = false;
        this.state.suggestions = [];
    }

    onKeyDown(ev) {
        if (!this.state.showDropdown) return;

        switch (ev.key) {
            case "ArrowDown":
                ev.preventDefault();
                this.state.selectedIndex = Math.min(
                    this.state.selectedIndex + 1,
                    this.state.suggestions.length - 1
                );
                break;
            case "ArrowUp":
                ev.preventDefault();
                this.state.selectedIndex = Math.max(this.state.selectedIndex - 1, 0);
                break;
            case "Enter":
                if (this.state.selectedIndex >= 0) {
                    ev.preventDefault();
                    this.selectVendor(this.state.suggestions[this.state.selectedIndex]);
                }
                break;
            case "Escape":
                this.state.showDropdown = false;
                break;
        }
    }

    onBlur() {
        setTimeout(() => {
            this.state.showDropdown = false;
        }, 200);
    }
}

export const vatLookupField = {
    ...charField,
    component: VatLookupField,
};

registry.category("fields").add("vat_lookup", vatLookupField);
