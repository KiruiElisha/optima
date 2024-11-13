frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        // Add retry button for failed syncs
        if (frm.doc.custom_optima_sync_status === "Failed") {
            
            frm.add_custom_button(__('Retry Optima Sync'), function() {
                frappe.confirm(
                    __('Are you sure you want to retry syncing this order to Optima?'),
                    function() {
                        // Clear previous error
                        frm.set_value('custom_optima_sync_error', '');
                        frm.set_value('custom_optima_sync_status', 'Pending');
                        
                        frappe.call({
                            method: 'optima.optima.utils.order_sync.enqueue_optima_order_sync',
                            args: {
                                sales_order: frm.doc.name
                            },
                            freeze: true,
                            freeze_message: __('Queuing sync...'),
                            callback: function(r) {
                                frm.reload_doc();
                            }
                        });
                    }
                );
            }, __('Actions'));
        }
        
        // Show sync error if any
        if (frm.doc.custom_optima_sync_error) {
            frm.dashboard.add_comment(__('Optima Sync Error: {0}', [frm.doc.custom_optima_sync_error]), 'red');
        }
        
        // Show sync status
        if (frm.doc.custom_optima_sync_status) {
            let indicator = {
                'Pending': 'orange',
                'Synced': 'green',
                'Failed': 'red'
            }[frm.doc.custom_optima_sync_status] || 'gray';
            
            frm.dashboard.add_comment(
                __('Optima Sync Status: {0}', [frm.doc.custom_optima_sync_status]),
                indicator
            );
        }
    },
    
    custom_send_to_optima: function(frm) {
        // Clear sync status when toggling send to optima
        if (!frm.doc.custom_send_to_optima) {
            frm.set_value('custom_optima_sync_status', 'Not Synced');
            frm.set_value('custom_optima_sync_error', '');
        }
    }
}); 