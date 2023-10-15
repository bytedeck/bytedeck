from django.urls import path

from courses import views

app_name = 'courses'

urlpatterns = [

    # Semester
    path('semesters/', views.SemesterList.as_view(), name='semester_list'),
    path('semesters/add/', views.SemesterCreate.as_view(), name='semester_create'),
    path('semesters/<pk>/edit/', views.SemesterUpdate.as_view(), name='semester_update'),
    path('semesters/<pk>/delete/', views.SemesterDelete.as_view(), name='semester_delete'),
    path('semesters/close/', views.end_active_semester, name='end_active_semester'),
    path('semesters/<pk>/activate/', views.SemesterActivate.as_view(), name='semester_activate'),

    # Blocks
    path('blocks/', views.BlockList.as_view(), name='block_list'),
    path('blocks/add/', views.BlockCreate.as_view(), name='block_create'),
    path('blocks/<pk>/edit/', views.BlockUpdate.as_view(), name='block_update'),
    path('blocks/<pk>/delete/', views.BlockDelete.as_view(), name='block_delete'),

    # CourseStudent
    path('student/add/', views.CourseStudentCreate.as_view(), name='create'),
    path('student/<int:user_id>/join/', views.CourseAddStudent.as_view(), name='join'),
    path('student/<pk>/edit/', views.CourseStudentUpdate.as_view(), name='update'),
    path('student/<pk>/delete/', views.CourseStudentDelete.as_view(), name='coursestudent_delete'),

    # Ranks
    path('ranks/', views.RankList.as_view(), name='ranks'),
    path('ranks/create/', views.RankCreate.as_view(), name='rank_create'),
    path('ranks/<pk>/edit/', views.RankUpdate.as_view(), name='rank_update'),
    path('ranks/<pk>/delete/', views.RankDelete.as_view(), name='rank_delete'),

    # Marks
    path('marks/', views.mark_calculations, name='my_marks'),
    path('marks/<int:user_id>', views.mark_calculations, name='marks'),
    path('ajax/progress_chart/<int:user_id>/', views.ajax_progress_chart, name='ajax_progress_chart'),
    path('ajax/marks_bar_chart/<int:user_id>/', views.Ajax_MarkDistributionChart.as_view(), name='mark_distribution_chart'),
    path('ajax/tag_progress_chart/<int:user_id>/', views.Ajax_TagChart.as_view(), name='ajax_tag_progress_chart'),

    # MarkRanges
    path('markranges/', views.MarkRangeList.as_view(), name='markranges'),
    path('markranges/create/', views.MarkRangeCreate.as_view(), name='markrange_create'),
    path('markranges/<pk>/edit/', views.MarkRangeUpdate.as_view(), name='markrange_update'),
    path('markranges/<pk>/delete/', views.MarkRangeDelete.as_view(), name='markrange_delete'),

    # Course
    path('list/', views.CourseList.as_view(), name='course_list'),
    path('create/', views.CourseCreate.as_view(), name='course_create'),
    path('<pk>/edit/', views.CourseUpdate.as_view(), name='course_update'),
    path('<pk>/delete/', views.CourseDelete.as_view(), name='course_delete'),

]
