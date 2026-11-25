/* Reorder a quest's submission questions in the background (#2216), and open the quest form's
 * Submission Questions section when a link back to the form names it (#2971).
 *
 * A container opts in with `data-question-table`. Each move is posted as an XHR and the table
 * redrawn from the server's answer, so the teacher keeps their place in the list between clicks,
 * and the ordering and the disabled arrows at its ends stay the server's business.
 *
 * The arrows come in two kinds. On the question list each is its own small form, so with
 * JavaScript off it posts normally and the view redirects to the reloaded list. In the quest
 * form's Submission Questions section the table sits inside the quest's own <form>, where a form
 * can't nest, so each arrow is a plain button carrying its URL in `data-move-url`. That one is
 * posted with the quest form's CSRF token and `in_quest_form`, so the view draws the table back
 * the same way.
 */
$(function () {
    $('[data-question-table]').each(function () {
        var $table = $(this);
        // The quest form the table sits in; none on the question list, whose arrows are forms.
        var $form = $table.closest('form');
        // The moves still to be answered, one after another. Each is posted only once the one
        // before it has been answered and drawn: two in flight at once could be answered out of
        // order, and the table would then be redrawn from the older answer, showing an order
        // that isn't the saved one. In click order, the last table drawn is the latest move's.
        var queue = $.when();
        // How many moves are clicked but not yet answered, and the quest form's submit buttons
        // held disabled meanwhile (see setPending).
        var pending = 0;
        var $held = $();

        /* Count a move in (+1) or out (-1).
         *
         * Saving the quest leaves the page, which would drop the moves not yet posted, so while
         * any is pending the form's submit buttons are disabled; with its first one disabled, the
         * enter key can't submit it either. Only the buttons this disabled are enabled again.
         */
        function setPending(change) {
            pending += change;
            if (pending > 0 && !$held.length) {
                $held = $form.find(':submit:enabled').prop('disabled', true);
            } else if (pending === 0) {
                $held.prop('disabled', false);
                $held = $();
            }
        }

        /* Queue one move, to be posted once those before it are answered, and swap the server's
         * table in for this one.
         *
         * url: the move's URL. data: the post's body. focusSelector: finds, in the new table, the
         * button that was clicked.
         */
        function move(url, data, focusSelector) {
            setPending(+1);
            queue = queue.then(function () {
                return $.ajax({type: 'POST', url: url, data: data}).then(function (response) {
                    setPending(-1);
                    $table.html(response.question_table_html);
                    // The site-wide initializer ran on the rows this just replaced, so the new
                    // ones need theirs: an uninitialized bootstrap tooltip or popover does nothing.
                    $table.find('[data-toggle="tooltip"]').tooltip();
                    $table.find('[data-toggle="popover"]').popover();
                    // Put focus back on the same button of the same question, so a teacher moving
                    // a question several places keeps clicking (or pressing enter on) one button.
                    $table.find(focusSelector).focus();
                }, function () {
                    setPending(-1);
                    // Nothing was redrawn, so the page still shows the old order: reload to find
                    // out what the server actually did.
                    window.location.reload();
                    // The reload can be cancelled (the quest form asks first when it holds unsaved
                    // changes), leaving the page open. So hand the queue on able to run: the next
                    // move's answer redraws the table from the saved order. The failed move isn't
                    // posted again, since the server may already have made it.
                    return $.when();
                });
            });
        }

        // Leaving the page by a link, a reload or closing it also drops the moves not yet
        // answered, so ask first, as the unsaved-changes guard does for edited fields.
        window.addEventListener('beforeunload', function (event) {
            if (pending > 0) {
                event.preventDefault();
                event.returnValue = '';
                return '';
            }
        });

        $table.on('submit', 'form.question-move-form', function (event) {
            event.preventDefault();
            var action = $(this).attr('action');
            move(action, $(this).serialize(), 'form[action="' + action + '"] button');
        });

        $table.on('click', 'button[data-move-url]', function () {
            var url = $(this).attr('data-move-url');
            move(url, {
                csrfmiddlewaretoken: $form.find('input[name="csrfmiddlewaretoken"]').val(),
                in_quest_form: '1'
            }, 'button[data-move-url="' + url + '"]');
        });

        // A question's page returns to the quest form with the section's id as the URL's
        // fragment. The form's sections start closed, so open this one and bring it into view.
        var $section = $table.closest('.panel-collapse');
        if ($section.length && window.location.hash === '#' + $section.attr('id')) {
            $section.one('shown.bs.collapse', function () {
                $section.closest('.panel')[0].scrollIntoView();
            });
            $section.collapse('show');
        }
    });
});
