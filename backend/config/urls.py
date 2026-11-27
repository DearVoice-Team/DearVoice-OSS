from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include, re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="SW_2025 API",
        default_version='v1',
        description="SSWU 프로젝트 API 문서",
        contact=openapi.Contact(email="your@email.com"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

def health_check(request):
    return HttpResponse("ok", status=200)

urlpatterns = [
    path('health/', health_check),
    path('admin/', admin.site.urls),
    path('api/auth/', include('users.urls')),
    path('api/mypage/', include('mypage.urls')),
    path('api/letters/', include('letters.urls')),
    path('skyvoice/', include('skyvoice.urls')),
]