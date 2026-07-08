from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('transcribe_chunk/', views.transcribe_chunk, name='transcribe_chunk'),
]