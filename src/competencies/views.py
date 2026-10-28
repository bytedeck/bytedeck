import csv
import json
from collections import Counter
from itertools import groupby

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.generic import FormView, ListView, TemplateView

from courses.models import Block, Course, CourseStudent
from hackerspace_online.decorators import staff_member_required

from siteconfig.models import SiteConfig

from tenant.views import NonPublicOnlyViewMixin

from .forms import CompetencyImportForm
from .import_export import export_competency_set, export_csv, import_competency_set, preview_entry_statuses
from .models import Competency, ProficiencyLevel
from .summaries import LEVEL_RANGES, course_competencies, course_matrix, evidence_by_competency, level_codes

# session key holding the parsed competency set between the upload and preview steps
IMPORT_SESSION_KEY = 'competency_import_set'


#: What a spreadsheet takes a cell beginning with to be a formula (or the start of one).
SPREADSHEET_FORMULA_STARTS = ('=', '+', '-', '@', '\t', '\r')


def csv_safe(value):
    """ A CSV cell's value as text a spreadsheet won't run as a formula: one starting with =, +, -,
    @, a tab or a carriage return gets a leading single quote. A downloaded CSV is opened in a
    spreadsheet, and its text comes from people (a student's own name, an imported competency set),
    so a value like "=HYPERLINK(...)" would otherwise run when staff open it.

    Args:
        value (object): the cell's value.

    Returns:
        str: the text to write.
    """
    text = '' if value is None else str(value)
    return f"'{text}" if text.startswith(SPREADSHEET_FORMULA_STARTS) else text


def competencies_enabled(f):
    """ Raises 404 unless this deck has competencies enabled: the feature flag gates
    all user-visible parts of the feature. Must be applied outermost (before any
    auth decorators) so that a disabled deck reveals nothing, not even a 403.
    The public schema has no SiteConfig (SiteConfig.get() returns None there), which
    counts as disabled.
    """
    def wrapper(request, *args, **kwargs):
        config = SiteConfig.get()
        if config is None or not config.enable_competencies:
            raise Http404
        return f(request, *args, **kwargs)
    return wrapper


@method_decorator([competencies_enabled, staff_member_required], name='dispatch')
class CompetencyListView(NonPublicOnlyViewMixin, ListView):
    """ The staff-facing list of this deck's competencies, with links to the
    import/export tools.
    """
    model = Competency
    template_name = 'competencies/list.html'


@method_decorator([competencies_enabled, staff_member_required], name='dispatch')
class CompetencyImportView(NonPublicOnlyViewMixin, FormView):
    """ Step 1: pick a bundled set or upload a JSON/CSV file. The parsed set is
    stashed in the session and the user is sent to the preview step.
    """
    form_class = CompetencyImportForm
    template_name = 'competencies/import.html'

    def form_valid(self, form):
        """ Stashes the parsed competency set from the valid form in the session and
        returns a redirect to the preview step.
        """
        self.request.session[IMPORT_SESSION_KEY] = form.cleaned_data['competency_set']
        return redirect('competencies:import_preview')


@method_decorator([competencies_enabled, staff_member_required], name='dispatch')
class CompetencyImportPreviewView(NonPublicOnlyViewMixin, TemplateView):
    """ Step 2: preview the set's entries, showing whether each would be created
    or would update an existing competency, and import the selected ones.
    """
    template_name = 'competencies/import_preview.html'

    def get(self, request, *args, **kwargs):
        """ Renders the preview page, or returns a redirect back to the upload step
        when there's no parsed set in the session (e.g. a direct visit or a reload
        after importing).
        """
        if IMPORT_SESSION_KEY not in request.session:
            return redirect('competencies:import')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """ Returns the template context with the session's competency set and its
        entries annotated with the create/update action an import would take.
        """
        competency_set = self.request.session[IMPORT_SESSION_KEY]
        kwargs['competency_set'] = competency_set
        kwargs['entries'] = preview_entry_statuses(competency_set)
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        """ Imports the entries selected on the preview form from the session's
        competency set, then returns a redirect: to the competency list with a
        success message, back to the preview when nothing was selected, or back
        to the upload step when the session holds no set.
        """
        competency_set = request.session.get(IMPORT_SESSION_KEY)
        if competency_set is None:
            return redirect('competencies:import')

        selected_indexes = [int(i) for i in request.POST.getlist('entries') if i.isdigit()]
        if not selected_indexes:
            messages.warning(request, "No competencies were selected, so nothing was imported.")
            return redirect('competencies:import_preview')

        created, updated = import_competency_set(competency_set, selected_indexes)
        del request.session[IMPORT_SESSION_KEY]

        messages.success(request, f"Competencies imported: {created} created and {updated} updated.")
        return redirect('competencies:list')


@method_decorator([competencies_enabled, staff_member_required], name='dispatch')
class CompetencyExportView(NonPublicOnlyViewMixin, TemplateView):
    """ Download this deck's active competencies as a portable competency set,
    as JSON (default) or CSV (?format=csv). Either file can be re-imported here
    or on another deck.
    """

    def get(self, request, *args, **kwargs):
        """ Returns the deck's active competencies as a file-download HttpResponse in
        the format given by the ?format= query param: 'json' (the default) or 'csv'.

        Raises:
            Http404: for any other requested format.
        """
        export_format = request.GET.get('format', 'json')
        filename = f"{slugify(SiteConfig.get().site_name)}-competencies"
        set_name = f"{SiteConfig.get().site_name} Competencies"

        if export_format == 'csv':
            response = HttpResponse(export_csv(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        elif export_format == 'json':
            content = json.dumps(export_competency_set(name=set_name), indent=4)
            response = HttpResponse(content, content_type='application/json')
            response['Content-Disposition'] = f'attachment; filename="{filename}.json"'
        else:
            raise Http404
        return response


@method_decorator([competencies_enabled, login_required], name='dispatch')
class CompetencySummaryView(NonPublicOnlyViewMixin, TemplateView):
    """ A student's competencies summary, linked from beside Mark Calculations on their profile and
    laid out like it: a table of their courses (see competencies.summaries) with each one's average,
    then a tab per course (when there is more than one) listing all of the course's competencies, each
    with a chip for every assessment of it, oldest first, linking to the work it was given for.
    Students see their own; staff see anyone's.
    """
    template_name = 'competencies/summary.html'

    def get(self, request, *args, **kwargs):
        """ Renders the summary for the student in the URL.

        Raises:
            Http404: if there's no such user, or it's someone else and the requesting user isn't
                staff (so another student's summary isn't even confirmed to exist).
        """
        self.student = get_object_or_404(get_user_model(), pk=kwargs['user_pk'])
        if self.student != request.user and not request.user.is_staff:
            raise Http404
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """ Returns the template context: the student and 'panes', one per course, each with:

        - the course, and the deck's label for its average level ('' below the scale);
        - 'active': whether its tab is the one open, which is the course named by the ``course`` query
          parameter (a pane id, as the profile links with), else the first;
        - 'level_counts', for the breakdown of its average: each level the student holds in the course,
          as (level, label, how many competencies), and 'scale', each level with its label and code, the
          averages that round to it and whether the course's average does;
        - 'rows', each of the course's competencies with its evidence and the deck's label and code for
          each assessment's level.

        Also 'scale': each level of the Proficiency Scale as (level, label, code), for the explanation.
        """
        labels = SiteConfig.get().get_competency_scale_labels()
        codes = level_codes(labels)
        evidence = evidence_by_competency(self.student)
        courses = course_competencies(self.student)
        pane_ids = [course.pane_id for course in courses]
        requested = self.request.GET.get('course')
        active_id = requested if requested in pane_ids else next(iter(pane_ids), None)
        panes = []
        for course in courses:
            counts = Counter(course.course_levels)
            panes.append({
                'course': course,
                'active': course.pane_id == active_id,
                'level_label': labels.get(course.level, ''),
                'level_counts': [(level, labels[level], counts[level]) for level in ProficiencyLevel.values if counts[level]],
                'scale': [
                    {
                        'level': level, 'label': labels.get(level, ''), 'code': codes.get(level, ''),
                        'range': LEVEL_RANGES[level], 'current': level == course.level,
                    }
                    for level in LEVEL_RANGES
                ],
                'rows': [
                    {
                        'competency': competency,
                        'evidence': [
                            {'item': item, 'label': labels[item.assessment.level], 'code': codes[item.assessment.level]}
                            for item in evidence.get(competency.pk, [])
                        ],
                    }
                    for competency in course.competencies
                ],
            })
        kwargs.update({
            'student': self.student,
            'panes': panes,
            'scale': [(level, labels[level], codes[level]) for level in ProficiencyLevel.values],
        })
        return super().get_context_data(**kwargs)


@method_decorator([competencies_enabled, staff_member_required], name='dispatch')
class CompetencyMatrixView(NonPublicOnlyViewMixin, TemplateView):
    """ The staff competency matrix: a course's students (optionally in one block) by the competencies of
    the course's set, each cell the student's current level, from the same roll-up as each student's own
    competencies page, which each cell links to. ``?format=csv`` downloads the matrix with the levels'
    labels, for report cards.

    The course and block are chosen by the ``course`` and ``block`` query parameters (pks); an unknown
    or missing course is the first course with a competency set, and an unknown or missing block is all
    of them.
    """
    template_name = 'competencies/matrix.html'

    def get(self, request, *args, **kwargs):
        """ Renders the matrix, or with ``?format=csv`` returns it as a CSV download. """
        context = self.get_context_data(**kwargs)
        if request.GET.get('format') == 'csv' and context['course'] is not None:
            return self.csv_response(context)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):
        """ Returns the template context:

        - 'courses', the active courses with a competency set, and 'course', the one shown (None when
          there are none);
        - 'blocks', the blocks with students in that course this semester, and 'selected_block', the one
          shown (None for all), named so because templates already use ``block`` for ``{{ block.super }}``;
        - 'columns', the course's competencies, and 'categories', each category with how many of them
          it spans, for the header;
        - 'rows', one per student, each with their CourseCompetencies, the deck's label for their
          current level of proficiency, and a cell per column: its competency, and the student's level
          in it with its code and label (None and '' when not yet assessed);
        - 'scale', each level of the Proficiency Scale as (level, label, code), for the key.
        """
        labels = SiteConfig.get().get_competency_scale_labels()
        codes = level_codes(labels)
        courses = list(Course.objects.filter(active=True).exclude(competency_set=''))
        course = next((course for course in courses if str(course.pk) == self.request.GET.get('course')), next(iter(courses), None))

        blocks, block, columns, rows = [], None, [], []
        if course is not None:
            registrations = CourseStudent.objects.get_queryset().in_open_semesters().get_students_only().filter(course=course)
            blocks = list(Block.objects.filter(pk__in=registrations.values('block')))
            block = next((block for block in blocks if str(block.pk) == self.request.GET.get('block')), None)
            columns, matrix = course_matrix(course, block)
            for row in matrix:
                rows.append({
                    'course': row,
                    'level_label': labels.get(row.level, ''),
                    'cells': [
                        {
                            'competency': column,
                            'level': row.levels.get(column.pk),
                            'code': codes.get(row.levels.get(column.pk), ''),
                            'label': labels.get(row.levels.get(column.pk), ''),
                        }
                        for column in columns
                    ],
                })

        kwargs.update({
            'courses': courses,
            'course': course,
            'blocks': blocks,
            'selected_block': block,
            'columns': columns,
            'categories': [(category, len(list(group))) for category, group in groupby(columns, key=lambda column: column.category)],
            'rows': rows,
            'scale': [(level, labels[level], codes[level]) for level in ProficiencyLevel.values],
        })
        return super().get_context_data(**kwargs)

    def csv_response(self, context):
        """ The matrix as a CSV download: a row per student with their name, username, block, average
        and current level of proficiency, then their level in each competency (headed "Category:
        Competency"), by the deck's labels ("n/a" where not yet assessed). Every cell is made safe
        to open in a spreadsheet (csv_safe).

        Args:
            context (dict): what get_context_data returned, with a course.

        Returns:
            HttpResponse: the CSV file, named after the course (and block).
        """
        response = HttpResponse(content_type='text/csv')
        name = slugify(f"{context['course'].title} {context['selected_block'] or ''} competencies")
        response['Content-Disposition'] = f'attachment; filename="{name}.csv"'
        writer = csv.writer(response)
        writer.writerow([csv_safe(cell) for cell in (
            ['Student', 'Username', SiteConfig.get().custom_name_for_group, 'Average', 'Current level of proficiency']
            # the course is the file's own, so each column is named by category and competency
            + [': '.join(part for part in (column.category, column.name) if part) for column in context['columns']]
        )])
        for row in context['rows']:
            registration = row['course'].registration
            writer.writerow([csv_safe(cell) for cell in (
                [
                    registration.user.profile.teacher_name(), registration.user.username, registration.block,
                    f"{row['course'].average:.2f}", row['level_label'] or 'n/a',
                ]
                + [cell['label'] or 'n/a' for cell in row['cells']]
            )])
        return response
