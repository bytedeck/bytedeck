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

        /* Post one move and swap the server's table in for this one.
         *
         * url: the move's URL. data: the post's body. focusSelector: finds, in the new table, the
         * button that was clicked.
         */
        function move(url, data, focusSelector) {
            $.ajax({
                type: 'POST',
                url: url,
                data: data,
                success: function (response) {
                    $table.html(response.question_table_html);
                    // The site-wide initializer ran on the rows this just replaced, so the new
                    // ones need theirs: an uninitialized bootstrap tooltip or popover does nothing.
                    $table.find('[data-toggle="tooltip"]').tooltip();
                    $table.find('[data-toggle="popover"]').popover();
                    // Put focus back on the same button of the same question, so a teacher moving
                    // a question several places keeps clicking (or pressing enter on) one button.
                    $table.find(focusSelector).focus();
                },
                error: function () {
                    // Nothing was redrawn, so the page still shows the old order: reload to find
                    // out what the server actually did.
                    window.location.reload();
                }
            });
        }

        $table.on('submit', 'form.question-move-form', function (event) {
            event.preventDefault();
            var action = $(this).attr('action');
            move(action, $(this).serialize(), 'form[action="' + action + '"] button');
        });

        $table.on('click', 'button[data-move-url]', function () {
            var url = $(this).attr('data-move-url');
            move(url, {
                csrfmiddlewaretoken: $table.closest('form').find('input[name="csrfmiddlewaretoken"]').val(),
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
