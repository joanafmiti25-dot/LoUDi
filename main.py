import hashlib
import hmac
import logging
import os
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from typing import Any, Iterator, Optional

import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from services import (
    ReglaNegocioError,
    ahora_local,
    hash_contrasena,
    normalizar_fecha_hora_local,
    obtener_turno,
    registrar_intento_fallido,
    token_sesion,
    validar_capacidad,
    validar_cancelacion_reserva,
    validar_contrasena,
    validar_correo,
    validar_publicacion,
    validar_reserva,
    validar_transicion_viaje,
    verificar_contrasena,
)

logger = logging.getLogger("loudi")
app = FastAPI(
    title="API de LoUDi",
    description="API REST de traslados compartidos de la comunidad UTSJR",
    version="3.0.0",
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5000"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Seed-Token"],
)

bearer = HTTPBearer(auto_error=False)
DOMINIO_CORREO = os.getenv("DOMINIO_CORREO", "@utsjr.edu.mx")
TOKEN_HORAS = int(os.getenv("TOKEN_HORAS", "12"))


def get_db_connection():
    required = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise HTTPException(
            status_code=503,
            detail="Falta configurar la conexión de base de datos en el servidor.",
        )
    kwargs: dict[str, Any] = {}
    ca_file = os.getenv("DB_SSL_CA")
    if ca_file:
        kwargs.update(
            ssl_ca=ca_file,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )
    elif os.getenv("DB_SSL_DISABLED", "").lower() == "true":
        kwargs["ssl_disabled"] = True
    try:
        return pymysql.connect(
            host=os.environ["DB_HOST"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            database=os.environ["DB_NAME"],
            port=int(os.getenv("DB_PORT", "3306")),
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            connect_timeout=15,
            read_timeout=60,
            write_timeout=60,
            **kwargs,
        )
    except pymysql.MySQLError as exc:
        logger.exception("No se pudo conectar con MySQL.")
        raise HTTPException(
            status_code=503,
            detail="No fue posible conectar con la base de datos.",
        ) from exc


@contextmanager
def db_cursor() -> Iterator[Any]:
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@app.exception_handler(ReglaNegocioError)
async def regla_error_handler(_, exc: ReglaNegocioError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc)},
    )


@app.exception_handler(pymysql.err.IntegrityError)
async def integridad_error_handler(_, exc: pymysql.err.IntegrityError):
    from fastapi.responses import JSONResponse

    logger.info("Conflicto de integridad en operación de base de datos: %s", exc.args[0])
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "El registro ya existe o viola una relación requerida."},
    )


@app.exception_handler(RequestValidationError)
async def validacion_request_handler(_, exc: RequestValidationError):
    from fastapi.responses import JSONResponse

    campos = sorted(
        {
            ".".join(str(parte) for parte in error["loc"] if parte != "body")
            for error in exc.errors()
        }
        - {""}
    )
    detalle = (
        f"Revisa los datos enviados: {', '.join(campos)}."
        if campos
        else "Los datos enviados no son válidos."
    )
    return JSONResponse(status_code=422, content={"detail": detalle})


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MensajeResponse(Modelo):
    message: str
    id: Optional[int] = None


class UsuarioResponse(Modelo):
    id: str
    nombre: str
    apellido: str
    correo: Optional[str] = None
    rol: str
    Estado_Cuenta: Optional[str] = None


class LoginRequest(Modelo):
    correo: EmailStr
    password: str


class LoginResponse(Modelo):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    rol: str
    usuario: UsuarioResponse


class RegistroRequest(Modelo):
    NoControl: int
    Nombre_Estudiante: str = Field(min_length=1, max_length=30)
    Apellido_Estudiante: str = Field(min_length=1, max_length=30)
    Correo_Estudiante: EmailStr
    Rol_Usuario: str
    Telefono: str = Field(min_length=1, max_length=15)
    Contraseña: str
    Cuatrimestre: str = ""
    Colonia: str = ""
    Municipio: str = ""
    CP: int = 0
    Estado: str = ""
    Calle: str = ""
    NoCalle: int = 0
    idHorario1: Optional[int] = None
    NumLicencia: Optional[str] = None


class AdministradorCreate(Modelo):
    id_Administrador: Optional[int] = None
    Nombre_Administrador: str = Field(min_length=1, max_length=30)
    Apellido_Administrador: str = Field(min_length=1, max_length=20)
    Correo_Administrador: EmailStr
    Contraseña_Administrador: str


class AdministradorResponse(Modelo):
    id_Administrador: int
    Nombre_Administrador: str
    Apellido_Administrador: str
    Correo_Administrador: str


class HorarioCreate(Modelo):
    idHorario: Optional[int] = None
    Turno: str
    HoraEntrada: time
    HoraSalida: time


class HorarioResponse(Modelo):
    idHorario: int
    Turno: str
    HoraEntrada: time
    HoraSalida: time


class EstudianteCreate(RegistroRequest):
    id_Administrador1: Optional[int] = None


class EstudianteResponse(Modelo):
    NoControl: int
    Nombre_Estudiante: str
    Apellido_Estudiante: str
    Correo_Estudiante: Optional[str] = None
    Rol_Usuario: str
    Telefono: str
    Estado_Cuenta: str
    Intentos_Fallidos: int
    Bloqueado_Hasta: Optional[datetime] = None
    Reportes: int
    Fecha_Registro: datetime


class PagoCreate(Modelo):
    IdPago: Optional[int] = None
    Monto: float = Field(ge=0)
    Estatus: str
    Fecha: date


class PagoResponse(Modelo):
    IdPago: int
    Monto: float
    Estatus: str
    Fecha: date


class PoseeResponse(Modelo):
    IdConductor1: int
    IdVehiculo1: int


class RealizaResponse(Modelo):
    IdConductor2: int
    IdViaje2: int
    IdVehiculo2: int
    Fecha_Realiza: date
    Hora_Realiza: time


class VehiculoCreate(Modelo):
    id_conductor: int
    Marca: str = Field(min_length=1, max_length=60)
    Modelo: str = Field(min_length=1, max_length=20)
    Placa: str = Field(min_length=1, max_length=10)
    Año: int = Field(ge=1900, le=2100)
    Color: str = Field(min_length=1, max_length=20)
    NoSeguro: str = Field(min_length=1, max_length=25)
    Capacidad_Pasajeros: int = Field(ge=1, le=4)


class VehiculoResponse(Modelo):
    idVehiculo: int
    id_conductor: int
    Marca: str
    Modelo: str
    Placa: str
    Año: int
    Color: str
    Capacidad_Pasajeros: int


class ViajeCreate(Modelo):
    id_conductor: int
    id_vehiculo: int
    origen: str = Field(min_length=1, max_length=50)
    destino: str = Field(min_length=1, max_length=50)
    fecha_hora_salida: datetime
    lugares: int = Field(ge=1, le=4)
    costo: float = Field(ge=0, le=999.99)


class ViajeResponse(Modelo):
    idViaje: int
    idConductor: Optional[int] = None
    Nombre_Conductor: Optional[str] = None
    idVehiculo: Optional[int] = None
    Marca: Optional[str] = None
    Modelo: Optional[str] = None
    Color: Optional[str] = None
    Capacidad_Pasajeros: Optional[int] = None
    Origen: str
    Destino: str
    Fecha_Hora_Salida: Optional[datetime] = None
    Turno: Optional[str] = None
    Precio_Estimado: float
    Asientos_Disponibles: int
    Asientos_Totales: int
    Estado: str


class ReservaCreate(Modelo):
    IdPasajero1: int
    IdViaje1: int
    Lugares_Solicitados: int = Field(default=1, ge=1, le=4)


class ReservaResponse(Modelo):
    idSolicitud: int
    IdPasajero1: Optional[int] = None
    Nombre_Pasajero: Optional[str] = None
    IdViaje1: Optional[int] = None
    Lugares_Solicitados: int
    Fecha: date
    Hora: time
    Estado_Reserva: str
    Califica: float


class EstadoReservaUpdate(Modelo):
    Estado_Reserva: str


class CalificacionCreate(Modelo):
    idCalificacion: Optional[int] = None
    idViaje1: int
    NoControl_Evaluador: int
    NoControl_Evaluado: int
    Rol_Evaluado: str
    Puntuacion: int = Field(ge=1, le=5)
    Comentario: Optional[str] = Field(default=None, max_length=250)


class CalificacionResponse(Modelo):
    idCalificacion: int
    idViaje1: Optional[int] = None
    NoControl_Evaluador: int
    NoControl_Evaluado: int
    Rol_Evaluado: str
    Puntuacion: float
    Comentario: Optional[str] = None
    Fecha_Registro: datetime
    Promedio: Optional[float] = None


class ReporteCreate(Modelo):
    NoControl_Reportante: int
    NoControl_Reportado: Optional[int] = None
    idViaje1: Optional[int] = None
    Motivo: str = Field(min_length=1, max_length=100)
    Descripcion: str


class ReporteResponse(Modelo):
    idReporte: int
    NoControl_Reportante: int
    NoControl_Reportado: Optional[int] = None
    idViaje1: Optional[int] = None
    Motivo: str
    Descripcion: str
    Estado_Reporte: str
    Fecha_Reporte: datetime


class NotificacionCreate(Modelo):
    NoControl_Destinatario: Optional[int] = None
    id_Administrador_Destinatario: Optional[int] = None
    Titulo: str = Field(min_length=1, max_length=80)
    Mensaje: str = Field(min_length=1, max_length=255)


class NotificacionResponse(Modelo):
    idNotificacion: int
    NoControl_Destinatario: Optional[int] = None
    id_Administrador_Destinatario: Optional[int] = None
    Titulo: str
    Mensaje: str
    Leida: bool
    Fecha_Creacion: datetime


class BloqueoRequest(Modelo):
    id_administrador: int


class SemanaResponse(Modelo):
    semana: str
    viajes: int
    reservas: int


def _crear_estudiante(cursor: Any, datos: RegistroRequest) -> dict[str, Any]:
    correo = validar_correo(str(datos.Correo_Estudiante), DOMINIO_CORREO)
    validar_contrasena(datos.Contraseña)
    rol = datos.Rol_Usuario.strip().lower()
    if rol not in ("pasajero", "conductor", "ambos"):
        raise ReglaNegocioError("El rol debe ser pasajero, conductor o ambos.", 422)
    if rol in ("conductor", "ambos") and not datos.NumLicencia:
        raise ReglaNegocioError(
            "El número de licencia es obligatorio para el rol conductor.", 422
        )
    cursor.execute(
        "SELECT NoControl FROM Estudiante WHERE Correo_Estudiante = %s OR NoControl = %s",
        (correo, datos.NoControl),
    )
    if cursor.fetchone():
        raise ReglaNegocioError(
            "El correo o número de control ya está registrado.", 409
        )
    cursor.execute(
        """INSERT INTO Estudiante
        (NoControl, Nombre_Estudiante, Apellido_Estudiante, Correo_Estudiante,
         Rol_Usuario, Telefono, Cuatrimestre, Colonia, Municipio, CP, Estado,
         Calle, NoCalle, Contraseña, Contraseña_Hash, Estado_Cuenta,
         Intentos_Fallidos, Reportes, id_Administrador1, idHorario1)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,
                'activo',0,0,%s,%s)""",
        (
            datos.NoControl,
            datos.Nombre_Estudiante.strip(),
            datos.Apellido_Estudiante.strip(),
            correo,
            rol,
            datos.Telefono.strip(),
            datos.Cuatrimestre,
            datos.Colonia,
            datos.Municipio,
            datos.CP,
            datos.Estado,
            datos.Calle,
            datos.NoCalle,
            hash_contrasena(datos.Contraseña),
            getattr(datos, "id_Administrador1", None),
            datos.idHorario1,
        ),
    )
    if rol in ("pasajero", "ambos"):
        cursor.execute(
            "INSERT INTO Pasajero (IdPasajero1, IdPago1) VALUES (%s, NULL)",
            (datos.NoControl,),
        )
    if rol in ("conductor", "ambos"):
        cursor.execute(
            """INSERT INTO Conductor (IdConductor, NumLicencia, Num_Viajes)
            VALUES (%s, %s, 0)""",
            (datos.NoControl, datos.NumLicencia),
        )
    return {
        "NoControl": datos.NoControl,
        "Nombre_Estudiante": datos.Nombre_Estudiante.strip(),
        "Apellido_Estudiante": datos.Apellido_Estudiante.strip(),
        "Correo_Estudiante": correo,
        "Rol_Usuario": rol,
        "Telefono": datos.Telefono,
        "Estado_Cuenta": "activo",
        "Intentos_Fallidos": 0,
        "Bloqueado_Hasta": None,
        "Reportes": 0,
        "Fecha_Registro": datetime.now(),
    }


def _es_admin(actor: dict[str, Any]) -> None:
    if actor["rol"] != "administrador":
        raise HTTPException(status_code=403, detail="Se requiere rol administrador.")


def _es_mismo_usuario(actor: dict[str, Any], no_control: int) -> None:
    if actor["rol"] != "administrador" and (
        actor["tipo"] != "estudiante" or actor["id"] != no_control
    ):
        raise HTTPException(status_code=403, detail="No puedes acceder a esta cuenta.")


def actor_actual(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Inicia sesión para continuar.")
    token_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT s.Id_Administrador, s.NoControl, s.Expira,
                      a.Nombre_Administrador, a.Apellido_Administrador,
                      e.Nombre_Estudiante, e.Apellido_Estudiante, e.Estado_Cuenta
               FROM Sesion s
               LEFT JOIN Administrador a ON a.id_Administrador=s.Id_Administrador
               LEFT JOIN Estudiante e ON e.NoControl=s.NoControl
               WHERE s.Token_Hash=%s AND s.Revocada=0 AND s.Expira>NOW()
               LIMIT 1""",
            (token_hash,),
        )
        sesion = cursor.fetchone()
        if not sesion:
            raise HTTPException(status_code=401, detail="La sesión no es válida.")
        if sesion["Id_Administrador"] is not None:
            return {
                "id": sesion["Id_Administrador"],
                "tipo": "administrador",
                "rol": "administrador",
                "nombre": sesion["Nombre_Administrador"],
            }
        if sesion["NoControl"] is None or sesion["Estado_Cuenta"] != "activo":
            raise HTTPException(status_code=403, detail="La cuenta está bloqueada.")
        cursor.execute(
            "SELECT Rol_Usuario FROM Estudiante WHERE NoControl=%s",
            (sesion["NoControl"],),
        )
        estudiante = cursor.fetchone()
        return {
            "id": sesion["NoControl"],
            "tipo": "estudiante",
            "rol": estudiante["Rol_Usuario"] if estudiante else "",
            "nombre": sesion["Nombre_Estudiante"],
        }


def _notificar_estudiante(cursor: Any, no_control: int, titulo: str, mensaje: str):
    cursor.execute(
        """INSERT INTO Notificacion
        (NoControl_Destinatario, Titulo, Mensaje)
        VALUES (%s,%s,%s)""",
        (no_control, titulo[:80], mensaje[:255]),
    )


def _notificar_admins(cursor: Any, titulo: str, mensaje: str):
    cursor.execute("SELECT id_Administrador FROM Administrador")
    for admin in cursor.fetchall():
        cursor.execute(
            """INSERT INTO Notificacion
            (id_Administrador_Destinatario, Titulo, Mensaje)
            VALUES (%s,%s,%s)""",
            (admin["id_Administrador"], titulo[:80], mensaje[:255]),
        )


def _cancelar_viaje(cursor: Any, id_viaje: int, titulo: str, mensaje: str):
    cursor.execute(
        "SELECT Estado, Asientos_Totales FROM Viaje WHERE idViaje=%s FOR UPDATE",
        (id_viaje,),
    )
    viaje = cursor.fetchone()
    if not viaje:
        raise HTTPException(status_code=404, detail="Viaje no encontrado.")
    estado = validar_transicion_viaje(viaje["Estado"], "cancelar")
    cursor.execute(
        """SELECT idSolicitud, IdPasajero1 FROM Solicita
           WHERE IdViaje1=%s AND Estado_Reserva IN ('pendiente','confirmada')
           FOR UPDATE""",
        (id_viaje,),
    )
    for reserva in cursor.fetchall():
        cursor.execute(
            "UPDATE Solicita SET Estado_Reserva='cancelada' WHERE idSolicitud=%s",
            (reserva["idSolicitud"],),
        )
        if reserva["IdPasajero1"] is not None:
            _notificar_estudiante(
                cursor, reserva["IdPasajero1"], titulo, mensaje
            )
    cursor.execute(
        """UPDATE Viaje SET Estado=%s, Asientos_Disponibles=Asientos_Totales
           WHERE idViaje=%s""",
        (estado, id_viaje),
    )


def _viaje_query() -> str:
    return """SELECT v.idViaje, r.IdConductor2 AS idConductor,
        CONCAT(e.Nombre_Estudiante, ' ', LEFT(e.Apellido_Estudiante,1),'.')
            AS Nombre_Conductor,
        r.IdVehiculo2 AS idVehiculo, ve.Marca, ve.Modelo, ve.Color,
        ve.Capacidad_Pasajeros, v.Origen, v.Destino, v.Fecha_Hora_Salida,
        h.Turno, v.Precio_Estimado, v.Asientos_Disponibles,
        v.Asientos_Totales, v.Estado
        FROM Viaje v
        LEFT JOIN Realiza r ON r.IdViaje2=v.idViaje
        LEFT JOIN Estudiante e ON e.NoControl=r.IdConductor2
        LEFT JOIN Vehiculo ve ON ve.idVehiculo=r.IdVehiculo2
        LEFT JOIN Horario h ON h.idHorario=v.idHorario1"""


def _obtener_viaje(cursor: Any, id_viaje: int) -> dict[str, Any]:
    cursor.execute(_viaje_query() + " WHERE v.idViaje=%s LIMIT 1", (id_viaje,))
    viaje = cursor.fetchone()
    if not viaje:
        raise HTTPException(status_code=404, detail="Viaje no encontrado.")
    return viaje


@app.post("/api/registro", status_code=201, response_model=EstudianteResponse, tags=["Autenticación"])
def registrar_usuario(datos: RegistroRequest):
    with db_cursor() as cursor:
        return _crear_estudiante(cursor, datos)


@app.post("/api/login", response_model=LoginResponse, tags=["Autenticación"])
def login_usuario(datos: LoginRequest):
    ahora = datetime.now()
    respuesta: Optional[LoginResponse] = None
    fallo = False
    with db_cursor() as cursor:
        correo = str(datos.correo).strip().lower()
        cursor.execute(
            """SELECT id_Administrador, Nombre_Administrador, Apellido_Administrador,
                      Correo_Administrador, Contraseña_Hash
               FROM Administrador WHERE Correo_Administrador=%s LIMIT 1 FOR UPDATE""",
            (correo,),
        )
        admin = cursor.fetchone()
        tipo = "administrador"
        rol = "administrador"
        usuario = admin
        if not admin:
            cursor.execute(
                """SELECT NoControl, Nombre_Estudiante, Apellido_Estudiante,
                          Correo_Estudiante, Rol_Usuario, Estado_Cuenta,
                          Intentos_Fallidos, Bloqueado_Hasta, Contraseña_Hash
                   FROM Estudiante WHERE Correo_Estudiante=%s LIMIT 1 FOR UPDATE""",
                (correo,),
            )
            usuario = cursor.fetchone()
            tipo = "estudiante"
            rol = usuario["Rol_Usuario"] if usuario else ""

        if not usuario:
            fallo = True
        else:
            password_hash = usuario["Contraseña_Hash"]
            cuenta_activa = True
            if tipo == "estudiante":
                if (
                    usuario["Bloqueado_Hasta"]
                    and usuario["Bloqueado_Hasta"] <= ahora
                ):
                    cursor.execute(
                        """UPDATE Estudiante SET Estado_Cuenta='activo',
                            Intentos_Fallidos=0, Bloqueado_Hasta=NULL
                           WHERE NoControl=%s""",
                        (usuario["NoControl"],),
                    )
                    usuario["Estado_Cuenta"] = "activo"
                    usuario["Intentos_Fallidos"] = 0
                    usuario["Bloqueado_Hasta"] = None
                cuenta_activa = usuario["Estado_Cuenta"] == "activo"

            if not cuenta_activa or not verificar_contrasena(
                datos.password, password_hash
            ):
                if tipo == "estudiante" and cuenta_activa:
                    intentos, bloqueado_hasta, estado = registrar_intento_fallido(
                        usuario["Intentos_Fallidos"], ahora
                    )
                    cursor.execute(
                        """UPDATE Estudiante SET Intentos_Fallidos=%s,
                            Estado_Cuenta=%s, Bloqueado_Hasta=%s
                           WHERE NoControl=%s""",
                        (intentos, estado, bloqueado_hasta, usuario["NoControl"]),
                    )
                fallo = True
            else:
                if tipo == "estudiante":
                    cursor.execute(
                        """UPDATE Estudiante SET Intentos_Fallidos=0,
                            Bloqueado_Hasta=NULL WHERE NoControl=%s""",
                        (usuario["NoControl"],),
                    )
                    user_id = usuario["NoControl"]
                    user_data = UsuarioResponse(
                        id=str(user_id),
                        nombre=usuario["Nombre_Estudiante"],
                        apellido=usuario["Apellido_Estudiante"],
                        correo=usuario["Correo_Estudiante"],
                        rol=rol,
                        Estado_Cuenta="activo",
                    )
                else:
                    user_id = usuario["id_Administrador"]
                    user_data = UsuarioResponse(
                        id=str(user_id),
                        nombre=usuario["Nombre_Administrador"],
                        apellido=usuario["Apellido_Administrador"],
                        correo=usuario["Correo_Administrador"],
                        rol="administrador",
                    )
                token, token_hash = token_sesion()
                expira = ahora + timedelta(hours=TOKEN_HORAS)
                cursor.execute(
                    """INSERT INTO Sesion
                    (Id_Administrador, NoControl, Token_Hash, Expira)
                    VALUES (%s,%s,%s,%s)""",
                    (
                        user_id if tipo == "administrador" else None,
                        user_id if tipo == "estudiante" else None,
                        token_hash,
                        expira,
                    ),
                )
                respuesta = LoginResponse(
                    access_token=token,
                    expires_at=expira,
                    rol=rol,
                    usuario=user_data,
                )
    if fallo:
        raise HTTPException(
            status_code=401,
            detail="Correo o contraseña incorrectos, o cuenta no activa.",
        )
    assert respuesta is not None
    return respuesta


@app.post("/api/logout", response_model=MensajeResponse, tags=["Autenticación"])
def cerrar_sesion(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    actor: dict[str, Any] = Depends(actor_actual),
):
    token_hash = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
    with db_cursor() as cursor:
        cursor.execute(
            "UPDATE Sesion SET Revocada=1 WHERE Token_Hash=%s",
            (token_hash,),
        )
    return {"message": "Sesión cerrada."}


@app.post(
    "/api/sembrar-datos-prueba",
    response_model=MensajeResponse,
    tags=["Datos de Prueba"],
)
def sembrar_datos_prueba(
    x_seed_token: Optional[str] = Header(default=None, alias="X-Seed-Token"),
):
    seed_token = os.getenv("SEED_TOKEN")
    if not seed_token or not x_seed_token or not hmac.compare_digest(
        seed_token, x_seed_token
    ):
        raise HTTPException(
            status_code=403,
            detail="La carga de datos de prueba está deshabilitada o no autorizada.",
        )
    mañana = (ahora_local() + timedelta(days=1)).date()
    password_hash = hash_contrasena("loudi1234")
    estudiantes = [
        (2023001, "Ana", "Martínez", "pasajero", None, 1),
        (2023002, "Luis", "Hernández", "conductor", "LIC23002", 1),
        (2023003, "Sofía", "Ruiz", "conductor", "LIC23003", 2),
        (2023004, "Marco", "Díaz", "conductor", "LIC23004", 1),
        (2023005, "Diego", "Cruz", "pasajero", None, 2),
        (2023006, "Valeria", "Soto", "pasajero", None, 1),
    ]
    with db_cursor() as cursor:
        cursor.execute(
            """INSERT INTO Administrador
            (id_Administrador, Nombre_Administrador, Apellido_Administrador,
             Correo_Administrador, Contraseña_Administrador, Contraseña_Hash)
            VALUES (1,'Administración','LoUDi','admin@utsjr.edu.mx',NULL,%s)
            ON DUPLICATE KEY UPDATE Contraseña_Hash=VALUES(Contraseña_Hash),
              Contraseña_Administrador=NULL""",
            (password_hash,),
        )
        cursor.execute(
            """INSERT INTO Horario (idHorario, Turno, HoraEntrada, HoraSalida)
               VALUES (1,'Matutino','07:00:00','14:00:00'),
                      (2,'Vespertino','14:00:00','21:00:00')
               ON DUPLICATE KEY UPDATE Turno=VALUES(Turno),
                 HoraEntrada=VALUES(HoraEntrada), HoraSalida=VALUES(HoraSalida)"""
        )
        for no_control, nombre, apellido, rol, licencia, horario in estudiantes:
            cursor.execute(
                """INSERT INTO Estudiante
                (NoControl,Nombre_Estudiante,Apellido_Estudiante,Correo_Estudiante,
                 Rol_Usuario,Telefono,Cuatrimestre,Colonia,Municipio,CP,Estado,
                 Calle,NoCalle,Contraseña,Contraseña_Hash,Estado_Cuenta,
                 Intentos_Fallidos,Reportes,Fecha_Registro,id_Administrador1,idHorario1)
                VALUES (%s,%s,%s,%s,%s,'0000000000','4to','Centro',
                        'San Juan del Río',76800,'Querétaro','Universidad',1,
                        NULL,%s,'activo',0,0,NOW(),1,%s)
                ON DUPLICATE KEY UPDATE Correo_Estudiante=VALUES(Correo_Estudiante),
                  Rol_Usuario=VALUES(Rol_Usuario),Contraseña_Hash=VALUES(Contraseña_Hash),
                  Contraseña=NULL,Estado_Cuenta='activo',Intentos_Fallidos=0,
                  Bloqueado_Hasta=NULL""",
                (
                    no_control,
                    nombre,
                    apellido,
                    f"{nombre.lower()}@utsjr.edu.mx",
                    rol,
                    password_hash,
                    horario,
                ),
            )
            if rol in ("pasajero", "ambos"):
                cursor.execute(
                    "INSERT IGNORE INTO Pasajero (IdPasajero1,IdPago1) VALUES (%s,NULL)",
                    (no_control,),
                )
            if rol in ("conductor", "ambos"):
                cursor.execute(
                    """INSERT INTO Conductor (IdConductor,NumLicencia,Num_Viajes)
                       VALUES (%s,%s,0)
                       ON DUPLICATE KEY UPDATE NumLicencia=VALUES(NumLicencia)""",
                    (no_control, licencia),
                )

        autos = [
            (2023002, "SJR001", "Nissan Versa", "Azul", 4, "DEMO-S1"),
            (2023003, "SJR002", "Toyota Yaris", "Blanco", 3, "DEMO-S2"),
            (2023004, "SJR003", "Kia Rio", "Gris", 4, "DEMO-S3"),
        ]
        vehiculos: list[tuple[int, int]] = []
        for conductor, placas, modelo, color, capacidad, seguro in autos:
            cursor.execute(
                """INSERT INTO Vehiculo
                (Placa,Modelo,Año,Color,NoSeguro,Capacidad_Pasajeros,Marca)
                VALUES (%s,%s,2022,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE Modelo=VALUES(Modelo),Color=VALUES(Color),
                  Capacidad_Pasajeros=VALUES(Capacidad_Pasajeros),Marca=VALUES(Marca)""",
                (placas, modelo, color, seguro, capacidad, modelo.split()[0]),
            )
            cursor.execute("SELECT idVehiculo FROM Vehiculo WHERE Placa=%s", (placas,))
            id_vehiculo = cursor.fetchone()["idVehiculo"]
            cursor.execute(
                """INSERT INTO Posee (IdConductor1,IdVehiculo1) VALUES (%s,%s)
                   ON DUPLICATE KEY UPDATE IdConductor1=VALUES(IdConductor1)""",
                (conductor, id_vehiculo),
            )
            vehiculos.append((conductor, id_vehiculo))

        rutas = [
            ("Centro San Juan", "UTSJR", time(7, 30), 1, 2023002, vehiculos[0][1], 20, 4),
            ("Tequisquiapan", "UTSJR", time(15, 30), 2, 2023003, vehiculos[1][1], 35, 3),
            ("La Estancia", "UTSJR", time(8, 0), 1, 2023004, vehiculos[2][1], 25, 4),
            ("UTSJR", "Centro San Juan", time(18, 0), 2, 2023002, vehiculos[0][1], 20, 4),
        ]
        ids_viajes: list[int] = []
        for origen, destino, hora, horario, conductor, vehiculo, costo, lugares in rutas:
            salida = datetime.combine(mañana, hora)
            cursor.execute(
                """SELECT idViaje FROM Viaje
                   WHERE Origen=%s AND Destino=%s AND Fecha_Hora_Salida=%s LIMIT 1""",
                (origen, destino, salida),
            )
            row = cursor.fetchone()
            if row:
                id_viaje = row["idViaje"]
            else:
                cursor.execute(
                    """INSERT INTO Viaje
                    (Origen,Destino,Precio_Estimado,Asientos_Disponibles,
                     Asientos_Totales,Estado,idHorario1,Fecha_Hora_Salida)
                    VALUES (%s,%s,%s,%s,%s,'Publicado',%s,%s)""",
                    (origen, destino, costo, lugares, lugares, horario, salida),
                )
                id_viaje = cursor.lastrowid
            cursor.execute(
                """SELECT IdViaje2 FROM Realiza
                   WHERE IdViaje2=%s LIMIT 1""",
                (id_viaje,),
            )
            if not cursor.fetchone():
                cursor.execute(
                    """INSERT INTO Realiza
                    (IdConductor2,IdViaje2,IdVehiculo2,Fecha_Realiza,Hora_Realiza)
                    VALUES (%s,%s,%s,%s,%s)""",
                    (conductor, id_viaje, vehiculo, mañana, hora),
                )
            ids_viajes.append(id_viaje)
        # Una reserva de ejemplo por pasajero, insertada solo si no existe activa.
        for pasajero, viaje_id in ((2023001, ids_viajes[0]), (2023005, ids_viajes[1])):
            cursor.execute(
                """SELECT idSolicitud FROM Solicita
                   WHERE IdPasajero1=%s AND IdViaje1=%s
                     AND Estado_Reserva IN ('pendiente','confirmada') LIMIT 1""",
                (pasajero, viaje_id),
            )
            if not cursor.fetchone():
                cursor.execute(
                    """UPDATE Viaje
                       SET Estado=IF(Asientos_Disponibles-1=0,'Lleno','Publicado'),
                           Asientos_Disponibles=Asientos_Disponibles-1
                       WHERE idViaje=%s AND Estado='Publicado'
                         AND Asientos_Disponibles>=1""",
                    (viaje_id,),
                )
                if cursor.rowcount == 1:
                    cursor.execute(
                        """INSERT INTO Solicita
                        (IdPasajero1,Fecha,Hora,Lugares_Solicitados,Estado_Reserva,
                         Califica,IdViaje1)
                        VALUES (%s,%s,%s,1,'confirmada',0,%s)""",
                        (pasajero, mañana, time(6), viaje_id),
                    )
    return {"message": "Datos de prueba insertados o actualizados de forma idempotente."}


@app.get(
    "/api/administradores",
    response_model=list[AdministradorResponse],
    tags=["Administrador"],
)
def obtener_administradores():
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT id_Administrador,Nombre_Administrador,Apellido_Administrador,
               Correo_Administrador FROM Administrador ORDER BY id_Administrador"""
        )
        return cursor.fetchall()


@app.post(
    "/api/administradores",
    status_code=201,
    response_model=AdministradorResponse,
    tags=["Administrador"],
)
def crear_administrador(
    admin: AdministradorCreate,
):
    validar_contrasena(admin.Contraseña_Administrador)
    with db_cursor() as cursor:
        cursor.execute(
            """INSERT INTO Administrador
            (Nombre_Administrador,Apellido_Administrador,Correo_Administrador,
             Contraseña_Administrador,Contraseña_Hash)
            VALUES (%s,%s,%s,NULL,%s)""",
            (
                admin.Nombre_Administrador.strip(),
                admin.Apellido_Administrador.strip(),
                str(admin.Correo_Administrador).lower(),
                hash_contrasena(admin.Contraseña_Administrador),
            ),
        )
        admin_id = cursor.lastrowid
        cursor.execute(
            """SELECT id_Administrador,Nombre_Administrador,Apellido_Administrador,
               Correo_Administrador FROM Administrador WHERE id_Administrador=%s""",
            (admin_id,),
        )
        return cursor.fetchone()


@app.get(
    "/api/horarios",
    response_model=list[HorarioResponse],
    tags=["Horario"],
)
def obtener_horarios():
    with db_cursor() as cursor:
        cursor.execute("SELECT idHorario,Turno,HoraEntrada,HoraSalida FROM Horario")
        filas = cursor.fetchall()
        return [
            {
                **fila,
                "HoraEntrada": _hora_python(fila["HoraEntrada"]),
                "HoraSalida": _hora_python(fila["HoraSalida"]),
            }
            for fila in filas
        ]


@app.post(
    "/api/horarios",
    status_code=201,
    response_model=HorarioResponse,
    tags=["Horario"],
)
def crear_horario(
    horario: HorarioCreate,
):
    if horario.Turno not in ("Matutino", "Vespertino"):
        raise HTTPException(status_code=422, detail="Turno debe ser Matutino o Vespertino.")
    if horario.HoraEntrada >= horario.HoraSalida:
        raise HTTPException(status_code=422, detail="El horario de entrada debe preceder a la salida.")
    with db_cursor() as cursor:
        cursor.execute(
            """INSERT INTO Horario (Turno,HoraEntrada,HoraSalida)
               VALUES (%s,%s,%s)""",
            (horario.Turno, horario.HoraEntrada, horario.HoraSalida),
        )
        horario_id = cursor.lastrowid
        cursor.execute(
            "SELECT idHorario,Turno,HoraEntrada,HoraSalida FROM Horario WHERE idHorario=%s",
            (horario_id,),
        )
        return cursor.fetchone()


@app.get(
    "/api/estudiantes",
    response_model=list[EstudianteResponse],
    tags=["Estudiante"],
)
def obtener_estudiantes(
    q: str = Query(default="", max_length=100),
):
    patron = f"%{q.strip()}%"
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT NoControl,Nombre_Estudiante,Apellido_Estudiante,
                      Correo_Estudiante,Rol_Usuario,Telefono,Estado_Cuenta,
                      Intentos_Fallidos,Bloqueado_Hasta,Reportes,Fecha_Registro
               FROM Estudiante
               WHERE %s='' OR Nombre_Estudiante LIKE %s OR
                     Apellido_Estudiante LIKE %s OR Correo_Estudiante LIKE %s
               ORDER BY Apellido_Estudiante,Nombre_Estudiante""",
            (q.strip(), patron, patron, patron),
        )
        return cursor.fetchall()


@app.post(
    "/api/estudiantes",
    status_code=201,
    response_model=EstudianteResponse,
    tags=["Estudiante"],
)
def crear_estudiante(
    est: EstudianteCreate,
):
    with db_cursor() as cursor:
        return _crear_estudiante(cursor, est)


@app.get(
    "/api/pasajeros",
    response_model=list[UsuarioResponse],
    tags=["Pasajero"],
)
def obtener_pasajeros():
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT e.NoControl AS id,e.Nombre_Estudiante AS nombre,
                      e.Apellido_Estudiante AS apellido,e.Correo_Estudiante AS correo,
                      'pasajero' AS rol,e.Estado_Cuenta
               FROM Estudiante e JOIN Pasajero p ON p.IdPasajero1=e.NoControl
               ORDER BY e.NoControl"""
        )
        return cursor.fetchall()


@app.get(
    "/api/conductores",
    response_model=list[UsuarioResponse],
    tags=["Conductor"],
)
def obtener_conductores():
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT e.NoControl AS id,e.Nombre_Estudiante AS nombre,
                      e.Apellido_Estudiante AS apellido,e.Correo_Estudiante AS correo,
                      'conductor' AS rol,e.Estado_Cuenta
               FROM Estudiante e JOIN Conductor c ON c.IdConductor=e.NoControl
               ORDER BY e.NoControl"""
        )
        return cursor.fetchall()


@app.get("/api/pagos", response_model=list[PagoResponse], tags=["Pago"])
def obtener_pagos():
    with db_cursor() as cursor:
        cursor.execute("SELECT IdPago,Monto,Estatus,Fecha FROM Pago ORDER BY IdPago")
        return cursor.fetchall()


@app.post(
    "/api/pagos",
    status_code=201,
    response_model=PagoResponse,
    tags=["Pago"],
)
def crear_pago(
    pago: PagoCreate,
):
    with db_cursor() as cursor:
        cursor.execute(
            "INSERT INTO Pago (Monto,Estatus,Fecha) VALUES (%s,%s,%s)",
            (pago.Monto, pago.Estatus, pago.Fecha),
        )
        cursor.execute(
            "SELECT IdPago,Monto,Estatus,Fecha FROM Pago WHERE IdPago=%s",
            (cursor.lastrowid,),
        )
        return cursor.fetchone()


@app.get(
    "/api/posee",
    response_model=list[PoseeResponse],
    tags=["Posee"],
)
def obtener_posee():
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT IdConductor1,IdVehiculo1 FROM Posee
               WHERE IdConductor1 IS NOT NULL AND IdVehiculo1 IS NOT NULL"""
        )
        return cursor.fetchall()


@app.get(
    "/api/realiza",
    response_model=list[RealizaResponse],
    tags=["Realiza"],
)
def obtener_realiza():
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT IdConductor2,IdViaje2,IdVehiculo2,Fecha_Realiza,Hora_Realiza
               FROM Realiza
               WHERE IdConductor2 IS NOT NULL AND IdViaje2 IS NOT NULL
                 AND IdVehiculo2 IS NOT NULL"""
        )
        return cursor.fetchall()


@app.get(
    "/api/vehiculos",
    response_model=list[VehiculoResponse],
    tags=["Vehiculo"],
)
def obtener_vehiculos(
    id_conductor: Optional[int] = None,
):
    with db_cursor() as cursor:
        sql = """SELECT v.idVehiculo,p.IdConductor1 AS id_conductor,v.Marca,
                        v.Modelo,v.Placa,v.`Año`,v.Color,v.Capacidad_Pasajeros
                 FROM Vehiculo v JOIN Posee p ON p.IdVehiculo1=v.idVehiculo
                 WHERE p.IdConductor1 IS NOT NULL"""
        params: tuple[Any, ...] = ()
        if id_conductor is not None:
            sql += " AND p.IdConductor1=%s"
            params = (id_conductor,)
        cursor.execute(sql, params)
        return cursor.fetchall()


@app.post(
    "/api/vehiculos",
    status_code=201,
    response_model=VehiculoResponse,
    tags=["Vehiculo"],
)
def registrar_vehiculo(
    veh: VehiculoCreate,
):
    validar_capacidad(veh.Capacidad_Pasajeros, veh.Capacidad_Pasajeros)
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT e.Estado_Cuenta FROM Estudiante e
               JOIN Conductor c ON c.IdConductor=e.NoControl
               WHERE e.NoControl=%s FOR UPDATE""",
            (veh.id_conductor,),
        )
        conductor = cursor.fetchone()
        if not conductor:
            raise HTTPException(status_code=404, detail="Conductor no encontrado.")
        if conductor["Estado_Cuenta"] != "activo":
            raise HTTPException(status_code=403, detail="La cuenta está bloqueada.")
        cursor.execute(
            "SELECT idVehiculo FROM Vehiculo WHERE UPPER(Placa)=UPPER(%s)",
            (veh.Placa.strip(),),
        )
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="Las placas ya están registradas.")
        cursor.execute(
            """INSERT INTO Vehiculo (Placa,Modelo,`Año`,Color,NoSeguro,
                       Capacidad_Pasajeros,Marca)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (
                veh.Placa.strip().upper(),
                veh.Modelo.strip(),
                veh.Año,
                veh.Color.strip(),
                veh.NoSeguro.strip(),
                veh.Capacidad_Pasajeros,
                veh.Marca.strip(),
            ),
        )
        vehicle_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO Posee (IdConductor1,IdVehiculo1) VALUES (%s,%s)",
            (veh.id_conductor, vehicle_id),
        )
        return {
            "idVehiculo": vehicle_id,
            "id_conductor": veh.id_conductor,
            "Marca": veh.Marca,
            "Modelo": veh.Modelo,
            "Placa": veh.Placa.strip().upper(),
            "Año": veh.Año,
            "Color": veh.Color,
            "Capacidad_Pasajeros": veh.Capacidad_Pasajeros,
        }


@app.get(
    "/api/conductores/{id}/vehiculos",
    response_model=list[VehiculoResponse],
    tags=["Vehiculo"],
)
def obtener_vehiculos_conductor(
    id: int,
):
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT v.idVehiculo,p.IdConductor1 AS id_conductor,v.Marca,
                      v.Modelo,v.Placa,v.`Año`,v.Color,v.Capacidad_Pasajeros
               FROM Vehiculo v JOIN Posee p ON p.IdVehiculo1=v.idVehiculo
               WHERE p.IdConductor1=%s""",
            (id,),
        )
        return cursor.fetchall()


def _crear_viaje(cursor: Any, viaje: ViajeCreate) -> dict[str, Any]:
    conductor_id = viaje.id_conductor
    salida_local = normalizar_fecha_hora_local(viaje.fecha_hora_salida)
    cursor.execute(
        """SELECT e.Estado_Cuenta,c.IdConductor FROM Estudiante e
           LEFT JOIN Conductor c ON c.IdConductor=e.NoControl
           WHERE e.NoControl=%s FOR UPDATE""",
        (conductor_id,),
    )
    conductor = cursor.fetchone()
    if not conductor or conductor["IdConductor"] is None:
        raise HTTPException(status_code=404, detail="Conductor no encontrado.")
    if conductor["Estado_Cuenta"] != "activo":
        raise HTTPException(status_code=403, detail="La cuenta está bloqueada.")
    cursor.execute(
        """SELECT v.idVehiculo,v.Capacidad_Pasajeros
           FROM Vehiculo v JOIN Posee p ON p.IdVehiculo1=v.idVehiculo
           WHERE p.IdConductor1=%s AND v.idVehiculo=%s FOR UPDATE""",
        (conductor_id, viaje.id_vehiculo),
    )
    vehiculo = cursor.fetchone()
    if not vehiculo:
        raise HTTPException(
            status_code=409,
            detail="Registra o selecciona uno de tus vehículos para continuar la publicación.",
        )
    cursor.execute(
        """SELECT idHorario,Turno,HoraEntrada,HoraSalida FROM Horario
           ORDER BY HoraEntrada"""
    )
    horarios = cursor.fetchall()
    horarios = [
        {
            **horario,
            "HoraEntrada": _hora_python(horario["HoraEntrada"]),
            "HoraSalida": _hora_python(horario["HoraSalida"]),
        }
        for horario in horarios
    ]
    cursor.execute(
        """SELECT v.Fecha_Hora_Salida
           FROM Viaje v JOIN Realiza r ON r.IdViaje2=v.idViaje
           WHERE r.IdConductor2=%s AND v.Estado IN ('Publicado','Lleno','EnCurso')
             AND v.Fecha_Hora_Salida IS NOT NULL FOR UPDATE""",
        (conductor_id,),
    )
    salidas = [row["Fecha_Hora_Salida"] for row in cursor.fetchall()]
    turno_id = validar_publicacion(
        salida=salida_local,
        capacidad=vehiculo["Capacidad_Pasajeros"],
        lugares=viaje.lugares,
        horarios=horarios,
        viajes_conductor=salidas,
        ahora=ahora_local(),
    )
    cursor.execute(
        """INSERT INTO Viaje
        (Origen,Destino,Precio_Estimado,Asientos_Disponibles,Asientos_Totales,
         Estado,idHorario1,Fecha_Hora_Salida)
        VALUES (%s,%s,%s,%s,%s,'Publicado',%s,%s)""",
        (
            viaje.origen.strip(),
            viaje.destino.strip(),
            viaje.costo,
            viaje.lugares,
            viaje.lugares,
            turno_id,
            salida_local,
        ),
    )
    viaje_id = cursor.lastrowid
    cursor.execute(
        """INSERT INTO Realiza
        (IdConductor2,IdViaje2,IdVehiculo2,Fecha_Realiza,Hora_Realiza)
        VALUES (%s,%s,%s,%s,%s)""",
        (
            conductor_id,
            viaje_id,
            viaje.id_vehiculo,
            salida_local.date(),
            salida_local.time(),
        ),
    )
    return _obtener_viaje(cursor, viaje_id)


def _hora_python(value: Any) -> time:
    if isinstance(value, time):
        return value
    if isinstance(value, timedelta):
        segundos = int(value.total_seconds()) % 86400
        return time(segundos // 3600, (segundos % 3600) // 60, segundos % 60)
    raise HTTPException(status_code=500, detail="Horario de base de datos inválido.")


@app.post(
    "/api/viajes",
    status_code=201,
    response_model=ViajeResponse,
    tags=["Viaje"],
)
def publicar_viaje(
    viaje: ViajeCreate,
):
    with db_cursor() as cursor:
        return _crear_viaje(cursor, viaje)


@app.get(
    "/api/viajes",
    response_model=list[ViajeResponse],
    tags=["Viaje"],
)
def obtener_viajes(
    origen: Optional[str] = Query(default=None, max_length=50),
    destino: Optional[str] = Query(default=None, max_length=50),
    turno: Optional[str] = None,
    fecha: Optional[date] = None,
    solo_disponibles: bool = True,
):
    sql = _viaje_query() + " WHERE r.IdViaje2 IS NOT NULL"
    params: list[Any] = []
    if origen:
        sql += " AND LOWER(v.Origen) LIKE LOWER(%s)"
        params.append(f"%{origen.strip()}%")
    if destino:
        sql += " AND LOWER(v.Destino) LIKE LOWER(%s)"
        params.append(f"%{destino.strip()}%")
    if turno:
        if turno.lower() not in ("matutino", "vespertino"):
            raise HTTPException(status_code=422, detail="Turno debe ser Matutino o Vespertino.")
        sql += " AND LOWER(h.Turno)=LOWER(%s)"
        params.append(turno)
    if fecha:
        sql += " AND DATE(v.Fecha_Hora_Salida)=%s"
        params.append(fecha)
    if solo_disponibles:
        sql += """ AND v.Estado='Publicado' AND v.Asientos_Disponibles>0
                   AND v.Fecha_Hora_Salida IS NOT NULL"""
    sql += " ORDER BY v.Fecha_Hora_Salida"
    with db_cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()


@app.get(
    "/api/viajes/{id}",
    response_model=ViajeResponse,
    tags=["Viaje"],
)
def obtener_viaje(id: int):
    with db_cursor() as cursor:
        viaje = _obtener_viaje(cursor, id)
        if viaje["idConductor"] is None or viaje["idVehiculo"] is None:
            raise HTTPException(
                status_code=409,
                detail="El viaje no tiene una relación Realiza completa.",
            )
        return viaje


@app.get(
    "/api/conductores/{id}/viajes",
    response_model=list[ViajeResponse],
    tags=["Viaje"],
)
def obtener_viajes_conductor(
    id: int,
):
    with db_cursor() as cursor:
        cursor.execute(
            _viaje_query() + " WHERE r.IdConductor2=%s ORDER BY v.Fecha_Hora_Salida",
            (id,),
        )
        return cursor.fetchall()


@app.get(
    "/api/solicitudes",
    response_model=list[ReservaResponse],
    tags=["Reservas"],
)
def obtener_solicitudes():
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT s.idSolicitud,s.IdPasajero1,
                      CONCAT(e.Nombre_Estudiante,' ',e.Apellido_Estudiante) AS Nombre_Pasajero,
                      s.IdViaje1,s.Lugares_Solicitados,s.Fecha,s.Hora,
                      s.Estado_Reserva,s.Califica
               FROM Solicita s
               LEFT JOIN Estudiante e ON e.NoControl=s.IdPasajero1
               ORDER BY s.Fecha DESC,s.Hora DESC"""
        )
        return cursor.fetchall()


def _reserva_query() -> str:
    return """SELECT s.idSolicitud,s.IdPasajero1,
        CONCAT(e.Nombre_Estudiante,' ',LEFT(e.Apellido_Estudiante,1),'.')
            AS Nombre_Pasajero,
        s.IdViaje1,s.Lugares_Solicitados,s.Fecha,s.Hora,s.Estado_Reserva,s.Califica
        FROM Solicita s
        LEFT JOIN Estudiante e ON e.NoControl=s.IdPasajero1"""


def _obtener_reserva(
    cursor: Any, id_solicitud: int, bloquear: bool = True
) -> dict[str, Any]:
    sufijo_bloqueo = " FOR UPDATE" if bloquear else ""
    cursor.execute(
        _reserva_query() + " WHERE s.idSolicitud=%s LIMIT 1" + sufijo_bloqueo,
        (id_solicitud,),
    )
    reserva = cursor.fetchone()
    if not reserva:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    return reserva


def _liberar_lugares(cursor: Any, id_viaje: int, lugares: int):
    cursor.execute(
        """UPDATE Viaje
           SET Estado=IF(Estado='Lleno' AND
                         Asientos_Disponibles+%s>0,'Publicado',Estado),
               Asientos_Disponibles=LEAST(Asientos_Totales,
                                          Asientos_Disponibles+%s)
           WHERE idViaje=%s AND Estado IN ('Publicado','Lleno')""",
        (lugares, lugares, id_viaje),
    )


@app.post(
    "/api/reservas",
    status_code=201,
    response_model=ReservaResponse,
    tags=["Reservas"],
)
def crear_reserva(
    reserva: ReservaCreate,
):
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT e.Estado_Cuenta,p.IdPasajero1
               FROM Estudiante e JOIN Pasajero p ON p.IdPasajero1=e.NoControl
               WHERE e.NoControl=%s FOR UPDATE""",
            (reserva.IdPasajero1,),
        )
        pasajero = cursor.fetchone()
        if not pasajero:
            raise HTTPException(status_code=403, detail="La cuenta no tiene rol pasajero.")
        cursor.execute(
            """SELECT idViaje,Estado,Asientos_Disponibles,Asientos_Totales,
                      Fecha_Hora_Salida
               FROM Viaje WHERE idViaje=%s FOR UPDATE""",
            (reserva.IdViaje1,),
        )
        viaje = cursor.fetchone()
        if not viaje:
            raise HTTPException(status_code=404, detail="Viaje no encontrado.")
        if viaje["Fecha_Hora_Salida"] is None:
            raise HTTPException(
                status_code=409,
                detail="El viaje no tiene una fecha de salida válida.",
            )
        if viaje["Fecha_Hora_Salida"] <= ahora_local():
            raise HTTPException(status_code=409, detail="La salida del viaje ya pasó.")
        cursor.execute(
            """SELECT idSolicitud FROM Solicita
               WHERE IdPasajero1=%s AND IdViaje1=%s
                 AND Estado_Reserva IN ('pendiente','confirmada')
               LIMIT 1 FOR UPDATE""",
            (reserva.IdPasajero1, reserva.IdViaje1),
        )
        duplicada = cursor.fetchone() is not None
        validar_reserva(
            estado_viaje=viaje["Estado"],
            disponibles=viaje["Asientos_Disponibles"],
            lugares=reserva.Lugares_Solicitados,
            reserva_activa=duplicada,
            estado_cuenta=pasajero["Estado_Cuenta"],
        )
        cursor.execute(
            """UPDATE Viaje
               SET Estado=IF(Asientos_Disponibles-%s=0,'Lleno','Publicado'),
                   Asientos_Disponibles=Asientos_Disponibles-%s
               WHERE idViaje=%s AND Estado='Publicado'
                 AND Asientos_Disponibles >= %s""",
            (
                reserva.Lugares_Solicitados,
                reserva.Lugares_Solicitados,
                reserva.IdViaje1,
                reserva.Lugares_Solicitados,
            ),
        )
        if cursor.rowcount != 1:
            raise HTTPException(
                status_code=409,
                detail="El viaje se llenó mientras procesábamos tu solicitud.",
            )
        ahora = ahora_local()
        cursor.execute(
            """INSERT INTO Solicita
            (IdPasajero1,Fecha,Hora,Lugares_Solicitados,Estado_Reserva,Califica,IdViaje1)
            VALUES (%s,%s,%s,%s,'pendiente',0,%s)""",
            (
                reserva.IdPasajero1,
                ahora.date(),
                ahora.time(),
                reserva.Lugares_Solicitados,
                reserva.IdViaje1,
            ),
        )
        solicitud_id = cursor.lastrowid
        cursor.execute(
            "SELECT IdConductor2 FROM Realiza WHERE IdViaje2=%s LIMIT 1",
            (reserva.IdViaje1,),
        )
        conductor = cursor.fetchone()
        if conductor and conductor["IdConductor2"]:
            _notificar_estudiante(
                cursor,
                conductor["IdConductor2"],
                "Nueva solicitud",
                f"El pasajero {reserva.IdPasajero1} solicitó lugares en el viaje {reserva.IdViaje1}.",
            )
        return _obtener_reserva(cursor, solicitud_id)


def _responder_reserva(
    id_solicitud: int,
    accion: str,
) -> dict[str, Any]:
    with db_cursor() as cursor:
        reserva = _obtener_reserva(cursor, id_solicitud, bloquear=False)
        cursor.execute(
            """SELECT v.Estado,v.Asientos_Totales,r.IdConductor2
               FROM Viaje v JOIN Realiza r ON r.IdViaje2=v.idViaje
               WHERE v.idViaje=%s FOR UPDATE""",
            (reserva["IdViaje1"],),
        )
        viaje = cursor.fetchone()
        if not viaje:
            raise HTTPException(status_code=404, detail="Viaje no encontrado.")
        reserva = _obtener_reserva(cursor, id_solicitud)
        if reserva["Estado_Reserva"] != "pendiente":
            raise HTTPException(status_code=409, detail="La solicitud ya fue atendida.")
        if viaje["Estado"] in ("EnCurso", "Cancelado", "Finalizado"):
            raise HTTPException(status_code=409, detail="El viaje ya no acepta cambios.")
        if accion == "rechazada":
            _liberar_lugares(
                cursor, reserva["IdViaje1"], reserva["Lugares_Solicitados"]
            )
        cursor.execute(
            "UPDATE Solicita SET Estado_Reserva=%s WHERE idSolicitud=%s",
            (accion, id_solicitud),
        )
        texto = "confirmada" if accion == "confirmada" else "rechazada"
        _notificar_estudiante(
            cursor,
            reserva["IdPasajero1"],
            "Respuesta a tu solicitud",
            f"Tu solicitud para el viaje {reserva['IdViaje1']} fue {texto}.",
        )
        return _obtener_reserva(cursor, id_solicitud)


@app.post(
    "/api/reservas/{id}/confirmar",
    response_model=ReservaResponse,
    tags=["Reservas"],
)
def confirmar_reserva(
    id: int,
):
    return _responder_reserva(id, "confirmada")


@app.post(
    "/api/reservas/{id}/rechazar",
    response_model=ReservaResponse,
    tags=["Reservas"],
)
def rechazar_reserva(
    id: int,
):
    return _responder_reserva(id, "rechazada")


@app.post(
    "/api/reservas/{id}/cancelar",
    response_model=ReservaResponse,
    tags=["Reservas"],
)
def cancelar_reserva(
    id: int,
):
    with db_cursor() as cursor:
        reserva = _obtener_reserva(cursor, id, bloquear=False)
        cursor.execute(
            """SELECT Estado,Fecha_Hora_Salida FROM Viaje
               WHERE idViaje=%s FOR UPDATE""",
            (reserva["IdViaje1"],),
        )
        viaje = cursor.fetchone()
        if not viaje:
            raise HTTPException(status_code=404, detail="Viaje no encontrado.")
        reserva = _obtener_reserva(cursor, id)
        if viaje["Estado"] == "EnCurso":
            raise HTTPException(status_code=409, detail="El viaje ya está en curso.")
        if viaje["Estado"] in ("Cancelado", "Finalizado"):
            raise HTTPException(status_code=409, detail="El viaje ya no acepta cambios.")
        if reserva["Estado_Reserva"] not in ("pendiente", "confirmada"):
            raise HTTPException(status_code=409, detail="La reserva no está activa.")
        if viaje["Fecha_Hora_Salida"] is None:
            raise HTTPException(
                status_code=409,
                detail="No es posible cancelar: el viaje no tiene fecha de salida.",
            )
        validar_cancelacion_reserva(
            viaje["Fecha_Hora_Salida"], ahora=ahora_local()
        )
        _liberar_lugares(
            cursor, reserva["IdViaje1"], reserva["Lugares_Solicitados"]
        )
        cursor.execute(
            "UPDATE Solicita SET Estado_Reserva='cancelada' WHERE idSolicitud=%s",
            (id,),
        )
        cursor.execute(
            "SELECT IdConductor2 FROM Realiza WHERE IdViaje2=%s LIMIT 1",
            (reserva["IdViaje1"],),
        )
        conductor = cursor.fetchone()
        if conductor and conductor["IdConductor2"]:
            _notificar_estudiante(
                cursor,
                conductor["IdConductor2"],
                "Reserva cancelada",
                f"El pasajero {reserva['IdPasajero1']} canceló su reserva.",
            )
        _notificar_estudiante(
            cursor,
            reserva["IdPasajero1"],
            "Reserva cancelada",
            "Tu reserva fue cancelada y los lugares quedaron disponibles.",
        )
        return _obtener_reserva(cursor, id)


@app.get(
    "/api/pasajeros/{id}/reservas",
    response_model=list[ReservaResponse],
    tags=["Reservas"],
)
def obtener_reservas_pasajero(
    id: int,
):
    with db_cursor() as cursor:
        cursor.execute(
            _reserva_query() + " WHERE s.IdPasajero1=%s ORDER BY s.Fecha DESC,s.Hora DESC",
            (id,),
        )
        return cursor.fetchall()


@app.get(
    "/api/viajes/{id}/reservas",
    response_model=list[ReservaResponse],
    tags=["Reservas"],
)
def obtener_reservas_viaje(
    id: int,
    estado: Optional[str] = None,
):
    sql = _reserva_query() + " WHERE s.IdViaje1=%s"
    params: list[Any] = [id]
    if estado:
        permitidos = {"pendiente", "confirmada", "rechazada", "cancelada"}
        if estado not in permitidos:
            raise HTTPException(status_code=422, detail="Estado de reserva inválido.")
        sql += " AND s.Estado_Reserva=%s"
        params.append(estado)
    sql += " ORDER BY s.Fecha,s.Hora"
    with db_cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()


def _cambiar_estado_viaje(
    id_viaje: int,
    accion: str,
    actor: dict[str, Any] | None = None,
    como_admin: bool = False,
) -> dict[str, Any]:
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT r.IdConductor2 FROM Realiza r
               WHERE r.IdViaje2=%s LIMIT 1""",
            (id_viaje,),
        )
        relacion = cursor.fetchone()
        if not relacion:
            raise HTTPException(status_code=404, detail="Viaje no encontrado.")
        if accion == "cancelar":
            _cancelar_viaje(
                cursor,
                id_viaje,
                "Viaje cancelado",
                "El viaje fue cancelado. Tu reserva quedó cancelada y los lugares liberados.",
            )
        else:
            cursor.execute(
                "SELECT Estado FROM Viaje WHERE idViaje=%s FOR UPDATE",
                (id_viaje,),
            )
            viaje = cursor.fetchone()
            estado = validar_transicion_viaje(viaje["Estado"], accion)
            cursor.execute(
                "UPDATE Viaje SET Estado=%s WHERE idViaje=%s",
                (estado, id_viaje),
            )
            cursor.execute(
                """SELECT IdPasajero1 FROM Solicita
                   WHERE IdViaje1=%s AND Estado_Reserva IN ('pendiente','confirmada')""",
                (id_viaje,),
            )
            for pasajero in cursor.fetchall():
                _notificar_estudiante(
                    cursor,
                    pasajero["IdPasajero1"],
                    "Estado del viaje actualizado",
                    f"El viaje {id_viaje} ahora está en estado {estado}.",
                )
        return _obtener_viaje(cursor, id_viaje)


@app.post("/api/viajes/{id}/iniciar", response_model=ViajeResponse, tags=["Viaje"])
def iniciar_viaje(id: int):
    return _cambiar_estado_viaje(id, "iniciar")


@app.post("/api/viajes/{id}/finalizar", response_model=ViajeResponse, tags=["Viaje"])
def finalizar_viaje(id: int):
    return _cambiar_estado_viaje(id, "finalizar")


@app.post("/api/viajes/{id}/cancelar", response_model=ViajeResponse, tags=["Viaje"])
def cancelar_viaje(id: int):
    return _cambiar_estado_viaje(id, "cancelar")


@app.post(
    "/api/usuarios/{no_control}/bloquear",
    response_model=MensajeResponse,
    tags=["Administrador"],
)
def bloquear_usuario(
    no_control: int,
    datos: BloqueoRequest,
):
    with db_cursor() as cursor:
        cursor.execute(
            "SELECT Estado_Cuenta FROM Estudiante WHERE NoControl=%s FOR UPDATE",
            (no_control,),
        )
        estudiante = cursor.fetchone()
        if not estudiante:
            raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
        cursor.execute(
            """UPDATE Estudiante SET Estado_Cuenta='bloqueado',
               Bloqueado_Hasta=NULL WHERE NoControl=%s""",
            (no_control,),
        )
        cursor.execute(
            """INSERT INTO Bitacora_Admin
               (id_Administrador,NoControl_Afectado,Accion)
               VALUES (%s,%s,'bloqueo')""",
            (datos.id_administrador, no_control),
        )
        cursor.execute(
            "SELECT idViaje FROM Realiza WHERE IdConductor2=%s",
            (no_control,),
        )
        for viaje in cursor.fetchall():
            cursor.execute(
                "SELECT Estado FROM Viaje WHERE idViaje=%s",
                (viaje["idViaje"],),
            )
            estado = cursor.fetchone()
            if estado and estado["Estado"] in ("Publicado", "Lleno"):
                _cancelar_viaje(
                    cursor,
                    viaje["idViaje"],
                    "Viaje cancelado",
                    "El viaje fue cancelado porque la cuenta del conductor fue bloqueada.",
                )
    return {"message": "Cuenta bloqueada; se cancelaron sus viajes publicados."}


@app.post(
    "/api/usuarios/{no_control}/desbloquear",
    response_model=MensajeResponse,
    tags=["Administrador"],
)
def desbloquear_usuario(
    no_control: int,
    datos: BloqueoRequest,
):
    with db_cursor() as cursor:
        cursor.execute(
            "SELECT NoControl FROM Estudiante WHERE NoControl=%s FOR UPDATE",
            (no_control,),
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
        cursor.execute(
            """UPDATE Estudiante SET Estado_Cuenta='activo',
               Intentos_Fallidos=0,Bloqueado_Hasta=NULL WHERE NoControl=%s""",
            (no_control,),
        )
        cursor.execute(
            """INSERT INTO Bitacora_Admin
               (id_Administrador,NoControl_Afectado,Accion)
               VALUES (%s,%s,'desbloqueo')""",
            (datos.id_administrador, no_control),
        )
    return {"message": "Cuenta desbloqueada."}


@app.post(
    "/api/calificaciones",
    status_code=201,
    response_model=CalificacionResponse,
    tags=["Calificaciones"],
)
def crear_calificacion(
    cal: CalificacionCreate,
):
    if cal.Rol_Evaluado not in ("conductor", "pasajero"):
        raise HTTPException(status_code=422, detail="Rol_Evaluado debe ser conductor o pasajero.")
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT v.Estado,r.IdConductor2
               FROM Viaje v JOIN Realiza r ON r.IdViaje2=v.idViaje
               WHERE v.idViaje=%s FOR UPDATE""",
            (cal.idViaje1,),
        )
        viaje = cursor.fetchone()
        if not viaje:
            raise HTTPException(status_code=404, detail="Viaje no encontrado.")
        if viaje["Estado"] != "Finalizado":
            raise HTTPException(
                status_code=409,
                detail="Solo se pueden calificar viajes finalizados.",
            )
        if cal.Rol_Evaluado == "conductor":
            cursor.execute(
                """SELECT idSolicitud FROM Solicita
                   WHERE IdViaje1=%s AND IdPasajero1=%s
                     AND Estado_Reserva='confirmada' LIMIT 1""",
                (cal.idViaje1, cal.NoControl_Evaluador),
            )
            evaluador_valido = cursor.fetchone() is not None
            participante = (
                evaluador_valido
                and cal.NoControl_Evaluado == viaje["IdConductor2"]
                and cal.NoControl_Evaluador != viaje["IdConductor2"]
            )
        else:
            if cal.NoControl_Evaluador == cal.NoControl_Evaluado:
                raise HTTPException(status_code=400, detail="No puedes calificarte a ti mismo.")
            cursor.execute(
                """SELECT idSolicitud FROM Solicita
                   WHERE IdViaje1=%s AND IdPasajero1=%s
                     AND Estado_Reserva='confirmada' LIMIT 1""",
                (cal.idViaje1, cal.NoControl_Evaluado),
            )
            pasajero_valido = cursor.fetchone() is not None
            cursor.execute(
                """SELECT idSolicitud FROM Solicita
                   WHERE IdViaje1=%s AND IdPasajero1=%s
                     AND Estado_Reserva='confirmada' LIMIT 1""",
                (cal.idViaje1, cal.NoControl_Evaluador),
            )
            evaluador_valido = cursor.fetchone() is not None
            participante = pasajero_valido and evaluador_valido
        if not participante:
            raise HTTPException(
                status_code=403,
                detail="Solo participantes pueden calificarse entre sí.",
            )
        cursor.execute(
            """SELECT idCalificacion FROM Calificacion
               WHERE idViaje1=%s AND NoControl_Evaluador=%s
                 AND NoControl_Evaluado=%s LIMIT 1""",
            (cal.idViaje1, cal.NoControl_Evaluador, cal.NoControl_Evaluado),
        )
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="Ya calificaste a esta persona en este viaje.")
        cursor.execute(
            """INSERT INTO Calificacion
            (idViaje1,NoControl_Evaluador,NoControl_Evaluado,Rol_Evaluado,
             Puntuacion,Comentario)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            (
                cal.idViaje1,
                cal.NoControl_Evaluador,
                cal.NoControl_Evaluado,
                cal.Rol_Evaluado,
                cal.Puntuacion,
                cal.Comentario,
            ),
        )
        cal_id = cursor.lastrowid
        cursor.execute(
            """SELECT c.idCalificacion,c.idViaje1,c.NoControl_Evaluador,
               c.NoControl_Evaluado,c.Rol_Evaluado,c.Puntuacion,c.Comentario,
               c.Fecha_Registro,
               (SELECT AVG(x.Puntuacion) FROM Calificacion x
                WHERE x.NoControl_Evaluado=c.NoControl_Evaluado) AS Promedio
               FROM Calificacion c WHERE c.idCalificacion=%s""",
            (cal_id,),
        )
        return cursor.fetchone()


@app.get(
    "/api/calificaciones/{no_control}",
    response_model=list[CalificacionResponse],
    tags=["Calificaciones"],
)
def obtener_calificaciones_usuario(
    no_control: int,
):
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT c.idCalificacion,c.idViaje1,c.NoControl_Evaluador,
                      c.NoControl_Evaluado,c.Rol_Evaluado,c.Puntuacion,
                      c.Comentario,c.Fecha_Registro,
                      AVG(c.Puntuacion) OVER (
                        PARTITION BY c.NoControl_Evaluado
                      ) AS Promedio
               FROM Calificacion c
               WHERE c.NoControl_Evaluado=%s
               ORDER BY c.Fecha_Registro DESC""",
            (no_control,),
        )
        return cursor.fetchall()


@app.post(
    "/api/reportes",
    status_code=201,
    response_model=ReporteResponse,
    tags=["Reportes"],
)
def crear_reporte(
    rep: ReporteCreate,
):
    if rep.NoControl_Reportado == rep.NoControl_Reportante:
        raise HTTPException(status_code=400, detail="No puedes reportarte a ti mismo.")
    if not rep.Motivo.strip() or not rep.Descripcion.strip():
        raise HTTPException(status_code=422, detail="El motivo y la descripción son obligatorios.")
    with db_cursor() as cursor:
        if rep.NoControl_Reportado is not None:
            cursor.execute(
                "SELECT Reportes FROM Estudiante WHERE NoControl=%s FOR UPDATE",
                (rep.NoControl_Reportado,),
            )
            reportado = cursor.fetchone()
            if not reportado:
                raise HTTPException(status_code=404, detail="Usuario reportado no encontrado.")
        cursor.execute(
            """INSERT INTO Reporte
            (NoControl_Reportante,NoControl_Reportado,idViaje1,Motivo,Descripcion)
            VALUES (%s,%s,%s,%s,%s)""",
            (
                rep.NoControl_Reportante,
                rep.NoControl_Reportado,
                rep.idViaje1,
                rep.Motivo.strip(),
                rep.Descripcion.strip(),
            ),
        )
        reporte_id = cursor.lastrowid
        if rep.NoControl_Reportado is not None:
            cursor.execute(
                """UPDATE Estudiante SET Reportes=Reportes+1
                   WHERE NoControl=%s""",
                (rep.NoControl_Reportado,),
            )
            cursor.execute(
                """SELECT Reportes FROM Estudiante WHERE NoControl=%s""",
                (rep.NoControl_Reportado,),
            )
            total = cursor.fetchone()["Reportes"]
            if total == 5:
                cursor.execute(
                    """UPDATE Estudiante SET Estado_Cuenta='bloqueado',
                       Bloqueado_Hasta=NULL WHERE NoControl=%s""",
                    (rep.NoControl_Reportado,),
                )
                _notificar_admins(
                    cursor,
                    "Usuario sancionado",
                    f"El usuario {rep.NoControl_Reportado} llegó a cinco reportes.",
                )
                cursor.execute(
                    "SELECT idViaje FROM Realiza WHERE IdConductor2=%s",
                    (rep.NoControl_Reportado,),
                )
                for viaje in cursor.fetchall():
                    cursor.execute(
                        "SELECT Estado FROM Viaje WHERE idViaje=%s",
                        (viaje["idViaje"],),
                    )
                    estado = cursor.fetchone()
                    if estado and estado["Estado"] in ("Publicado", "Lleno"):
                        _cancelar_viaje(
                            cursor,
                            viaje["idViaje"],
                            "Viaje cancelado",
                            "El viaje fue cancelado porque el conductor alcanzó el límite de reportes.",
                        )
        cursor.execute(
            """SELECT idReporte,NoControl_Reportante,NoControl_Reportado,idViaje1,
                      Motivo,Descripcion,Estado_Reporte,Fecha_Reporte
               FROM Reporte WHERE idReporte=%s""",
            (reporte_id,),
        )
        return cursor.fetchone()


@app.get(
    "/api/reportes",
    response_model=list[ReporteResponse],
    tags=["Reportes"],
)
def obtener_reportes():
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT idReporte,NoControl_Reportante,NoControl_Reportado,idViaje1,
                      Motivo,Descripcion,Estado_Reporte,Fecha_Reporte
               FROM Reporte ORDER BY Fecha_Reporte DESC"""
        )
        return cursor.fetchall()


@app.get(
    "/api/notificaciones/admin/{id}",
    response_model=list[NotificacionResponse],
    tags=["Notificaciones"],
)
def obtener_notificaciones_admin(
    id: int,
):
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT idNotificacion,NoControl_Destinatario,
                      id_Administrador_Destinatario,Titulo,Mensaje,Leida,Fecha_Creacion
               FROM Notificacion WHERE id_Administrador_Destinatario=%s
               ORDER BY Fecha_Creacion DESC""",
            (id,),
        )
        return cursor.fetchall()


@app.get(
    "/api/notificaciones/{no_control}",
    response_model=list[NotificacionResponse],
    tags=["Notificaciones"],
)
def obtener_notificaciones(
    no_control: int,
):
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT idNotificacion,NoControl_Destinatario,
                      id_Administrador_Destinatario,Titulo,Mensaje,Leida,Fecha_Creacion
               FROM Notificacion WHERE NoControl_Destinatario=%s
               ORDER BY Fecha_Creacion DESC""",
            (no_control,),
        )
        return cursor.fetchall()


@app.post(
    "/api/notificaciones/{id}/leer",
    response_model=NotificacionResponse,
    tags=["Notificaciones"],
)
def marcar_notificacion_leida(
    id: int,
):
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT idNotificacion,NoControl_Destinatario,
                      id_Administrador_Destinatario,Titulo,Mensaje,Leida,Fecha_Creacion
               FROM Notificacion WHERE idNotificacion=%s FOR UPDATE""",
            (id,),
        )
        notificacion = cursor.fetchone()
        if not notificacion:
            raise HTTPException(status_code=404, detail="Notificación no encontrada.")
        cursor.execute(
            "UPDATE Notificacion SET Leida=1 WHERE idNotificacion=%s",
            (id,),
        )
        notificacion["Leida"] = 1
        return notificacion


@app.get(
    "/api/usuarios/{id}/historial",
    response_model=list[ViajeResponse],
    tags=["Viaje"],
)
def historial_usuario(
    id: int,
):
    with db_cursor() as cursor:
        cursor.execute(
            _viaje_query()
            + """ WHERE v.Estado='Finalizado'
                AND (r.IdConductor2=%s OR EXISTS (
                    SELECT 1 FROM Solicita s
                    WHERE s.IdViaje1=v.idViaje AND s.IdPasajero1=%s
                      AND s.Estado_Reserva='confirmada'
                ))
                ORDER BY v.Fecha_Hora_Salida DESC""",
            (id, id),
        )
        return cursor.fetchall()


@app.get(
    "/api/admin/viajes",
    response_model=list[ViajeResponse],
    tags=["Administrador"],
)
def admin_viajes(
    estado: Optional[str] = None,
    fecha: Optional[date] = None,
    conductor: Optional[int] = None,
):
    sql = _viaje_query() + " WHERE 1=1"
    params: list[Any] = []
    if estado:
        estados_validos = {"Publicado", "Lleno", "EnCurso", "Finalizado", "Cancelado"}
        if estado not in estados_validos:
            raise HTTPException(status_code=422, detail="Estado de viaje inválido.")
        sql += " AND v.Estado=%s"
        params.append(estado)
    if fecha:
        sql += " AND DATE(v.Fecha_Hora_Salida)=%s"
        params.append(fecha)
    if conductor is not None:
        sql += " AND r.IdConductor2=%s"
        params.append(conductor)
    sql += " ORDER BY v.Fecha_Hora_Salida DESC"
    with db_cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()


@app.get(
    "/api/admin/reservas",
    response_model=list[ReservaResponse],
    tags=["Administrador"],
)
def admin_reservas(
    estado: Optional[str] = None,
    fecha: Optional[date] = None,
    conductor: Optional[int] = None,
):
    sql = (
        _reserva_query()
        + """ JOIN Viaje v ON v.idViaje=s.IdViaje1
             LEFT JOIN Realiza r ON r.IdViaje2=v.idViaje
             WHERE 1=1"""
    )
    params: list[Any] = []
    if estado:
        estados_validos = {"pendiente", "confirmada", "rechazada", "cancelada"}
        if estado not in estados_validos:
            raise HTTPException(status_code=422, detail="Estado de reserva inválido.")
        sql += " AND s.Estado_Reserva=%s"
        params.append(estado)
    if fecha:
        sql += " AND DATE(v.Fecha_Hora_Salida)=%s"
        params.append(fecha)
    if conductor is not None:
        sql += " AND r.IdConductor2=%s"
        params.append(conductor)
    sql += " ORDER BY v.Fecha_Hora_Salida DESC,s.Fecha DESC,s.Hora DESC"
    with db_cursor() as cursor:
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()


@app.post(
    "/api/admin/viajes/{id}/cancelar",
    response_model=ViajeResponse,
    tags=["Administrador"],
)
def admin_cancelar_viaje(
    id: int,
):
    return _cambiar_estado_viaje(id, "cancelar", como_admin=True)


@app.get(
    "/api/admin/estadisticas-semanales",
    response_model=list[SemanaResponse],
    tags=["Administrador"],
)
def estadisticas_semanales():
    with db_cursor() as cursor:
        cursor.execute(
            """SELECT CONCAT(LEFT(YEARWEEK(Fecha_Hora_Salida,3),4),'-W',
                             LPAD(MOD(YEARWEEK(Fecha_Hora_Salida,3),100),2,'0')) AS semana,
                      COUNT(*) AS viajes
               FROM Viaje
               WHERE Fecha_Hora_Salida >= DATE_SUB(CURDATE(),INTERVAL 12 WEEK)
               GROUP BY YEARWEEK(Fecha_Hora_Salida,3)
               ORDER BY YEARWEEK(Fecha_Hora_Salida,3)"""
        )
        por_semana = {
            fila["semana"]: {"semana": fila["semana"], "viajes": fila["viajes"], "reservas": 0}
            for fila in cursor.fetchall()
        }
        cursor.execute(
            """SELECT CONCAT(LEFT(YEARWEEK(v.Fecha_Hora_Salida,3),4),'-W',
                             LPAD(MOD(YEARWEEK(v.Fecha_Hora_Salida,3),100),2,'0')) AS semana,
                      COUNT(s.idSolicitud) AS reservas
               FROM Viaje v
               LEFT JOIN Solicita s ON s.IdViaje1=v.idViaje
               WHERE v.Fecha_Hora_Salida >= DATE_SUB(CURDATE(),INTERVAL 12 WEEK)
               GROUP BY YEARWEEK(v.Fecha_Hora_Salida,3)
               ORDER BY YEARWEEK(v.Fecha_Hora_Salida,3)"""
        )
        for fila in cursor.fetchall():
            semana = fila["semana"]
            por_semana.setdefault(
                semana, {"semana": semana, "viajes": 0, "reservas": 0}
            )
            por_semana[semana]["reservas"] = fila["reservas"]
        return [por_semana[clave] for clave in sorted(por_semana)]
