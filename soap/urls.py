from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('transcribe_chunk/', views.transcribe_chunk, name='transcribe_chunk'),
    path('generate_soap/', views.generate_soap, name='generate_soap'),
    path('generate_referral/', views.generate_referral, name='generate_referral'),
]