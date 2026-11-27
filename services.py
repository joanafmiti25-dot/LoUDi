"""Reglas de dominio independientes de FastAPI y MySQL."""

import hashlib
import hmac
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


class ReglaNegocioError(Exception):
    def __init__(self, mensaje: str, status_code: int = 400):
        super().__init__(mensaje)
        self.status_code = status_code


ZONA_HORARIA_UTSJR = ZoneInfo("America/Mexico_City")


def normalizar_fecha_hora_local(fecha_hora: datetime) -> datetime:
    """Interpreta fechas con zona y las convierte a la hora local de la UTSJR."""
    if fecha_hora.tzinfo is None:
        return fecha_hora
    return fecha_hora.astimezone(ZONA_HORARIA_UTSJR).replace(tzinfo=None)


def ahora_local(ahora: datetime | None = None) -> datetime:
    if ahora is not None:
        return normalizar_fecha_hora_local(ahora)
    return datetime.now(ZONA_HORARIA_UTSJR).replace(tzinfo=None)


def validar_correo(correo: str, dominio: str) -> str:
    normalizado = correo.strip().lower()
    if not normalizado.endswith(dominio.strip().lower()):
        raise ReglaNegocioError(f"Usa tu correo institucional {dominio}.", 422)
    if normalizado.count("@") != 1 or normalizado.startswith("@"):
        raise ReglaNegocioError("El correo institucional no es válido.", 422)
    return normalizado


def validar_contrasena(contrasena: str) -> None:
    if len(contrasena) < 8:
        raise ReglaNegocioError(
            "La contraseña debe tener al menos 8 caracteres.", 422
        )


def hash_contrasena(contrasena: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derivada = hashlib.pbkdf2_hmac(
        "sha256", contrasena.encode("utf-8"), salt, 310_000
    )
    return f"pbkdf2_sha256$310000${salt.hex()}${derivada.hex()}"


def verificar_contrasena(contrasena: str, almacenada: str | None) -> bool:
    if not almacenada:
        return False
    try:
        algoritmo, iteraciones, salt_hex, hash_hex = almacenada.split("$", 3)
        if algoritmo != "pbkdf2_sha256":
            return False
        calculada = hashlib.pbkdf2_hmac(
            "sha256",
            contrasena.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iteraciones),
        ).hex()
        return hmac.compare_digest(calculada, hash_hex)
    except (ValueError, TypeError):
        return False


def token_sesion() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return token, digest


def validar_capacidad(capacidad: int, lugares: int) -> None:
    if capacidad < 1 or capacidad > 4:
        raise ReglaNegocioError(
            "La capacidad del vehículo debe ser de 1 a 4 pasajeros.", 422
        )
    if lugares < 1 or lugares > capacidad:
        raise ReglaNegocioError(
            "Los lugares ofrecidos no pueden superar la capacidad del vehículo.",
            422,
        )


def validar_salida_futura(salida: datetime, ahora: datetime | None = None) -> None:
    salida_local = normalizar_fecha_hora_local(salida)
    if salida_local <= ahora_local(ahora):
        raise ReglaNegocioError(
            "La fecha y hora de salida deben ser futuras.", 422
        )


def obtener_turno(hora_salida: time, horarios: list[dict]) -> tuple[int, str]:
    segundos = (
        hora_salida.hour * 3600 + hora_salida.minute * 60 + hora_salida.second
    )
    for horario in horarios:
        inicio = horario["HoraEntrada"]
        fin = horario["HoraSalida"]
        nombre = str(horario["Turno"])
        inicio_seg = inicio.hour * 3600 + inicio.minute * 60 + inicio.second
        fin_seg = fin.hour * 3600 + fin.minute * 60 + fin.second
        dentro = (
            inicio_seg <= segundos < fin_seg
            if inicio_seg <= fin_seg
            else segundos >= inicio_seg or segundos < fin_seg
        )
        if dentro and nombre.lower() in ("matutino", "vespertino"):
            return horario["idHorario"], nombre
    raise ReglaNegocioError(
        "La hora de salida no pertenece a un turno configurado.", 422
    )


def validar_publicacion(
    *,
    salida: datetime,
    capacidad: int,
    lugares: int,
    horarios: list[dict],
    viajes_conductor: list[datetime],
    ahora: datetime | None = None,
) -> int:
    salida = normalizar_fecha_hora_local(salida)
    validar_salida_futura(salida, ahora)
    validar_capacidad(capacidad, lugares)
    turno_id, _ = obtener_turno(salida.time(), horarios)
    momento = ahora_local(ahora)
    if any(
        viaje > momento and abs((viaje - salida).total_seconds()) < 2 * 3600
        for viaje in viajes_conductor
    ):
        raise ReglaNegocioError(
            "Ya tienes otro viaje a menos de dos horas de esa salida.", 409
        )
    return turno_id


def validar_reserva(
    *,
    estado_viaje: str,
    disponibles: int,
    lugares: int,
    reserva_activa: bool,
    estado_cuenta: str,
) -> None:
    if estado_cuenta != "activo":
        raise ReglaNegocioError("La cuenta está bloqueada.", 403)
    if estado_viaje == "EnCurso":
        raise ReglaNegocioError("El viaje ya está en curso.", 409)
    if estado_viaje != "Publicado":
        raise ReglaNegocioError(
            "El viaje no está publicado o no acepta reservas.", 409
        )
    if reserva_activa:
        raise ReglaNegocioError(
            "Ya tienes una reserva activa para este viaje.", 409
        )
    if lugares < 1 or disponibles < lugares:
        raise ReglaNegocioError("No hay suficientes lugares disponibles.", 409)


def validar_cancelacion_reserva(
    salida: datetime, ahora: datetime | None = None
) -> None:
    salida_local = normalizar_fecha_hora_local(salida)
    if salida_local - ahora_local(ahora) < timedelta(hours=1):
        raise ReglaNegocioError(
            "La reserva solo se puede cancelar hasta una hora antes.", 409
        )


def registrar_intento_fallido(
    intentos: int, ahora: datetime | None = None
) -> tuple[int, datetime | None, str]:
    nuevos = intentos + 1
    if nuevos >= 5:
        return nuevos, (ahora or datetime.now()) + timedelta(minutes=15), "bloqueado"
    return nuevos, None, "activo"


def validar_transicion_viaje(estado_actual: str, accion: str) -> str:
    transiciones = {
        ("Publicado", "iniciar"): "EnCurso",
        ("Lleno", "iniciar"): "EnCurso",
        ("EnCurso", "finalizar"): "Finalizado",
        ("Publicado", "cancelar"): "Cancelado",
        ("Lleno", "cancelar"): "Cancelado",
    }
    resultado = transiciones.get((estado_actual, accion))
    if resultado is None:
        raise ReglaNegocioError(
            f"No se puede {accion} un viaje en estado {estado_actual}.", 409
        )
    return resultado


def ajustar_estado_por_asientos(estado: str, disponibles: int) -> str:
    if estado in ("Publicado", "Lleno"):
        return "Lleno" if disponibles == 0 else "Publicado"
    return estado
