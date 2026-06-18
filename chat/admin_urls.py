from django.urls import path

from .admin_views import AdminDeleteUserView, AdminSuspendUserView, AdminUnsuspendUserView, AdminUserListView

urlpatterns = [
    path('users/', AdminUserListView.as_view(), name='admin-user-list'),
    path('users/<int:pk>/suspend/', AdminSuspendUserView.as_view(), name='admin-user-suspend'),
    path('users/<int:pk>/unsuspend/', AdminUnsuspendUserView.as_view(), name='admin-user-unsuspend'),
    path('users/<int:pk>/delete/', AdminDeleteUserView.as_view(), name='admin-user-delete'),
]
