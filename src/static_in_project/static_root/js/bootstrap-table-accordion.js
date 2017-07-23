/**
 * Created by couture on 14/06/17.
 */


/* CONVERT TO AN ACCORDIAN-STYLE TABLE */
$table.on('expand-row.bs.table', function (e, index, row, $detail) {
    var detailContent = $("#collapse" + row.id).html();

    //sliding doesn't work on table elements, so add a div and animate that.
    $detail.html('<div class="detail-container" style="display:none;"></div>');
    var $detailContainer = $detail.find('div');
    $detailContainer.html(detailContent);
    $detailContainer.slideDown();
});

$table.on("click-row.bs.table", function (e, row, $tr) {
    // prints Clicked on: table table-hover, no matter if you click on row or detail-icon
    //console.log("Clicked on: " + $(e.target).attr('class'), [e, row, $tr]);


    if ($tr.next().is('tr.detail-view')) {
        $tr.next().find('div.detail-container').slideUp(function () {
            // when animation complete, otherwise element will be deleted before animation
            $table.bootstrapTable('collapseRow', $tr.data('index'));
            $table.find('tr').removeClass('primary');
        });
    } else {

        var $detailContainer = $('div.detail-container');
        if ($detailContainer.length > 0) {
            $detailContainer.slideUp(function () {
                scrollToRow($tr);
                var $expanded_tr = $detailContainer.parents('tr.detail-view').prev();
                $table.bootstrapTable('collapseRow', $expanded_tr.data('index'));
            });
            $table.find('tr').not($tr).removeClass('primary');
        }
        activateRow($tr);
    }
});

// Sort the last column, which has a date div hidden in it for easy sorting
function dateSorter(a, b) {
    // need to pull 8 digit date out of this part of a,b: <div>YYYYMMDD</div>
    var re = /\d{6}/; // max 6 digits from 0-9
    var dateA = a.match(re); // first element is the match
    var dateB = b.match(re); // first element is the match

    dateA = dateA == null ? 0 : dateA[0];
    dateB = dateB == null ? 0 : dateB[0];

    // match the text up to the first tag, probably <br>
    //var re = /^.*(?=(<))/;

    if (dateA > dateB) return 1;
    if (dateA < dateB) return -1;
    return 0;
}


function scrollToRow($tr) {
    $('html, body').animate({scrollTop: $tr.offset().top - 60});
}

function activateRow($tr) {
    $tr.addClass('primary');
    $table.bootstrapTable('expandRow', $tr.data('index'));
}

$(document).ready(function () {

    // Stop links in table-accordian from triggering accordian opening and closing
    $('a.dont-expand').click(function (e) {
        e.stopPropagation();
    });


    /* SCROLL AND OPEN ACTIVE SUGGESTION */
    if (active_id != null) {
        var $active_tr = $('tr[data-uniqueid=' + active_id + ']');
        activateRow($active_tr);
        scrollToRow($active_tr);
    }

});