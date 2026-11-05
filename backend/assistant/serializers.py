from rest_framework import serializers

from wallets.serializers import TransactionSerializer

from .models import Draft


class CommandSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=500)


class SpeakSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=600)


class VoiceSerializer(serializers.Serializer):
    audio = serializers.FileField()
    # Hands-free mode: ignore anything that doesn't start with the wake word.
    wake_word = serializers.BooleanField(required=False, default=False)


class DraftSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    transaction = TransactionSerializer(read_only=True)

    class Meta:
        model = Draft
        fields = [
            'reference', 'action', 'status', 'quote', 'summary', 'transcript',
            'expires_at', 'created_at', 'resolved_at', 'transaction',
        ]
        read_only_fields = fields

    def get_status(self, draft):
        if draft.status == Draft.Status.PENDING and draft.is_expired:
            return Draft.Status.EXPIRED.value
        return draft.status
