import json

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.generic import FormView, ListView, TemplateView

from hackerspace_online.decorators import staff_member_required

from siteconfig.models import SiteConfig

from tenant.views import NonPublicOnlyViewMixin

from .forms import CompetencyImportForm
from .import_export import export_competency_set, export_csv, import_competency_set, preview_entry_statuses
from .models import Competency

# session key holding the parsed competency set between the upload and preview steps
IMPORT_SESSION_KEY = 'competency_import_set'


def competencies_enabled(f):
    """ Raises 404 unless this deck has competencies enabled: the feature flag gates
    all user-visible parts of the feature. Must be applied outermost (before any
    auth decorators) so that a disabled deck reveals nothing, not even a 403.
    """
    def wrapper(request, *args, **kwargs):
        if not SiteConfig.get().enable_competencies:
            raise Http404
        return f(request, *args, **kwargs)
    return wrapper


@method_decorator([competencies_enabled, staff_member_required], name='dispatch')
class CompetencyListView(NonPublicOnlyViewMixin, ListView):
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
        self.request.session[IMPORT_SESSION_KEY] = form.cleaned_data['competency_set']
        return redirect('competencies:import_preview')


@method_decorator([competencies_enabled, staff_member_required], name='dispatch')
class CompetencyImportPreviewView(NonPublicOnlyViewMixin, TemplateView):
    """ Step 2: preview the set's entries, showing whether each would be created
    or would update an existing competency, and import the selected ones.
    """
    template_name = 'competencies/import_preview.html'

    def get(self, request, *args, **kwargs):
        if IMPORT_SESSION_KEY not in request.session:
            return redirect('competencies:import')
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        competency_set = self.request.session[IMPORT_SESSION_KEY]
        kwargs['competency_set'] = competency_set
        kwargs['entries'] = preview_entry_statuses(competency_set)
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
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
