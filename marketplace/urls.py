from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api_views, views, management_views

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
    path('complaints/', management_views.my_complaints, name='my_complaints'),
    path('booking/<int:booking_id>/advance/', management_views.advance_payment_view, name='advance_payment'),
    path('booking/<int:booking_id>/advance/confirm/', management_views.gateway_confirm, name='gateway_confirm'),
    path('payments/razorpay/webhook/', management_views.gateway_webhook, name='gateway_webhook'),
    path('staff/dashboard/', management_views.admin_dashboard, name='admin_dashboard'),
    path('staff/payments/', management_views.staff_payments, name='staff_payments'),
    path('staff/complaints/', management_views.staff_complaints, name='staff_complaints'),
    path('staff/users/', management_views.staff_users, name='staff_users'),
    path('staff/services/', management_views.staff_services, name='staff_services'),
    path('staff/bookings/', management_views.staff_bookings, name='staff_bookings'),
    path('staff/reviews/', management_views.staff_reviews, name='staff_reviews'),
    path('staff/users/<int:user_id>/toggle/', management_views.staff_toggle_user, name='staff_toggle_user'),
    path('staff/services/<int:service_id>/toggle/', management_views.staff_toggle_service, name='staff_toggle_service'),
    path('staff/bookings/<int:booking_id>/status/', management_views.staff_update_booking, name='staff_update_booking'),
    path('staff/reviews/<int:review_id>/delete/', management_views.staff_delete_review, name='staff_delete_review'),
    path('staff/complaints/<int:complaint_id>/review/', management_views.admin_review_complaint, name='admin_review_complaint'),
    path('staff/advances/<int:payment_id>/review/', management_views.admin_review_payment, name='admin_review_payment'),
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
