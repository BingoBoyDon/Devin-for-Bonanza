<?php
// report_by_site.php

require_once '/var/www/weblynxx/vendor/autoload.php';
$dotenv = Dotenv\Dotenv::createImmutable('/var/www/weblynxx', 'db_credentials.env');
$dotenv->load();

// Get the user_id from GET parameters
$user_id = isset($_GET['user_id']) ? intval($_GET['user_id']) : 0;
if ($user_id <= 0) {
    die("Invalid or missing user_id");
}

// Connect to the database
$dbHost = $_ENV['DB_HOST'];
$dbName = $_ENV['DB_NAME'];
$dbUser = $_ENV['DB_USER'];
$dbPass = $_ENV['DB_PASS'];
$connectionString = "host=$dbHost dbname=$dbName user=$dbUser password=$dbPass";
$dbconn = pg_connect($connectionString);
if (!$dbconn) {
    die("Database connection error");
}

// Get the list of sites the user has permissions for using the provided query.
$querySites = "
SELECT ip_sites.id, ip_sites.site
FROM ip_sites
JOIN user_site_relation ON ip_sites.id = user_site_relation.site_id
JOIN site_details ON ip_sites.id = site_details.site_id
WHERE user_site_relation.user_id = $1
  AND user_site_relation.is_enabled = 't'
  AND ip_sites.active = 't'
ORDER BY user_site_relation.sort_order ASC";
$resultSites = pg_query_params($dbconn, $querySites, [$user_id]);
$sites = [];
while ($row = pg_fetch_assoc($resultSites)) {
    $sites[] = $row;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Report by Site</title>
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
  <!-- Bootstrap CSS -->
  <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
  <!-- External CSS file - Multiple path options to ensure loading -->
  <link rel="stylesheet" href="style.css">
  <!-- Alternative paths if the CSS is in different locations -->
  <link rel="stylesheet" href="css/style.css">
  <link rel="stylesheet" href="../style.css">
  <link rel="stylesheet" href="/style.css">
  <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
  <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
  <style>
    .scroll-menu {
      max-height: 200px;
      overflow-y: auto;
    }
  </style>
</head>
<body>
<div class="container mt-3">
  <h2>Report by Site</h2>
  <div class="form-group">
    <label for="siteSelect">Select a Site:</label>
    <select id="siteSelect" class="form-control scroll-menu">
      <option value="">-- Select a Site --</option>
      <?php foreach ($sites as $site): ?>
         <option value="<?php echo $site['id']; ?>"><?php echo $site['site']; ?></option>
      <?php endforeach; ?>
    </select>
  </div>
  <div id="reportContainer">
    <!-- The report records will be loaded here -->
  </div>
</div>

<!-- Modal for transaction action -->
<div class="modal fade" id="actionModal" tabindex="-1" role="dialog" aria-labelledby="actionModalLabel">
  <div class="modal-dialog" role="document">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="actionModalLabel">Transaction Action</h5>
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body">
        <p id="requestedAmountText"></p>
        <div id="differentAmountContainer" style="display:none;">
          <label for="differentAmount">Enter Amount ($):</label>
          <input type="number" id="differentAmount" class="form-control" step="0.01" placeholder="e.g., 20.00">
        </div>
      </div>
      <div class="modal-footer">
        <button id="btnApproveFull" type="button" class="btn btn-success">Approve Full Amount</button>
        <button id="btnReject" type="button" class="btn btn-danger">Reject Transaction</button>
        <button id="btnApproveDiff" type="button" class="btn btn-primary">Approve Different Amount</button>
        <button id="btnAcceptDiff" type="button" class="btn btn-primary" style="display:none;">Accept</button>
      </div>
    </div>
  </div>
</div>

<script>
// Global variable for current user id (from GET)
var currentUserId = <?php echo $user_id; ?>;
var currentAdjustmentId = 0;
var currentRequestedCents = 0;

$(document).ready(function(){
    // Load report based on selected site
    $('#siteSelect').on('change', function(){
       var siteId = $(this).val();
       if(siteId === ''){
          $('#reportContainer').html('');
          return;
       }
       $.ajax({
         url: 'fetch_adjustments_by_site.php',
         type: 'POST',
         dataType: 'json',
         data: { site_id: siteId },
         success: function(response){
            console.log(response);
            if(response.success){
               var html = '';
               if(response.records.length > 0){
                   html += '<table class="table table-bordered">';
                   html += '<thead><tr>';
                   html += '<th>Adjustment ID</th>';
                   html += '<th>Ticket ID</th>';
                   html += '<th>User</th>';
                   html += '<th>Customer</th>';
                   html += '<th>Reason</th>';
                   html += '<th>Requested Amount ($)</th>';
                   html += '<th>Approved Amount ($)</th>';
                   html += '<th>Balance ($)</th>';
                   html += '<th>Previous Balance ($)</th>';
                   html += '<th>Transaction ID</th>';
                   html += '<th>Device</th>';
                   html += '<th>Transaction Type</th>';
                   html += '<th>First Date</th>';
                   html += '<th>Status</th>';
                   html += '</tr></thead><tbody>';
                   $.each(response.records, function(i, rec){
                      var requested = (parseFloat(rec.adjustment_requested_amount) / 100).toFixed(2);
                      var approved  = (parseFloat(rec.approved_adjustment) / 100).toFixed(2);
                      var balance   = (parseFloat(rec.balance) / 100).toFixed(2);
                      var prevBalance = (parseFloat(rec.previous_balance) / 100).toFixed(2);
                      var customerName = rec.f_name + " " + rec.l_name;
                      // Use "==" to allow for boolean or 'f'
                      var clickable = (rec.waiting_processes == false || rec.waiting_processes == 'f') ? 'clickable-row' : '';
                      html += '<tr class="'+clickable+'" data-adjustment-id="'+ rec.adjustment_id +'" data-requested="'+ rec.adjustment_requested_amount +'">';
                      html += '<td>' + rec.adjustment_id + '</td>';
                      html += '<td>' + rec.ticket_id + '</td>';
                      html += '<td>' + rec.user_name + '</td>';
                      html += '<td>' + customerName + '</td>';
                      html += '<td>' + rec.reason + '</td>';
                      html += '<td>$' + requested + '</td>';
                      html += '<td>$' + approved + '</td>';
                      html += '<td>$' + balance + '</td>';
                      html += '<td>$' + prevBalance + '</td>';
                      html += '<td>' + rec.transaction_id + '</td>';
                      html += '<td>' + rec.device_type + '</td>';
                      html += '<td>' + rec.action_type + '</td>';
                      html += '<td>' + (rec.first_date ? rec.first_date.substr(0,19) : '') + '</td>';
                      html += '<td>' + rec.last_status_type + '</td>';
                      html += '</tr>';
                   });
                   html += '</tbody></table>';
               } else {
                   html = '<div class="alert alert-info">No records found for this Site.</div>';
               }
               $('#reportContainer').html(html);
            } else {
               $('#reportContainer').html('<div class="alert alert-danger">' + response.error + '</div>');
            }
         },
         error: function(){
            $('#reportContainer').html('<div class="alert alert-danger">Error loading the report.</div>');
         }
       });
    });

    // When a clickable row is clicked, insert record in status_adjustment_record and open the modal.
    $(document).on('click', '.clickable-row', function(){
        currentAdjustmentId = $(this).data('adjustment-id');
        currentRequestedCents = $(this).data('requested');
        var requestedDollars = (parseFloat(currentRequestedCents) / 100).toFixed(2);
        $('#requestedAmountText').html("Requested Amount: $" + requestedDollars);
        // Insert into status_adjustment_record via AJAX
        $.ajax({
            url: 'insert_status_adjustment_record.php',
            type: 'POST',
            dataType: 'json',
            data: { adjustment_id: currentAdjustmentId, user_id: currentUserId },
            success: function(response){
                console.log("Status adjustment record:", response);
                // Regardless of result, show modal for further action.
                $('#btnAcceptDiff').hide();
                $('#differentAmountContainer').hide();
                $('#btnApproveFull').show();
                $('#btnReject').show();
                $('#btnApproveDiff').show();
                $('#actionModal').modal('show');
            },
            error: function(){
                alert("Error inserting status adjustment record.");
            }
        });
    });

    // Approve full amount button
    $('#btnApproveFull').click(function(){
        updateAdjustment(currentAdjustmentId, 'approve_full', null);
    });

    // Reject transaction button
    $('#btnReject').click(function(){
        updateAdjustment(currentAdjustmentId, 'reject', null);
    });

    // Approve different amount button: show input field
    $('#btnApproveDiff').click(function(){
        $('#differentAmountContainer').show();
        $('#btnAcceptDiff').show();
        $('#btnApproveFull').hide();
        $('#btnReject').hide();
        $('#btnApproveDiff').hide();
    });

    // Accept different amount button: read the input and update
    $('#btnAcceptDiff').click(function(){
        var diffAmount = $('#differentAmount').val().trim();
        if(diffAmount === "" || isNaN(diffAmount)){
            alert("Please enter a valid amount.");
            return;
        }
        var diffCents = Math.round(parseFloat(diffAmount) * 100);
        updateAdjustment(currentAdjustmentId, 'approve_diff', diffCents);
    });

    // Function to update adjustment via AJAX (update balance_adjustments and insert in status_transaction)
	function updateAdjustment(adjustmentId, actionType, approvedAmountCents) {
		// Crear objeto de datos para la solicitud AJAX
		var ajaxData = { 
			adjustment_id: adjustmentId, 
			action: actionType, 
			user_id: currentUserId 
		};
		
		// Incluir approved_amount solo cuando la acción es approve_diff
		if (actionType === 'approve_diff' && approvedAmountCents !== null) {
			ajaxData.approved_amount = approvedAmountCents;
		}
		
		$.ajax({
			url: 'update_status_adjustment_record.php',
			type: 'POST',
			dataType: 'json',
			data: ajaxData,
			success: function(response) {
				if(response.success){
					alert("Update successful.");
					$('#actionModal').modal('hide');
					$('#siteSelect').trigger('change'); // refresh report
				} else {
					alert("Update error: " + response.error);
				}
			},
			error: function(){
				alert("Error updating the adjustment.");
			}
		});
	}

});
</script>
</body>
</html>

