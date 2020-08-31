from django.conf.urls import url
from jchart.views import ChartView

from courses import views
from courses.models import MarkDistributionHistogram

app_name = 'courses'

urlpatterns = [
    url(r'^create/$', views.CourseStudentCreate.as_view(), name='create'),
    url(r'^add/(?P<user_id>[0-9]+)/$', views.CourseAddStudent.as_view(), name='add'),
    url(r'^ranks/$', views.RankList.as_view(), name='ranks'),
    # DISABLE MARKS
    url(r'^marks/$', views.mark_calculations, name='my_marks'),
    url(r'^marks/(?P<user_id>[0-9]+)/$', views.mark_calculations, name='marks'),
    url(r'^close_semester/$', views.end_active_semester, name='end_active_semester'),
    url(r'^ajax/progress_chart/(?P<user_id>[0-9]+)/$', views.ajax_progress_chart, name='ajax_progress_chart'),

    url(r'^charts/bar_chart/(?P<user_id>[0-9]+)/$', ChartView.from_chart(MarkDistributionHistogram()),
        name='mark_distribution_chart'),
    # url(r'^semester/$', views.semesters, name='semester'),
    # url(r'^semester/$', views.semesters, name='semester'),
    # url(r'^create2/$', views.course_student_create, name='create2'),
    # url(r'^(?P<pk>[0-9]+)/$', views.Detail.as_view(), name='detail'),
    # url(r'^(?P<pk>[0-9]+)/edit/$', views.Update.as_view(), name='update'),
]
