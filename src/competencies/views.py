import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.generic import FormView, ListView, TemplateView

from hackerspace_online.decorators import staff_member_required

from quest_manager.models import QuestSubmission

from siteconfig.models import SiteConfig

from tenant.views import NonPublicOnlyViewMixin

from .forms import CompetencyImportForm
from .import_export import export_competency_set, export_csv, import_competency_set, preview_entry_statuses
from .models import Competency, CompetencyAssessment

# session key holding the parsed competency set between the upload and preview steps
IMPORT_SESSION_KEY = 'competency_import_set'


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
class CompetencyEvidenceView(NonPublicOnlyViewMixin, TemplateView):
    """ The evidence behind a student's level in one competency, which their profile's Competencies
    panel links to: every assessment of it, most recent first, with the quest it came from, its
    level and who assessed it. Students see their own evidence; staff see anyone's.
    """
    template_name = 'competencies/evidence.html'

    def get(self, request, *args, **kwargs):
        """ Renders the page for the student and competency in the URL.

        Raises:
            Http404: if either doesn't exist, or the student is someone else and the requesting
                user isn't staff (so another student's evidence isn't even confirmed to exist).
        """
        self.student = get_object_or_404(get_user_model(), pk=kwargs['user_pk'])
        if self.student != request.user and not request.user.is_staff:
            raise Http404
        self.competency = get_object_or_404(Competency, pk=kwargs['competency_pk'])
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """ Returns the template context: the student, the competency, their current assessment of
        it with the deck's label, and 'rows', each assessment with its label.

        Each assessment's submission and quest are prefetched, through the base manager so that
        submissions of quests since archived or unpublished still name their quest.
        """
        labels = SiteConfig.get().get_competency_scale_labels()
        evidence = CompetencyAssessment.objects.filter(user=self.student, competency=self.competency)
        current = evidence.current().first()
        assessments = evidence.select_related('assessed_by__profile').prefetch_related(
            GenericPrefetch('source_object', [QuestSubmission._base_manager.select_related('quest')]),
        )
        kwargs.update({
            'student': self.student,
            'competency': self.competency,
            'current': current,
            'current_label': labels[current.level] if current else '',
            'rows': [{'assessment': assessment, 'label': labels[assessment.level]} for assessment in assessments],
        })
        return super().get_context_data(**kwargs)
