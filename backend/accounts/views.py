from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from wallets.views import WalletApiView

from .customers import add_customer, find_user
from .serializers import (
    CustomerRequestSerializer,
    CustomerSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class CustomerListView(WalletApiView):
    def get(self, request):
        customers = request.user.customers.select_related('user')
        return Response(CustomerSerializer(customers, many=True).data)

    def post(self, request):
        serializer = CustomerRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = add_customer(request.user, serializer.validated_data['username'])
        return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)


class CustomerLookupView(WalletApiView):
    """Shows whose username this is, so nobody saves the wrong person."""

    def get(self, request):
        user = find_user(request.user, request.query_params.get('username'))
        return Response({'username': user.username, 'full_name': user.full_name})


class CustomerDetailView(generics.DestroyAPIView):
    def get_queryset(self):
        return self.request.user.customers.all()
