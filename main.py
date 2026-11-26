import os
import pymysql
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, time

app = FastAPI(
    title="API de LoUDI",
    description="API REST con todas las tablas y relaciones de la base de datos LoUDI",
    version="2.1"
)

# Habilitar CORS para conectar desde app móvil o web sin bloqueos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Conexión a MySQL en la nube (Aiven)
def get_db_connection():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "mysql-35731f3f-utsjr-f320.e.aivencloud.com"),
        user=os.getenv("DB_USER", "avnadmin"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "defaultdb"),
        port=int(os.getenv("DB_PORT", "27731")),
        cursorclass=pymysql.cursors.DictCursor,
        ssl={"ssl_mode": "REQUIRED"}
    )

# ==========================================
# MODELOS PYDANTIC (Validación de entrada)
# ==========================================

class LoginRequest(BaseModel):
    correo: str
    password: str

class AdministradorCreate(BaseModel):
    id_Administrador: int
    Nombre_Administrador: str
    Apellido_Administrador: str
    Correo_Administrador: str
    Contraseña_Administrador: str

class HorarioCreate(BaseModel):
    idHorario: int
    Turno: str
    HoraEntrada: time
    HoraSalida: time

class EstudianteCreate(BaseModel):
    NoControl: int
    Nombre_Estudiante: str
    Apellido_Estudiante: str
    Correo_Estudiante: Optional[str] = None
    Rol_Usuario: str = "pasajero"  # pasajero, conductor, ambos
    Telefono: str
    Cuatrimestre: str
    Colonia: str
    Municipio: str
    CP: int
    Estado: str
    Calle: str
    NoCalle: int
    Contraseña: str
    id_Administrador1: Optional[int] = None
    idHorario1: Optional[int] = None

class PagoCreate(BaseModel):
    IdPago: int
    Monto: float
    Estatus: str
    Fecha: date

class ViajeCreate(BaseModel):
    idViaje: int
    Origen: str
    Destino: str
    Precio_Estimado: float
    Asientos_Disponibles: int
    Asientos_Totales: Optional[int] = None
    Estado: str = "Disponible"
    idHorario1: Optional[int] = None

class VehiculoCreate(BaseModel):
    idVehiculo: int
    Placa: str
    Modelo: str
    Año: int
    Color: str
    NoSeguro: str
    Capacidad_Pasajeros: int

class PasajeroCreate(BaseModel):
    IdPasajero1: int
    IdPago1: Optional[int] = None

class ConductorCreate(BaseModel):
    IdConductor: int
    NumLicencia: str
    Num_Viajes: int

class ReservaCreate(BaseModel):
    IdPasajero1: int
    IdViaje1: int
    Fecha: date
    Hora: time
    Lugares_Solicitados: int = 1
    Califica: float = 0.0

class EstadoReservaUpdate(BaseModel):
    Estado_Reserva: str  # pendiente, confirmada, cancelada, completada

class CalificacionCreate(BaseModel):
    idViaje1: Optional[int] = None
    NoControl_Evaluador: int
    NoControl_Evaluado: int
    Rol_Evaluado: str  # conductor o pasajero
    Puntuacion: float
    Comentario: Optional[str] = None

class ReporteCreate(BaseModel):
    NoControl_Reportante: int
    NoControl_Reportado: Optional[int] = None
    idViaje1: Optional[int] = None
    Motivo: str
    Descripcion: str

class NotificacionCreate(BaseModel):
    NoControl_Destinatario: Optional[int] = None
    id_Administrador_Destinatario: Optional[int] = None
    Titulo: str
    Mensaje: str


# ==========================================
# LOGIN UNIFICADO (ADMIN / CONDUCTOR / PASAJERO)
# ==========================================

@app.post("/api/login", tags=["Autenticación"])
def login_usuario(datos: LoginRequest):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id_Administrador, Nombre_Administrador, Apellido_Administrador, Correo_Administrador
                   FROM Administrador
                   WHERE Correo_Administrador = %s AND Contraseña_Administrador = %s""",
                (datos.correo, datos.password)
            )
            admin = cursor.fetchone()
            if admin:
                return {"rol": "administrador", "usuario": admin}

            cursor.execute(
                """SELECT e.NoControl, e.Nombre_Estudiante, e.Apellido_Estudiante, e.Correo_Estudiante,
                          e.Rol_Usuario, e.idHorario1, h.Turno, h.HoraEntrada, h.HoraSalida
                   FROM Estudiante e
                   LEFT JOIN Horario h ON e.idHorario1 = h.idHorario
                   WHERE e.Correo_Estudiante = %s AND e.Contraseña = %s""",
                (datos.correo, datos.password)
            )
            estudiante = cursor.fetchone()
            if estudiante:
                return {"rol": estudiante["Rol_Usuario"], "usuario": estudiante}

            raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    finally:
        connection.close()


# ==========================================
# ENDPOINT PARA CARGAR DATOS DE PRUEBA
# ==========================================

@app.post("/api/sembrar-datos-prueba", tags=["Datos de Prueba"])
def sembrar_datos_prueba():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")

            cursor.execute("""
                INSERT IGNORE INTO Administrador (id_Administrador, Nombre_Administrador, Apellido_Administrador, Correo_Administrador, Contraseña_Administrador)
                VALUES (1, 'Carlos', 'Gómez', 'carlos.admin@loudi.com', 'adminPass123');
            """)

            cursor.execute("""
                INSERT IGNORE INTO Horario (idHorario, Turno, HoraEntrada, HoraSalida)
                VALUES 
                (1, 'Matutino', '07:00:00', '14:00:00'),
                (2, 'Vespertino', '14:00:00', '21:00:00');
            """)

            cursor.execute("""
                INSERT IGNORE INTO Estudiante (NoControl, Nombre_Estudiante, Apellido_Estudiante, Telefono, Cuatrimestre, Colonia, Municipio, CP, Estado, Calle, NoCalle, Contraseña, id_Administrador1, idHorario1)
                VALUES 
                (2023001, 'Ana', 'Martínez', '4421234567', '4to', 'Centro', 'Querétaro', 76000, 'Querétaro', 'Hidalgo', 12, 'ana12345', 1, 1),
                (2023002, 'Luis', 'Hernández', '4429876543', '5to', 'Candelaria', 'San Juan del Río', 76800, 'Querétaro', 'Juárez', 45, 'luis12345', 1, 2);
            """)

            cursor.execute("""
                INSERT IGNORE INTO Pago (IdPago, Monto, Estatus, Fecha)
                VALUES (101, 35.50, 'Completado', '2026-03-01');
            """)

            cursor.execute("""
                INSERT IGNORE INTO Viaje (idViaje, Origen, Destino, Precio_Estimado, Asientos_Disponibles, Estado)
                VALUES (501, 'Centro San Juan', 'Universidad', 35.50, 3, 'Disponible');
            """)

            cursor.execute("""
                INSERT IGNORE INTO Vehiculo (idVehiculo, Placa, Modelo, Año, Color, NoSeguro, Capacidad_Pasajeros)
                VALUES (1, 'UKJ-123-A', 'Nissan Versa', 2022, 'Rojo', 'SEG-998877', 4);
            """)

            cursor.execute("""
                INSERT IGNORE INTO Pasajero (IdPasajero1, IdPago1)
                VALUES (2023001, 101);
            """)

            cursor.execute("""
                INSERT IGNORE INTO Conductor (IdConductor, NumLicencia, Num_Viajes)
                VALUES (2023002, 'LIC88776', 15);
            """)

            cursor.execute("""
                INSERT IGNORE INTO Solicita (IdPasajero1, Fecha, Hora, Califica, IdViaje1)
                VALUES (2023001, '2026-03-01', '07:30:00', 4.8, 501);
            """)

            cursor.execute("""
                INSERT IGNORE INTO Posee (IdConductor1, IdVehiculo1)
                VALUES (2023002, 1);
            """)

            cursor.execute("""
                INSERT IGNORE INTO Realiza (IdConductor2, IdViaje2, IdVehiculo2, Fecha_Realiza, Hora_Realiza)
                VALUES (2023002, 501, 1, '2026-03-01', '07:30:00');
            """)

            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            connection.commit()
            return {"message": "¡Datos de prueba insertados exitosamente en todas las tablas!"}
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Error al sembrar datos: {str(e)}")
    finally:
        connection.close()


# ==========================================
# RUTAS EXISTENTES Y NUEVAS DE OPERACIÓN
# ==========================================

@app.get("/api/administradores", tags=["Administrador"])
def obtener_administradores():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Administrador")
            return cursor.fetchall()
    finally:
        connection.close()

@app.post("/api/administradores", status_code=201, tags=["Administrador"])
def crear_administrador(admin: AdministradorCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO Administrador VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (admin.id_Administrador, admin.Nombre_Administrador, admin.Apellido_Administrador, admin.Correo_Administrador, admin.Contraseña_Administrador))
            connection.commit()
            return {"message": "Administrador registrado"}
    finally:
        connection.close()

@app.get("/api/horarios", tags=["Horario"])
def obtener_horarios():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Horario")
            return cursor.fetchall()
    finally:
        connection.close()

@app.post("/api/horarios", status_code=201, tags=["Horario"])
def crear_horario(horario: HorarioCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = "INSERT INTO Horario VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (horario.idHorario, horario.Turno, horario.HoraEntrada, horario.HoraSalida))
            connection.commit()
            return {"message": "Horario registrado"}
    finally:
        connection.close()

@app.get("/api/estudiantes", tags=["Estudiante"])
def obtener_estudiantes():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Estudiante")
            return cursor.fetchall()
    finally:
        connection.close()

@app.post("/api/estudiantes", status_code=201, tags=["Estudiante"])
def crear_estudiante(est: EstudianteCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            sql = """INSERT INTO Estudiante (NoControl, Nombre_Estudiante, Apellido_Estudiante, Correo_Estudiante, Rol_Usuario, Telefono, Cuatrimestre, Colonia, Municipio, CP, Estado, Calle, NoCalle, Contraseña, id_Administrador1, idHorario1)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            cursor.execute(sql, (est.NoControl, est.Nombre_Estudiante, est.Apellido_Estudiante, est.Correo_Estudiante, est.Rol_Usuario, est.Telefono, est.Cuatrimestre, est.Colonia, est.Municipio, est.CP, est.Estado, est.Calle, est.NoCalle, est.Contraseña, est.id_Administrador1, est.idHorario1))
            connection.commit()
            return {"message": "Estudiante registrado"}
    finally:
        connection.close()

@app.get("/api/viajes", tags=["Viaje"])
def obtener_viajes(turno: Optional[str] = None):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            if turno:
                cursor.execute(
                    """SELECT v.*, h.Turno, h.HoraEntrada, h.HoraSalida
                       FROM Viaje v
                       LEFT JOIN Horario h ON v.idHorario1 = h.idHorario
                       WHERE h.Turno = %s""",
                    (turno,)
                )
            else:
                cursor.execute(
                    """SELECT v.*, h.Turno, h.HoraEntrada, h.HoraSalida
                       FROM Viaje v
                       LEFT JOIN Horario h ON v.idHorario1 = h.idHorario"""
                )
            return cursor.fetchall()
    finally:
        connection.close()

@app.post("/api/viajes", status_code=201, tags=["Viaje"])
def publicar_viaje(viaje: ViajeCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            asientos_totales = viaje.Asientos_Totales if viaje.Asientos_Totales is not None else viaje.Asientos_Disponibles
            cursor.execute(
                """INSERT INTO Viaje (idViaje, Origen, Destino, Precio_Estimado, Asientos_Disponibles, Asientos_Totales, Estado, idHorario1)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (viaje.idViaje, viaje.Origen, viaje.Destino, viaje.Precio_Estimado, viaje.Asientos_Disponibles, asientos_totales, viaje.Estado, viaje.idHorario1)
            )
            connection.commit()
            return {"message": "Viaje publicado exitosamente"}
    finally:
        connection.close()

@app.get("/api/vehiculos", tags=["Vehiculo"])
def obtener_vehiculos():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Vehiculo")
            return cursor.fetchall()
    finally:
        connection.close()

@app.post("/api/vehiculos", status_code=201, tags=["Vehiculo"])
def registrar_vehiculo(veh: VehiculoCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO Vehiculo (idVehiculo, Placa, Modelo, Año, Color, NoSeguro, Capacidad_Pasajeros)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (veh.idVehiculo, veh.Placa, veh.Modelo, veh.Año, veh.Color, veh.NoSeguro, veh.Capacidad_Pasajeros)
            )
            connection.commit()
            return {"message": "Vehículo registrado"}
    finally:
        connection.close()

@app.get("/api/solicitudes", tags=["Reservas"])
def obtener_solicitudes():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM Solicita")
            return cursor.fetchall()
    finally:
        connection.close()

@app.post("/api/reservas", status_code=201, tags=["Reservas"])
def crear_reserva(res: ReservaCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT Asientos_Disponibles FROM Viaje WHERE idViaje = %s", (res.IdViaje1,))
            viaje = cursor.fetchone()
            if not viaje:
                raise HTTPException(status_code=404, detail="Viaje no encontrado")
            if viaje["Asientos_Disponibles"] < res.Lugares_Solicitados:
                raise HTTPException(status_code=400, detail="No hay suficientes asientos disponibles")

            cursor.execute(
                """INSERT INTO Solicita (IdPasajero1, Fecha, Hora, Lugares_Solicitados, Estado_Reserva, Califica, IdViaje1)
                   VALUES (%s, %s, %s, %s, 'confirmada', %s, %s)""",
                (res.IdPasajero1, res.Fecha, res.Hora, res.Lugares_Solicitados, res.Califica, res.IdViaje1)
            )
            cursor.execute(
                "UPDATE Viaje SET Asientos_Disponibles = Asientos_Disponibles - %s WHERE idViaje = %s",
                (res.Lugares_Solicitados, res.IdViaje1)
            )
            connection.commit()
            return {"message": "Reserva registrada y asientos actualizados"}
    except HTTPException:
        connection.rollback()
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        connection.close()

@app.post("/api/calificaciones", status_code=201, tags=["Calificaciones"])
def crear_calificacion(cal: CalificacionCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO Calificacion (idViaje1, NoControl_Evaluador, NoControl_Evaluado, Rol_Evaluado, Puntuacion, Comentario)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (cal.idViaje1, cal.NoControl_Evaluador, cal.NoControl_Evaluado, cal.Rol_Evaluado, cal.Puntuacion, cal.Comentario)
            )
            connection.commit()
            return {"message": "Calificación guardada"}
    finally:
        connection.close()

@app.get("/api/calificaciones/{no_control}", tags=["Calificaciones"])
def obtener_calificaciones_usuario(no_control: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT *, AVG(Puntuacion) OVER (PARTITION BY NoControl_Evaluado) AS Promedio
                   FROM Calificacion
                   WHERE NoControl_Evaluado = %s""",
                (no_control,)
            )
            return cursor.fetchall()
    finally:
        connection.close()

@app.post("/api/reportes", status_code=201, tags=["Reportes"])
def crear_reporte(rep: ReporteCreate):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO Reporte (NoControl_Reportante, NoControl_Reportado, idViaje1, Motivo, Descripcion)
                   VALUES (%s, %s, %s, %s, %s)""",
                (rep.NoControl_Reportante, rep.NoControl_Reportado, rep.idViaje1, rep.Motivo, rep.Descripcion)
            )
            connection.commit()
            return {"message": "Reporte registrado"}
    finally:
        connection.close()

@app.get("/api/notificaciones/{no_control}", tags=["Notificaciones"])
def obtener_notificaciones(no_control: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM Notificacion WHERE NoControl_Destinatario = %s ORDER BY Fecha_Creacion DESC",
                (no_control,)
            )
            return cursor.fetchall()
    finally:
        connection.close()