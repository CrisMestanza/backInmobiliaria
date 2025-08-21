from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..serializers import UsuarioSerializer
from ..models import Usuario
from rest_framework import status
import json


# Listar todos los usuarios activos
@api_view(['GET'])
def listUsuarios(request):
    usuarios = Usuario.objects.filter(estado=1)
    serializer = UsuarioSerializer(usuarios, many=True)
    return Response(serializer.data)


# Crear usuario
@api_view(['POST'])
def registerUsuario(request):
    data = {
        'correo': request.data.get('correo'),
        'contrasena': request.data.get('contrasena'),
        'nombre': request.data.get('nombre'),
        'estado': 1
    }
    serializer = UsuarioSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Obtener usuario por id
@api_view(['GET'])
def listUsuarioId(request, idusuario):
    usuario = Usuario.objects.filter(idusuario=idusuario, estado=1).first()
    if usuario:
        serializer = UsuarioSerializer(usuario)
        return Response(serializer.data)
    return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)


# Actualizar usuario (PUT - todo el objeto)
@api_view(['PUT'])
def updateUsuario(request, idusuario):
    try:
        usuario = Usuario.objects.get(idusuario=idusuario)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    serializer = UsuarioSerializer(usuario, data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)


# Eliminar usuario (soft delete → estado = 0)
@api_view(['PUT'])
def deleteUsuario(request, idusuario):
    try:
        usuario = Usuario.objects.get(idusuario=idusuario)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    usuario.estado = 0
    usuario.save()
    return Response({'message': 'Usuario desactivado correctamente'}, status=status.HTTP_200_OK)


# Validar ingreso (login)
@api_view(['POST'])
def loginUsuario(request):
    correo = request.data.get('correo')
    contrasena = request.data.get('contrasena')
    print(correo, contrasena)
    # Verificar si el correo existe
    usuario = Usuario.objects.filter(correo=correo, estado=1).first()
    print(usuario)
    if not usuario:
        return Response({'error': 'Correo incorrecto'}, status=status.HTTP_400_BAD_REQUEST)

    # Verificar contraseña
    if usuario.contrasena != contrasena:
        return Response({'error': 'Contraseña incorrecta'}, status=status.HTTP_400_BAD_REQUEST)

    # Si todo está bien
    serializer = UsuarioSerializer(usuario)
    return Response({'message': 'Ingreso exitoso', 'usuario': serializer.data}, status=status.HTTP_200_OK)
