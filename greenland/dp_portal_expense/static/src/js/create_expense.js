/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";
import {
	_t
} from "@web/core/l10n/translation";

publicWidget.registry.new_time_off = publicWidget.Widget.extend({
	selector: '.js_create_expense_record,.js_edit_expense_record,.js_cls_del', //class for dialog box
	events: {
		'click #create_expense_record': '_create_expense_record_dialog', //dialogbox for flieds
		'click #createrecordset': '_createrecord', //create record set
		'click #save_expense_record': '_saveRecord', //save record after edit
		'click #edit_expense_record': '_editRecordButton', //fetch data from odoo
		'click #delete_ids': '_delete_expense_record', //for delete
		'click #delete_expense_record': '_delete_record', //dialogbox poup
		'change #vendor_id': '_onVendorChange', //vendor selection change
		'change #edit_vendor_id': '_onEditVendorChange' //edit vendor selection change
	},

	_create_expense_record_dialog: function(e) {
		var self = this;
		self._openDialog();
	},

	// _saveRecord:function(e){
	//     var save_record_id = parseInt($('#save_button_id').val())
	//     var name = $('#edit_name_id').val()
	//     var product = $("#edit_product_id").val()
	//     var total = $("#edit_total_id").val()
	//     var date = $("#edit_from_date").val();
	//     var paidBy = $("input[name='paid_by']:checked").val();
	//     const files = $('#attachment')[0].files;


	//     // var expense_attachments = $('#edit_expense_attachments').val();

	//     console.log('files = == = = ', files)
	//     $.ajax({
	//         url:"/save_record",
	//         data :{
	//             'id':save_record_id,
	//             'name':name,
	//             'product_id':product,
	//             'total_amount_currency':total,
	//             'date':date,
	//             'payment_mode':paidBy,
	//             'attachment_file':'',
	//         },
	//         type: "post",
	//         dataType:'json',
	//         success:function(data){
	//             console.log(data);
	//         }
	//     })
	//     alert('saved success');
	//     $('#edit_box').modal('hide');
	//     location.reload(true);//reload the page after save
	// },// Saved Record End

	_saveRecord: function(e) {
		var save_record_id = parseInt($('#save_button_id').val());
		var name = $('#edit_name_id').val();
		var product = $("#edit_product_id").val();
		var vendorId = $("#edit_vendor_id").val();
		var vatNumber = $("#edit_vat_number").val();
		var total = $("#edit_total_id").val();
		var date = $("#edit_from_date").val();
		var paidBy = $("input[name='paid_by']:checked").val();
		const files = $('#attachment')[0].files;

		if (files.length > 0) {
			var file = files[0]; // Get the first file

			var reader = new FileReader();
			reader.onload = function(event) {
				var base64String = event.target.result.split(',')[1]; // Get Base64 string without the prefix
				var fileName = file.name; // Get the file name

				// Now you can send the base64 string and file name in your AJAX request
				$.ajax({
					url: "/save_record",
					data: {
						'id': save_record_id,
						'name': name,
						'product_id': product,
						'vendor_id': vendorId,
						'vat_number': vatNumber,
						'total_amount_currency': total,
						'date': date,
						'payment_mode': paidBy,
						'attachment_file': base64String,
						'attachment_name': fileName // Include the file name
					},
					type: "post",
					dataType: 'json',
					success: function(data) {
						console.log(data);
					}
				});

				alert('saved success');
				$('#edit_box').modal('hide');
				location.reload(true); // Reload the page after save
			};

			reader.readAsDataURL(file); // Read the file as a data URL
		} else {
			// Handle the case where no file is selected
			$.ajax({
				url: "/save_record",
				data: {
					'id': save_record_id,
					'name': name,
					'product_id': product,
					'vendor_id': vendorId,
					'vat_number': vatNumber,
					'total_amount_currency': total,
					'date': date,
					'payment_mode': paidBy,
					'attachment_file': '',
				},
				type: "post",
				dataType: 'json',
				success: function(data) {
					console.log(data);
				}
			})
			alert('saved success');
			$('#edit_box').modal('hide');
			location.reload(true); //reload the page after save
		}
	}, // Saved Record End



	_openDialog: function() {
		var currentDate = new Date().toISOString().split('T')[0];
		$("#from_date").val(currentDate);
		$('#create_box').modal('show') //popup with current date
	},

	_openeditDialog: function() {
		$('#edit_box').modal('show')
	},

	_createrecord: function(e) {
		var fromDate = $('#from_date').val();
		var name = $('#name').val();
		var category = $('#category').val();
		var vendorId = $('#vendor_id').val();
		var vatNumber = $('#vat_number').val();
		var paidBy = $("input[name='paid_by']:checked").val();
		var total = $('#total_expense').val();
        const files = $('#attachment')[0].files;

		if (!name || !category || !total || isNaN(parseFloat(total))) {
			alert("Please fill in all required fields.");
			return false;
		}

        if (files.length > 0){
            var file = files[0]; // Get the first file
			var reader = new FileReader();
            reader.readAsDataURL(file); 

			reader.onload = function(event) {
				var base64String = event.target.result.split(',')[1]; // Get Base64 string without the prefix
				var fileName = file.name; // Get the file name
                $.ajax({
                    url: '/create_record',
                    type: 'POST',
                    data: {
                        name: name,
                        from_date: fromDate,
                        category: category,
                        vendor_id: vendorId,
                        vat_number: vatNumber,
                        paid_by: paidBy,
                        total_expense: total,
                        attachment_file: base64String,
						attachment_name: fileName // Include the file name
                        
                    },
                    success: function(data) {
                        alert('Record Created Success');
                        $('#create_box').modal('hide');
                        location.reload(true);
                    },
                    error: function(error) {
                        console.error("Failed to create", error);
                    }
                });
            }
        }

        else {
            $.ajax({
                url: '/create_record',
                type: 'POST',
                data: {
                    name: name,
                    from_date: fromDate,
                    category: category,
                    vendor_id: vendorId,
                    vat_number: vatNumber,
                    paid_by: paidBy,
                    total_expense: total,
                },
                success: function(data) {
                    alert('Record Created Success');
                    $('#create_box').modal('hide');
                    location.reload(true);
                },
                error: function(error) {
                    console.error("Failed to create", error);
                }
            });
        }
	}, //Create Record End

	_editRecordButton: function(e) {
		var self = this;
		var $el = $(e.target).parents('tr').find("#edit_button_id").attr("value")
		var get_id = parseInt($el)
		$.ajax({
			url: "/edit_record",
			data: {
				'edit_button_id': get_id,
			},
			type: "post",
			success: function(data) {
				try {
					var jdata = JSON.parse(data);

					$("#edit_from_date").val(jdata.date);
					$("#save_button_id").val(jdata.id);
					$("#edit_product_id").val(jdata.product_id);
					$("#edit_vendor_id").val(jdata.vendor_id);
					$("#edit_vat_number").val(jdata.vat_number);
					$("#edit_name_id").val(jdata.name);
					$("#edit_total_id").val(jdata.total_amount_currency);
					$("input[name='paid_by'][value='" + jdata.payment_mode + "']").prop("checked", true);

				} catch (error) {
					console.error("Error parsing JSON response:", error);
				}
			}
		});
		self._openeditDialog()
	}, //edit end

	error: function(error) {
		console.error("Failed to fetch record for editing", error);
	},

	_delete_record: function(e) {
		var self = this;
		var $el = $(e.target).parents('tr').find("#edit_button_id").attr("value")
		var get_id = parseInt($el)
		$('#delete_id').val(get_id)
		$('#delete_dialog').modal('show');
	},

	_delete_expense_record: function(e) {
		$.ajax({
			url: "/delete_record",
			data: {
				'edit_button_id': $('#delete_id').val()
			},
			type: "post",
			success: function(result) {
				var datas = JSON.parse(result);
				if (datas.success_msg) {
					location.reload(true);
				}
			},
		});
	},

	_onVendorChange: function(e) {
		var vendorId = $(e.target).val();
		if (vendorId) {
			$.ajax({
				url: "/get_vendor_vat",
				data: {
					'vendor_id': vendorId
				},
				type: "post",
				success: function(data) {
					try {
						var jdata = JSON.parse(data);
						$("#vat_number").val(jdata.vat || '');
					} catch (error) {
						console.error("Error parsing VAT response:", error);
					}
				}
			});
		} else {
			$("#vat_number").val('');
		}
	},

	_onEditVendorChange: function(e) {
		var vendorId = $(e.target).val();
		if (vendorId) {
			$.ajax({
				url: "/get_vendor_vat",
				data: {
					'vendor_id': vendorId
				},
				type: "post",
				success: function(data) {
					try {
						var jdata = JSON.parse(data);
						$("#edit_vat_number").val(jdata.vat || '');
					} catch (error) {
						console.error("Error parsing VAT response:", error);
					}
				}
			});
		} else {
			$("#edit_vat_number").val('');
		}
	}
}) //end