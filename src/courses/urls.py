from courses import views

from django.conf.urls import url

# For TemplateView example
# from django.views.generic import TemplateView

# Admin site customizations

urlpatterns = [
    url(r'^$', views.CourseStudentList.as_view(), name='list'),
    url(r'^create/$', views.CourseStudentCreate.as_view(), name='create'),
    url(r'^add/(?P<user_id>[0-9]+)/$', views.add_course_student, name='add'),
    url(r'^ranks/$', views.RankList.as_view(), name='ranks'),
    url(r'^marks/$', views.mark_calculations, name='my_marks'),
    url(r'^marks/(?P<user_id>[0-9]+)/$', views.mark_calculations, name='marks'),
    url(r'^close_semester/$',
        views.end_active_semester, name='end_active_semester'),
    url(r'^ajax/progress_chart/(?P<user_id>[0-9]+)/$',
        views.ajax_progress_chart, name='ajax_progress_chart'),
    # url(r'^semester/$', views.semesters, name='semester'),
    # url(r'^semester/$', views.semesters, name='semester'),
    # url(r'^create2/$', views.course_student_create, name='create2'),
    # url(r'^(?P<pk>[0-9]+)/$', views.Detail.as_view(), name='detail'),
    # url(r'^(?P<pk>[0-9]+)/edit/$', views.Update.as_view(), name='update'),
]
