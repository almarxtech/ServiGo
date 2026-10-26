from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api_views, views

router = DefaultRouter()
router.register(r'api/reviews', api_views.ReviewViewSet, basename='review-api')
router.register(r'api/services', api_views.ServiceViewSet, basename='service-api')
router.register(r'api/bookings', api_views.BookingViewSet, basename='booking-api')

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('about/', views.about_view, name='about'),

    path('service/add/', views.add_service_view, name='add_service'),
    path('service/<int:service_id>/', views.service_detail_view, name='service_detail'),
    path('service/<int:service_id>/edit/', views.edit_service_view, name='edit_service'),
    path('service/<int:service_id>/delete/', views.delete_service_view, name='delete_service'),
    path('service/<int:service_id>/review/', views.add_review_view, name='add_review'),
    path('service/book/<int:service_id>/', views.book_service_view, name='book_service'),

    path('booking/<int:booking_id>/edit/', views.edit_booking_view, name='edit_booking'),
    path('booking/<int:booking_id>/delete/', views.delete_booking_view, name='delete_booking'),
    path('booking/update/<int:booking_id>/<str:status>/', views.update_booking_status, name='update_booking_status'),

    path('api/chat/', views.ai_chat_api, name='ai_chat_api'),
    path('api/chat/clear/', views.clear_chat_session, name='clear_chat_session'),
    path('', include(router.urls)),
]
