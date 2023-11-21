from django.http import HttpResponseRedirect
from rest_framework.response import Response
from rest_framework.status import (
        HTTP_201_CREATED,
        HTTP_400_BAD_REQUEST,
        HTTP_401_UNAUTHORIZED
)
from .models import CustomUser
from django.contrib.auth.decorators import login_required
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.debug import sensitive_post_parameters
from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, render, redirect
from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import method_decorator
from .forms import CustomUserCreationForm, CustomUserCreationFormEmail
from .serializers import UserSerializer
from .models import CustomUser
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.shortcuts import resolve_url
from django.contrib.auth.views import LoginView
from django.urls import reverse
import pyotp
import qrcode
import os
from django.contrib.auth.forms import AuthenticationForm
from decide.settings import AUTH_MAX_FAILED_LOGIN_ATTEMPTS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@login_required
def home(request):
        data = {
        'form': CustomUserCreationForm(),
        'user': request.user}

        return render(request, "home.html", data)

user_failed_login_attempts = 0
class Custom_loginView(LoginView):
    def login2(request):
        """Inicia sesión a un usuario.

        Args:
            request: La solicitud HTTP.

        Returns:
            La respuesta HTTP.
        """
        
        
        global user_failed_login_attempts
        # ...

        if request.user != 'AnonymousUser':
            # El usuario no existe o la contraseña es incorrecta.
            user_failed_login_attempts += 1
            print(user_failed_login_attempts)
            if user_failed_login_attempts >= AUTH_MAX_FAILED_LOGIN_ATTEMPTS:
            # El límite de intentos fallidos se ha alcanzado.
                usuario = CustomUser.objects.get(username=request.POST.get("username"))
                CustomUser.block_account(usuario)
                return redirect("registro")
            else:
                return render(request, "registration/login.html", { 'form': AuthenticationForm})
        else:
            # El usuario ha iniciado sesión correctamente.
            user_failed_login_attempts = 0
            login(request, request.user)
            return redirect("home")
    
    def get_success_url(self):
        user = self.request.user

        # Verificar si el usuario tiene un dato llamado 'secret'
        if hasattr(user, 'secret') and user.secret:
            user_id = self.request.user.id
            success_url = reverse('comprobarqr', kwargs={'user_id': user_id})
            logout(self.request)
            return success_url 

        return super().get_success_url()
   

def registro(request):
    data = {
        'form': CustomUserCreationForm()
    }
    if request.method == 'POST':
        user_creation_form = CustomUserCreationForm(data=request.POST)

        if user_creation_form.is_valid():
            user = user_creation_form.save()

            login(request, user)
            return redirect('home')
        else:
            data['mensaje'] = 'Ha habido un error en el formulario'
    return render(request, "registro.html", data)

def registroEmail(request):
    data = {
        'form': CustomUserCreationFormEmail()
    }
    if request.method == 'POST':
        user_creation_form = CustomUserCreationFormEmail(data=request.POST)

        if user_creation_form.is_valid():
            user = user_creation_form.save()

            login(request, user)
            return redirect('home')
        else:
            data['mensaje'] = 'Ha habido un error en el formulario'
    return render(request, "registroEmail.html", data)


def comprobarqr(request, user_id):
    if(request.method == 'POST'):
        user = CustomUser.objects.get(pk=user_id)
        codigo = request.POST.get('codigo', None)
        totp_object = pyotp.TOTP(user.secret)
        print(totp_object.now())
        
        if(totp_object.verify(codigo)):
            login(request, user)
            return render(request, 'home.html')
    return render(request, '2fa.html')

@login_required
def dobleautenticacion(request, user_id):

    if(request.method == 'POST'):
        return redirect('home')
    secreto = pyotp.random_base32()
    totp_object = pyotp.TOTP(secreto)
    user = get_object_or_404(CustomUser, id=user_id)
    user.secret = secreto
    user.save()
    qr_texto = totp_object.provisioning_uri(name=request.user.username , issuer_name="Decide App")
    qr = qrcode.make(qr_texto)
    raiz = os.path.join(BASE_DIR, 'authentication/static')
    camino = f'{raiz}/{request.user.username}.png'
    camino_foto = f'/static/{request.user.username}.png'
    qr.save(camino)
    datos = {
        'qr_text' : qr_texto,
        'camino': camino_foto
    }
    return render(request, 'factordoble.html', datos)

class GetUserView(APIView):
    def post(self, request):
        key = request.data.get('token', '')
        tk = get_object_or_404(Token, key=key)
        return Response(UserSerializer(tk.user, many=False).data)


class LogoutView(APIView):
    def post(self, request):
        key = request.data.get('token', '')
        try:
            tk = Token.objects.get(key=key)
            tk.delete()
        except ObjectDoesNotExist:
            pass

        return Response({})


class RegisterView(APIView):
    def post(self, request):
        key = request.data.get('token', '')
        tk = get_object_or_404(Token, key=key)
        if not tk.user.is_superuser:
            return Response({}, status=HTTP_401_UNAUTHORIZED)

        username = request.data.get('username', '')
        pwd = request.data.get('password', '')
        if not username or not pwd:
            return Response({}, status=HTTP_400_BAD_REQUEST)

        try:
            user = CustomUser(username=username)
            user.set_password(pwd)
            user.save()
            token, _ = Token.objects.get_or_create(user=user)
        except IntegrityError:
            return Response({}, status=HTTP_400_BAD_REQUEST)
        return Response({'user_pk': user.pk, 'token': token.key}, HTTP_201_CREATED)
