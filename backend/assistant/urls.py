from django.urls import path

from .views import (
    ApproveDraftView,
    CommandView,
    DraftDetailView,
    DraftListView,
    RejectDraftView,
    SpeakView,
    VoiceCommandView,
)

urlpatterns = [
    path('command/', CommandView.as_view(), name='assistant-command'),
    path('voice/', VoiceCommandView.as_view(), name='assistant-voice'),
    path('speak/', SpeakView.as_view(), name='assistant-speak'),
    path('drafts/', DraftListView.as_view(), name='draft-list'),
    path('drafts/<uuid:reference>/', DraftDetailView.as_view(), name='draft-detail'),
    path('drafts/<uuid:reference>/approve/', ApproveDraftView.as_view(), name='draft-approve'),
    path('drafts/<uuid:reference>/reject/', RejectDraftView.as_view(), name='draft-reject'),
]
