from django.conf.urls import  url
from courses import views

#For TemplateView example
# from django.views.generic import TemplateView

# Admin site customizations

urlpatterns = [
    url(r'^$', views.CourseStudentList.as_view(), name='list'),
    url(r'^create/$', views.CourseStudentCreate.as_view(), name='create'),
    url(r'^ranks/$', views.RankList.as_view(), name='ranks'),
    url(r'^marks/$', views.mark_calculations, name='marks'),
    # url(r'^create2/$', views.course_student_create, name='create2'),
    # url(r'^(?P<pk>[0-9]+)/$', views.Detail.as_view(), name='detail'),
    # url(r'^(?P<pk>[0-9]+)/edit/$', views.Update.as_view(), name='update'),
]
