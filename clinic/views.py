from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@require_GET
@never_cache
def health(request):
    """プロセス稼働だけを返し、設定・診療情報は返さない。"""
    return JsonResponse(
        {
            "status": "ok",
            "service": "AIClinic",
        }
    )
