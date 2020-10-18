from django.urls import path

from jchart.views import ChartView

from courses import views
from courses.models import MarkDistributionHistogram

app_name = 'courses'

urlpatterns = [

    # Semester
    path('semesters/', views.SemesterList.as_view(), name='semester_list'),
    path('semesters/add/', views.SemesterCreate.as_view(), name='semester_create'),
    path('semesters/<pk>/edit/', views.SemesterUpdate.as_view(), name='semester_update'),
    path('close_semester/', views.end_active_semester, name='end_active_semester'),

    # Blocks
    path('blocks/', views.BlockList.as_view(), name='block_list'),
    path('blocks/add/', views.BlockCreate.as_view(), name='block_create'),
    path('blocks/<pk>/edit/', views.BlockUpdate.as_view(), name='block_update'),
    path('blocks/<pk>/delete/', views.BlockDelete.as_view(), name='block_delete'),

    # CourseStudent
    path('create/', views.CourseStudentCreate.as_view(), name='create'),
    path('add/<int:user_id>/', views.CourseAddStudent.as_view(), name='add'),

    # Ranks
    path('ranks/', views.RankList.as_view(), name='ranks'),

    # Marks
    path('marks', views.mark_calculations, name='my_marks'),
    path('marks/<int:user_id>', views.mark_calculations, name='marks'),
    path('ajax/progress_chart/<int:user_id>/', views.ajax_progress_chart, name='ajax_progress_chart'),

    path('charts/bar_chart/<int:user_id>)/', ChartView.from_chart(MarkDistributionHistogram()),
         name='mark_distribution_chart'),

    # Course
    path('list/', views.CourseList.as_view(), name='course_list'),
    path('add/', views.CourseCreate.as_view(), name='course_create'),
    path('<pk>/edit/', views.CourseUpdate.as_view(), name='course_update'),
    path('<pk>/delete/', views.CourseDelete.as_view(), name='course_delete'),

    # url(r'^semester/$', views.semesters, name='semester'),
    # url(r'^semester/$', views.semesters, name='semester'),
    # url(r'^create2/$', views.course_student_create, name='create2'),
    # url(r'^(?P<pk>[0-9]+)/$', views.Detail.as_view(), name='detail'),
    # url(r'^(?P<pk>[0-9]+)/edit/$', views.Update.as_view(), name='update'),
]
