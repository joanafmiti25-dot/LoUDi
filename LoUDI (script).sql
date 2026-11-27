USE defaultdb;
-- se crea y se selecciona la base de datos LoUDI, borrando cualquier otra llamada igual.

-- DROP SCHEMA IF EXISTS LoUDI;
CREATE SCHEMA IF NOT EXISTS defaultdb;
USE defaultdb;

-- Se crea la tabla Administrador, como en todas las otras, borra otra existente llamada igual, y se guarda id_Administrador como PK.
SET sql_require_primary_key = 0;
DROP TABLE IF EXISTS Administrador;
CREATE TABLE IF NOT EXISTS Administrador (
    id_Administrador INT NOT NULL PRIMARY KEY, 
    Nombre_Administrador VARCHAR(30) NOT NULL,
    Apellido_Administrador VARCHAR(20) NOT NULL,
    Correo_Administrador VARCHAR(35) NOT NULL,
    Contraseña_Administrador VARCHAR(16) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- Se crea la tabla Horario, y guarda idHorario como PK.

DROP TABLE IF EXISTS Horario;
CREATE TABLE IF NOT EXISTS Horario(
    idHorario INT NOT NULL PRIMARY KEY, 
    Turno VARCHAR(15) NOT NULL,
    HoraEntrada TIME NOT NULL,
    HoraSalida TIME NOT NULL
) ENGINE=InnoDB;

/* se crea una tabla estudiante, se toma su NoControl como PK,
entre sus atributos hay dos FK: 
id_Administrador1 que hace referencia a Administrador(id_Administrador) y 
idHorario1 que referencía a Horario(idHorario).*/
 
DROP TABLE IF EXISTS Estudiante;
CREATE TABLE IF NOT EXISTS Estudiante(
    NoControl INT NOT NULL PRIMARY KEY,
    Nombre_Estudiante VARCHAR(30) NOT NULL,
    Apellido_Estudiante VARCHAR(30) NOT NULL,
    Telefono VARCHAR(15) NOT NULL,
    Cuatrimestre VARCHAR(15) NOT NULL,
    Colonia VARCHAR(20) NOT NULL,
    Municipio VARCHAR(30) NOT NULL,
    CP INT NOT NULL,
    Estado VARCHAR(50) NOT NULL,
    Calle VARCHAR(25) NOT NULL,
    NoCalle INT NOT NULL,
    Contraseña VARCHAR(16) NOT NULL,
    id_Administrador1 INT NULL,
    idHorario1 INT NULL,
    FOREIGN KEY (id_Administrador1) REFERENCES Administrador(id_Administrador) ON DELETE SET NULL ON UPDATE SET NULL,
    FOREIGN KEY (idHorario1) REFERENCES Horario(idHorario) ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB;

-- Se crea la tabla llamada Pago, tomando IdPago como PK.

DROP TABLE IF EXISTS Pago;
CREATE TABLE IF NOT EXISTS Pago(
    IdPago INT NOT NULL PRIMARY KEY,
    Monto DECIMAL(5,2) NOT NULL,
    Estatus VARCHAR(45) NOT NULL,
    Fecha DATE NOT NULL
) ENGINE=InnoDB;

-- Se crea la tabla llamada Viaje, tomando IdViaje como PK.

DROP TABLE IF EXISTS Viaje;
CREATE TABLE IF NOT EXISTS Viaje(
    idViaje INT NOT NULL PRIMARY KEY,
    Origen VARCHAR(50) NOT NULL,
    Destino VARCHAR(50) NOT NULL,
    Precio_Estimado DECIMAL(5,2) NOT NULL,
    Asientos_Disponibles INT NOT NULL,
    Estado VARCHAR(20) NOT NULL
) ENGINE=InnoDB;

-- Se crea la tabla llamada Vehiculo, tomando idVehiculo como PK.

DROP TABLE IF EXISTS Vehiculo;
CREATE TABLE IF NOT EXISTS Vehiculo(
    idVehiculo INT NOT NULL PRIMARY KEY,
    Placa VARCHAR(10) NOT NULL UNIQUE,
    Modelo VARCHAR(20) NOT NULL,
    Año INT NOT NULL,
    Color VARCHAR(20) NOT NULL,
    NoSeguro VARCHAR(25) NOT NULL,
    Capacidad_Pasajeros INT NOT NULL
) ENGINE=InnoDB;

/* Se crea la tabla llamada Pasajero, tomando IdPasajero1 como PK siendo FK al mismo tiempo.
IdPago1 Hace referencia a la tabla pago(IdPago)
El IdPasajero1 se usa en cascada porque el valor de una Pk no puede ser nulo */

DROP TABLE IF EXISTS Pasajero;
CREATE TABLE IF NOT EXISTS Pasajero(
    IdPasajero1 INT NOT NULL PRIMARY KEY,
    IdPago1 INT NULL,
    FOREIGN KEY (IdPasajero1) REFERENCES Estudiante(NoControl) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (IdPago1) REFERENCES Pago(IdPago) ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB;

/* Se crea la tabla llamada Conductor, tomando IdConductor como PK siendo FK al mismo tiempo. 
IdConductor hace referencia a Estudiante(NoControl) y puesta en cascada porque un PK no puede ser nulo*/

DROP TABLE IF EXISTS Conductor;
CREATE TABLE IF NOT EXISTS Conductor (
    IdConductor INT NOT NULL PRIMARY KEY,
    NumLicencia VARCHAR(8) NOT NULL UNIQUE,
    Num_Viajes INT NOT NULL,
    FOREIGN KEY (IdConductor) REFERENCES Estudiante(NoControl) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- se crea la tabla llamada Solicita, IdPasajero1 hace referencia a Pasajero(IdPasajero1) y también IdViaje referencía a Viaje(idViaje).

DROP TABLE IF EXISTS Solicita;
CREATE TABLE IF NOT EXISTS Solicita (
    IdPasajero1 INT NULL,
    Fecha DATE NOT NULL,
    Hora TIME NOT NULL,
    Califica DOUBLE(2,1) NOT NULL,
    IdViaje1 INT NULL,
    FOREIGN KEY (IdViaje1) REFERENCES Viaje(idViaje) ON DELETE SET NULL ON UPDATE SET NULL,
    FOREIGN KEY (IdPasajero1) REFERENCES Pasajero(IdPasajero1) ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB;

-- Se crea la tabla posee, teniendo dos FK como sus unicos atributos.
-- IdConductor1 hace referencia a Conductor(IdConductor).
-- IdVehiculo1 referencía a Vehiculo(idVehiculo).

DROP TABLE IF EXISTS Posee;
CREATE TABLE IF NOT EXISTS Posee (
    IdConductor1 INT NULL UNIQUE,
    IdVehiculo1 INT NULL UNIQUE,
    FOREIGN KEY (IdConductor1) REFERENCES Conductor(IdConductor) ON DELETE SET NULL ON UPDATE SET NULL,
    FOREIGN KEY (IdVehiculo1) REFERENCES Vehiculo(idVehiculo) ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB;


/* se crea la tabla llamada Realiza, teniendo tres FK:
IdConductor2 hace referencia a Conductor(IdConductor),
IdViaje2 hace referencia a Viaje(idViaje) y por último 
IdVehiculo2 referencía a Vehiculo(idVehiculo). */

DROP TABLE IF EXISTS Realiza;
CREATE TABLE IF NOT EXISTS Realiza (
    IdConductor2 INT NULL,
    IdViaje2 INT NULL,
    IdVehiculo2 INT NULL,
    Fecha_Realiza DATE NOT NULL,
    Hora_Realiza TIME NOT NULL,
    FOREIGN KEY (IdConductor2) REFERENCES Conductor(IdConductor) ON DELETE SET NULL ON UPDATE SET NULL,
    FOREIGN KEY (IdViaje2) REFERENCES Viaje(idViaje) ON DELETE SET NULL ON UPDATE SET NULL,
    FOREIGN KEY (IdVehiculo2) REFERENCES Vehiculo(idVehiculo) ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB;



-- 1. Correo y rol en Estudiante para login de conductores/pasajeros
ALTER TABLE Estudiante
    ADD COLUMN Correo_Estudiante VARCHAR(60) NULL UNIQUE AFTER Apellido_Estudiante,
    ADD COLUMN Rol_Usuario ENUM('pasajero', 'conductor', 'ambos') NOT NULL DEFAULT 'pasajero' AFTER Contraseña;

-- 2. Vincular Viaje con Horario / Turno y controlar cupo de reserva
ALTER TABLE Viaje
    ADD COLUMN idHorario1 INT NULL AFTER Estado,
    ADD COLUMN Asientos_Totales INT NOT NULL DEFAULT 4 AFTER Asientos_Disponibles,
    ADD CONSTRAINT fk_viaje_horario FOREIGN KEY (idHorario1) REFERENCES Horario(idHorario)
        ON DELETE SET NULL ON UPDATE SET NULL;

-- 3. Mejorar Solicita como reserva con lugares solicitados y estado
ALTER TABLE Solicita
    ADD COLUMN idSolicitud INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST,
    ADD COLUMN Lugares_Solicitados INT NOT NULL DEFAULT 1 AFTER Hora,
    ADD COLUMN Estado_Reserva ENUM('pendiente', 'confirmada', 'cancelada', 'completada') NOT NULL DEFAULT 'pendiente' AFTER Lugares_Solicitados;

-- 4. Tabla de Calificaciones (administración de calificaciones de cada usuario)
CREATE TABLE IF NOT EXISTS Calificacion (
    idCalificacion INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    idViaje1 INT NULL,
    NoControl_Evaluador INT NOT NULL,
    NoControl_Evaluado INT NOT NULL,
    Rol_Evaluado ENUM('conductor', 'pasajero') NOT NULL,
    Puntuacion DECIMAL(2,1) NOT NULL,
    Comentario VARCHAR(250) NULL,
    Fecha_Registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (idViaje1) REFERENCES Viaje(idViaje) ON DELETE SET NULL ON UPDATE SET NULL,
    FOREIGN KEY (NoControl_Evaluador) REFERENCES Estudiante(NoControl) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (NoControl_Evaluado) REFERENCES Estudiante(NoControl) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 5. Tabla de Notificaciones
CREATE TABLE IF NOT EXISTS Notificacion (
    idNotificacion INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    NoControl_Destinatario INT NULL,
    id_Administrador_Destinatario INT NULL,
    Titulo VARCHAR(80) NOT NULL,
    Mensaje VARCHAR(255) NOT NULL,
    Leida TINYINT(1) NOT NULL DEFAULT 0,
    Fecha_Creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (NoControl_Destinatario) REFERENCES Estudiante(NoControl) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (id_Administrador_Destinatario) REFERENCES Administrador(id_Administrador) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 6. Tabla de Reportes
CREATE TABLE IF NOT EXISTS Reporte (
    idReporte INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    NoControl_Reportante INT NOT NULL,
    NoControl_Reportado INT NULL,
    idViaje1 INT NULL,
    Motivo VARCHAR(100) NOT NULL,
    Descripcion TEXT NOT NULL,
    Estado_Reporte ENUM('abierto', 'en_revision', 'resuelto', 'rechazado') NOT NULL DEFAULT 'abierto',
    Fecha_Reporte DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (NoControl_Reportante) REFERENCES Estudiante(NoControl) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (NoControl_Reportado) REFERENCES Estudiante(NoControl) ON DELETE SET NULL ON UPDATE SET NULL,
    FOREIGN KEY (idViaje1) REFERENCES Viaje(idViaje) ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB;

-- LoUDi: migración incremental para MySQL 8/Aiven.
-- Ejecutar sobre la base existente. No elimina tablas ni registros.

ALTER TABLE Horario
    MODIFY COLUMN idHorario INT NOT NULL AUTO_INCREMENT;

ALTER TABLE Estudiante
    ADD COLUMN Estado_Cuenta ENUM('activo','bloqueado') NOT NULL DEFAULT 'activo',
    ADD COLUMN Intentos_Fallidos INT NOT NULL DEFAULT 0,
    ADD COLUMN Bloqueado_Hasta DATETIME NULL,
    ADD COLUMN Reportes INT NOT NULL DEFAULT 0,
    ADD COLUMN Fecha_Registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN Contraseña_Hash VARCHAR(255) NULL,
    MODIFY COLUMN Contraseña VARCHAR(255) NULL;

ALTER TABLE Administrador
    ADD COLUMN Contraseña_Hash VARCHAR(255) NULL,
    MODIFY COLUMN Contraseña_Administrador VARCHAR(255) NULL,
    MODIFY COLUMN id_Administrador INT NOT NULL AUTO_INCREMENT,
    ADD UNIQUE KEY uq_administrador_correo (Correo_Administrador);

ALTER TABLE Viaje
    ADD COLUMN Fecha_Hora_Salida DATETIME NULL,
    MODIFY COLUMN Estado ENUM(
        'Disponible','Publicado','Lleno','EnCurso','Finalizado','Cancelado'
    ) NOT NULL DEFAULT 'Publicado',
    MODIFY COLUMN idViaje INT NOT NULL AUTO_INCREMENT;

UPDATE Viaje SET Estado = 'Publicado' WHERE Estado = 'Disponible';

ALTER TABLE Viaje
    MODIFY COLUMN Estado ENUM(
        'Publicado','Lleno','EnCurso','Finalizado','Cancelado'
    ) NOT NULL DEFAULT 'Publicado';

ALTER TABLE Vehiculo
    ADD COLUMN Marca VARCHAR(60) NOT NULL DEFAULT '',
    MODIFY COLUMN idVehiculo INT NOT NULL AUTO_INCREMENT,
    ADD CONSTRAINT chk_vehiculo_capacidad
        CHECK (Capacidad_Pasajeros BETWEEN 1 AND 4);

ALTER TABLE Pago
    MODIFY COLUMN IdPago INT NOT NULL AUTO_INCREMENT;

-- El índice de IdVehiculo1 se conserva para mantener un vehículo por relación.
-- Solo se quita la unicidad del conductor para permitir varios vehículos.
ALTER TABLE Posee DROP INDEX IdConductor1;

UPDATE Solicita
    SET Estado_Reserva = 'confirmada'
    WHERE Estado_Reserva = 'completada';

ALTER TABLE Solicita
    MODIFY COLUMN Estado_Reserva ENUM(
        'pendiente','confirmada','rechazada','cancelada'
    ) NOT NULL DEFAULT 'pendiente';

CREATE TABLE IF NOT EXISTS Bitacora_Admin (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    id_Administrador INT NOT NULL,
    NoControl_Afectado INT NOT NULL,
    Accion ENUM('bloqueo','desbloqueo') NOT NULL,
    Fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_bitacora_admin
        FOREIGN KEY (id_Administrador)
        REFERENCES Administrador(id_Administrador),
    CONSTRAINT fk_bitacora_estudiante
        FOREIGN KEY (NoControl_Afectado)
        REFERENCES Estudiante(NoControl)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Sesion (
    idSesion BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    Id_Administrador INT NULL,
    NoControl INT NULL,
    Token_Hash CHAR(64) NOT NULL UNIQUE,
    Expira DATETIME NOT NULL,
    Revocada TINYINT(1) NOT NULL DEFAULT 0,
    Fecha_Creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_sesion_admin FOREIGN KEY (Id_Administrador)
        REFERENCES Administrador(id_Administrador) ON DELETE CASCADE,
    CONSTRAINT fk_sesion_estudiante FOREIGN KEY (NoControl)
        REFERENCES Estudiante(NoControl) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_sesion_expira ON Sesion(Expira, Revocada);
CREATE INDEX idx_viaje_salida_estado ON Viaje(Fecha_Hora_Salida, Estado);
CREATE INDEX idx_solicita_viaje_estado ON Solicita(IdViaje1, Estado_Reserva);
CREATE INDEX idx_solicita_pasajero_estado ON Solicita(IdPasajero1, Estado_Reserva);
