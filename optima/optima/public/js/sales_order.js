frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        // Add retry button for failed syncs
        if (frm.doc.docstatus === 1 && frm.doc.custom_send_to_optima && 
            frm.doc.optima_sync_status === "Failed") {
            frm.add_custom_button(__('Retry Optima Sync'), function() {
                frappe.confirm(
                    __('Are you sure you want to retry syncing this order to Optima?'),
                    function() {
                        frappe.call({
                            method: 'optima.optima.utils.order_sync.enqueue_optima_order_sync',
                            args: {
                                sales_order: frm.doc.name
                            },
                            freeze: true,
                            freeze_message: __('Queuing sync...'),
                        });
                    }
                );
            }, __('Actions'));
        }
        
        // Show sync error if any
        if (frm.doc.optima_sync_error) {
            frm.dashboard.add_comment(__('Optima Sync Error: {0}', [frm.doc.optima_sync_error]), 'red');
        }
    }
}); 