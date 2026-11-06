from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health(request):
    return JsonResponse({'status': 'ok', 'service': 'vira'})


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', health),
    path('api/auth/', include('accounts.urls')),
    path('api/customers/', include('accounts.customer_urls')),
    path('api/wallets/', include('wallets.urls')),
    path('api/market/', include('market.urls')),
    path('api/assistant/', include('assistant.urls')),
]
