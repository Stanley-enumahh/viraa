import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from wallets.serializers import SendRequestSerializer, TradeRequestSerializer, TransactionSerializer
from wallets.views import WalletApiView

from . import drafts, speech
from .commands import draft_manual_send, draft_manual_trade, handle_command
from .models import Draft
from .serializers import CommandSerializer, DraftSerializer, SpeakSerializer, VoiceSerializer
from .speakable import speakable
from .wake import strip_wake_word

logger = logging.getLogger(__name__)

ALLOWED_AUDIO_PREFIXES = ('audio/', 'video/webm')


def speech_unavailable(exc):
    logger.warning('Speech service failed: %s', exc)
    return Response(
        {'detail': "Voice isn't available right now. You can type your request instead.", 'code': 'speech_unavailable'},
        status=status.HTTP_502_BAD_GATEWAY,
    )


def command_response(transcript, reply, parser):
    return Response({
        'transcript': transcript,
        'type': reply.kind,
        'reply': reply.text,
        'parser': parser,
        'draft': DraftSerializer(reply.draft).data if reply.draft else None,
        'data': reply.data,
    })


def simple_response(kind, transcript='', reply=''):
    """A result that never reached Claude."""
    return Response({'transcript': transcript, 'type': kind, 'reply': reply, 'parser': None, 'draft': None, 'data': None})


def respond_to_speech(user, transcript):
    """Run what was said, minus any wake word. Saying only "hey Vira" just gets her attention."""
    heard, command = strip_wake_word(transcript)
    if heard and not command:
        return simple_response('listening', transcript, 'Yes?')
    reply, intent = handle_command(user, command[:500])
    return command_response(transcript, reply, intent.source)


class AssistantThrottled:
    """These endpoints spend real API credits, so cap how fast one user can call them."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'assistant'


class CommandView(AssistantThrottled, WalletApiView):
    def post(self, request):
        serializer = CommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return respond_to_speech(request.user, serializer.validated_data['text'])


class VoiceCommandView(AssistantThrottled, WalletApiView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = VoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        audio = serializer.validated_data['audio']
        if audio.size > settings.MAX_AUDIO_UPLOAD_BYTES:
            return Response(
                {'detail': 'That recording is too long.', 'code': 'audio_too_large'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (audio.content_type or '').startswith(ALLOWED_AUDIO_PREFIXES):
            return Response(
                {'detail': 'Please upload an audio recording.', 'code': 'invalid_audio'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            transcript = speech.transcribe(audio)
        except speech.SpeechError as exc:
            return speech_unavailable(exc)

        if serializer.validated_data['wake_word'] and not strip_wake_word(transcript)[0]:
            # Not addressed to Vira. Drop it without storing it or calling Claude.
            return simple_response('ignored')
        if not transcript:
            return simple_response('question', reply="I didn't catch that. Could you say it again?")
        return respond_to_speech(request.user, transcript)


class SpeakView(AssistantThrottled, WalletApiView):
    def post(self, request):
        serializer = SpeakSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            audio = speech.synthesize(speakable(serializer.validated_data['text']))
        except speech.SpeechError as exc:
            return speech_unavailable(exc)
        return HttpResponse(audio, content_type='audio/mpeg')


class DraftListView(WalletApiView):
    def get(self, request):
        drafts_list = request.user.assistant_drafts.select_related('transaction__counterparty')[:20]
        return Response(DraftSerializer(drafts_list, many=True).data)

    def post(self, request):
        serializer = TradeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = draft_manual_trade(request.user, **serializer.validated_data)
        return Response(DraftSerializer(draft).data, status=status.HTTP_201_CREATED)


class SendDraftView(WalletApiView):
    def post(self, request):
        serializer = SendRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        draft = draft_manual_send(request.user, **serializer.validated_data)
        return Response(DraftSerializer(draft).data, status=status.HTTP_201_CREATED)


class DraftDetailView(generics.RetrieveAPIView):
    serializer_class = DraftSerializer
    lookup_field = 'reference'

    def get_queryset(self):
        return self.request.user.assistant_drafts.select_related('transaction__counterparty')


class ApproveDraftView(WalletApiView):
    def post(self, request, reference):
        try:
            draft = drafts.approve_draft(request.user, reference)
        except Draft.DoesNotExist as exc:
            raise Http404 from exc
        tx = TransactionSerializer(draft.transaction).data
        return Response({
            'reply': f"Done. {tx['summary']}.",
            'draft': DraftSerializer(draft).data,
        })


class RejectDraftView(WalletApiView):
    def post(self, request, reference):
        try:
            draft = drafts.reject_draft(request.user, reference)
        except Draft.DoesNotExist as exc:
            raise Http404 from exc
        return Response({'reply': 'Okay, I cancelled that request.', 'draft': DraftSerializer(draft).data})
